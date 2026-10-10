"""
Focus Protocol ("protocolo foco total").

    "Jarvis, protocolo foco total"   →  the focus playlist starts under the
    voice, JARVIS says "Modo foco total aberto. Suas tarefas do dia são: …"
    (from the organizer), and every N minutes reminds you to drink water.
    "Jarvis, encerra o foco"         →  music off, reminders off.

The music and the water timer live in main.py (JarvisLive.set_focus_mode);
this plugin is the voice command and the words. Settings: focus_music_url
and focus_water_minutes in config/api_keys.json (see core/music.py).
"""
from datetime import date

PLUGIN = {
    "name": "focus_mode",
    "description": (
        "The Focus Protocol ('protocolo foco total', 'modo foco', 'foco total'): "
        "start plays the user's focus playlist quietly under your voice, reads out "
        "today's tasks, and schedules periodic water reminders; stop ends the music "
        "and the reminders; status says whether it is on. After start, say EXACTLY "
        "the sentence the tool returns, nothing else."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "start | stop | status"},
        },
        "required": ["action"],
    },
}


def _uniq(items):
    seen, out = set(), []
    for x in items:
        k = x.strip().lower()
        if k and k not in seen:
            seen.add(k); out.append(x.strip())
    return out


def _trello_today() -> list[str]:
    """Cards due today on the default Trello board, or [] (never raises)."""
    try:
        from plugins import trello_control as tc
        from datetime import date as _d
        board = tc._board("")
        today = _d.today()
        out = []
        for c in tc._cards(board["id"]):
            d = tc._due_local(c)
            if d and not c.get("dueComplete") and d.date() == today:
                out.append(f"{c['name']} às {d.strftime('%H:%M')}")
        return out
    except Exception:
        return []


def _tasks_sentence() -> tuple[str, str]:
    """(spoken sentence, source note for the model)."""
    try:
        from plugins.organizer import _load, _overdue
        from datetime import datetime
        data = _load()
        today = date.today().isoformat()
        now = datetime.now()
        due = _uniq(t["title"] for t in data["tasks"] if not t.get("done") and t.get("date") == today)
        late = _uniq(t["title"] for t in data["tasks"] if _overdue(t, now) and t.get("date") != today)
        ev = _uniq(f"{e['title']} às {e['time']}" for e in
                   sorted((e for e in data["events"] if e["date"] == today), key=lambda e: e.get("time") or ""))
        trello = _uniq(_trello_today())
        items = due + ev
        parts = []
        if items:
            parts.append(", ".join(items[:8]))
        if trello:
            parts.append("no Trello: " + ", ".join(trello[:6]))
        if not parts:
            s = "nenhuma tarefa marcada para hoje"
        else:
            s = "; ".join(parts)
        if late:
            s += f"; e {len(late)} atrasada{'s' if len(late) != 1 else ''}: " + ", ".join(late[:4])
        note = ("Source: the organizer tool (tasks/events, editable with organizer actions "
                "remove_task, complete_task, dedupe)" + (" and the Trello default board" if trello else "")
                + ". If the user asks to change, remove or deduplicate them, use those tools.")
        return s, note
    except Exception as e:
        return f"(não consegui ler o organizador: {e})", "Source: organizer read failed."


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = (parameters.get("action") or "start").strip().lower()
    hook = getattr(player, "on_focus_mode", None) if player is not None else None
    if not callable(hook):
        return "Focus Protocol is not available in this build."
    try:
        state = hook(action)          # thread-safe; returns 'on' | 'off' | 'error: …'
    except Exception as e:
        return f"Focus Protocol failed: {e}"
    if action == "status":
        return "Focus Protocol is on." if state == "on" else "Focus Protocol is off."
    if action == "stop":
        return "Say exactly: 'Modo foco total encerrado, senhor.'"
    if str(state).startswith("error"):
        return f"Could not start the focus music ({state}). Say so briefly."
    sentence, note = _tasks_sentence()
    return ("Say exactly this, then nothing else: 'Modo foco total aberto. Suas tarefas "
            f"do dia são: {sentence}. Vou lembrá-lo de beber água.'\n[{note}]")
