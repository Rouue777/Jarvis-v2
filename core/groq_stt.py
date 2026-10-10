"""
Groq listening — the microphone goes to Whisper on Groq, and only the TEXT
reaches the Gemini Live session.

Why anyone would want this: Gemini Live bills audio input by the second, and
on a quiet day most of what it hears is room tone. Whisper on Groq is free up
to a generous daily limit and transcribes Portuguese very well. With this on,
the conversation stays on Gemini (voice out, tools, memory, everything), but
"what did the user say" is answered here, for free, and sent as text.

What changes for the user: speech is cut into utterances locally (start when
the room gets louder than its own floor, end after ~0.7 s of silence), so
JARVIS answers a beat after you stop talking rather than mid-sentence, and it
cannot be interrupted by voice while it speaks — ESC or the INTERRUPT button
still work.

Settings live in config/api_keys.json under plugin_config.groq, written by the
⚙ → PLUGIN SETTINGS → GROQ form that plugins/groq_listen.py declares:
    api_key   gsk_...            (https://console.groq.com/keys)
    model     whisper-large-v3-turbo | whisper-large-v3
    language  pt | en | ... | auto
"""
from __future__ import annotations

import io
import queue
import threading
import time
import wave
from typing import Callable

import numpy as np
import requests

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODELS = ("whisper-large-v3-turbo", "whisper-large-v3")
NAMESPACE = "groq"

# Segmenter, in 64 ms blocks at 16 kHz (CHUNK_SIZE 1024 in main.py).
_START_BLOCKS = 3        # ~190 ms above threshold opens an utterance
_END_BLOCKS = 11         # ~700 ms below closes it
_PREROLL = 8             # ~500 ms kept from before the start
_MIN_SPEECH = 6          # ~380 ms of voiced blocks, else dropped as noise
_MAX_BLOCKS = 390        # ~25 s hard cap, then sent as-is
_FLOOR_MIN = 0.003       # the quietest floor we believe
_THRESH_MIN = 0.008      # the quietest threshold we accept (≈ -42 dBFS)
_FLOOR_MULT = 2.5        # speech must be this many times the room floor
_LEVEL_LOG_S = 5.0       # console line with the mic level, to tune the above

# Whisper hallucinates on silence, and does so with a short list of
# favourites. Anything that is only one of these is dropped.
_NOISE = {
    "obrigado", "obrigado.", "obrigada", "obrigada.", "tchau", "tchau.", "legendas",
    "thank you", "thank you.", "thanks for watching", "thanks for watching.",
    "you", "bye", "bye.", "legendas pela comunidade amara.org",
    "legendas pela comunidade amara.org.", "amara.org",
}


def settings(get_plugin_config: Callable[[str], dict]) -> dict:
    cfg = get_plugin_config(NAMESPACE)
    model = str(cfg.get("model") or MODELS[0]).strip()
    lang = str(cfg.get("language") or "pt").strip().lower()
    return {
        "api_key": str(cfg.get("api_key") or "").strip(),
        "model": model if model in MODELS else MODELS[0],
        "language": "" if lang in ("auto", "") else lang,
    }


