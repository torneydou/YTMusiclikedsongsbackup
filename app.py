import os
import sys
import json
import threading
import ctypes
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageTk  # Added ImageTk for explicit container generation
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
    def __init__(self):
        super().__init__()

        # Hard-bind a completely unique process signature into the Windows Shell kernel
        try:
            myappid = 'studio.ytmusic.backuptool.v1'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        self.title("YouTube Music Backup Studio")
        self.geometry("720x650")
        self.resizable(False, False)

        # Core Application Paths
        self.base_path = os.path.join(os.path.expanduser("~"), "Documents", "ytmusicbackup", "liked_songs")
        self.download_path = os.path.join(os.path.expanduser("~"), "Music", "YTMusic Songs Backup")
        self.auth_file = os.path.join(os.path.expanduser("~"), "Documents", "ytmusicbackup", "browser.json")
        
        # Handle embedded internal asset path mapping for PyInstaller
        if getattr(sys, 'frozen', False):
            self.ffmpeg_dir = sys._MEIPASS
            icon_path = os.path.join(sys._MEIPASS, "app_icon.ico")
        else:
            self.ffmpeg_dir = os.path.dirname(os.path.abspath(__file__))
            icon_path = "app_icon.ico"

        # Apply Window Icon Assets
        if os.path.exists(icon_path):
            try:
                # Force Windows to assign the icon file directly
                self.iconbitmap(icon_path)
            except Exception:
                pass
            try:
                # Fallback: Generate an explicit multi-frame image object array
                pil_img = Image.open(icon_path)
                tk_img = ImageTk.PhotoImage(pil_img)
                self.iconphoto(True, tk_img)
            except Exception:
                pass

        os.makedirs(self.base_path, exist_ok=True)
        os.makedirs(self.download_path, exist_ok=True)

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

        self.headers_input = ctk.CTkTextbox(self.auth_frame, height=110, font=ctk.CTkFont(family="Consolas", size=10))
        self.headers_input.pack(fill="x", padx=15, pady=5)

        self.save_headers_btn = ctk.CTkButton(self.auth_frame, text="Parse & Save Headers", command=self.save_headers, width=150)
        self.save_headers_btn.pack(anchor="e", padx=15, pady=(5, 10))

        # --- SAVE PATH AND BROWSE SELECTOR ---
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.pack(pady=5, fill="x", padx=30)

        self.path_label = ctk.CTkLabel(self.settings_frame, text=f"Save Path: {self.download_path}", font=ctk.CTkFont(size=12), text_color="#A0A0A0")
        self.path_label.pack(side="left", padx=15, pady=10)

        self.browse_btn = ctk.CTkButton(self.settings_frame, text="Browse...", command=self.browse_for_directory, width=90, height=26, font=ctk.CTkFont(size=11))
        self.browse_btn.pack(side="right", padx=15, pady=10)

        # --- ENGINE TRIGGER CONTROLS ---
        self.start_btn = ctk.CTkButton(self, text="Run Playlist Sync Pipeline", font=ctk.CTkFont(size=15, weight="bold"), height=42, command=self.start_backup_thread)
        self.start_btn.pack(pady=15)

        self.progress_bar = ctk.CTkProgressBar(self, width=660)
        self.progress_bar.pack(pady=(0, 10))
        self.progress_bar.set(0)

        # --- TERMINAL FEEDBACK WINDOW ---
        self.log_box = ctk.CTkTextbox(self, width=660, height=190, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_box.pack(pady=10)
        self.log_text("Dashboard Core Active. Awaiting commands.")

    def log_text(self, msg):
        self.log_box.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.log_box.see("end")

    def check_auth_status(self):
        if os.path.exists(self.auth_file):
            self.auth_status_label.configure(text="Session Status: Authenticated & Connected", text_color="#4CAF50")
            self.start_btn.configure(state="normal")
        else:
            self.auth_status_label.configure(text="Session Status: No Valid Session (Pasting Headers Required)", text_color="#F44336")
            self.start_btn.configure(state="disabled")

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

    def start_backup_thread(self):
        self.start_btn.configure(state="disabled", text="Running Exporter...")
        threading.Thread(target=self.run_backup_logic, daemon=True).start()

    def run_backup_logic(self):
        try:
            self.log_text("Accessing YouTube Music server via authentication handshake...")
            yt = YTMusic(self.auth_file)
            
            self.log_text("Downloading account Liked Songs index records...")
            liked_songs = yt.get_liked_songs(limit=None)
            
            tracks = liked_songs.get('tracks', [])
            if not tracks:
                self.log_text("Warning: No tracks found. Your saved browser headers might be expired! Try pasting fresh headers.")
                self.start_btn.configure(state="normal", text="Run Playlist Sync Pipeline")
                return

            self.log_text(f"Successfully retrieved {len(tracks)} tracks from cloud profile. Scanning local directory...")
            
            songs_to_download = []
            for t in tracks:
                vid = t.get('videoId')
                title = t.get('title')
                if not vid or not title:
                    continue
                
                exists, file_name = self.is_already_downloaded(title, self.download_path)
                if not exists:
                    songs_to_download.append((vid, title))

            if not songs_to_download:
                self.log_text("Directory is perfectly matched with your target account playlists. No actions required.")
                self.progress_bar.set(1.0)
            else:
                total = len(songs_to_download)
                self.log_text(f"Identified {total} missing files. Initiating download pipeline...")
                
                for idx, (vid, title) in enumerate(songs_to_download, start=1):
                    self.log_text(f"  [Downloading {idx}/{total}] Processing: '{title}'")
                    self.download_track(vid)
                    self.progress_bar.set(idx / total)

            self.log_text("Sync operations complete! Accessing output folder...")
            os.startfile(self.download_path)

        except Exception as e:
            self.log_text(f"Fatal System Fault occurred: {e}")
        
        self.start_btn.configure(state="normal", text="Run Playlist Sync Pipeline")

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

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

        for f in os.listdir(self.download_path):
            if video_id in f and f.lower().endswith(".mp3"):
                self.process_mp3_cover(os.path.join(self.download_path, f))

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
    app = YTMusicBackupStudio()
    app.mainloop()