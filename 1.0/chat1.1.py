import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageGrab
import requests
import base64
import io
import threading
import time
import random
from collections import deque
import json

# --- CONFIGURATION ---

# !!! IMPORTANT !!!
# Change this to your specific model.
# NOTE: The model MUST support vision (images). 'llava' is a common choice.
# If 'gemma3:4b' is a vision model, it will work. If not, use 'llava'.
OLLAMA_MODEL = "gemma3:12b"  # <-- CHANGE THIS TO 'gemma3:4b' IF IT'S A VISION MODEL

# URL for your local Ollama API
OLLAMA_URL = "http://localhost:11434/api/chat"

# How often to capture the screen (in seconds)
CAPTURE_INTERVAL_SEC = 0

# Max messages to keep in history (for context)
MAX_CHAT_HISTORY = 10

# System prompt as requested, refined for better AI output
SYSTEM_PROMPT = """
You are an expert at simulating a fast-paced, highly interactive livestream chat. Your sole task is to analyze a provided screenshot and generate 3 to 5 new, realistic chat messages reacting to the content shown.

YOUR ENTIRE OUTPUT MUST CONTAIN NOTHING EXCEPT THE GENERATED CHAT MESSAGES. DO NOT INCLUDE ANY INTRODUCTORY, EXPLANATORY, OR DESCRIPTIVE TEXT (e.g., "Here are the reactions:", "Okay, here are the persona reactions to this new screenshot:", "I have analyzed the screenshot:").

Core Directives:

Input Focus: The primary input is a screenshot. While a chat window may be visible within the screenshot, you MUST focus your analysis and reactions on the main content (e.g., the game, the person, the action, the video) that is happening outside of the chat area.

Output Format: Every single message you generate MUST strictly adhere to the following format:
username: message

    Username: Must be a plausible, short, and distinct username (e.g., xX_GamerGod_Xx, PotatoFan, LurkModeActive, SaltyStreams).

    Message: Must be a short, authentic-sounding reaction (e.g., excitement, question, meme, confusion, praise, or spam).

Behavior & Tone: Messages must simulate a realistic chat environment, including:

    Instant Reactions: Immediate emotional responses to actions on screen (e.g., hype for a good play, shock, laughter).

    Common Chat Tropes: Use of caps lock for emphasis, simple emojis, short-form internet slang, or meme references relevant to the observed content.

    Variety: Ensure the 5-8 messages come from different perspectives and users (e.g., one could be asking a question, another spamming a single emoji, and a third offering a serious comment).
    
Constraint:

    You MUST generate exactly 3 to 5 messages for each input.
    
    The ENTIRE output MUST consist ONLY of lines following the format username: message. NO extra text is permitted.

Example of Expected Output:
FailBot99: NOOOOOOO WAY
PogChampFan: Rip the run 😭
MVP_Lover: Chat is so fast today lol
GetGud: wait, did you see the health bar? that was close!
"""

# --- END CONFIGURATION ---

# --- UI SETUP ---

# Fake users and colors for the chat
CHAT_USERS = ["StreamFan",
              "Gamer123", 
              "NoobSlayer", 
              "ChatterBoi", 
              "PixelPro", 
              "LagKing", 
              "W_Key_Warrior", 
              "Lurker22",
              "PixelPirateLord",
              "SwiftShadow_X",
                "NeonNomadTV",
                "CrimsonByte99",
                "FrostyFiasco_live",
                "AstroZenith7",
                "SilentSpecter84",
                "TheWittyWombat",
                "HyperPanda_Stream",
                "VaporWaveViking",
                "GalacticGoblin",
                "MistyMayhem_yt",
                "CodeCrafter_01",
                "EchoingKnight",
                "RogueRobot_23",
                "QuantumQuasar",
                "BlazingBacon42",
                "MidnightMarauder",
                "ElectricEel_Gaming",
                "NomadicNoodle",
                "ArcaneAnarchy_",
                "TurboTaco_Time",
                "ZenithZebra_z",
                "CosmicCrusader5",
                "FlickeringFlamez",
                "GloomyGamerGuy",
                "StellarSquid_",
                "WaffleWarrior_77",
                "TheCrypticCapybara",
                "DigitalDrifter_"]