def transcribe(pcm16: bytes, api_key: str, model: str, language: str = "pt",
               sample_rate: int = 16000, timeout: float = 20.0,
               prompt: str = "") -> str:
    """One utterance of int16 mono PCM → text. Raises on HTTP/network errors.

    `prompt` is Whisper's vocabulary hint: a short text in the user's
    language that contains the words it should know how to spell — above all
    the assistant's name, which it otherwise renders as Gervis or Charles."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm16)
    data = {"model": model, "response_format": "json", "temperature": "0"}
    if language:
        data["language"] = language
    if prompt:
        data["prompt"] = prompt[:200]
    r = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": ("fala.wav", buf.getvalue(), "audio/wav")},
        data=data, timeout=timeout,
    )
    if r.status_code in (400, 404) and model != MODELS[1]:
        # The turbo model can be renamed or paused; the full model is the
        # fallback Ares uses too.
        return transcribe(pcm16, api_key, MODELS[1], language, sample_rate, timeout, prompt)
    r.raise_for_status()
    return str(r.json().get("text") or "").strip()


def test_connection(values: dict):
    """⚙ TEST CONNECTION: can this key list Groq's models?"""
    key = str(values.get("api_key") or "").strip()
    if not key:
        return False, "Enter a Groq API key (gsk_...) first."
    try:
        r = requests.get("https://api.groq.com/openai/v1/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=10)
        if r.status_code == 401:
            return False, "Groq rejected the key (401)."
        r.raise_for_status()
        ids = {m.get("id") for m in r.json().get("data", [])}
        have = [m for m in MODELS if m in ids]
        if not have:
            return True, "Connected, but no Whisper model is listed for this key."
        return True, "Connected. Whisper available: " + ", ".join(have)
    except Exception as e:
        return False, f"Connection failed: {e}"


class GroqListener:
    """Feed it microphone blocks; it calls `on_text(text)` per utterance.

    `feed()` runs on the audio callback thread and only does arithmetic and a
    queue push. Transcription happens on one worker thread, in order, so two
    quick sentences never arrive swapped.
    """

    def __init__(self, api_key: str, model: str, language: str,
                 on_text: Callable[[str], None],
                 on_status: Callable[[str], None] | None = None,
                 sample_rate: int = 16000, prompt: str = "") -> None:
        self._key, self._model, self._lang = api_key, model, language
        self.prompt = prompt
        self._on_text = on_text
        self._on_status = on_status or (lambda m: None)
        self._sr = sample_rate
        self._q: queue.Queue = queue.Queue()
        self._floor = 0.02
        self._active = False
        self._above = 0
        self._below = 0
        self._voiced = 0
        self._pre: list[bytes] = []
        self._seg: list[bytes] = []
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, name="groq-stt", daemon=True)
        self._worker.start()
        self.speaking = False          # True while an utterance is open
        self._peak = 0.0
        self._peak_t = time.monotonic()

    # ── audio thread ────────────────────────────────────────────────────────

    def feed(self, block) -> None:
        x = np.asarray(block, dtype=np.float32).ravel()
        if x.size == 0:
            return
        level = float(np.sqrt(np.mean(x * x))) / 32768.0
        raw = np.asarray(block, dtype=np.int16).tobytes()

        if not self._active:
            # Track the room while nobody speaks; follow drops quickly, rises slowly.
            if level < self._floor:
                self._floor = 0.90 * self._floor + 0.10 * level
            else:
                self._floor = 0.995 * self._floor + 0.005 * level
            self._floor = max(_FLOOR_MIN, self._floor)
        thresh = max(_THRESH_MIN, self._floor * _FLOOR_MULT)

        # A level line every few seconds on the console: the one number that
        # says whether the microphone is even reaching us, and how it compares
        # to the threshold, so sensitivity can be tuned from a log instead of
        # a guess.
        self._peak = max(self._peak, level)
        now = time.monotonic()
        if now - self._peak_t >= _LEVEL_LOG_S:
            print(f"[Groq] mic peak {self._peak:.4f}  floor {self._floor:.4f}  "
                  f"threshold {thresh:.4f}  {'SPEECH' if self._active else 'quiet'}")
            self._peak, self._peak_t = 0.0, now

        if not self._active:
            self._pre.append(raw)
            if len(self._pre) > _PREROLL:
                self._pre.pop(0)
            if level > thresh:
                self._above += 1
                if self._above >= _START_BLOCKS:
                    self._active = True
                    self.speaking = True
                    self._seg = list(self._pre)
                    self._pre = []
                    self._voiced = self._above
                    self._below = 0
            else:
                self._above = 0
            return

        self._seg.append(raw)
        if level > thresh:
            self._voiced += 1
            self._below = 0
        else:
            self._below += 1
        if self._below >= _END_BLOCKS or len(self._seg) >= _MAX_BLOCKS:
            self._close()

    def _close(self) -> None:
        seg, voiced = self._seg, self._voiced
        self._seg, self._active, self.speaking = [], False, False
        self._above = self._below = self._voiced = 0
        if voiced >= _MIN_SPEECH:
            pcm = b"".join(seg)
            self._on_status(f"Heard {len(pcm) / (2 * self._sr):.1f}s — transcribing on Groq…")
            self._q.put(pcm)
        else:
            print(f"[Groq] dropped a {voiced}-block blip as noise")

    def flush(self) -> None:
        """Push-to-talk released: whatever is open is an utterance."""
        if self._active:
            self._close()

    # ── worker thread ───────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                pcm = self._q.get(timeout=0.25)
            except queue.Empty:
                continue
            t0 = time.monotonic()
            try:
                text = transcribe(pcm, self._key, self._model, self._lang, self._sr,
                                  prompt=self.prompt)
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else "?"
                self._on_status(f"Groq transcription failed ({code}).")
                continue
            except Exception as e:
                self._on_status(f"Groq transcription failed: {e.__class__.__name__}.")
                continue
            clean = text.strip()
            if len(clean) < 2 or clean.lower() in _NOISE:
                self._on_status("Groq heard nothing recognisable in that.")
                continue
            secs = len(pcm) / (2 * self._sr)
            print(f"[Groq] {secs:.1f}s of speech → {len(clean)} chars in "
                  f"{time.monotonic() - t0:.2f}s")
            try:
                from core import usage as _usage
                _usage.note("groq", utterances=1, audio_s=secs)
            except Exception:
                pass
            self._on_text(clean)

    def stop(self) -> None:
        self._stop.set()
