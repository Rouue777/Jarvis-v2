"""
Economy brain — an OpenAI-compatible chat model writes the replies, a free
voice reads them, and Gemini is not involved at all.

The expensive part of Gemini Live is audio: every second in and every second
out is billed. This mode replaces the whole session with three cheap pieces:

    microphone → Whisper on Groq (core.groq_stt, free)
              → a chat model over /chat/completions (DeepSeek, Groq's free
                Llama, OpenRouter, or anything OpenAI-compatible)
              → Microsoft Edge TTS (free, no key) → the speakers

Everything else the assistant does stays: the persona prompt, memory, every
action and plugin (they are offered to the model as OpenAI tools), reminders,
the briefing, the avatar's lip-sync (the voice is played through the same
queue Gemini's audio used). What is lost: barge-in by voice, vision tools
(deepseek-chat cannot see), and Gemini's native hearing of tone.

Settings come from ⚙ → PLUGIN SETTINGS → ECONOMY BRAIN (plugins/brain_economy.py),
stored under plugin_config.brain in config/api_keys.json.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Callable

import requests

NAMESPACE = "brain"
TIMEOUT = 60
MAX_REPLY_CHARS = 12000        # a spoken reply never needs more; guards runaway streams

PRESETS = {
    "deepseek":   {"base_url": "https://api.deepseek.com/v1",
                   "model": "deepseek-chat",
                   "key_url": "https://platform.deepseek.com/api_keys"},
    "groq":       {"base_url": "https://api.groq.com/openai/v1",
                   "model": "llama-3.3-70b-versatile",
                   "key_url": "https://console.groq.com/keys"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1",
                   "model": "deepseek/deepseek-chat",
                   "key_url": "https://openrouter.ai/keys"},
    "gemini":     {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                   "model": "gemini-2.5-flash",
                   "key_url": "https://aistudio.google.com/app/apikey"},
    "custom":     {"base_url": "http://localhost:11434/v1", "model": "llama3.2", "key_url": ""},
}
PROVIDERS = tuple(PRESETS)
DEFAULT_VOICE = "pt-BR-AntonioNeural"
EDGE_VOICES = ("pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-BR-ThalitaNeural",
               "pt-PT-DuarteNeural", "en-GB-RyanNeural", "en-US-GuyNeural")

# Which service reads the replies aloud. "edge" is free (Microsoft); "fish" is
# Fish Audio (fish.audio), paid per character, any voice from its library or a
# clone of your own — this is how the assistant gets a specific voice.
TTS_ENGINES = ("edge", "fish")
FISH_BASE = "https://api.fish.audio"
FISH_MODELS = ("s2-pro", "s1")

# Tools that only make sense when the model can receive an image.
_VISION_TOOLS = {"screen_process", "close_camera"}


def settings(get_plugin_config: Callable[[str], dict]) -> dict:
    cfg = get_plugin_config(NAMESPACE)
    provider = str(cfg.get("provider") or "deepseek").strip().lower()
    preset = PRESETS.get(provider, PRESETS["deepseek"])
    base = str(cfg.get("base_url") or "").strip().rstrip("/") or preset["base_url"]
    model = str(cfg.get("model") or "").strip() or preset["model"]
    voice = str(cfg.get("tts_voice") or DEFAULT_VOICE).strip() or DEFAULT_VOICE
    engine = str(cfg.get("tts_engine") or "edge").strip().lower()
    fish_model = str(cfg.get("fish_model") or FISH_MODELS[0]).strip() or FISH_MODELS[0]
    return {
        "provider": provider if provider in PRESETS else "deepseek",
        "base_url": base, "model": model,
        "api_key": str(cfg.get("api_key") or "").strip(),
        "tts_voice": voice,
        "tts_engine": engine if engine in TTS_ENGINES else "edge",
        "fish_api_key": str(cfg.get("fish_api_key") or "").strip(),
        "fish_voice_id": fish_voice_id(cfg.get("fish_voice_id")),
        "fish_model": fish_model if fish_model in FISH_MODELS else FISH_MODELS[0],
    }


def fish_voice_id(raw) -> str:
    """Accept the bare model id or the voice's page URL
    (https://fish.audio/m/<id>/ ...) and return the id."""
    txt = str(raw or "").strip()
    if not txt:
        return ""
    m = re.search(r"[0-9a-fA-F]{32}", txt)
    if m:
        return m.group(0).lower()
    return txt.rstrip("/").split("/")[-1].split("?")[0]


def voice_label(st: dict) -> str:
    if st.get("tts_engine") == "fish":
        return f"Fish Audio {st.get('fish_model')} voice {st.get('fish_voice_id') or '(default)'}"
    return f"Edge TTS {st.get('tts_voice')}"


# ── tools: Gemini declarations → OpenAI tools ────────────────────────────────

def _lower_schema(node):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "type" and isinstance(v, str):
                out[k] = v.lower()
            elif k in ("properties", "items") or isinstance(v, (dict, list)):
                out[k] = _lower_schema(v)
            else:
                out[k] = v
        return out
    if isinstance(node, list):
        return [_lower_schema(x) for x in node]
    return node


def to_openai_tools(decls: list) -> list[dict]:
    out = []
    for d in decls:
        if not isinstance(d, dict):
            d = {"name": getattr(d, "name", ""), "description": getattr(d, "description", ""),
                 "parameters": getattr(d, "parameters", None)}
        name = d.get("name")
        if not name or name in _VISION_TOOLS:
            continue
        params = _lower_schema(d.get("parameters") or {"type": "object", "properties": {}})
        params.setdefault("type", "object")
        params.setdefault("properties", {})
        out.append({"type": "function", "function": {
            "name": name, "description": (d.get("description") or "")[:1024],
            "parameters": params}})
    return out


# ── chat ─────────────────────────────────────────────────────────────────────

# A sentence ends at punctuation FOLLOWED BY WHITESPACE. Matching the end of
# the buffer too cut "R$ 381.000,00" into "R$ 381." and "000,00" whenever a
# streamed chunk happened to stop on the dot — the voice then read two
# nonsense numbers. The tail is flushed when the stream ends anyway.
_SENT_END = re.compile(r"(?<=[.!?…])\s+|\n+")


class ContextTooLong(RuntimeError):
    """The provider refused the request because the conversation sent is
    bigger than the model's window. The caller drops the history and retries."""


def chat_stream(messages: list, tools: list | None, st: dict,
                on_sentence: Callable[[str], None],
                should_stop: Callable[[], bool] = lambda: False) -> tuple[str, list[dict]]:
    """Stream one reply. Calls on_sentence() for each finished sentence as it
    arrives; returns (full_content, tool_calls) where tool_calls are
    [{"id", "name", "arguments": dict}]. Raises on HTTP errors."""
    payload = {"model": st["model"], "messages": messages, "stream": True,
               "max_tokens": 600, "temperature": 0.6}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {"Content-Type": "application/json"}
    if st["api_key"]:
        headers["Authorization"] = f"Bearer {st['api_key']}"
    if st["provider"] == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/FatihMakes/Mark-LV"
        headers["X-Title"] = "MARK LV"

    content, buf = "", ""
    frags: dict[int, dict] = {}
    with requests.post(f"{st['base_url']}/chat/completions", json=payload,
                       headers=headers, timeout=TIMEOUT, stream=True) as r:
        if r.status_code >= 400:
            body = r.text[:300]
            low = body.lower()
            if r.status_code == 400 and ("context length" in low or "maximum context" in low
                                         or "too many tokens" in low or "token limit" in low):
                raise ContextTooLong(f"{r.status_code}: {body}")
            raise requests.HTTPError(f"{r.status_code}: {body}", response=r)
        for raw in r.iter_lines():
            if should_stop():
                break
            if not raw:
                continue
            line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content") or ""
            if piece:
                # Some OpenAI-compatible gateways stream the WHOLE text so far
                # in every chunk instead of the new bit. Appending that would
                # square the reply; keep only what is new.
                if content and len(piece) > len(content) and piece.startswith(content):
                    piece = piece[len(content):]
                if len(content) + len(piece) > MAX_REPLY_CHARS:
                    piece = piece[: max(0, MAX_REPLY_CHARS - len(content))]
                    if not piece:
                        break
                content += piece
                buf += piece
                # hand over finished sentences, keep the open tail
                parts = _SENT_END.split(buf)
                if len(parts) > 1:
                    for s in parts[:-1]:
                        s = s.strip()
                        if s:
                            on_sentence(s)
                    buf = parts[-1]
            for tc in delta.get("tool_calls") or []:
                i = int(tc.get("index", 0))
                f = frags.setdefault(i, {"id": "", "name": "", "arguments": ""})
                if tc.get("id"):
                    f["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    f["name"] += fn["name"]
                if fn.get("arguments"):
                    f["arguments"] += fn["arguments"]
    tail = buf.strip()
    if tail and not should_stop():
        on_sentence(tail)
    calls = []
    for i in sorted(frags):
        f = frags[i]
        try:
            args = json.loads(f["arguments"] or "{}")
        except json.JSONDecodeError:
            args = {}
        if f["name"]:
            calls.append({"id": f["id"] or f"call_{i}", "name": f["name"],
                          "arguments": args if isinstance(args, dict) else {}})
    return content, calls


# ── voice: Microsoft Edge TTS → 24 kHz int16 PCM ─────────────────────────────

def tts_pcm24k(text: str, voice: str) -> bytes:
    """Synthesise `text` and return mono int16 PCM at 24 kHz, the rate the
    playback queue already uses. Needs the `edge-tts` and `miniaudio` packages."""
    import edge_tts
    import miniaudio

    async def _synth() -> bytes:
        comm = edge_tts.Communicate(text, voice)
        buf = bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        return bytes(buf)

    loop = asyncio.new_event_loop()
    try:
        mp3 = loop.run_until_complete(_synth())
    finally:
        loop.close()
    if not mp3:
        return b""
    dec = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16,
                           nchannels=1, sample_rate=24000)
    return bytes(dec.samples)


# ── voice: Fish Audio → 24 kHz int16 PCM ─────────────────────────────────────

class FishCreditsExhausted(RuntimeError):
    """Fish Audio refused to synthesise because the account has no credits
    left. The caller falls back to another voice and switches brains."""


def _fish_out_of_credits(r) -> bool:
    if r.status_code == 402:
        return True
    if r.status_code in (400, 403):
        t = (r.text or "").lower()
        return any(w in t for w in ("credit", "balance", "insufficient", "quota"))
    return False


def tts_fish_pcm24k(text: str, st: dict) -> bytes:
    """Synthesise `text` with Fish Audio (POST /v1/tts) in the configured voice
    and return mono int16 PCM at 24 kHz. The audio is requested as WAV and
    decoded with miniaudio, so the playback path is the same as Edge's.

    The official SDK sends the body as MessagePack; the API also takes JSON.
    JSON is used here so no extra package is needed."""
    import miniaudio

    key = st.get("fish_api_key") or ""
    if not key:
        raise RuntimeError("Fish Audio API key missing (⚙ → PLUGIN SETTINGS → ECONOMY BRAIN)")
    body = {
        "text": text,
        "format": "wav",
        "sample_rate": 24000,
        "latency": "balanced",
        "chunk_length": 200,
        "normalize": True,
        # Low sampling temperature: the default (0.7) let a cloned voice
        # improvise on long spelled-out numbers, sometimes drifting into
        # another language. Pronunciation is not a place for creativity.
        "temperature": 0.3,
        "top_p": 0.6,
        "repetition_penalty": 1.2,
    }
    if st.get("fish_voice_id"):
        body["reference_id"] = st["fish_voice_id"]
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "model": st.get("fish_model") or FISH_MODELS[0],
    }
    r = requests.post(f"{FISH_BASE}/v1/tts", headers=headers, json=body, timeout=TIMEOUT)
    if r.status_code in (415, 422):
        # Server insisting on MessagePack (the SDK's encoding): retry that way
        # when the package is present.
        try:
            import ormsgpack
            headers["Content-Type"] = "application/msgpack"
            r = requests.post(f"{FISH_BASE}/v1/tts", headers=headers,
                              data=ormsgpack.packb(body), timeout=TIMEOUT)
        except ImportError:
            raise RuntimeError(f"Fish Audio refused the JSON request ({r.status_code}): "
                               f"{r.text[:120]} — run: py -m pip install ormsgpack")
    if _fish_out_of_credits(r):
        raise FishCreditsExhausted(f"Fish Audio: no credits left on the account ({r.status_code})")
    if r.status_code == 401:
        raise RuntimeError("Fish Audio rejected the API key (401)")
    if r.status_code == 404 and st.get("fish_voice_id"):
        raise RuntimeError(f"Fish Audio: voice {st['fish_voice_id']} not found (404)")
    r.raise_for_status()
    data = r.content
    if not data:
        return b""
    dec = miniaudio.decode(data, output_format=miniaudio.SampleFormat.SIGNED16,
                           nchannels=1, sample_rate=24000)
    return bytes(dec.samples)


