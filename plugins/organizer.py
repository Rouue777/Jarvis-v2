"""
Organizer — tasks, calendar, lists and notes, kept on this machine.

What the Ares assistant has in its Tarefas / Calendário / Listas tabs, done
the JARVIS way: one tool the model drives by voice, one JSON file in memory/,
and the HUD's content panel as the display. Nothing leaves the computer.

    "cria uma tarefa pagar a conta de luz para sexta"
    "marca dentista sexta às 15h e me avisa 30 minutos antes"
    "adiciona leite na lista de compras"   "o que tenho amanhã?"
    "anota que a senha do wifi é casa123"  "desfaz"

Events and tasks with a time are announced aloud when due (main.py polls
due_now() the way it does reminders), and the startup briefing opens with
today's agenda. Names are matched case- and accent-insensitively, by prefix
or substring, like the Trello plugin. The last change can be undone.
"""
from __future__ import annotations

import copy
import json
import re
import threading
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

_FILE = Path(__file__).resolve().parent.parent / "memory" / "organizer.json"
_lock = threading.RLock()
_undo: list[dict] = []          # previous snapshots, newest last (max 10)

_EMPTY = {"tasks": [], "events": [], "lists": {}, "notes": [], "fired": []}
_PRIOS = ("baixa", "media", "alta")

PLUGIN = {
    "name": "organizer",
    "description": (
        "The user's local organizer: tasks (with due date and priority), calendar "
        "events (with a spoken reminder N minutes before), named lists (shopping, "
        "packing…), quick notes, today's/tomorrow's agenda, and undo. Use it for "
        "'create a task', 'what do I have tomorrow', 'add X to the shopping list', "
        "'note that…', 'mark the dentist Friday at 3', 'what's overdue'. Dates and "
        "times must be ISO (YYYY-MM-DD, HH:MM) worked out from the current date in "
        "your context. Not for Trello boards (trello_control) and not for a plain "
        "timed alert with no task behind it (reminder)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": (
                "One of: add_task, complete_task, reopen_task, remove_task, list_tasks, "
                "add_event, remove_event, list_events, agenda, "
                "add_item, check_item, remove_item, show_list, clear_list, remove_list, lists, "
                "add_note, list_notes, remove_note, dedupe, undo. "
                "dedupe removes duplicated tasks/events (same title and day), keeping one.")},
            "title": {"type": "STRING", "description": "Task / event / note text, or the list item"},
            "list": {"type": "STRING", "description": "List name (default 'compras' for items)"},
            "date": {"type": "STRING", "description": "YYYY-MM-DD (task due, event day, agenda day)"},
            "time": {"type": "STRING", "description": "HH:MM, 24h (task due time, event start)"},
            "priority": {"type": "STRING", "description": "baixa | media | alta (tasks)"},
            "remind_minutes": {"type": "INTEGER", "description": "Event: speak a reminder this many minutes before (default 10)"},
            "filter": {"type": "STRING", "description": "list_tasks: open (default) | overdue | today | done | all; list_events: today | tomorrow | week (default)"},
            "note": {"type": "STRING", "description": "Extra description for a task or event"},
        },
        "required": ["action"],
    },
}


# ── storage ──────────────────────────────────────────────────────────────────

def _load() -> dict:
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for k, v in _EMPTY.items():
                data.setdefault(k, copy.deepcopy(v))
            return data
    except Exception:
        pass
    return copy.deepcopy(_EMPTY)


def _save(data: dict) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _mutate(fn):
    """Run fn(data) under the lock with an undo snapshot; persist; return fn's text."""
    with _lock:
        data = _load()
        before = copy.deepcopy(data)
        out = fn(data)
        _undo.append(before)
        del _undo[:-10]
        _save(data)
        return out


# ── helpers ──────────────────────────────────────────────────────────────────

def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch)).strip()


