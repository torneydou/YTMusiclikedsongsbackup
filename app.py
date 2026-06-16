import os
import sys
import json
import threading
import ctypes
import subprocess
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageTk  
import customtkinter as ctk
import ytmusicapi
from ytmusicapi import YTMusic
import yt_dlp
from mutagen.id3 import ID3, APIC, ID3NoHeaderError
from thefuzz import fuzz

# UI Look & Feel Configuration
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ---------------------------------------------------------
# LIGHTWEIGHT TOOLTIP HELPER CLASS
# ---------------------------------------------------------
class CTkToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() - 220
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(
            tw, text=self.text, justify="left",
            background="#2B2B2B", foreground="#FFFFFF",
            relief="solid", borderwidth=1, highlightthickness=0,
            font=("Segoe UI", 9), padx=10, pady=10
        )
        label.pack()

    def hide_tip(self, event=None):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()


class YTMusicBackupStudio(ctk.CTk):
    def __init__(self, headless=False):
        # Core Application Paths
        self.base_path = os.path.join(os.path.expanduser("~"), "Documents", "ytmusicbackup", "liked_songs")
        self.download_path = os.path.join(os.path.expanduser("~"), "Music", "YTMusic Songs Backup")
        self.auth_file = os.path.join(os.path.expanduser("~"), "Documents", "ytmusicbackup", "browser.json")
        self.config_file = os.path.join(os.path.expanduser("~"), "Documents", "ytmusicbackup", "config.json")
        
        os.makedirs(self.base_path, exist_ok=True)
        os.makedirs(self.download_path, exist_ok=True)

        # Thread management for cancellation control
        self.cancel_event = threading.Event()
        self.is_syncing = False

        # Assets mapping
        if getattr(sys, 'frozen', False):
            self.ffmpeg_dir = sys._MEIPASS
            self.exe_path = sys.executable
            self.icon_path = os.path.join(sys._MEIPASS, "app_icon.ico")
        else:
            self.ffmpeg_dir = os.path.dirname(os.path.abspath(__file__))
            self.exe_path = os.path.abspath(sys.argv[0])
            self.icon_path = os.path.join(self.ffmpeg_dir, "app_icon.ico")

        self.headless = headless

        if self.headless:
            self.run_headless_sync()
            sys.exit(0)

        # Regular GUI Initialization
        super().__init__()

        try:
            myappid = 'studio.ytmusic.backuptool.v1'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        self.title("YouTube Music Backup Studio")
        self.geometry("720x720") 
        self.resizable(False, False)

        if os.path.exists(self.icon_path):
            try:
                self.iconbitmap(self.icon_path)
            except Exception:
                pass
            try:
                pil_img = Image.open(self.icon_path)
                tk_img = ImageTk.PhotoImage(pil_img)
                self.iconphoto(True, tk_img)
            except Exception:
                pass

        self.auto_sync_var = tk.BooleanVar(value=False)
        self.load_config()
        self.init_ui()
        self.check_auth_status()

    def init_ui(self):
        # --- APP TITLE ---
        self.title_label = ctk.CTkLabel(self, text="YouTube Music Audio Exporter", font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(pady=(15, 10))

        # --- AUTHENTICATION CONTAINER ---
        self.auth_frame = ctk.CTkFrame(self)
        self.auth_frame.pack(pady=10, fill="x", padx=30)
        
        self.status_header_frame = ctk.CTkFrame(self.auth_frame, fg_color="transparent")
        self.status_header_frame.pack(fill="x", padx=15, pady=(10, 5))

        self.auth_status_label = ctk.CTkLabel(self.status_header_frame, text="Checking Status...", font=ctk.CTkFont(size=13, weight="bold"))
        self.auth_status_label.pack(side="left")

        self.info_icon = ctk.CTkLabel(self.status_header_frame, text="ⓘ", font=ctk.CTkFont(size=18, weight="bold"), cursor="hand2", text_color="#3B8ED0")
        self.info_icon.pack(side="right", padx=5)
        
        instructions_text = (
            "1. Open Firefox and go to music.youtube.com.\n\n"
            "2. Log in to your account.\n\n"
            "3. Press F12 to open Developer Tools and select the Network tab.\n\n"
            "4. Click on your Liked Songs playlist.\n\n"
            "5. In the Network tab 'Filter' box, type: browse\n\n"
            "6. Right-click the result, select Copy Value, then Copy Request Headers.\n\n"
            "7. Paste the result in the textbox"
        )
        CTkToolTip(self.info_icon, instructions_text)

        self.info_label = ctk.CTkLabel(self.auth_frame, text="Paste raw request headers from Firefox F12 below:", font=ctk.CTkFont(size=11), text_color="gray")
        self.info_label.pack(anchor="w", padx=15, pady=(5, 2))

        # Horizontal block to handle textbox and quick action button right next to it
        self.input_actions_frame = ctk.CTkFrame(self.auth_frame, fg_color="transparent")
        self.input_actions_frame.pack(fill="x", padx=15, pady=5)

        self.headers_input = ctk.CTkTextbox(self.input_actions_frame, height=110, font=ctk.CTkFont(family="Consolas", size=10))
        self.headers_input.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.paste_btn = ctk.CTkButton(self.input_actions_frame, text="📋 Paste", command=self.paste_from_clipboard, width=80, height=110)
        self.paste_btn.pack(side="right")

        self.save_headers_btn = ctk.CTkButton(self.auth_frame, text="Parse & Save Headers", command=self.save_headers, width=150)
        self.save_headers_btn.pack(anchor="e", padx=15, pady=(5, 10))

        # --- AUTOMATION CONTROLS ---
        self.automation_frame = ctk.CTkFrame(self)
        self.automation_frame.pack(pady=5, fill="x", padx=30)
        
        self.auto_sync_check = ctk.CTkCheckBox(
            self.automation_frame, 
            text="Automatically Sync Songs When App Is Closed (Logon & Every 6 Hours)",
            variable=self.auto_sync_var,
            command=self.toggle_background_sync,
            font=ctk.CTkFont(size=12)
        )
        self.auto_sync_check.pack(side="left", padx=15, pady=10)

        # --- SAVE PATH AND BROWSE SELECTOR ---
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.pack(pady=5, fill="x", padx=30)

        self.path_label = ctk.CTkLabel(self.settings_frame, text=f"Save Path: {self.download_path}", font=ctk.CTkFont(size=12), text_color="#A0A0A0")
        self.path_label.pack(side="left", padx=15, pady=10)

        self.browse_btn = ctk.CTkButton(self.settings_frame, text="Browse...", command=self.browse_for_directory, width=90, height=26, font=ctk.CTkFont(size=11))
        self.browse_btn.pack(side="right", padx=15, pady=10)

        # --- ENGINE TRIGGER CONTROLS ---
        self.controls_btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.controls_btn_frame.pack(pady=15)

        self.start_btn = ctk.CTkButton(self.controls_btn_frame, text="Run Playlist Sync Pipeline", font=ctk.CTkFont(size=15, weight="bold"), height=42, width=220, command=self.start_backup_thread)
        self.start_btn.pack(side="left", padx=10)

        self.stop_btn = ctk.CTkButton(self.controls_btn_frame, text="Stop Sync", font=ctk.CTkFont(size=15, weight="bold"), height=42, width=140, fg_color="#D32F2F", hover_color="#B71C1C", command=self.stop_backup_pipeline)
        self.stop_btn.pack(side="left", padx=10)
        self.stop_btn.configure(state="disabled")

        self.progress_bar = ctk.CTkProgressBar(self, width=660)
        self.progress_bar.pack(pady=(0, 10))
        self.progress_bar.set(0)

        # --- TERMINAL FEEDBACK WINDOW ---
        self.log_box = ctk.CTkTextbox(self, width=660, height=190, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_box.pack(pady=10)
        self.log_text("Dashboard Core Active. Awaiting commands.")

    def log_text(self, msg):
        if not self.headless:
            self.log_box.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
            self.log_box.see("end")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def get_ytmusic_client(self):
        """Builds instance cleanly from physical absolute path target strings."""
        if not os.path.exists(self.auth_file):
            return None
        try:
            return YTMusic(self.auth_file)
        except Exception as e:
            self.log_text(f"API Instantiation Error: {e}")
            return None

    def validate_session(self):
        yt = self.get_ytmusic_client()
        if not yt:
            return False
        try:
            yt.get_liked_songs(limit=1)
            return True
        except Exception as e:
            self.log_text(f"Session Authentication Validation Exception: {e}")
            return False

    def check_auth_status(self):
        if not os.path.exists(self.auth_file):
            self.auth_status_label.configure(text="Session Status: No Valid Session (Pasting Headers Required)", text_color="#F44336")
            self.start_btn.configure(state="disabled")
            return

        def async_check():
            if self.validate_session():
                self.auth_status_label.configure(text="Session Status: Authenticated & Connected", text_color="#4CAF50")
                self.start_btn.configure(state="normal")
            else:
                self.auth_status_label.configure(text="Session Status: EXPIRED / INVALID (Update Headers!)", text_color="#F44336")
                self.start_btn.configure(state="disabled")

        threading.Thread(target=async_check, daemon=True).start()

    def paste_from_clipboard(self):
        try:
            clipboard_text = self.clipboard_get().strip()
            if clipboard_text:
                self.headers_input.delete("1.0", "end")
                self.headers_input.insert("1.0", clipboard_text)
                self.log_text("Clipboard data injected. Running auto-compile validation...")
                self.save_headers()
            else:
                self.log_text("Paste Cancelled: Clipboard contains empty textual values.")
        except Exception as e:
            self.log_text(f"Clipboard System Error: Unable to access memory buffer. Details: {e}")

    def save_headers(self):
        raw_text = self.headers_input.get("1.0", "end-1c").strip()
        if not raw_text:
            self.log_text("Action rejected: Textarea container cannot be blank.")
            return
        
        try:
            ytmusicapi.setup(filepath=self.auth_file, headers_raw=raw_text)
            self.log_text("Authentication file browser.json successfully compiled locally.")
            self.headers_input.delete("1.0", "end")
            self.check_auth_status()
        except Exception as e:
            self.log_text(f"Parsing Fault: Headers context unrecognized. Reason: {e}")

    def browse_for_directory(self):
        selected_directory = filedialog.askdirectory(initialdir=self.download_path, title="Select Backup Destination Folder")
        if selected_directory:
            self.download_path = os.path.normpath(selected_directory)
            self.path_label.configure(text=f"Save Path: {self.download_path}")
            self.log_text(f"Destination save target updated to: {self.download_path}")
            self.save_config()

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    self.auto_sync_var.set(data.get("auto_sync", False))
                    if "download_path" in data and os.path.exists(data["download_path"]):
                        self.download_path = data["download_path"]
            except Exception:
                pass

    def save_config(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump({
                    "auto_sync": self.auto_sync_var.get(),
                    "download_path": self.download_path
                }, f)
        except Exception:
            pass

    def toggle_background_sync(self):
        self.save_config()
        task_name = "YTMusicBackupStudio_AutoSync"
        
        if self.auto_sync_var.get():
            try:
                subprocess.run(f'schtasks /delete /tn "{task_name}" /f', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                cmd_hourly = (
                    f'schtasks /create /tn "{task_name}" /tr "\'{self.exe_path}\' --headless" '
                    f'/sc HOURLY /mo 6 /st 00:00 /f'
                )
                subprocess.run(cmd_hourly, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                cmd_logon = (
                    f'schtasks /create /tn "{task_name}_Logon" /tr "\'{self.exe_path}\' --headless" '
                    f'/sc ONLOGON /f'
                )
                subprocess.run(cmd_logon, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                self.log_text("Background automation profiles injected into OS Task Engine successfully.")
            except Exception as e:
                self.log_text(f"Failed to register Windows Task: {e}")
        else:
            try:
                subprocess.run(f'schtasks /delete /tn "{task_name}" /f', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(f'schtasks /delete /tn "{task_name}_Logon" /f', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.log_text("Background automation entries removed from system.")
            except Exception as e:
                self.log_text(f"Failed to clear Windows Tasks: {e}")

    def start_backup_thread(self):
        self.cancel_event.clear()
        self.is_syncing = True
        self.start_btn.configure(state="disabled", text="Running Exporter...")
        self.stop_btn.configure(state="normal")
        threading.Thread(target=self.run_backup_logic, daemon=True).start()

    def stop_backup_pipeline(self):
        if self.is_syncing:
            self.log_text("Cancellation command received. Terminating processes gracefully...")
            self.cancel_event.set()
            self.stop_btn.configure(state="disabled")

    def run_headless_sync(self):
        if not self.validate_session():
            try:
                import tkinter.messagebox as messagebox
                root = tk.Tk()
                root.withdraw() 
                root.attributes("-topmost", True) 
                
                messagebox.showerror(
                    title="YTMusic Backup Alert",
                    message="Your YouTube Music backup authentication has expired!\n\nPlease open the application window and re-paste your headers."
                )
                root.destroy()
            except Exception:
                pass
            return
            
        self.run_backup_logic()

    def run_backup_logic(self):
        try:
            self.log_text("Accessing YouTube Music server via authentication handshake...")
            yt = self.get_ytmusic_client()
            if not yt:
                self.log_text("Error: Failed to safely build memory client.")
                self.finalize_sync_ui()
                return
            
            self.log_text("Downloading account Liked Songs index records...")
            liked_songs = yt.get_liked_songs(limit=None)
            
            tracks = liked_songs.get('tracks', [])
            if not tracks:
                self.log_text("Warning: No tracks found. Headers might be corrupted.")
                self.finalize_sync_ui()
                return

            self.log_text(f"Successfully retrieved {len(tracks)} tracks from cloud profile. Scanning local directory...")
            
            songs_to_download = []
            for t in tracks:
                if self.cancel_event.is_set(): break
                vid = t.get('videoId')
                title = t.get('title')
                if not vid or not title:
                    continue
                
                exists, file_name = self.is_already_downloaded(title, self.download_path)
                if not exists:
                    songs_to_download.append((vid, title))

            if self.cancel_event.is_set():
                self.log_text("Sync pipeline execution canceled by user.")
                self.finalize_sync_ui()
                return

            if not songs_to_download:
                self.log_text("Directory perfectly matched with account playlist. No actions required.")
                if not self.headless:
                    self.progress_bar.set(1.0)
            else:
                total = len(songs_to_download)
                self.log_text(f"Identified {total} missing files. Initiating download pipeline...")
                
                for idx, (vid, title) in enumerate(songs_to_download, start=1):
                    if self.cancel_event.is_set():
                        self.log_text("Sync pipeline canceled mid-execution.")
                        break
                    self.log_text(f"  [Downloading {idx}/{total}] Processing: '{title}'")
                    self.download_track(vid)
                    if not self.headless:
                        self.progress_bar.set(idx / total)

            if not self.cancel_event.is_set():
                self.log_text("Sync operations complete!")
                if not self.headless:
                    os.startfile(self.download_path)

        except Exception as e:
            self.log_text(f"Fatal System Fault occurred: {e}")
        
        self.finalize_sync_ui()

    def finalize_sync_ui(self):
        self.is_syncing = False
        if not self.headless:
            self.start_btn.configure(state="normal", text="Run Playlist Sync Pipeline")
            self.stop_btn.configure(state="disabled")

    def is_already_downloaded(self, target_title, folder_path, threshold=90):
        if not os.path.exists(folder_path): return False, None
        existing_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".mp3")]
        for f_name in existing_files:
            clean_name = f_name.rsplit('.', 1)[0]
            if "[" in clean_name: clean_name = clean_name.split("[")[0].strip()
            if fuzz.token_sort_ratio(target_title.lower(), clean_name.lower()) >= threshold:
                return True, f_name
        return False, None

    def download_track(self, video_id):
        file_template = os.path.join(self.download_path, f"%(title)s [{video_id}].%(ext)s")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'ffmpeg_location': self.ffmpeg_dir,
            'outtmpl': file_template,
            'writethumbnail': True,  
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['default', '-android_sdkless']
                }
            },
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }, {
                'key': 'FFmpegThumbnailsConvertor',
                'format': 'jpg',     
            }, {
                'key': 'EmbedThumbnail',
            }, {
                'key': 'FFmpegMetadata',
            }],
            'sleep_interval': 2,
            'max_sleep_interval': 3,
        }

        def ydl_progress_hook(d):
            if self.cancel_event.is_set():
                raise Exception("User Aborted Operational Run")

        ydl_opts['progress_hooks'] = [ydl_progress_hook]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

            for f in os.listdir(self.download_path):
                if video_id in f and f.lower().endswith(".mp3"):
                    self.process_mp3_cover(os.path.join(self.download_path, f))
        except Exception:
            pass

    def process_mp3_cover(self, path):
        try:
            try: audio = ID3(path)
            except ID3NoHeaderError:
                audio = ID3(); audio.save(path); audio = ID3(path)

            pics = audio.getall('APIC')
            if not pics:
                audio.update_to_v23()
                pics = audio.getall('APIC')

            if not pics: return

            tag = pics[0]
            img = Image.open(BytesIO(tag.data))
            w, h = img.size
            side = min(w, h)
            img = img.crop(((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side))

            if img.mode in ("RGBA", "LA"): img = img.convert("RGB")

            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=95)
            audio.delall('APIC')
            audio.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=buffer.getvalue()))
            audio.save(v2_version=3)
        except Exception as e:
            self.log_text(f"  [Art Warning] Image conversion bypassed: {e}")


if __name__ == "__main__":
    is_headless = "--headless" in sys.argv
    app = YTMusicBackupStudio(headless=is_headless)
    if not is_headless:
        app.mainloop()