_FISH_SPLIT = re.compile(r"(?<=[,;:])\s+")
_FISH_GAP = b"\x00" * int(24000 * 0.22) * 2      # 220 ms of silence between pieces


def _fish_pieces(text: str) -> list[str]:
    """A long sentence with figures goes to Fish in short pieces, split at
    commas — each piece is a thing the voice can say in one breath, and the
    model never has to hold "trezentos e oitenta e um mil, novecentos e
    oitenta e nove reais em 896 vendas, de 170 clientes" in its head at once.
    Short sentences go whole."""
    text = (text or "").strip()
    if len(text) < 70 or not any(ch.isdigit() for ch in text) and " mil" not in text and " reais" not in text:
        return [text] if text else []
    pieces, cur = [], ""
    for part in _FISH_SPLIT.split(text):
        if cur and len(cur) + len(part) < 60:
            cur = f"{cur} {part}"
        else:
            if cur:
                pieces.append(cur)
            cur = part
    if cur:
        pieces.append(cur)
    return pieces


def synth_pcm24k(text: str, st: dict) -> bytes:
    """One sentence → 24 kHz PCM with whichever voice engine is configured."""
    if st.get("tts_engine") == "fish":
        pieces = _fish_pieces(text)
        if len(pieces) <= 1:
            return tts_fish_pcm24k(text, st)
        out = bytearray()
        for i, piece in enumerate(pieces):
            if i:
                out.extend(_FISH_GAP)
            out.extend(tts_fish_pcm24k(piece, st))
        return bytes(out)
    return tts_pcm24k(text, st["tts_voice"])


