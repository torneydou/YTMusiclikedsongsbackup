# YTMusic liked songs backup
A tool that allows the user to backup the songs inside their accounts liked songs playlist.

Amma be honest this shit was fully made by Gemini, i am NOT a developer, but i needed a problem solved, so i did.

## Features

* **Intelligent Incremental Sync:** Scans your local backup folder and only downloads newly liked songs or tracks missing from your machine.
* **Metadata & Artwork Processing:** Automatically embeds track details and crops album covers into clean, high-quality squares.
* **403 Forbidden Bypass:** Includes custom extractor routing to prevent YouTube from blocking audio streams.
* **Persistent Session Handling:** Securely caches your encrypted request headers locally so you don't have to paste them every time you open the app.

## Credits & Acknowledgments

This project is built upon the incredible work of the open-source community. Special thanks to the creators and maintainers of the following core libraries:

* **[yt-dlp](https://github.com/yt-dlp/yt-dlp):** For providing the powerful, reliable media extraction engine used to download audio streams.
* **[FFmpeg](https://ffmpeg.org/):** For the essential backend multimedia framework that handles the high-quality audio conversion and processing.
* **[ytmusicapi](https://github.com/sigma67/ytmusicapi):** For the excellent unofficial API wrapper that handles the secure profile authentication and fetches playlist data.
* **[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter):** For the modern, beautiful Dark Mode UI framework that brings the desktop layout to life.
* **[Mutagen](https://github.com/quodlibet/mutagen):** For the audio metadata handling that embeds the track information and crops the album covers.
* **[TheFuzz](https://github.com/seatgeek/thefuzz):** For the fuzzy logic string matching used to cleanly deduplicate your local directory.