USER_COLORS = ["#FF0000", "#0000FF", "#008000", "#B22222", "#FF7F50", "#9ACD32", "#FF4500", "#2E8B57", "#DAA520", "#D2691E"]
THUMBNAIL_WIDTH = 320 # Width for the image preview

class ChatStreamApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Ollama Screen Reactor")
        self.root.geometry("400x600")
        
        # Set dark theme for the window
        self.root.configure(bg="#18181B")
        
        # This deque will store the chat history, automatically discarding old messages
        self.messages_history = deque(maxlen=MAX_CHAT_HISTORY)
        self.messages_history.append({"role": "system", "content": SYSTEM_PROMPT})

        # --- Top Frame (Image Preview & "On Top" Checkbox) ---
        self.top_frame = tk.Frame(root, bg="#18181B")
        self.top_frame.pack(fill='x', pady=5, padx=5)

        # Image Preview Label
        self.image_label = tk.Label(self.top_frame, bg="#000000")
        self.image_label.pack(fill='x')
        
        # "Always on Top" Checkbox
        self.on_top_var = tk.BooleanVar()
        self.on_top_check = tk.Checkbutton(
            self.top_frame,
            text="Always on Top",
            variable=self.on_top_var,
            command=self.toggle_on_top,
            bg="#18181B",
            fg="white",
            selectcolor="#18181B",
            activebackground="#18181B",
            activeforeground="white"
        )
        self.on_top_check.pack(side='left', padx=5)

        # --- Chat Window ---
        self.chat_frame = tk.Frame(root, bg="#18181B")
        self.chat_frame.pack(fill='both', expand=True, padx=5, pady=(0, 5))

        self.chat_text = tk.Text(
            self.chat_frame,
            wrap='word',
            bg="#1F1F23",  # Twitch chat background color
            fg="white",
            state='disabled',
            font=("Helvetica", 10),
            borderwidth=0,
            padx=10,
            pady=10
        )
        self.chat_text.pack(fill='both', expand=True)
        
        # Configure a "system" tag for error messages
        self.chat_text.tag_config('system', foreground="#FFD700") # Gold color for system messages

        # --- MODIFICATION 1: Pause state and hotkey binding ---
        self.is_paused = True # Start in a paused state
        self.root.bind('<Key-0>', self.toggle_pause) # Bind '0' key
        # --- End modification ---

        # Start the background thread for screen capture and AI processing
        self.start_capture_thread()

        # Add initial paused message
        self.add_chat_message("System: Chat is paused. Press '0' to start.", is_system=True)

    def toggle_on_top(self):
        """Toggles the 'always on top' attribute of the window."""
        self.root.attributes('-topmost', self.on_top_var.get())

    # --- MODIFICATION 2: Add toggle_pause method ---
    def toggle_pause(self, event=None):
        """Toggles the pause state of the capture loop."""
        self.is_paused = not self.is_paused
        
        if self.is_paused:
            self.add_chat_message("System: Chat paused.", is_system=True)
        else:
            self.add_chat_message("System: Chat resumed.", is_system=True)
    # --- End modification ---

    def start_capture_thread(self):
        """Starts the background thread."""
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.capture_loop, daemon=True)
        self.thread.start()

    def image_to_base64(self, img, format="JPEG"):
        """Converts a PIL Image to a base64 string."""
        buffered = io.BytesIO()
        img.save(buffered, format=format)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def update_image_preview(self, pil_img):
        """Updates the image label with the new screenshot."""
        # Calculate new height to maintain aspect ratio
        w, h = pil_img.size
        ratio = h / w
        new_height = int(THUMBNAIL_WIDTH * ratio)
        
        thumbnail = pil_img.resize((THUMBNAIL_WIDTH, new_height), Image.LANCZOS)
        
        # Keep a reference to the image to prevent garbage collection
        self.tk_image = ImageTk.PhotoImage(thumbnail)
        self.image_label.config(image=self.tk_image)

    def add_chat_message(self, message_block, is_system=False):
        """Adds formatted messages to the chat window."""
        self.chat_text.config(state='normal') # Enable editing
        
        if is_system:
            self.chat_text.insert('end', f"{message_block}\n", 'system')
        else:
            # AI may return multiple chat lines
            for line in message_block.strip().split('\n'):
                if not line:
                    continue
                
                # Try to split user:message, fallback to random user
                try:
                    user, msg = line.split(":", 1)
                except ValueError:
                    user = random.choice(CHAT_USERS)
                    msg = line
                
                # Get a random color for the user
                color = random.choice(USER_COLORS)
                tag_name = f"user_{user.strip()}_{color}"
                
                # Configure the tag with the color
                self.chat_text.tag_config(tag_name, foreground=color, font=('Helvetica', 10, 'bold'))
                
                # Insert the username and message
                self.chat_text.insert('end', f"{user.strip()}: ", tag_name)
                self.chat_text.insert('end', f"{msg.strip()}\n")

        self.chat_text.config(state='disabled') # Disable editing
        # --- MODIFICATION 3: Add autoscroll ---
        self.chat_text.see('end') # Auto-scroll to the end
        # --- End modification ---

    def get_ai_response(self, base64_img):
        """Sends the request to Ollama and gets a response."""
        
        # We only want the *last* user message to have the image
        # So we create a temporary list from the text-only history
        payload_messages = list(self.messages_history)
        
        # Now, add the new user prompt with *only* the new image
        payload_messages.append({
            "role": "user",
            "content": "React to this new screenshot.",
            "images": [base64_img]
        })
        
        try:
            payload = {
                "model": OLLAMA_MODEL,
                "messages": payload_messages,
                "stream": False
            }
            
            # --- MODIFICATION 1 ---
            # Increased timeout from 20 to 60 seconds, which is safer for
            # potentially slow vision model responses.
            response = requests.post(OLLAMA_URL, json=payload, timeout=60)
            response.raise_for_status() # Raise an error for bad responses
            
            response_data = response.json()
            ai_content = response_data.get('message', {}).get('content', '')
            
            return ai_content

        except requests.exceptions.ConnectionError:
            return "System: Error - Cannot connect to Ollama. Is it running?"
        except requests.exceptions.ReadTimeout:
            return "System: Error - Ollama request timed out."
        except requests.exceptions.RequestException as e:
            return f"System: Error - {e}"

    def capture_loop(self):
        """The main loop for the background thread."""
        while not self.stop_event.is_set():
            # --- MODIFICATION 4: Check for pause state ---
            if self.is_paused:
                time.sleep(0.5) # Sleep briefly to avoid a busy-loop
                continue
            # --- End modification ---
            
            try:
                # 1. Capture screen
                screenshot = ImageGrab.grab()
                
                # 2. Convert to base64
                # Use a smaller, lower-quality JPEG for faster upload
                img_small = screenshot.resize((1280, 720), Image.LANCZOS)
                base64_img = self.image_to_base64(img_small, format="JPEG")
                
                # 3. Update UI preview (must be done on the main thread)
                self.root.after(0, self.update_image_preview, screenshot)
                
                # --- MODIFICATION 2 ---
                # This is the main fix. We no longer add the image to the
                # permanent history. We pass the base64 image *directly*
                # to get_ai_response.
                
                # 4. Get AI response using the new image
                ai_response = self.get_ai_response(base64_img)
                
                if ai_response:
                    # 5. Add the *text-only* user prompt and the AI
                    # response to history *after* getting a reply.
                    # This keeps the history deque clean and small.
                    self.messages_history.append({
                        "role": "user",
                        "content": "React to this new screenshot."
                    })
                    self.messages_history.append({
                        "role": "assistant",
                        "content": ai_response
                    })
                    
                    # 6. Add AI message to chat (must be done on the main thread)
                    # Check if it's a system error message
                    is_system = ai_response.startswith("System:")
                    self.root.after(0, self.add_chat_message, ai_response, is_system)
                
            except Exception as e:
                # Handle unexpected errors in the loop
                error_msg = f"System: Error in capture loop: {e}"
                self.root.after(0, self.add_chat_message, error_msg, True)
            
            # 8. Wait for the next interval
            time.sleep(CAPTURE_INTERVAL_SEC)

    def on_close(self):
        """Handles window close event."""
        self.stop_event.set() # Signal the thread to stop
        self.root.destroy()

# --- Main execution ---
if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = ChatStreamApp(root)
        root.protocol("WM_DELETE_WINDOW", app.on_close) # Handle window close
        root.mainloop()
    except Exception as e:
        print(f"Failed to start application: {e}")
        print("Do you have an X server (like XQuartz or VcXsrv) or a desktop environment running?")