def _pick(items: list, name: str, key: str, what: str):
    q = _fold(name)
    if not q:
        raise ValueError(f"Which {what}?" + (" Options: " + ", ".join(i[key] for i in items[:8]) if items else ""))
    for test in (lambda n: n == q, lambda n: n.startswith(q), lambda n: q in n):
        hits = [i for i in items if test(_fold(i[key]))]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ValueError(f"Several {what}s match '{name}': " + ", ".join(h[key] for h in hits[:6]))
    raise ValueError(f"No {what} called '{name}'." + (" Options: " + ", ".join(i[key] for i in items[:8]) if items else ""))


def _parse_date(s: str) -> date:
    s = (s or "").strip().lower()
    today = date.today()
    if s in ("", "hoje", "today"):
        return today
    if s in ("amanha", "amanhã", "tomorrow"):
        return today + timedelta(days=1)
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Date must be YYYY-MM-DD.")


def _parse_time(s: str) -> str | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%H:%M", "%H:%M:%S", "%Hh%M", "%Hh"):
        try:
            return datetime.strptime(s, fmt).strftime("%H:%M")
        except ValueError:
            continue
    raise ValueError("Time must be HH:MM (24h).")


def _when(d: str | None, t: str | None) -> datetime | None:
    if not d:
        return None
    return datetime.strptime(f"{d} {t or '09:00'}", "%Y-%m-%d %H:%M")


def _fmt_when(d: str | None, t: str | None) -> str:
    if not d:
        return ""
    dd = datetime.strptime(d, "%Y-%m-%d").date()
    today = date.today()
    label = ("hoje" if dd == today else "amanhã" if dd == today + timedelta(days=1)
             else dd.strftime("%d/%m"))
    return label + (f" {t}" if t else "")


def _fmt_task(t: dict) -> str:
    bits = [t["title"]]
    if t.get("date"):
        bits.append(_fmt_when(t["date"], t.get("time")))
    if t.get("priority") == "alta":
        bits.append("alta")
    if t.get("done"):
        bits.append("✓")
    return " — ".join(bits)


def _fmt_event(e: dict) -> str:
    return f"{_fmt_when(e['date'], e.get('time'))} {e['title']}" + (f" ({e['note']})" if e.get("note") else "")


def _overdue(t: dict, now: datetime) -> bool:
    w = _when(t.get("date"), t.get("time") or "23:59")
    return bool(w and not t.get("done") and w < now)


# ── read-only views used by the briefing and the ⚙ AGENDA button ─────────────

def agenda_text(day: date | None = None) -> str:
    """Plain text: events of the day, tasks due that day, overdue tasks."""
    day = day or date.today()
    with _lock:
        data = _load()
    now = datetime.now()
    ds = day.isoformat()
    label = "Hoje" if day == date.today() else ("Amanhã" if day == date.today() + timedelta(days=1)
                                                  else day.strftime("%d/%m"))
    ev = sorted((e for e in data["events"] if e["date"] == ds), key=lambda e: e.get("time") or "")
    due = [t for t in data["tasks"] if not t.get("done") and t.get("date") == ds]
    late = [t for t in data["tasks"] if _overdue(t, now) and t.get("date") != ds] if day == date.today() else []
    lines = [f"{label} — {len(ev)} compromisso(s), {len(due)} tarefa(s)"]
    for e in ev:
        lines.append(f"  • {(e.get('time') or '--:--')}  {e['title']}")
    for t in due:
        lines.append(f"  ☐ {t['title']}" + (f" ({t['time']})" if t.get("time") else ""))
    if late:
        lines.append(f"  Atrasadas: " + "; ".join(t["title"] for t in late[:6]))
    open_n = sum(1 for t in data["tasks"] if not t.get("done"))
    lines.append(f"  Tarefas abertas no total: {open_n}")
    return "\n".join(lines)


def briefing_summary() -> str:
    """One compact block for the startup briefing (empty when nothing today)."""
    with _lock:
        data = _load()
    now = datetime.now()
    ds = date.today().isoformat()
    ev = sorted((e for e in data["events"] if e["date"] == ds), key=lambda e: e.get("time") or "")
    due = [t for t in data["tasks"] if not t.get("done") and t.get("date") == ds]
    late = [t for t in data["tasks"] if _overdue(t, now) and t.get("date") != ds]
    if not (ev or due or late):
        return ""
    out = []
    if ev:
        out.append("Events today: " + "; ".join(f"{e.get('time') or ''} {e['title']}".strip() for e in ev))
    if due:
        out.append("Tasks due today: " + "; ".join(t["title"] for t in due))
    if late:
        out.append(f"Overdue tasks ({len(late)}): " + "; ".join(t["title"] for t in late[:5]))
    return "\n".join(out)