def fish_balance(key: str) -> float | None:
    """Current API credit balance, or None when it cannot be read."""
    try:
        r = requests.get(f"{FISH_BASE}/wallet/self/api-credit",
                         headers={"Authorization": f"Bearer {key}"}, timeout=15)
        if r.ok:
            c = r.json().get("credit")
            return float(c) if c is not None else None
    except Exception:
        pass
    return None


def fish_credits(key: str) -> str:
    """Best-effort balance line for TEST CONNECTION ("" if unavailable)."""
    b = fish_balance(key)
    return f"credits: {b:.2f}" if b is not None else ""


def missing_packages(st: dict | None = None) -> list[str]:
    out = []
    need = [("miniaudio", "miniaudio")]
    if not st or st.get("tts_engine") != "fish":
        need.insert(0, ("edge_tts", "edge-tts"))
    for mod, pkg in need:
        try:
            __import__(mod)
        except Exception:
            out.append(pkg)
    return out


def test_connection(values: dict):
    """⚙ TEST CONNECTION: key accepted, model listed, voice packages present."""
    fake = dict(values)
    st = settings(lambda ns: fake)
    notes = []
    missing = missing_packages(st)
    if missing:
        notes.append("voice packages missing — run: py -m pip install " + " ".join(missing))
    if st["tts_engine"] == "fish":
        if not st["fish_api_key"]:
            return False, "Voice is Fish Audio but its API key is empty (fish.audio → API keys)."
        if not missing:
            try:
                pcm = tts_fish_pcm24k("Teste de voz.", st)
                secs = len(pcm) / 48000.0
                bal = fish_credits(st["fish_api_key"])
                notes.append(f"Fish Audio voice OK ({secs:.1f} s of audio"
                             + (f", {bal}" if bal else "") + ")")
            except Exception as e:
                return False, f"Fish Audio voice failed: {e}"
    if not st["api_key"] and st["provider"] != "custom":
        return False, "Enter the API key first. " + " ".join(notes)
    headers = {"Authorization": f"Bearer {st['api_key']}"} if st["api_key"] else {}
    try:
        r = requests.get(f"{st['base_url']}/models", headers=headers, timeout=15)
        if r.status_code == 401:
            return False, "The provider rejected the key (401)."
        r.raise_for_status()
        ids = {m.get("id") for m in (r.json().get("data") or [])}
        if ids and st["model"] not in ids:
            notes.append(f"model '{st['model']}' not in the provider's list — check the name")
    except Exception as e:
        return False, f"Connection failed: {e}"

    # The list says the key works; only a real reply says the MODEL works for
    # this key (credits, access, tool support). One tiny request, with a tool
    # attached, because that is exactly what the assistant will send.
    probe_tool = [{"type": "function", "function": {
        "name": "noop", "description": "does nothing",
        "parameters": {"type": "object", "properties": {}}}}]
    try:
        got: list[str] = []
        content, calls = chat_stream(
            [{"role": "system", "content": "Reply with the single word OK."},
             {"role": "user", "content": "Ready?"}],
            probe_tool, st, got.append)
        reply = (content or " ".join(got)).strip()[:40] or ("(tool call)" if calls else "(empty)")
        ok_line = (f"Connected to {st['provider']}, model {st['model']} answered: "
                   f"\"{reply}\".")
        return (not missing), ok_line + (" " + "; ".join(notes) if notes else "")
    except requests.HTTPError as e:
        body = ""
        try:
            body = e.response.text[:200] if e.response is not None else str(e)[:200]
        except Exception:
            body = str(e)[:200]
        return False, (f"The key works but model {st['model']} refused: {body}. "
                       "On OpenRouter a 402 means no credits — add some or use a ':free' "
                       "model such as deepseek/deepseek-chat:free; a 404 means the model "
                       "id is wrong.")
    except Exception as e:
        return False, f"Model test failed: {e}"
