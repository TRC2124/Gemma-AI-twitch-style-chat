import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageGrab
import requests
import base64
import io
import threading
import time
import random
import re
from collections import deque
import json

# --- CONFIGURATION ---

OLLAMA_MODEL = "gemma3:12b"  # Or whichever model you are using
OLLAMA_URL = "http://localhost:11434/api/chat"
CAPTURE_INTERVAL_SEC = 3
MAX_CHAT_HISTORY = 10

# Context management
RESET_INTERVAL = 8      # How many screenshots before context reset
PRESERVE_RESPONSES = 2  # How many last AI messages (and user prompts) to keep

# --- UPDATED: More robust regex ---
# This will find the *first* valid "username: message" pattern in a line.
# 1. (?!(?:Impression|System)) - Negative lookahead: blocks "Impression:" or "System:"
# 2. ([A-Za-z0-9_\-]{3,}) - Group 1 (Username): At least 3 chars
# 3. \s*:\**\s* - Matches a colon, allowing spaces and markdown (e.g., ":** ")
# 4. (.+) - Group 2 (Message)
CHAT_LINE_REGEX = re.compile(r"(?!(?:Impression|System))([A-Za-z0-9_\-]{3,})\s*:\**\s*(.+)")


SYSTEM_PROMPT = """
You are an expert at simulating a fast-paced, highly interactive livestream chat. Your sole task is to analyze a provided screenshot and generate 3 to 5 new, realistic chat messages reacting to the content shown.

---
**CRITICAL RULES**
1.  **ONLY CHAT MESSAGES:** Your ENTIRE output MUST contain NOTHING except the generated chat messages.
2.  **NO EXTRA TEXT:** DO NOT include ANY introductory, explanatory, or descriptive text. No "Here are the reactions:", "Okay:", "Certainly:", or any other text.
3.  **NO MARKDOWN:** Do not use bullet points (*), bolding (**), or any other markdown.
4.  **NO META-COMMENTS:** Do not generate "meta" summaries (e.g., "Impression: ...", "Summary: ..."). Only output chat messages.

---
**OUTPUT FORMAT**
Every single line you generate MUST strictly adhere to the following format:
{username}: {message}

---
**BEHAVIOR**
* **Username:** Must be a plausible, short, and distinct username (e.g., xX_GamerGod_Xx, PotatoFan, LurkModeActive, SaltyStreams).
* **Message:** Must be a short, authentic-sounding reaction (e.g., excitement, question, meme, confusion, praise, or spam). Use caps, emojis, and slang.
* **Variety:** Ensure the 3-5 messages come from different perspectives.
* **Focus:** React to the MAIN CONTENT of the screenshot, not the chat window (if one is visible).

---
**EXAMPLE OF A PERFECT OUTPUT**
FailBot99: NOOOOOOO WAY
PogChampFan: Rip the run 😭
MVP_Lover: Chat is so fast today lol
GetGud: wait, did you see the health bar? that was close!
"""

CHAT_USERS = [
    "StreamFan", "Gamer123", "NoobSlayer", "ChatterBoi", "PixelPro", "LagKing",
    "W_Key_Warrior", "Lurker22", "PixelPirateLord", "SwiftShadow_X", "NeonNomadTV",
    "CrimsonByte99", "FrostyFiasco_live", "AstroZenith7", "SilentSpecter84",
    "TheWittyWombat", "HyperPanda_Stream", "VaporWaveViking", "GalacticGoblin",
    "MistyMayhem_yt", "CodeCrafter_01", "EchoingKnight", "RogueRobot_23",
    "QuantumQuasar", "BlazingBacon42", "MidnightMarauder", "ElectricEel_Gaming",
    "NomadicNoodle", "ArcaneAnarchy_", "TurboTaco_Time", "ZenithZebra_z",
    "CosmicCrusader5", "FlickeringFlamez", "GloomyGamerGuy", "StellarSquid_",
    "WaffleWarrior_77", "TheCrypticCapybara", "DigitalDrifter_"
]
USER_COLORS = [
    "#FF0000", "#0000FF", "#008000", "#B22222", "#FF7F50",
    "#9ACD32", "#FF4500", "#2E8B57", "#DAA520", "#D2691E"
]
THUMBNAIL_WIDTH = 320


class ChatStreamApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Ollama Screen Reactor")
        self.root.geometry("400x600")
        self.root.configure(bg="#18181B")

        self.messages_history = deque(maxlen=MAX_CHAT_HISTORY)
        self.messages_history.append({"role": "system", "content": SYSTEM_PROMPT})
        self.response_count = 0  # Track how many screenshot responses we've done

        # --- UI SETUP ---
        self.top_frame = tk.Frame(root, bg="#18181B")
        self.top_frame.pack(fill='x', pady=5, padx=5)

        self.image_label = tk.Label(self.top_frame, bg="#000000")
        self.image_label.pack(fill='x')

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

        self.chat_frame = tk.Frame(root, bg="#18181B")
        self.chat_frame.pack(fill='both', expand=True, padx=5, pady=(0, 5))

        self.chat_text = tk.Text(
            self.chat_frame,
            wrap='word',
            bg="#1F1F23",
            fg="white",
            state='disabled',
            font=("Helvetica", 10),
            borderwidth=0,
            padx=10,
            pady=10
        )
        self.chat_text.pack(fill='both', expand=True)
        self.chat_text.tag_config('system', foreground="#FFD700")

        self.is_paused = True
        self.root.bind('<Key-0>', self.toggle_pause)

        self.start_capture_thread()
        self.add_chat_message("System: Chat is paused. Press '0' to start.", is_system=True)

    def toggle_on_top(self):
        self.root.attributes('-topmost', self.on_top_var.get())

    def toggle_pause(self, event=None):
        self.is_paused = not self.is_paused
        msg = "System: Chat resumed." if not self.is_paused else "System: Chat paused."
        self.add_chat_message(msg, is_system=True)

    def start_capture_thread(self):
        self.stop_event = threading.Event()
        threading.Thread(target=self.capture_loop, daemon=True).start()

    def image_to_base64(self, img, format="JPEG"):
        buffered = io.BytesIO()
        img.save(buffered, format=format)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def update_image_preview(self, pil_img):
        w, h = pil_img.size
        ratio = h / w
        new_height = int(THUMBNAIL_WIDTH * ratio)
        thumbnail = pil_img.resize((THUMBNAIL_WIDTH, new_height), Image.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(thumbnail)
        self.image_label.config(image=self.tk_image)

    def add_chat_message(self, message_block, is_system=False):
        self.chat_text.config(state='normal')
        if is_system:
            self.chat_text.insert('end', f"{message_block}\n", 'system')
        else:
            for line in message_block.strip().split('\n'):
                line = line.strip()
                
                # --- UPDATED: Use regex search to find the pattern ---
                match = CHAT_LINE_REGEX.search(line)
                
                if not match:
                    print(f"Skipping malformed line: {line}")
                    continue
                
                user = match.group(1)
                msg = match.group(2)
                
                color = random.choice(USER_COLORS)
                tag_name = f"user_{user.strip()}_{color}"
                self.chat_text.tag_config(tag_name, foreground=color, font=('Helvetica', 10, 'bold'))
                
                self.chat_text.insert('end', f"{user.strip()}: ", tag_name)
                self.chat_text.insert('end', f"{msg.strip()}\n")
                
        self.chat_text.config(state='disabled')
        self.chat_text.see('end')

    def get_ai_response(self, base64_img):
        payload_messages = list(self.messages_history)
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
            response = requests.post(OLLAMA_URL, json=payload, timeout=60)
            response.raise_for_status()
            return response.json().get('message', {}).get('content', '')
        except requests.exceptions.ConnectionError:
            return "System: Error - Cannot connect to Ollama. Is it running?"
        except requests.exceptions.ReadTimeout:
            return "System: Error - Ollama request timed out."
        except requests.exceptions.RequestException as e:
            return f"System: Error - {e}"

    def capture_loop(self):
        while not self.stop_event.is_set():
            if self.is_paused:
                time.sleep(0.5)
                continue
            try:
                screenshot = ImageGrab.grab()
                img_small = screenshot.resize((1280, 720), Image.LANCZOS)
                base64_img = self.image_to_base64(img_small, format="JPEG")

                self.root.after(0, self.update_image_preview, screenshot)
                ai_response = self.get_ai_response(base64_img)

                if ai_response:
                    is_system = ai_response.startswith("System:")
                    self.root.after(0, self.add_chat_message, ai_response, is_system)

                    # --- Clean and Preserve Context ---
                    cleaned_ai_response_for_history = ""
                    if not is_system:
                        cleaned_lines = []
                        for line in ai_response.strip().split('\n'):
                            line = line.strip()
                            
                            # --- UPDATED: Use regex search to clean lines for history ---
                            match = CHAT_LINE_REGEX.search(line)
                            
                            if match:
                                # Reconstruct the line cleanly for history
                                cleaned_lines.append(f"{match.group(1)}: {match.group(2)}")
                            else:
                                print(f"Filtered malformed line from history: {line}")
                        cleaned_ai_response_for_history = "\n".join(cleaned_lines)
                    else:
                        cleaned_ai_response_for_history = ai_response

                    if cleaned_ai_response_for_history:
                        self.messages_history.append({
                            "role": "user",
                            "content": "React to this new screenshot."
                        })
                        self.messages_history.append({
                            "role": "assistant",
                            "content": cleaned_ai_response_for_history
                        })

                        # --- Reset Context Periodically ---
                        self.response_count += 1
                        if self.response_count >= RESET_INTERVAL:
                            print("Resetting context to avoid drift...")

                            # --- UPDATED: Correct context reset logic ---
                            # Get all messages except the system prompt
                            all_messages = list(self.messages_history)
                            if all_messages[0]["role"] == "system":
                                interaction_messages = all_messages[1:]
                            else:
                                interaction_messages = all_messages

                            # Take the last N pairs (user + assistant = 2 messages)
                            num_messages_to_preserve = PRESERVE_RESPONSES * 2
                            preserved_interactions = interaction_messages[-num_messages_to_preserve:]

                            self.messages_history.clear()
                            self.messages_history.append({"role": "system", "content": SYSTEM_PROMPT})
                            
                            # Add the preserved interactions back
                            for msg in preserved_interactions:
                                self.messages_history.append(msg)
                            
                            print(f"Context reset. Preserved {len(preserved_interactions)} messages.")
                            self.response_count = 0

            except Exception as e:
                error_msg = f"System: Error in capture loop: {e}"
                self.root.after(0, self.add_chat_message, error_msg, True)

            time.sleep(CAPTURE_INTERVAL_SEC)

    def on_close(self):
        self.stop_event.set()
        self.root.destroy()


if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = ChatStreamApp(root)
        root.protocol("WM_DELETE_WINDOW", app.on_close)
        root.mainloop()
    except Exception as e:
        print(f"Failed to start application: {e}")
        if "DISPLAY" in str(e):
            print("Error: No display detected. Run in a desktop environment.")