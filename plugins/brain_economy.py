"""
Economy brain — settings form and a status tool.

This plugin exists for its PLUGIN_SETTINGS: it puts the chat provider, key,
model and the Edge TTS voice into ⚙ → PLUGIN SETTINGS → ECONOMY BRAIN, with a
TEST CONNECTION button. The brain itself lives in core/brain.py and is
switched on with the BRAIN button in the ⚙ drawer (or "brain_engine":
"economy" in config/api_keys.json). It needs Groq listening for the ears
(⚙ → PLUGIN SETTINGS → GROQ) and two packages for the voice:

    py -m pip install edge-tts miniaudio
"""
from core.brain import (DEFAULT_VOICE, EDGE_VOICES, FISH_MODELS, NAMESPACE, PROVIDERS,
                        TTS_ENGINES, test_connection, voice_label)

PLUGIN = {
    "name": "brain_status",
    "description": (
        "Reports which brain is answering right now: Gemini Live (native audio) "
        "or the economy brain (a chat model such as DeepSeek, Groq's Llama or a "
        "Gemini text model writing the replies, read aloud by Microsoft Edge TTS "
        "or a Fish Audio voice), and which "
        "provider and model are configured. Use when the user asks what model "
        "or AI is answering, or whether economy mode is on. Switching is done "
        "from the gear menu, not by this tool."
    ),
    "parameters": {"type": "OBJECT", "properties": {}, "required": []},
}

PLUGIN_SETTINGS = {
    "namespace": NAMESPACE,
    "title": "ECONOMY BRAIN (DeepSeek / Groq / Gemini text + Edge or Fish Audio voice)",
    "fields": [
        {"key": "provider", "label": "Provider", "type": "choice",
         "options": list(PROVIDERS), "default": "deepseek"},
        {"key": "api_key", "label": "API key", "type": "password",
         "placeholder": "sk-... (DeepSeek) or gsk_... (Groq)"},
        {"key": "model", "label": "Model (blank = provider default)", "type": "text",
         "placeholder": "deepseek-chat · llama-3.3-70b-versatile · deepseek/deepseek-chat:free"},
        {"key": "base_url", "label": "Base URL (custom provider only)", "type": "text",
         "placeholder": "http://localhost:11434/v1"},
        {"key": "tts_engine", "label": "Voice engine", "type": "choice",
         "options": list(TTS_ENGINES), "default": "edge"},
        {"key": "tts_voice", "label": "Voice (Edge TTS, free)", "type": "choice",
         "options": list(EDGE_VOICES), "default": DEFAULT_VOICE},
        {"key": "fish_api_key", "label": "Fish Audio API key", "type": "password",
         "placeholder": "fish.audio → API keys"},
        {"key": "fish_voice_id", "label": "Fish Audio voice (ID or page URL)", "type": "text",
         "default": "5566fffe8b8046bc85e576aa9813b9bd",
         "placeholder": "https://fish.audio/m/<id>  or the 32-character id"},
        {"key": "fish_model", "label": "Fish Audio model", "type": "choice",
         "options": list(FISH_MODELS), "default": FISH_MODELS[0]},
    ],
    "action": {"label": "TEST CONNECTION", "run": test_connection},
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    from memory.config_manager import get_brain_engine, get_plugin_config
    from core.brain import settings
    st = settings(get_plugin_config)
    if get_brain_engine() == "economy":
        return (f"The economy brain is answering: {st['model']} via {st['provider']}, "
                f"read aloud by {voice_label(st)}. Gemini Live is not in use.")
    return ("Gemini Live is answering natively. The economy brain is configured for "
            f"{st['model']} via {st['provider']}; switch with the BRAIN button in the gear menu.")
