import tkinter as tk
from tkinter import scrolledtext, font
import threading
import time
import random
import keyboard  # pip install keyboard
import mss       # pip install mss
import mss.tools
from PIL import Image, ImageTk # pip install pillow
import ollama    # pip install ollama
import io
import queue

# Configuration
# Use a vision-capable model (e.g., "llama3.2-vision", "llava", or "moondream")
MODEL_NAME = "gemma3:12b" 
PROMPT_INSTRUCTION = (
    """
    You are an expert at simulating a fast-paced, highly interactive livestream chat. Your sole task is to analyze a provided screenshot and generate 8 to 10 new, realistic chat messages reacting to the content shown.

    **BEHAVIOR**
    * **Message:** Must be a short, authentic-sounding reaction (e.g., excitement, question, meme, confusion, praise, or spam). Use caps, emojis, and slang.
    * **Variety:** Ensure the 3-5 messages come from different perspectives.
    * **Focus:** React to the MAIN CONTENT of the screenshot, not the chat window (if one is visible).
    
    **EXAMPLE OF PERFECT COMMENTS**
    FailBot99: NOOOOOOO WAY
    PogChampFan: Rip the run 😭
    MVP_Lover: Chat is so fast today lol
    GetGud: wait, did you see the health bar? that was close!

    """
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
        self.msg_queue = queue.Queue()
        self.stop_event = threading.Event()
        
        # UI Setup
        self.setup_ui()
        
        # Global Hotkey (0 to toggle)
        try:
            keyboard.on_press_key("0", self.toggle_pause)
        except Exception as e:
            print(f"Hotkey Error (Run as Admin?): {e}")
        
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
        
        # Define tag colors for usernames
        self.colors = [
            "#FF0000", "#0000FF", "#008000", "#B22222", "#FF7F50", 
            "#9ACD32", "#FF4500", "#2E8B57", "#DAA520", "#D2691E", 
            "#5F9EA0", "#1E90FF", "#FF69B4", "#8A2BE2", "#00FF7F"
        ]
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
        with mss.mss() as sct:
            monitor = sct.monitors[1] 
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # AI Resize (smaller for speed)
            ai_img = img#.resize((640, 360), Image.Resampling.LANCZOS)
            # UI Resize (Fit window)
            ui_img = img.resize((380, 215), Image.Resampling.LANCZOS)
            
            return ai_img, ui_img

    def update_preview(self, pil_image):
        tk_img = ImageTk.PhotoImage(pil_image)
        self.image_label.config(image=tk_img, text="")
        self.image_label.image = tk_img 

    def ai_loop(self):
        while not self.stop_event.is_set():
            if not self.running:
                time.sleep(0.1)
                continue

            try:
                # 1. Capture
                ai_img, ui_img = self.get_screen_image()
                self.root.after(0, self.update_preview, ui_img)

                # 2. Convert for Ollama
                img_byte_arr = io.BytesIO()
                ai_img.save(img_byte_arr, format='JPEG')
                img_bytes = img_byte_arr.getvalue()

                # 3. Send to AI
                response = ollama.chat(
                    model=MODEL_NAME,
                    messages=[{
                        'role': 'user',
                        'content': PROMPT_INSTRUCTION,
                        'images': [img_bytes]
                    }]
                )
                
                content = response['message']['content']
                
                # 4. Parse Response (IMPROVED)
                lines = content.split('\n')
                for line in lines:
                    if ":" in line:
                        parts = line.split(":", 1)
                        username = parts[0].strip()
                        message = parts[1].strip()

                        # --- FILTER LOGIC ---
                        # 1. Check if message is empty
                        if not message: 
                            continue
                        # 2. Check if username has spaces (Twitch usernames don't have spaces).
                        #    This filters out "Okay here is the list:" sentences.
                        if " " in username:
                            continue
                        # 3. Length check to be safe
                        if len(username) > 25:
                            continue
                        # --------------------

                        color_idx = random.randint(0, len(self.colors)-1)
                        self.msg_queue.put((username, message, color_idx))

            except Exception as e:
                print(f"AI Error: {e}")
                time.sleep(1)

    def process_ui_queue(self):
        # Check if there are messages to display
        if not self.msg_queue.empty():
            username, text, color_idx = self.msg_queue.get()
            self.add_chat_message(username, text, color_idx)
            
            # --- TIMING LOGIC (IMPROVED) ---
            # Wait between 0.5s (500ms) and 1.5s (1500ms) before showing the next one
            next_delay = random.randint(1250, 3050)
        else:
            # If queue is empty, check again quickly
            next_delay = 100

        self.root.after(next_delay, self.process_ui_queue)

    def add_chat_message(self, username, message, color_idx):
        self.chat_area.configure(state='normal')
        self.chat_area.insert(tk.END, f"{username}: ", f"color_{color_idx}")
        self.chat_area.insert(tk.END, f"{message}\n")
        self.chat_area.configure(state='disabled')
        self.chat_area.see(tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = TwitchOverlay(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass