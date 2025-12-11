import asyncio, aiohttp, os, re, json, random, glob, logging
from typing import Union, Tuple, Optional
from urllib.parse import urlparse

import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch
from ERAVIBES.utils.database import is_on_off


# Global caching for cookie file path and video info
_cached_cookie = None
_info_cache = {}  # Cache ke liye: { link: info }

def cookie_txt_file():
    global _cached_cookie
    if _cached_cookie:
        return _cached_cookie

    folder_path = os.path.join(os.getcwd(), "cookies")
    log_filename = os.path.join(os.getcwd(), "cookies", "logs.csv")
    txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
    if not txt_files:
        raise FileNotFoundError("No .txt files found in the specified folder.")
    chosen_file = random.choice(txt_files)
    with open(log_filename, 'a') as file:
        file.write(f'Choosen File : {chosen_file}\n')
    _cached_cookie = f"cookies/{os.path.basename(chosen_file)}"
    return _cached_cookie

def extract_video_info(link: str) -> dict:
    # Agar info cache mein hai, use kar lo
    if link in _info_cache:
        return _info_cache[link]
    ytdl_opts = {
        "quiet": True,
        "cookiefile": cookie_txt_file(),
    }
    with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
        info = ydl.extract_info(link, download=False)
    _info_cache[link] = info
    return info

def time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60**i for i, x in enumerate(reversed(stringt.split(":"))))

# ============ NEW FUNCTIONS ADDED ============

def parse_tg_link(link: str) -> Tuple[Optional[str], Optional[int]]:
    """Telegram link se chat username aur message ID extract karta hai"""
    parsed = urlparse(link)
    path = parsed.path.strip('/')
    parts = path.split('/')
    
    if len(parts) >= 2:
        return str(parts[0]), int(parts[1])
        
    return None, None


async def fetch_song(query: str, streamtype: str):
    api_url = "https://eytapi02-28af26f8c000.herokuapp.com/try"
    status_url = "https://eytapi02-28af26f8c000.herokuapp.com/status"

    vid = "true" if streamtype.lower() == "video" else "false"
    params = {"query": query, "vid": vid}

    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, params=params) as response:
            data = await response.json()

        if "link" in data:
            return data

        job_id = data.get("job_id")
        if not job_id:
            return {"error": "No job id received"}

        for _ in range(600):
            await asyncio.sleep(2)
            async with session.get(status_url, params={"id": job_id}) as r:
                status_data = await r.json()

            if status_data.get("status") == "done":
                return {"link": status_data.get("link")}

            if status_data.get("status") == "failed":
                return {"error": "Download failed"}

        return {"error": "Timeout waiting for song"}

async def download_tg_media(tg_link: str) -> Optional[str]:
    """TG link se media download karta hai locally"""
    # Parse TG link
    c_username, message_id = parse_tg_link(tg_link)
    if not c_username or not message_id:
        print(f"Failed to parse TG link: {tg_link}")
        return None

    # Assume c_username is username or id
    if c_username.startswith("@"):
        c_username = c_username[1:]

    try:
        app = __import__("ERAVIBES", fromlist=["app"]).app
        msg = await app.get_messages(c_username, message_id)
        if not msg or not msg.media:
            print(f"No media in TG message: {tg_link}")
            return None

        filex = msg.audio or msg.video or msg.document
        if not filex:
            print(f"No filex in TG message")
            return None

        # Make filepath like Telegram.py
        if msg.audio:
            file_name = f"{filex.file_unique_id}.{filex.file_name.split('.')[-1] if filex.file_name else 'ogg'}"
        elif msg.video or msg.document:
            file_name = f"{filex.file_unique_id}.{filex.file_name.split('.')[-1] if filex.file_name else 'mp4'}"
        else:
            print("Not audio/video")
            return None

        fname = os.path.join("downloads", file_name)
        if os.path.exists(fname):
            print(f"File already exists: {fname}")
            return fname

        # Download
        await app.download_media(msg, fname)
        print(f"Downloaded TG media to: {fname}")
        return fname

    except Exception as e:
        print(f"Error downloading TG media: {e}")
        return None

