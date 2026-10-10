"""
Startup-briefing sources — what JARVIS looks up before it greets you.

Two things, both chosen by the user and both configurable in
config/api_keys.json:

  * `briefing_youtube_source` — a YouTube video or channel URL. The channel it
    belongs to is checked for videos published TODAY (local date). Resolving a
    video link to its channel needs yt-dlp once; the channel id is then cached
    in the config so later launches only read the channel's public RSS feed,
    which needs no API key.
  * `briefing_news_topics` — the news queries, run through the same DDG news
    search the web_search action uses, with Gemini grounding as the backup.
    Defaults to AI-model launches (OpenAI/GPT, Anthropic/Claude) and LLM
    pricing, which is what the user asked the briefing to track.

Everything here is synchronous and bounded; main.py runs it in an executor.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, date
from pathlib import Path

import requests

from memory.config_manager import load_api_keys, CONFIG_FILE, ensure_config_dir
import json

DEFAULT_YOUTUBE_SOURCE = "https://youtu.be/x4-7MyeKysc"
DEFAULT_NEWS_TOPICS = [
    "OpenAI new GPT model launch",
    "Anthropic Claude new model release",
    "LLM API pricing cost per token",
]

_RSS = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
_ATOM = "{http://www.w3.org/2005/Atom}"
_YT = "{http://www.youtube.com/xml/schemas/2015}"
_CHANNEL_ID = re.compile(r"(UC[0-9A-Za-z_-]{21}[AQgw])")


# ── config ───────────────────────────────────────────────────────────────────

def _cfg() -> dict:
    return load_api_keys()


def _save_cfg(**fields) -> None:
    ensure_config_dir()
    data = _cfg()
    data.update(fields)
    try:
        CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"[Briefing] config write failed: {e}")


def youtube_source() -> str:
    return str(_cfg().get("briefing_youtube_source") or DEFAULT_YOUTUBE_SOURCE).strip()


def news_topics() -> list[str]:
    t = _cfg().get("briefing_news_topics")
    if isinstance(t, list) and all(isinstance(x, str) and x.strip() for x in t):
        return [x.strip() for x in t]
    return list(DEFAULT_NEWS_TOPICS)


# ── YouTube: the channel's videos published today ────────────────────────────

def resolve_channel(source: str) -> tuple[str, str]:
    """(channel_id, channel_name) for a video/channel URL. Cached per source."""
    cfg = _cfg()
    if cfg.get("briefing_youtube_cached_for") == source and cfg.get("briefing_youtube_channel_id"):
        return str(cfg["briefing_youtube_channel_id"]), str(cfg.get("briefing_youtube_channel_name") or "")

    m = _CHANNEL_ID.search(source)
    if m:
        cid, name = m.group(1), ""
    else:
        try:
            import yt_dlp
        except Exception:
            return "", ""
        opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                "noplaylist": True, "extract_flat": True}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(source, download=False) or {}
        except Exception as e:
            print(f"[Briefing] yt-dlp could not resolve {source}: {e}")
            return "", ""
        cid = str(info.get("channel_id") or info.get("uploader_id") or "")
        name = str(info.get("channel") or info.get("uploader") or "")
        if not _CHANNEL_ID.fullmatch(cid):
            return "", name

    _save_cfg(briefing_youtube_cached_for=source,
              briefing_youtube_channel_id=cid,
              briefing_youtube_channel_name=name)
    return cid, name


def parse_feed(xml_text: str, today: date | None = None) -> tuple[str, list[dict]]:
    """(channel_name, [videos published today]) from a channel's Atom feed."""
    today = today or date.today()
    root = ET.fromstring(xml_text)
    name = (root.findtext(f"{_ATOM}title") or "").strip()
    out = []
    for entry in root.findall(f"{_ATOM}entry"):
        pub = (entry.findtext(f"{_ATOM}published") or "").strip()
        try:
            when = datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone()
        except Exception:
            continue
        if when.date() != today:
            continue
        link = entry.find(f"{_ATOM}link")
        out.append({
            "title": (entry.findtext(f"{_ATOM}title") or "").strip(),
            "url": (link.get("href") if link is not None else "") or
                   f"https://www.youtube.com/watch?v={entry.findtext(f'{_YT}videoId') or ''}",
            "time": when.strftime("%H:%M"),
        })
    return name, out


