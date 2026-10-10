"""
Acid humour mode — a switch the user flips by voice or in ⚙.

    "Jarvis, ativa o modo ácido"        "Jarvis, modo sarcástico"
    "Jarvis, desativa o modo ácido"     "Jarvis, volta ao normal"
    "Jarvis, o modo ácido está ligado?"

ON: after each answer JARVIS adds one sharp, deadpan, sarcastic aside (never
on anything serious, never about the user's body, family, health or money).
OFF: the usual dry butler. The setting is saved in config/api_keys.json as
"acid_humor_enabled" and takes effect after an automatic reconnect that keeps
the conversation.
"""

PLUGIN = {
    "name": "humor_mode",
    "description": (
        "Turns the assistant's ACID HUMOUR mode on or off, or reports its state. "
        "Use for 'ativa/liga o modo ácido', 'modo sarcástico', 'seja mais ácido', "
        "'desativa/desliga o modo ácido', 'para com o sarcasmo', 'volta ao normal', "
        "'o modo ácido está ligado?'. After calling it, confirm in ONE short "
        "sentence; the new mood starts on the next reply."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "on | off | status"},
        },
        "required": ["action"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    from memory.config_manager import get_acid_humor_enabled, save_acid_humor_enabled
    action = (parameters.get("action") or "status").strip().lower()
    cur = get_acid_humor_enabled()

    if action in ("status", "state", "check"):
        return ("Acid humour is ON." if cur else "Acid humour is OFF.")

    want = action in ("on", "enable", "activate", "ativa", "liga", "true", "1")
    if want == cur:
        return ("Acid humour was already ON." if cur else "Acid humour was already OFF.")

    setter = getattr(player, "set_acid_humor", None) if player is not None else None
    if callable(setter):
        # The UI saves the flag, repaints the button and schedules the session
        # rebuild a few seconds out, so the spoken confirmation is not cut off.
        setter(want, 6.0)
    else:
        save_acid_humor_enabled(want)
    return ("Acid humour switched ON. The session reconnects in a few seconds (the "
            "conversation is kept); from the next reply on, add a sharp aside."
            if want else
            "Acid humour switched OFF. The session reconnects in a few seconds; be "
            "the plain dry butler from the next reply on.")