# =============================================


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = re.compile(r"(?:youtube\.com|youtu\.be)")
        self.listbase = "https://youtube.com/playlist?list="

    async def get_download_link(self, query: str, video_stream: bool = False) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """
        Query se song fetch karke telegram link parse karta hai
        
        Returns:
            Tuple of (username, message_id, error_message)
            Agar success hai to error_message None hoga
        """
        streamtype = "video" if video_stream else "audio"
        song_data = await fetch_song(query, streamtype)

        if not song_data or "error" in song_data or "link" not in song_data:
            error_msg = song_data.get("error", "Failed to process query")
            return None, None, error_msg

        song_url = song_data["link"]
        c_username, message_id = parse_tg_link(song_url)
        
        return c_username, message_id, None

    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        if videoid:
            link = self.base + link
        return bool(self.regex.search(link))

    async def url(self, message: Message) -> Union[str, None]:
        messages = [message]
        if message.reply_to_message:
            messages.append(message.reply_to_message)
        text = ""
        offset = None
        length = None
        for msg in messages:
            if offset is not None:
                break
            if msg.entities:
                for entity in msg.entities:
                    if entity.type == MessageEntityType.URL:
                        text = msg.text or msg.caption
                        offset = entity.offset
                        length = entity.length
                        break
            elif msg.caption_entities:
                for entity in msg.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        if offset is None:
            return None
        return text[offset: offset + length]

    async def details(self, link: str, videoid: Union[bool, str] = None) -> Tuple[str, str, int, str, str]:
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        search_result = (await results.next())["result"][0]
        title = search_result["title"]
        duration_str = search_result["duration"]
        thumbnail = search_result["thumbnails"][0]["url"].split("?")[0]
        vidid = search_result["id"]
        duration_sec = int(time_to_seconds(duration_str)) if duration_str else 0
        return title, duration_str, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None) -> str:
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        return (await results.next())["result"][0]["title"]

    async def duration(self, link: str, videoid: Union[bool, str] = None) -> str:
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        return (await results.next())["result"][0]["duration"]

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None) -> str:
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        return (await results.next())["result"][0]["thumbnails"][0]["url"].split("?")[0]

    async def video(self, link: str, videoid: Union[bool, str] = None) -> Tuple[int, str]:
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]

        # Blocking operation ko async thread mein chalaya
        def get_video_url():
            info = extract_video_info(link)
            for fmt in info.get("formats", []):
                if fmt.get("format_id") and fmt.get("url"):
                    # Resolution filter
                    if fmt.get("height", 0) <= 720 and fmt.get("width", 0) <= 1280:
                        return 1, fmt["url"]
            return 0, "No suitable format found."

        return await asyncio.to_thread(get_video_url)

    async def playlist(self, link: str, limit: int, user_id, videoid: Union[bool, str] = None) -> list:
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]

        def get_playlist_ids():
            ytdl_opts = {"quiet": True, "cookiefile": cookie_txt_file()}
            with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                info = ydl.extract_info(link, download=False)
            return [entry["id"] for entry in info.get("entries", [])][:limit]

        return await asyncio.to_thread(get_playlist_ids)

    async def track(self, link: str, videoid: Union[bool, str] = None) -> Tuple[dict, str]:
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        search_result = (await results.next())["result"][0]
        track_details = {
            "title": search_result["title"],
            "link": search_result["link"],
            "vidid": search_result["id"],
            "duration_min": search_result["duration"],
            "thumb": search_result["thumbnails"][0]["url"].split("?")[0],
        }
        return track_details, search_result["id"]

    async def formats(self, link: str, videoid: Union[bool, str] = None) -> Tuple[list, str]:
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]

        def get_formats():
            info = extract_video_info(link)
            available = []
            for fmt in info.get("formats", []):
                if "dash" in fmt.get("format", "").lower():
                    continue
                try:
                    # Check required keys
                    _ = fmt["filesize"]
                    _ = fmt["format_id"]
                    _ = fmt["ext"]
                    _ = fmt["format_note"]
                    available.append({
                        "format": fmt["format"],
                        "filesize": fmt["filesize"],
                        "format_id": fmt["format_id"],
                        "ext": fmt["ext"],
                        "format_note": fmt["format_note"],
                        "yturl": link,
                    })
                except Exception:
                    continue
            return available

        formats_available = await asyncio.to_thread(get_formats)
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None) -> Tuple[str, str, str, str]:
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=10)
        entries = (await results.next()).get("result")
        selected = entries[query_type]
        return selected["title"], selected["duration"], selected["thumbnails"][0]["url"].split("?")[0], selected["id"]

    async def download(self, link: str, mystic, video: Union[bool, str] = None,
                       videoid: Union[bool, str] = None,
                       songaudio: Union[bool, str] = None,
                       songvideo: Union[bool, str] = None,
                       format_id: Union[bool, str] = None,
                       title: Union[bool, str] = None) -> Union[Tuple[str, bool], None]:
        if videoid:
            vid_id = link
            link = self.base + link

        loop = asyncio.get_running_loop()

        # Asynchronous audio download using aiohttp
        async def audio_dl():
            # Pehle API try karenge TG link ke liye
            query = await self.title(link, videoid)
            streamtype = "audio"
            song_data = await fetch_song(query, streamtype)
            if song_data and "link" in song_data and not song_data.get("error"):
                tg_link = song_data["link"]
                print(f"API returned TG link: {tg_link}")
                if tg_link.startswith("https://t.me/"):
                    local_path = await download_tg_media(tg_link)
                    if local_path:
                        return local_path  # direct=False
                return tg_link  # fallback direct if not TG

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"https://yt.okflix.top/api/{vid_id}") as resp:
                        response = await resp.json()
                    if response.get('status') == 'success':
                        fpath = f"downloads/{vid_id}.mp3"
                        if os.path.exists(fpath):
                            return fpath
                        download_link = response.get('download_link')
                        async with session.get(download_link) as d_resp:
                            if d_resp.status == 200:
                                content = await d_resp.read()
                                with open(fpath, "wb") as f:
                                    f.write(content)
                                return fpath
            except Exception as e:
                print("Async audio_dl error:", e)
            # Fallback using yt_dlp
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "cookiefile": cookie_txt_file(),
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=False)
            return info.get('url')

        def video_dl():
            ydl_opts = {
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio[ext=m4a])",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "cookiefile": cookie_txt_file(),
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=False)
            out_path = os.path.join("downloads", f"{info['id']}.{info['ext']}")
            if os.path.exists(out_path):
                return out_path
            ydl.download([link])
            return out_path

        def song_video_dl():
            formats_opt = f"{format_id}+140"
            fpath = f"downloads/{title}"
            ydl_opts = {
                "format": formats_opt,
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "cookiefile": cookie_txt_file(),
                "prefer_ffmpeg": True,
                "merge_output_format": "mp4",
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])

        def song_audio_dl():
            fpath = f"downloads/{title}.%(ext)s"
            ydl_opts = {
                "format": format_id,
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "cookiefile": cookie_txt_file(),
                "prefer_ffmpeg": True,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])

        if songvideo:
            # API try karenge
            query = title
            streamtype = "video"
            song_data = await fetch_song(query, streamtype)
            if song_data and "link" in song_data and not song_data.get("error"):
                tg_link = song_data["link"]
                print(f"API returned TG link for songvideo: {tg_link}")
                if tg_link.startswith("https://t.me/"):
                    local_path = await download_tg_media(tg_link)
                    if local_path:
                        return local_path, False
                return tg_link, True  # fallback
            await loop.run_in_executor(None, song_video_dl)
            return f"downloads/{title}.mp4", False
        elif songaudio:
            # API try karenge
            query = title
            streamtype = "audio"
            song_data = await fetch_song(query, streamtype)
            if song_data and "link" in song_data and not song_data.get("error"):
                tg_link = song_data["link"]
                print(f"API returned TG link for songaudio: {tg_link}")
                if tg_link.startswith("https://t.me/"):
                    local_path = await download_tg_media(tg_link)
                    if local_path:
                        return local_path, False
                return tg_link, True  # fallback
            await loop.run_in_executor(None, song_audio_dl)
            return f"downloads/{title}.mp3", False
        elif video:
            # Pehle API try karenge TG link ke liye
            query = await self.title(link, videoid)
            streamtype = "video"
            song_data = await fetch_song(query, streamtype)
            if song_data and "link" in song_data and not song_data.get("error"):
                tg_link = song_data["link"]
                print(f"API returned TG link for video: {tg_link}")
                if tg_link.startswith("https://t.me/"):
                    local_path = await download_tg_media(tg_link)
                    if local_path:
                        downloaded_file = local_path
                        direct = False  # local file
                    else:
                        downloaded_file = tg_link
                        direct = True
                else:
                    downloaded_file = tg_link
                    direct = True
            else:
                if await is_on_off(1):
                    downloaded_file = await loop.run_in_executor(None, video_dl)
                    direct = True
                else:
                    # Fallback: try using video_dl directly
                    downloaded_file = await loop.run_in_executor(None, video_dl)
                    direct = True
        else:
            downloaded_file = await audio_dl()
            direct = True
        return downloaded_file, direct
