"""
Background music — a YouTube track or mix played under JARVIS's voice.

Two uses, both configured in config/api_keys.json:

    "morning_music_url": the track that opens the first launch of the day.
        The greeting waits until the music has reached MORNING_SYNC_MS, so the
        voice lands on the music's opening rather than over a silent intro.
    "focus_music_url":   the track the Focus Protocol builds a playlist from
        (YouTube's own mix for that track, so it keeps going).
    "music_volume":      0..1, the level while JARVIS is quiet (default 0.35);
        while it speaks the level drops by MUSIC_DUCK so the voice stays on top.
    "focus_water_minutes": how often the Focus Protocol reminds you to drink
        water (default 30).

Streams are resolved with yt-dlp (already a dependency) and played by the HUD's
QtMultimedia player, so no new package is needed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_URL = "https://www.youtube.com/watch?v=XgWUDbYfNe4"
MORNING_SYNC_MS = 5000        # the greeting starts when the music is here
MUSIC_DUCK = 0.40             # volume factor while JARVIS speaks
DEFAULT_VOLUME = 0.35
DEFAULT_WATER_MIN = 30

_CFG = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
_VID = re.compile(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})")


def _cfg() -> dict:
    try:
        data = json.loads(_CFG.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def morning_url() -> str:
    v = _cfg().get("morning_music_url", DEFAULT_URL)
    return str(v or "").strip()          # "" disables the morning music


def focus_url() -> str:
    return str(_cfg().get("focus_music_url") or DEFAULT_URL).strip()


def volume() -> float:
    try:
        return max(0.0, min(1.0, float(_cfg().get("music_volume", DEFAULT_VOLUME))))
    except Exception:
        return DEFAULT_VOLUME


def water_minutes() -> int:
    try:
        return max(5, int(_cfg().get("focus_water_minutes", DEFAULT_WATER_MIN)))
    except Exception:
        return DEFAULT_WATER_MIN


def video_id(url: str) -> str:
    m = _VID.search(url or "")
    return m.group(1) if m else ""


def mix_url(url: str) -> str:
    """YouTube's auto-generated mix for a track: an endless playlist seeded by it."""
    vid = video_id(url)
    return f"https://www.youtube.com/watch?v={vid}&list=RD{vid}" if vid else url


CACHE_DIR = Path(__file__).resolve().parent.parent / "memory" / "music_cache"


def cached_file(url: str) -> str:
    """Path of an already-downloaded track for this video, or ""."""
    vid = video_id(url)
    if not vid or not CACHE_DIR.exists():
        return ""
    for f in CACHE_DIR.glob(f"{vid}.*"):
        if f.suffix.lower() in (".m4a", ".mp3", ".webm", ".opus", ".ogg") and f.stat().st_size > 50_000:
            return str(f)
    return ""


def download_audio(url: str) -> tuple[str, str]:
    """Download the track's audio once into memory/music_cache and return
    (local_path, title). A local file is the one source QtMultimedia never
    refuses; YouTube's streaming URLs sometimes do ("Could not open file")."""
    import yt_dlp
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    have = cached_file(url)
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": str(CACHE_DIR / "%(id)s.%(ext)s"),
            "skip_download": bool(have)}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=not have)
    if info and info.get("entries"):
        info = info["entries"][0]
    title = str((info or {}).get("title") or "")
    path = have or cached_file(url)
    if not path and info:
        for key in ("filepath", "_filename"):
            cand = (info.get("requested_downloads") or [{}])[0].get(key) if info.get("requested_downloads") else info.get(key)
            if cand and Path(cand).exists():
                path = str(cand)
                break
    if not path:
        raise RuntimeError("download produced no file")
    return path, title


def resolve_audio(url: str) -> tuple[str, str]:
    """(audio_stream_url, title) for one video. Raises with a reason."""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "noplaylist": True, "format": "bestaudio[ext=m4a]/bestaudio/best"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info and info.get("entries"):
        info = info["entries"][0]
    if not info:
        raise RuntimeError("nothing found")
    stream = info.get("url")
    if not stream:
        fmts = [f for f in (info.get("formats") or []) if f.get("url")
                and f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")]
        fmts.sort(key=lambda f: (f.get("language_preference") or 0, f.get("abr") or f.get("tbr") or 0))
        stream = fmts[-1]["url"] if fmts else ""
    if not stream:
        raise RuntimeError("no audio stream offered")
    return stream, str(info.get("title") or "")


def resolve_playlist(url: str, limit: int = 25) -> list[tuple[str, str]]:
    """[(video_url, title)] for the mix seeded by `url`; the track itself
    first. Falls back to the single track when the mix cannot be listed."""
    import yt_dlp
    seed = video_id(url)
    out: list[tuple[str, str]] = []
    try:
        opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                "extract_flat": True, "playlistend": limit}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(mix_url(url), download=False) or {}
        for e in info.get("entries") or []:
            vid = e.get("id") or video_id(e.get("url") or "")
            if vid:
                out.append((f"https://www.youtube.com/watch?v={vid}", str(e.get("title") or "")))
    except Exception as ex:
        print(f"[Music] mix unavailable ({ex}); looping the track instead")
    if seed:
        out = [(f"https://www.youtube.com/watch?v={seed}", "")] + [o for o in out if video_id(o[0]) != seed]
    return out or [(url, "")]
