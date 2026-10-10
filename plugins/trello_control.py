"""
Trello for JARVIS — boards, lists and cards by voice.

Setup (once, in ⚙ → PLUGIN SETTINGS → TRELLO):
  1. API key:  https://trello.com/power-ups/admin  → create a Power-Up (any
     name) → "API key" tab → copy the key.
  2. Token:    on that same page click the "Token" link next to the key (or
     open https://trello.com/1/authorize?expiration=never&scope=read,write
     &response_type=token&name=JARVIS&key=<API key>), allow, copy the token.
  3. Default board (optional): the board JARVIS uses when you don't name one.
  4. TEST CONNECTION.

Both values are stored in config/api_keys.json under plugin_config.trello,
plaintext like the Gemini key — treat the file as a password file.

Everything is matched by name, case-insensitively and by prefix, so "move the
card website to done" works without ids. Nothing is ever deleted: closing a
card archives it, which Trello can undo.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta

import requests

from memory.config_manager import get_plugin_config

_NS = "trello"
_API = "https://api.trello.com/1"
_TIMEOUT = 10

PLUGIN = {
    "name": "trello_control",
    "description": (
        "Works with the user's Trello boards: lists boards, the lists (columns) "
        "of a board, the cards in a list, cards due today/this week/overdue, "
        "creates a card, moves a card to another list, marks a card complete "
        "(sets dueComplete), archives a card, adds a comment, or searches cards. "
        "Use for anything mentioning Trello, boards, cards, a kanban column, "
        "'to do / doing / done' lists, or tasks the user keeps on Trello. "
        "Not for OS reminders — that is the reminder tool."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "One of: list_boards, list_lists, list_cards, due_cards, "
                    "create_card, move_card, complete_card, archive_card, "
                    "comment_card, search"),
            },
            "board": {"type": "STRING", "description": "Board name (optional; default board if empty)"},
            "list":  {"type": "STRING", "description": "List/column name, e.g. 'To Do', 'Done'"},
            "card":  {"type": "STRING", "description": "Card title (or its start) to act on"},
            "text":  {"type": "STRING", "description": "Card description, comment text, or search query"},
            "due":   {"type": "STRING", "description": "Due date YYYY-MM-DD or YYYY-MM-DD HH:MM (create_card); or 'today', 'week', 'overdue' (due_cards)"},
            "to_list": {"type": "STRING", "description": "Destination list name (move_card)"},
        },
        "required": ["action"],
    },
}


# ── settings panel (⚙ → PLUGIN SETTINGS) ────────────────────────────────────

def _test(values: dict):
    key, tok = (values.get("api_key") or "").strip(), (values.get("token") or "").strip()
    if not key or not tok:
        return False, "Enter the API key and the token first."
    try:
        me = requests.get(f"{_API}/members/me", params={"key": key, "token": tok,
                          "fields": "fullName,username"}, timeout=_TIMEOUT)
        if me.status_code == 401:
            return False, "Trello rejected the key/token (401)."
        me.raise_for_status()
        boards = requests.get(f"{_API}/members/me/boards", params={"key": key, "token": tok,
                              "fields": "name", "filter": "open"}, timeout=_TIMEOUT)
        boards.raise_for_status()
        names = [b["name"] for b in boards.json()]
        who = me.json().get("fullName") or me.json().get("username") or "you"
        return True, f"Connected as {who}. {len(names)} open board(s): " + ", ".join(names[:6])
    except Exception as e:
        return False, f"Connection failed: {e}"


PLUGIN_SETTINGS = {
    "namespace": _NS,
    "title": "TRELLO",
    "fields": [
        {"key": "api_key", "label": "API key", "type": "password",
         "placeholder": "from trello.com/power-ups/admin"},
        {"key": "token", "label": "Token", "type": "password",
         "placeholder": "the token generated for that key"},
        {"key": "default_board", "label": "Default board", "type": "text",
         "placeholder": "board name used when you don't say one"},
    ],
    "action": {"label": "TEST CONNECTION", "run": _test},
}


# ── API helpers ──────────────────────────────────────────────────────────────

class _NotConfigured(Exception):
    pass


def _auth() -> dict:
    cfg = get_plugin_config(_NS)
    key, tok = (cfg.get("api_key") or "").strip(), (cfg.get("token") or "").strip()
    if not key or not tok:
        raise _NotConfigured
    return {"key": key, "token": tok}


def _get(path: str, **params):
    r = requests.get(f"{_API}{path}", params={**_auth(), **params}, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _post(path: str, **params):
    r = requests.post(f"{_API}{path}", params={**_auth(), **params}, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _put(path: str, **params):
    r = requests.put(f"{_API}{path}", params={**_auth(), **params}, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _pick(items: list[dict], name: str, what: str) -> dict:
    """The item whose name matches `name`: exact, then prefix, then substring —
    all case-insensitive. Raises with the available names when nothing matches."""
    q = (name or "").strip().lower()
    if not q:
        raise ValueError(f"Which {what}? Options: " + ", ".join(i["name"] for i in items[:8]))
    for test in (lambda n: n == q, lambda n: n.startswith(q), lambda n: q in n):
        hits = [i for i in items if test(i["name"].lower())]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ValueError(f"Several {what}s match '{name}': " + ", ".join(h["name"] for h in hits[:6]))
    raise ValueError(f"No {what} called '{name}'. Options: " + ", ".join(i["name"] for i in items[:8]))


def _boards() -> list[dict]:
    return _get("/members/me/boards", fields="name,url", filter="open")


def _board(name: str) -> dict:
    name = (name or "").strip() or (get_plugin_config(_NS).get("default_board") or "").strip()
    boards = _boards()
    if not name:
        if len(boards) == 1:
            return boards[0]
        raise ValueError("Which board? Options: " + ", ".join(b["name"] for b in boards[:8]))
    return _pick(boards, name, "board")


def _lists(board_id: str) -> list[dict]:
    return _get(f"/boards/{board_id}/lists", fields="name", filter="open")


def _cards(board_id: str) -> list[dict]:
    return _get(f"/boards/{board_id}/cards", fields="name,due,dueComplete,idList,shortUrl",
                filter="open")


def _parse_due(text: str) -> str:
    t = (text or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            d = datetime.strptime(t, fmt)
            if fmt == "%Y-%m-%d":
                d = d.replace(hour=12)
            return d.astimezone().isoformat()
        except ValueError:
            continue
    raise ValueError("Due date must be YYYY-MM-DD or YYYY-MM-DD HH:MM.")


def _due_local(card: dict):
    if not card.get("due"):
        return None
    try:
        return datetime.fromisoformat(card["due"].replace("Z", "+00:00")).astimezone()
    except Exception:
        return None


def _fmt_card(c: dict, lists: dict | None = None) -> str:
    bits = [c["name"]]
    d = _due_local(c)
    if d:
        bits.append("due " + d.strftime("%d/%m %H:%M") + (" ✓" if c.get("dueComplete") else ""))
    if lists and c.get("idList") in lists:
        bits.append("in " + lists[c["idList"]])
    return " — ".join(bits)


# ── actions ──────────────────────────────────────────────────────────────────

def _do(p: dict, log) -> str:
    action = (p.get("action") or "").strip().lower()

    if action == "list_boards":
        names = [b["name"] for b in _boards()]
        return "Boards: " + ", ".join(names) if names else "No open boards."

    board = _board(p.get("board"))
    bid = board["id"]

    if action == "list_lists":
        return f"Lists on {board['name']}: " + ", ".join(l["name"] for l in _lists(bid))

    if action == "list_cards":
        lists = _lists(bid)
        lst = _pick(lists, p.get("list"), "list")
        cards = [c for c in _cards(bid) if c["idList"] == lst["id"]]
        if not cards:
            return f"'{lst['name']}' on {board['name']} is empty."
        return (f"{len(cards)} card(s) in '{lst['name']}' on {board['name']}: "
                + "; ".join(_fmt_card(c) for c in cards[:15]))

    if action == "due_cards":
        when = (p.get("due") or "today").strip().lower()
        lists = {l["id"]: l["name"] for l in _lists(bid)}
        today = date.today()
        out = []
        for c in _cards(bid):
            d = _due_local(c)
            if d is None or c.get("dueComplete"):
                continue
            dd = d.date()
            if (when == "today" and dd == today) or \
               (when == "overdue" and dd < today) or \
               (when == "week" and today <= dd <= today + timedelta(days=7)) or \
               (when == "tomorrow" and dd == today + timedelta(days=1)):
                out.append((d, c))
        out.sort(key=lambda t: t[0])
        label = {"today": "due today", "overdue": "overdue", "week": "due this week",
                 "tomorrow": "due tomorrow"}.get(when, f"due {when}")
        if not out:
            return f"Nothing {label} on {board['name']}."
        return (f"{len(out)} card(s) {label} on {board['name']}: "
                + "; ".join(_fmt_card(c, lists) for _, c in out[:15]))

    if action == "create_card":
        name = (p.get("card") or p.get("text") or "").strip()
        if not name:
            raise ValueError("What should the card be called?")
        lists = _lists(bid)
        lst = _pick(lists, p.get("list"), "list") if (p.get("list") or "").strip() else lists[0]
        params = {"idList": lst["id"], "name": name, "pos": "bottom"}
        if (p.get("text") or "").strip() and p.get("card"):
            params["desc"] = p["text"].strip()
        if (p.get("due") or "").strip():
            params["due"] = _parse_due(p["due"])
        card = _post("/cards", **params)
        return f"Created '{card['name']}' in '{lst['name']}' on {board['name']}."

    if action in ("move_card", "complete_card", "archive_card", "comment_card"):
        cards = _cards(bid)
        card = _pick(cards, p.get("card"), "card")
        if action == "move_card":
            lst = _pick(_lists(bid), p.get("to_list") or p.get("list"), "list")
            _put(f"/cards/{card['id']}", idList=lst["id"], pos="top")
            return f"Moved '{card['name']}' to '{lst['name']}'."
        if action == "complete_card":
            if card.get("due"):
                _put(f"/cards/{card['id']}", dueComplete="true")
                return f"Marked '{card['name']}' as complete."
            # No due date: completing means moving to a Done-like list if there is one.
            lists = _lists(bid)
            done = next((l for l in lists if l["name"].strip().lower() in
                         ("done", "concluído", "concluido", "feito", "finalizado", "pronto")), None)
            if done:
                _put(f"/cards/{card['id']}", idList=done["id"], pos="top")
                return f"Moved '{card['name']}' to '{done['name']}'."
            raise ValueError(f"'{card['name']}' has no due date and the board has no Done list; say which list to move it to.")
        if action == "archive_card":
            _put(f"/cards/{card['id']}", closed="true")
            return f"Archived '{card['name']}'. It can be restored from Trello's archive."
        if action == "comment_card":
            text = (p.get("text") or "").strip()
            if not text:
                raise ValueError("What should the comment say?")
            _post(f"/cards/{card['id']}/actions/comments", text=text)
            return f"Comment added to '{card['name']}'."

    if action == "search":
        q = (p.get("text") or p.get("card") or "").strip()
        if not q:
            raise ValueError("Search for what?")
        lists = {l["id"]: l["name"] for l in _lists(bid)}
        hits = [c for c in _cards(bid) if q.lower() in c["name"].lower()]
        if not hits:
            return f"No card matching '{q}' on {board['name']}."
        return f"{len(hits)} match(es) on {board['name']}: " + "; ".join(_fmt_card(c, lists) for c in hits[:10])

    raise ValueError(f"Unknown Trello action '{action}'.")


def run(parameters: dict, player=None, session_memory=None) -> str:
    def log(msg: str) -> None:
        if player:
            try:
                player.write_log(f"[Trello] {msg}")
            except Exception:
                pass
    try:
        result = _do(parameters or {}, log)
    except _NotConfigured:
        return ("Trello is not set up yet. Open the gear, PLUGIN SETTINGS, TRELLO, "
                "and enter the API key and token.")
    except ValueError as e:
        return str(e)
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        if code == 401:
            return "Trello rejected the key or token. Check them in PLUGIN SETTINGS."
        return f"Trello answered with an error ({code})."
    except requests.RequestException as e:
        return f"Could not reach Trello: {e.__class__.__name__}."
    except Exception as e:
        return f"Trello plugin failed: {e}"
    log(result)
    return result