def youtube_today(timeout: float = 6.0) -> dict:
    """{'channel': name, 'videos': [...], 'error': str}. Never raises."""
    source = youtube_source()
    if not source:
        return {"channel": "", "videos": [], "error": "no channel configured"}
    cid, name = resolve_channel(source)
    if not cid:
        return {"channel": name, "videos": [], "error": "could not resolve the channel"}
    try:
        r = requests.get(_RSS.format(cid=cid), timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0 (JARVIS briefing)"})
        r.raise_for_status()
        feed_name, vids = parse_feed(r.text)
    except Exception as e:
        return {"channel": name, "videos": [], "error": f"feed unavailable: {e}"}
    if feed_name and feed_name != name:
        _save_cfg(briefing_youtube_channel_name=feed_name)
        name = feed_name
    return {"channel": name or "the channel", "videos": vids, "error": ""}


# ── News: only the topics the user cares about ───────────────────────────────
# Google News publishes a public RSS feed per search, no key needed, and it
# answers in well under a second — unlike the DDG/Google scraping path, which
# times out on some networks. That feed is the primary source; the web_search
# backends (DDG, then Gemini grounding) are only tried when it yields nothing.

_GNEWS = ("https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}")
_RSS_DAYS = 7


def news_locale() -> tuple[str, str, str]:
    """(hl, gl, ceid) for Google News. Defaults to English/US, which is where
    model-launch and pricing news breaks first; set `briefing_news_locale` to
    e.g. "pt-BR" in the config for Brazilian sources instead."""
    loc = str(_cfg().get("briefing_news_locale") or "en-US").strip()
    if loc.lower().startswith("pt"):
        return "pt-BR", "BR", "BR:pt-419"
    return "en-US", "US", "US:en"


def parse_rss(xml_text: str, max_age_days: int = _RSS_DAYS) -> list[dict]:
    """Items of an RSS 2.0 feed, newest first, no older than `max_age_days`."""
    from email.utils import parsedate_to_datetime
    root = ET.fromstring(xml_text)
    out = []
    now = datetime.now().astimezone()
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        when = None
        try:
            when = parsedate_to_datetime(item.findtext("pubDate") or "").astimezone()
        except Exception:
            pass
        if when is not None and (now - when).days > max_age_days:
            continue
        src = item.find("source")
        out.append({
            "title": title,
            "url": (item.findtext("link") or "").strip(),
            "source": (src.text or "").strip() if src is not None else "",
            "when": when,
        })
    out.sort(key=lambda r: r["when"] or now, reverse=True)
    return out


def _gnews(topic: str, timeout: float = 6.0) -> list[dict]:
    from urllib.parse import quote_plus
    hl, gl, ceid = news_locale()
    url = _GNEWS.format(q=quote_plus(f"{topic} when:{_RSS_DAYS}d"), hl=hl, gl=gl, ceid=ceid)
    r = requests.get(url, timeout=timeout,
                     headers={"User-Agent": "Mozilla/5.0 (JARVIS briefing)"})
    r.raise_for_status()
    return parse_rss(r.text)


def ai_news(max_per_topic: int = 3) -> str:
    """Headlines for the configured topics, deduplicated. RSS first."""
    topics = news_topics()
    seen: set[str] = set()
    lines: list[str] = []

    def _add(r: dict) -> None:
        title = (r.get("title") or "").strip()
        key = title.lower()[:80]
        if not title or key in seen:
            return
        seen.add(key)
        src = f"  [{r['source']}]" if r.get("source") else ""
        when = r.get("when")
        day = f"  ({when.strftime('%d/%m')})" if when else ""
        lines.append(f"{len(seen)}. {title}{src}{day}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet'][:140]}")
        if r.get("url"):
            lines.append(f"   {r['url']}")

    # 1. Google News RSS — one request per topic, each bounded on its own.
    for topic in topics:
        try:
            for r in _gnews(topic)[:max_per_topic]:
                _add(r)
        except Exception as e:
            print(f"[Briefing] news RSS failed for {topic!r}: {e}")
    if lines:
        return "\n".join(["AI news — " + "; ".join(topics), ""] + lines).strip()

    # 2. The web_search backends, only if the feed gave nothing.
    try:
        from actions.web_search import _ddg_news, _gemini_search, _run_bounded
    except Exception:
        return "No news found for: " + "; ".join(topics)

    text = _run_bounded(
        lambda: _gemini_search("Latest news this week, numbered headlines only: "
                               + "; ".join(topics)),
        timeout=20.0, label="AI news (Gemini)")
    if text and len(text) > 60:
        return text

    def _ddg() -> None:
        for topic in topics:
            for r in _ddg_news(topic, max_results=max_per_topic):
                _add(r)
    _run_bounded(_ddg, timeout=8.0, label="AI news (DDG)")
    if lines:
        return "\n".join(["AI news — " + "; ".join(topics), ""] + lines).strip()
    return "No news found for: " + "; ".join(topics)


# ── What main.py calls ───────────────────────────────────────────────────────

def agenda_today() -> str:
    """Today's events and due tasks from the organizer plugin, or ""."""
    try:
        from plugins.organizer import briefing_summary
        return briefing_summary()
    except Exception as e:
        print(f"[Briefing] agenda unavailable: {e}")
        return ""


def rastracking_today() -> str:
    """Today's tracked revenue and support queue from the Rastracking plugin,
    or "" when it is not configured."""
    try:
        from plugins.rastracking import briefing_summary
        return briefing_summary()
    except Exception as e:
        print(f"[Briefing] Rastracking unavailable: {e}")
        return ""


def collect() -> dict:
    """All sources, run back to back inside one executor job."""
    agenda = agenda_today()
    tracking = rastracking_today()
    tracking_data = {}
    if tracking:
        try:
            from plugins.rastracking import last_briefing_data
            tracking_data = last_briefing_data() or {}
        except Exception:
            tracking_data = {}
    yt = youtube_today()
    news = ai_news()
    return {"agenda": agenda, "tracking": tracking, "tracking_data": tracking_data,
            "youtube": yt, "news": news}


def format_youtube(yt: dict) -> str:
    ch = yt.get("channel") or "the channel"
    if yt.get("error") and not yt.get("videos"):
        return f"{ch}: could not check for new videos ({yt['error']})."
    vids = yt.get("videos") or []
    if not vids:
        return f"{ch}: no new video today."
    lines = [f"{ch}: {len(vids)} new video{'s' if len(vids) != 1 else ''} today"]
    for v in vids:
        lines.append(f"- {v['time']}  {v['title']}")
        if v.get("url"):
            lines.append(f"  {v['url']}")
    return "\n".join(lines)