def due_now(grace_seconds: int = 180) -> list[dict]:
    """Pop items whose spoken moment has arrived: an event `remind_minutes`
    before its start (and again at the start), a task at its due time.
    Returns [{'text': ..., 'kind': 'event'|'task'}]. Each fires once."""
    now = datetime.now()
    out = []
    with _lock:
        data = _load()
        fired = set(data.get("fired") or [])
        changed = False
        for e in data["events"]:
            start = _when(e["date"], e.get("time") or "09:00")
            lead = int(e.get("remind_minutes") or 0)
            for tag, at, text in (("lead", start - timedelta(minutes=lead),
                                   f"em {lead} minuto{'s' if lead != 1 else ''}: {e['title']}" if lead else ""),
                                  ("start", start, f"agora: {e['title']}")):
                if not text:
                    continue
                key = f"{e['id']}:{tag}"
                if key in fired:
                    continue
                age = (now - at).total_seconds()
                if 0 <= age <= grace_seconds:
                    out.append({"text": text, "kind": "event"})
                    fired.add(key); changed = True
                elif age > grace_seconds:
                    fired.add(key); changed = True          # missed while off — never nag
        for t in data["tasks"]:
            if t.get("done") or not t.get("date") or not t.get("time"):
                continue
            key = f"{t['id']}:due"
            if key in fired:
                continue
            age = (now - _when(t["date"], t["time"])).total_seconds()
            if 0 <= age <= grace_seconds:
                out.append({"text": f"tarefa: {t['title']}", "kind": "task"})
                fired.add(key); changed = True
            elif age > grace_seconds:
                fired.add(key); changed = True
        if changed:
            live = {e["id"] for e in data["events"]} | {t["id"] for t in data["tasks"]}
            data["fired"] = [k for k in fired if k.split(":")[0] in live]
            _save(data)
    return out


# ── the tool ─────────────────────────────────────────────────────────────────

def _new_id(data: dict) -> str:
    n = int(data.get("_seq", 0)) + 1
    data["_seq"] = n
    return f"{n}"


