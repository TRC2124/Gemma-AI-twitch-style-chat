import tkinter as tk
from tkinter import scrolledtext, font
import threading
import time
import random
import keyboard  # For global hotkeys
import mss
import mss.tools
from PIL import Image, ImageTk
import ollama
import io
import queue

# Configuration
# NOTE: Ensure you have a vision-capable model installed. 
# If "gemma3" is not available, try "llama3.2-vision" or "llava"
MODEL_NAME = "gemma3:12b" 
PROMPT_INSTRUCTION = (
    "You are a Twitch chat. Look at this image of a stream/game/desktop. "
    "Generate 4 to 6 distinct, realistic chat messages reacting to what is happening. "
    "Vary the tone: some hype, some sarcastic, some confused, some emojis. "
    "Format EXACTLY like this for each line: 'Username: Message'"
)

class TwitchOverlay:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Chat Overlay")
        self.root.geometry("400x700")
        self.root.configure(bg="#18181b") # Twitch Dark Mode Background

        # State variables
        self.running = False
        self.processing = False
        self.msg_queue = queue.Queue()
        self.stop_event = threading.Event()
        
        # UI Setup
        self.setup_ui()
        
        # Global Hotkey (0 to toggle)
        keyboard.on_press_key("0", self.toggle_pause)
        
        # Threads
        self.ai_thread = threading.Thread(target=self.ai_loop, daemon=True)
        self.ai_thread.start()
        
        # Start the UI consumer loop
        self.process_ui_queue()

    def setup_ui(self):
        # Top Control Panel
        self.top_frame = tk.Frame(self.root, bg="#18181b")
        self.top_frame.pack(fill="x", padx=5, pady=5)

        self.status_label = tk.Label(
            self.top_frame, 
            text="PAUSED (Press '0' to Start)", 
            fg="red", bg="#18181b", 
            font=("Segoe UI", 10, "bold")
        )
        self.status_label.pack(side="left")

        # Always on Top Checkbox
        self.top_var = tk.BooleanVar(value=False)
        self.chk_top = tk.Checkbutton(
            self.top_frame, text="Always on Top", 
            variable=self.top_var, 
            command=self.toggle_always_on_top,
            bg="#18181b", fg="white", selectcolor="#18181b",
            activebackground="#18181b", activeforeground="white"
        )
        self.chk_top.pack(side="right")

        # Image Preview Area
        self.image_label = tk.Label(self.root, bg="black", text="Waiting for Stream...", fg="gray")
        self.image_label.pack(fill="x", padx=10, pady=5)

        # Chat Area
        self.chat_font = font.Font(family="Segoe UI", size=10)
        self.chat_area = scrolledtext.ScrolledText(
            self.root, 
            state='disabled', 
            bg="#18181b", 
            fg="#efeff1", # Twitch text color
            font=self.chat_font,
            borderwidth=0,
            highlightthickness=0
        )
        self.chat_area.pack(expand=True, fill="both", padx=10, pady=5)
        
        # Define tag colors for usernames (Twitch style colors)
        self.colors = ["#FF0000", "#0000FF", "#008000", "#B22222", "#FF7F50", "#9ACD32", "#FF4500", "#2E8B57", "#DAA520", "#D2691E", "#5F9EA0", "#1E90FF", "#FF69B4", "#8A2BE2", "#00FF7F"]
        for i, color in enumerate(self.colors):
            self.chat_area.tag_config(f"color_{i}", foreground=color, font=("Segoe UI", 10, "bold"))

    def toggle_always_on_top(self):
        self.root.attributes('-topmost', self.top_var.get())

    def toggle_pause(self, event=None):
        self.running = not self.running
        if self.running:
            self.status_label.config(text="● LIVE", fg="#00ff00")
        else:
            self.status_label.config(text="PAUSED (Press '0')", fg="red")

    def get_screen_image(self):
        # Capture the whole screen
        with mss.mss() as sct:
            monitor = sct.monitors[1] # Primary monitor
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # Resize for AI (Speed) and UI (Preview)
            # AI Resize (keep it somewhat clear but small for speed)
            ai_img = img.resize((640, 360), Image.Resampling.LANCZOS)
            
            # UI Resize (Fit the window width)
            ui_img = img.resize((380, 215), Image.Resampling.LANCZOS)
            
            return ai_img, ui_img

    def update_preview(self, pil_image):
        # Convert PIL image to Tkinter image
        tk_img = ImageTk.PhotoImage(pil_image)
        self.image_label.config(image=tk_img, text="")
        self.image_label.image = tk_img # Keep reference

    def ai_loop(self):
        while not self.stop_event.is_set():
            if not self.running:
                time.sleep(0.1)
                continue

            start_time = time.time()
            
            try:
                # 1. Capture
                ai_img, ui_img = self.get_screen_image()
                
                # Update UI Preview immediately
                self.root.after(0, self.update_preview, ui_img)

                # 2. Prepare for Ollama
                img_byte_arr = io.BytesIO()
                ai_img.save(img_byte_arr, format='JPEG')
                img_bytes = img_byte_arr.getvalue()

                # 3. Send to Ollama
                # Note: Gemma 2 is text only. Ensure using a Vision model or multimodal wrapper.
                # Assuming user has a valid vision model mapping to MODEL_NAME
                response = ollama.chat(
                    model=MODEL_NAME,
                    messages=[{
                        'role': 'user',
                        'content': PROMPT_INSTRUCTION,
                        'images': [img_bytes]
                    }]
                )
                
                content = response['message']['content']
                
                # 4. Parse Response
                new_messages = []
                lines = content.split('\n')
                for line in lines:
                    if ":" in line:
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            username = parts[0].strip()
                            message = parts[1].strip()
                            # Assign random color index
                            color_idx = random.randint(0, len(self.colors)-1)
                            new_messages.append((username, message, color_idx))

                # 5. Calculate Timing
                end_time = time.time()
                process_time = end_time - start_time
                
                # We want to stream these messages over the duration of the NEXT process
                # But we don't know next process time, so we use this process time as a baseline estimate.
                # Ensure at least 1 second duration so text doesn't fly too fast.
                display_duration = max(process_time, 2.0) 
                
                if new_messages:
                    delay_per_message = display_duration / len(new_messages)
                    
                    # Send to UI thread buffer
                    for msg in new_messages:
                        self.msg_queue.put(msg)
                        # We sleep here in the AI thread to trickle them into the queue? 
                        # No, blocking AI thread delays next screenshot.
                        # We should dump them all to a buffer and let UI thread handle pacing.
                        # actually, let's pause this thread slightly so we don't spam API if it's too fast
                        
                    # To achieve the effect of "sending one at a time while processing next",
                    # we rely on the UI loop to pull them slowly.
                    # But we want the AI to start immediately.
                    
            except Exception as e:
                print(f"AI Error: {e}")
                time.sleep(1)

    def process_ui_queue(self):
        # This function runs recursively via .after
        # It tries to simulate a natural chat flow
        
        if not self.msg_queue.empty():
            username, text, color_idx = self.msg_queue.get()
            self.add_chat_message(username, text, color_idx)
            
            # Randomize delay slightly for realism, roughly 500ms - 1500ms
            # This creates the "Streaming" effect
            next_delay = random.randint(500, 1500)
        else:
            # If empty, check more frequently
            next_delay = 100

        self.root.after(next_delay, self.process_ui_queue)

    def add_chat_message(self, username, message, color_idx):
        self.chat_area.configure(state='normal')
        
        # Insert Username with Color
        self.chat_area.insert(tk.END, f"{username}: ", f"color_{color_idx}")
        
        # Insert Message
        self.chat_area.insert(tk.END, f"{message}\n")
        
        self.chat_area.configure(state='disabled')
        self.chat_area.see(tk.END) # Auto scroll

if __name__ == "__main__":
    root = tk.Tk()
    app = TwitchOverlay(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass