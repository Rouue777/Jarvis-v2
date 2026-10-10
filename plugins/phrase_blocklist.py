"""
Blocked phrases — commands JARVIS must ignore even when they carry its name.

For a video, a stream or a recording in the room that keeps saying things
like "Jarvis, abre o navegador": once a phrase is on the list, any transcript
containing it is dropped on this machine before any model hears it.

    "Jarvis, bloqueia a frase abre o navegador"
    "Jarvis, quais frases estão bloqueadas?"
    "Jarvis, desbloqueia a frase abre o navegador"

The whole utterance must equal the phrase (case, accents, punctuation and
spaces ignored); a longer sentence containing it is NOT blocked. Stored in
config/api_keys.json as "blocked_phrases".
"""

PLUGIN = {
    "name": "phrase_blocklist",
    "description": (
        "Manages the list of blocked phrases: spoken commands JARVIS must ignore "
        "from now on even if they include its name — only when the WHOLE utterance "
        "equals the phrase (typically a sentence that keeps coming from a video "
        "or recording in the room). Actions: add a "
        "phrase, remove a phrase, list them. Use for 'bloqueia a frase/comando X', "
        "'ignora quando ouvir X', 'desbloqueia X', 'quais frases estão bloqueadas'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "add | remove | list"},
            "phrase": {"type": "STRING", "description": "The phrase, as the user said it (without the assistant's name is fine)"},
        },
        "required": ["action"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    from memory.config_manager import get_blocked_phrases, save_blocked_phrases
    action = (parameters.get("action") or "list").strip().lower()
    phrase = (parameters.get("phrase") or "").strip().strip('"\'«»')
    phrases = get_blocked_phrases()
    if action == "list":
        return ("No blocked phrases." if not phrases
                else f"{len(phrases)} blocked phrase(s): " + "; ".join(phrases))
    if not phrase:
        return "Which phrase?"
    if action == "add":
        if any(p.lower() == phrase.lower() for p in phrases):
            return f"'{phrase}' was already blocked."
        save_blocked_phrases(phrases + [phrase])
        return f"Blocked: '{phrase}'. I will ignore it from now on, even with my name."
    if action == "remove":
        keep = [p for p in phrases if phrase.lower() not in p.lower()]
        if len(keep) == len(phrases):
            return f"No blocked phrase matches '{phrase}'."
        save_blocked_phrases(keep)
        return f"Unblocked: '{phrase}'."
    return "Unknown action."
