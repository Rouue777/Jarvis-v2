"""
API usage meter — which service is doing the work right now, and how much it
has done since launch.

Two counters, one per API:

  gemini   audio_in_s   seconds of microphone streamed into the Live session
           audio_out_s  seconds of voice received from it
           turns        text turns sent (typed, Groq-transcribed, reminders…)
           calls        one-shot calls from core.gemini (search, vision, summaries)
  groq     utterances   sentences transcribed by Whisper on Groq
           audio_s      seconds of speech sent to it

`activity(api)` is a 0..1 value the HUD draws as the bar: 1.0 right after
the API was used, fading over a few seconds, so a glance at the panel shows
which one is actually being hit. Totals are also folded into a per-day record
in memory/usage.json so they survive a restart.

Every call here is a few arithmetic operations under a lock — safe from the
audio thread, the Groq worker and the asyncio loop alike.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import date
from pathlib import Path

_FILE = Path(__file__).resolve().parent.parent / "memory" / "usage.json"
_DECAY_S = 4.0          # seconds for the activity bar to fade to zero
_FLUSH_S = 15.0         # how often the day record is written

_lock = threading.RLock()
APIS = ("gemini", "groq", "brain")
_session: dict[str, dict[str, float]] = {a: {} for a in APIS}
_today: dict[str, dict[str, float]] = {a: {} for a in APIS}
_today_key = ""
_last: dict[str, float] = {a: 0.0 for a in APIS}
_dirty = False
_last_flush = 0.0


def _load_today() -> None:
    global _today, _today_key
    key = date.today().isoformat()
    if _today_key == key:
        return
    _today_key = key
    _today = {a: {} for a in APIS}
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
        rec = data.get(key) or {}
        for api in APIS:
            if isinstance(rec.get(api), dict):
                _today[api] = {k: float(v) for k, v in rec[api].items()}
    except Exception:
        pass


def note(api: str, **inc: float) -> None:
    """Add to the counters of `api` and mark it active now."""
    global _dirty
    api = api if api in APIS else "gemini"
    with _lock:
        _load_today()
        for k, v in inc.items():
            v = float(v)
            _session[api][k] = _session[api].get(k, 0.0) + v
            _today[api][k] = _today[api].get(k, 0.0) + v
        _last[api] = time.monotonic()
        _dirty = True
    _maybe_flush()


def activity(api: str) -> float:
    """1.0 when just used, fading to 0.0 over _DECAY_S."""
    with _lock:
        t = _last.get(api, 0.0)
    if not t:
        return 0.0
    return max(0.0, 1.0 - (time.monotonic() - t) / _DECAY_S)


def snapshot() -> dict:
    with _lock:
        _load_today()
        return {
            "session": {a: dict(c) for a, c in _session.items()},
            "today":   {a: dict(c) for a, c in _today.items()},
            "activity": {a: activity(a) for a in APIS},
        }


def _maybe_flush(force: bool = False) -> None:
    global _dirty, _last_flush
    now = time.monotonic()
    with _lock:
        if not _dirty or (not force and now - _last_flush < _FLUSH_S):
            return
        _dirty = False
        _last_flush = now
        payload = {_today_key: {a: dict(c) for a, c in _today.items()}}
    try:
        data = {}
        try:
            data = json.loads(_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            pass
        data.update(payload)
        # keep the last 60 days only
        for k in sorted(data)[:-60]:
            data.pop(k, None)
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[Usage] could not save usage.json: {e}")


def fmt_seconds(s: float) -> str:
    s = float(s or 0.0)
    if s < 60:
        return f"{s:.0f}s"
    if s < 3600:
        return f"{s / 60:.1f}m"
    return f"{s / 3600:.1f}h"


def summary(api: str, scope: str = "session") -> str:
    """Short text for the meter: what the API has done so far."""
    c = snapshot()[scope].get(api, {})
    if api == "groq":
        n = int(c.get("utterances", 0))
        return f"{n} fr · {fmt_seconds(c.get('audio_s', 0))}" if n else "--"
    if api == "brain":
        n = int(c.get("calls", 0))
        return f"{n} req · {fmt_seconds(c.get('tts_s', 0))}" if n else "--"
    audio = c.get("audio_in_s", 0) + c.get("audio_out_s", 0)
    req = int(c.get("turns", 0) + c.get("calls", 0))
    if not audio and not req:
        return "--"
    return f"{fmt_seconds(audio)} · {req} req"


def tooltip(api: str) -> str:
    s = snapshot()
    cs, ct = s["session"].get(api, {}), s["today"].get(api, {})
    if api == "groq":
        rows = [("Utterances transcribed", "utterances", None), ("Speech sent", "audio_s", fmt_seconds)]
    elif api == "brain":
        rows = [("Chat requests", "calls", None), ("Tool rounds", "tool_rounds", None),
                ("Characters written", "chars", None), ("Voice synthesised", "tts_s", fmt_seconds)]
    else:
        rows = [("Mic audio streamed in", "audio_in_s", fmt_seconds),
                ("Voice received", "audio_out_s", fmt_seconds),
                ("Text turns sent", "turns", None),
                ("One-shot calls (search, vision…)", "calls", None)]
    out = [f"{api.upper()} — this session / today"]
    for label, key, f in rows:
        a, b = cs.get(key, 0), ct.get(key, 0)
        out.append(f"{label}: {f(a) if f else int(a)} / {f(b) if f else int(b)}")
    return "\n".join(out)