def _do(p: dict, show) -> str:
    a = (p.get("action") or "").strip().lower()
    title = (p.get("title") or "").strip()

    # ── tasks ────────────────────────────────────────────────────────────
    if a == "add_task":
        if not title:
            raise ValueError("What is the task?")
        d = _parse_date(p["date"]).isoformat() if (p.get("date") or "").strip() else None
        t = _parse_time(p.get("time")) if d else None
        prio = (p.get("priority") or "media").strip().lower()
        prio = prio if prio in _PRIOS else "media"
        def f(data):
            dup = next((x for x in data["tasks"] if not x.get("done")
                        and _fold(x["title"]) == _fold(title) and x.get("date") == d), None)
            if dup:
                return (f"A tarefa '{dup['title']}' já existe"
                        + (f" para {_fmt_when(d, dup.get('time'))}" if d else "") + "; não criei outra.")
            data["tasks"].append({"id": _new_id(data), "title": title, "date": d, "time": t,
                                  "priority": prio, "note": (p.get("note") or "").strip(),
                                  "done": False, "created": datetime.now().isoformat(timespec="minutes")})
            return f"Tarefa criada: {title}" + (f", para {_fmt_when(d, t)}" if d else "") + "."
        return _mutate(f)

    if a in ("complete_task", "reopen_task", "remove_task"):
        def f(data):
            pool = [t for t in data["tasks"] if (a == "reopen_task") == bool(t.get("done"))] or data["tasks"]
            t = _pick(pool, title, "title", "task")
            if a == "remove_task":
                data["tasks"].remove(t)
                return f"Tarefa removida: {t['title']}."
            t["done"] = (a == "complete_task")
            return (f"Concluída: {t['title']}." if t["done"] else f"Reaberta: {t['title']}.")
        return _mutate(f)

    if a == "list_tasks":
        flt = (p.get("filter") or "open").strip().lower()
        data = _load(); now = datetime.now(); today = date.today().isoformat()
        if flt == "all":
            items = data["tasks"]
        elif flt == "done":
            items = [t for t in data["tasks"] if t.get("done")]
        elif flt == "overdue":
            items = [t for t in data["tasks"] if _overdue(t, now)]
        elif flt == "today":
            items = [t for t in data["tasks"] if not t.get("done") and t.get("date") == today]
        else:
            items = [t for t in data["tasks"] if not t.get("done")]
        items = sorted(items, key=lambda t: (t.get("date") or "9999", t.get("time") or ""))
        show("TAREFAS", "\n".join(("☑ " if t.get("done") else "☐ ") + _fmt_task(t) for t in items) or "Nenhuma.")
        if not items:
            return {"open": "Nenhuma tarefa aberta.", "overdue": "Nenhuma tarefa atrasada.",
                    "today": "Nenhuma tarefa para hoje.", "done": "Nenhuma tarefa concluída.",
                    "all": "Nenhuma tarefa."}.get(flt, "Nenhuma tarefa.")
        return f"{len(items)} tarefa(s): " + "; ".join(_fmt_task(t) for t in items[:12])

    # ── events ───────────────────────────────────────────────────────────
    if a == "add_event":
        if not title:
            raise ValueError("What is the event?")
        if not (p.get("date") or "").strip():
            raise ValueError("Which day? Give the date as YYYY-MM-DD.")
        d = _parse_date(p["date"]).isoformat()
        t = _parse_time(p.get("time")) or "09:00"
        lead = p.get("remind_minutes")
        lead = int(lead) if lead not in (None, "") else 10
        def f(data):
            dup = next((x for x in data["events"] if _fold(x["title"]) == _fold(title)
                        and x["date"] == d and x.get("time") == t), None)
            if dup:
                return f"'{dup['title']}' já está marcado para {_fmt_when(d, t)}; não marquei de novo."
            data["events"].append({"id": _new_id(data), "title": title, "date": d, "time": t,
                                   "remind_minutes": max(0, lead), "note": (p.get("note") or "").strip()})
            return (f"Marcado: {title}, {_fmt_when(d, t)}"
                    + (f", aviso {lead} minuto{'s' if lead != 1 else ''} antes." if lead else "."))
        return _mutate(f)

    if a == "remove_event":
        def f(data):
            e = _pick(data["events"], title, "title", "event")
            data["events"].remove(e)
            return f"Compromisso removido: {e['title']}."
        return _mutate(f)

    if a in ("list_events", "agenda"):
        data = _load()
        flt = (p.get("filter") or ("today" if a == "agenda" else "week")).strip().lower()
        if (p.get("date") or "").strip():
            day = _parse_date(p["date"]); days = [day]
        elif flt == "today":
            days = [date.today()]
        elif flt == "tomorrow":
            days = [date.today() + timedelta(days=1)]
        else:
            days = [date.today() + timedelta(days=i) for i in range(7)]
        if a == "agenda" or len(days) == 1:
            text = agenda_text(days[0])
            show("AGENDA", text)
            return text.replace("\n", " ")
        keys = {d.isoformat() for d in days}
        ev = sorted((e for e in data["events"] if e["date"] in keys), key=lambda e: (e["date"], e.get("time") or ""))
        show("AGENDA — 7 DIAS", "\n".join("• " + _fmt_event(e) for e in ev) or "Nada marcado.")
        return ("Nada marcado nos próximos 7 dias." if not ev else
                f"{len(ev)} compromisso(s): " + "; ".join(_fmt_event(e) for e in ev[:10]))

    # ── lists ────────────────────────────────────────────────────────────
    if a in ("add_item", "check_item", "remove_item", "show_list", "clear_list", "remove_list"):
        lname = (p.get("list") or "").strip() or "compras"
        def f(data):
            lists = data["lists"]
            if a == "add_item":
                if not title:
                    raise ValueError("What should I add?")
                key = next((k for k in lists if _fold(k) == _fold(lname)), lname)
                lists.setdefault(key, [])
                if any(_fold(i["text"]) == _fold(title) for i in lists[key]):
                    return f"'{title}' já está na lista {key}."
                lists[key].append({"text": title, "done": False})
                return f"Adicionado '{title}' à lista {key} ({len(lists[key])} itens)."
            names = [{"name": k} for k in lists]
            key = _pick(names, lname, "name", "list")["name"]
            items = lists[key]
            if a == "show_list":
                show(f"LISTA — {key.upper()}", "\n".join(("☑ " if i["done"] else "☐ ") + i["text"] for i in items) or "Vazia.")
                return (f"Lista {key} vazia." if not items else
                        f"Lista {key}, {len(items)} itens: " + "; ".join(("✓ " if i["done"] else "") + i["text"] for i in items))
            if a == "clear_list":
                lists[key] = []
                return f"Lista {key} esvaziada."
            if a == "remove_list":
                del lists[key]
                return f"Lista {key} apagada."
            it = _pick(items, title, "text", "item")
            if a == "check_item":
                it["done"] = True
                return f"Marcado: {it['text']}."
            items.remove(it)
            return f"Removido da lista {key}: {it['text']}."
        if a == "show_list":
            return f(_load())
        return _mutate(f)

    if a == "lists":
        data = _load()
        if not data["lists"]:
            return "Nenhuma lista ainda."
        show("LISTAS", "\n".join(f"• {k} ({sum(1 for i in v if not i['done'])} abertos de {len(v)})"
                                 for k, v in data["lists"].items()))
        return "Listas: " + "; ".join(f"{k} ({len(v)} itens)" for k, v in data["lists"].items())

    # ── notes ────────────────────────────────────────────────────────────
    if a == "add_note":
        if not title:
            raise ValueError("What should I note?")
        def f(data):
            data["notes"].append({"id": _new_id(data), "text": title,
                                  "created": datetime.now().isoformat(timespec="minutes")})
            return "Anotado."
        return _mutate(f)

    if a == "list_notes":
        data = _load()
        notes = data["notes"][-20:]
        show("NOTAS", "\n".join(f"• {n['text']}  ({n['created'][:10]})" for n in notes) or "Nenhuma.")
        return "Nenhuma nota." if not notes else f"{len(notes)} nota(s): " + "; ".join(n["text"] for n in notes[-8:])

    if a == "remove_note":
        def f(data):
            n = _pick(data["notes"], title, "text", "note")
            data["notes"].remove(n)
            return "Nota removida."
        return _mutate(f)

    # ── dedupe ───────────────────────────────────────────────────────────
    if a == "dedupe":
        def f(data):
            removed = 0
            seen = set(); keep = []
            for t in data["tasks"]:
                key = (_fold(t["title"]), t.get("date"), bool(t.get("done")))
                if key in seen:
                    removed += 1; continue
                seen.add(key); keep.append(t)
            data["tasks"] = keep
            seen = set(); keep = []
            for e in data["events"]:
                key = (_fold(e["title"]), e["date"], e.get("time"))
                if key in seen:
                    removed += 1; continue
                seen.add(key); keep.append(e)
            data["events"] = keep
            return (f"Removi {removed} duplicada{'s' if removed != 1 else ''}." if removed
                    else "Não há tarefas ou compromissos duplicados.")
        return _mutate(f)

    # ── undo ─────────────────────────────────────────────────────────────
    if a == "undo":
        with _lock:
            if not _undo:
                return "Nothing to undo in this session."
            _save(_undo.pop())
        return "Desfeito."

    raise ValueError(f"Unknown organizer action '{a}'.")


def run(parameters: dict, player=None, session_memory=None) -> str:
    def show(title: str, text: str) -> None:
        if player is not None and hasattr(player, "show_content"):
            try:
                player.show_content(title, text)
            except Exception:
                pass
    try:
        return _do(parameters or {}, show)
    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"Organizer failed: {e}"
