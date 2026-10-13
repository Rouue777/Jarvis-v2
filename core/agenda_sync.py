"""
Agenda ⇄ Trello sync.

Every appointment JARVIS keeps locally (plugins/organizer.py → memory/
organizer.json) is mirrored, when the switch is on, as a card in ONE chosen
Trello list, named in the house format:

    [11/10/2026 16:30] - Call com Thales

and carrying the same date/time as the card's due date. The link is the
card id stored on the local event ("trello_id"). Sync is two-way:

  local → Trello : add / edit / remove an event here → card created / renamed
                   (and due moved) / archived there, immediately.
  Trello → local : every 60 s the list is read; a new card becomes an event,
                   a renamed or re-dated card updates the event, an archived
                   or moved-away card removes it. When both sides changed, the
                   more recent change wins (Trello's dateLastActivity vs the
                   event's "updated").

Configuration (⚙ → 📅 AGENDAMENTOS): switch, board, list. Stored under the
plugin namespace "agenda" in config/api_keys.json. Needs the Trello key and
token from the TRELLO plugin settings.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timezone

NS = "agenda"
POLL_S = 60
_NAME_RE = re.compile(r"^\s*\[(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}):(\d{2}))?\]\s*-\s*(.+?)\s*$")

_lock = threading.RLock()
_thread: threading.Thread | None = None
_stop = threading.Event()
_log = print
_last_error = ""
_last_sync = 0.0


# ── config ───────────────────────────────────────────────────────────────────

def config() -> dict:
    from memory.config_manager import get_plugin_config
    c = get_plugin_config(NS)
    return {"enabled": bool(c.get("trello_sync")), "board_id": str(c.get("board_id") or ""),
            "board_name": str(c.get("board_name") or ""), "list_id": str(c.get("list_id") or ""),
            "list_name": str(c.get("list_name") or "")}


def save_config(**kw) -> None:
    from memory.config_manager import save_plugin_config
    save_plugin_config(NS, {k: v for k, v in kw.items() if v is not None})


def enabled() -> bool:
    c = config()
    return c["enabled"] and bool(c["list_id"]) and _trello_ready()


def _trello_ready() -> bool:
    try:
        from plugins import trello_control as t
        t._auth()
        return True
    except Exception:
        return False


# ── naming ───────────────────────────────────────────────────────────────────

def card_name(date_iso: str, time_hm: str | None, title: str) -> str:
    d = datetime.strptime(date_iso, "%Y-%m-%d")
    stamp = d.strftime("%d/%m/%Y") + (f" {time_hm}" if time_hm else "")
    return f"[{stamp}] - {title.strip()}"


def parse_card(card: dict) -> tuple[str, str | None, str] | None:
    """(date_iso, time_hm|None, title) from the card name, else from its due
    date, else None (a card that is not an appointment)."""
    name = str(card.get("name") or "")
    m = _NAME_RE.match(name)
    if m:
        dd, mm, yyyy, hh, mi, title = m.groups()
        try:
            datetime(int(yyyy), int(mm), int(dd))
        except ValueError:
            return None
        return f"{yyyy}-{mm}-{dd}", (f"{hh}:{mi}" if hh else None), title
    due = card.get("due")
    if due:
        try:
            d = datetime.fromisoformat(str(due).replace("Z", "+00:00")).astimezone()
            return d.strftime("%Y-%m-%d"), d.strftime("%H:%M"), name.strip()
        except Exception:
            return None
    return None


def _due_iso(date_iso: str, time_hm: str | None) -> str:
    d = datetime.strptime(f"{date_iso} {time_hm or '09:00'}", "%Y-%m-%d %H:%M").astimezone()
    return d.isoformat()


def _activity(card: dict) -> float:
    try:
        return datetime.fromisoformat(str(card.get("dateLastActivity") or "").replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _updated(e: dict) -> float:
    try:
        return datetime.fromisoformat(str(e.get("updated") or "")).timestamp()
    except Exception:
        return 0.0


# ── Trello side ──────────────────────────────────────────────────────────────

def boards() -> list[dict]:
    from plugins import trello_control as t
    return t._boards()


def lists(board_id: str) -> list[dict]:
    from plugins import trello_control as t
    return t._lists(board_id)


def _cards(list_id: str) -> list[dict]:
    from plugins import trello_control as t
    return t._get(f"/lists/{list_id}/cards", fields="name,due,closed,dateLastActivity,idList")


def push_event(e: dict) -> str | None:
    """Create or update the card for a local event. Returns the card id."""
    if not enabled():
        return None
    from plugins import trello_control as t
    cfg = config()
    name = card_name(e["date"], e.get("time"), e["title"])
    due = _due_iso(e["date"], e.get("time"))
    if e.get("trello_id"):
        try:
            t._put(f"/cards/{e['trello_id']}", name=name, due=due, closed="false", idList=cfg["list_id"])
            return e["trello_id"]
        except Exception as ex:
            if "404" not in str(ex):
                raise
    card = t._post("/cards", idList=cfg["list_id"], name=name, due=due, pos="bottom")
    return str(card.get("id") or "")


def archive_card(card_id: str) -> None:
    if not card_id or not enabled():
        return
    from plugins import trello_control as t
    try:
        t._put(f"/cards/{card_id}", closed="true")
    except Exception as ex:
        if "404" not in str(ex):
            raise


# ── two-way pass ─────────────────────────────────────────────────────────────

def sync_now() -> str:
    """One full reconciliation. Returns a short summary line."""
    global _last_error, _last_sync
    if not enabled():
        return "sync off"
    from plugins import organizer as org
    with _lock:
        try:
            cfg = config()
            cards = {c["id"]: c for c in _cards(cfg["list_id"]) if not c.get("closed")}
            events = org.events_all()
            created = updated = removed = pushed = 0
            seen_cards = set()
            for e in events:
                cid = e.get("trello_id")
                if cid and cid in cards:
                    seen_cards.add(cid)
                    c = cards[cid]
                    parsed = parse_card(c)
                    if parsed:
                        d, tm, title = parsed
                        same = (d == e["date"] and (tm or "09:00") == (e.get("time") or "09:00")
                                and title.strip() == e["title"].strip())
                        if not same:
                            if _activity(c) >= _updated(e):
                                org.event_update(e["id"], title=title, date=d, time=tm or "09:00",
                                                 _sync=False)
                                updated += 1
                            else:
                                push_event(e); pushed += 1
                elif cid:
                    # linked card gone from the list (archived, deleted or moved)
                    org.event_remove(e["id"], _sync=False); removed += 1
                else:
                    new_id = push_event(e)
                    if new_id:
                        org.event_update(e["id"], trello_id=new_id, _sync=False)
                        seen_cards.add(new_id); pushed += 1
            for cid, c in cards.items():
                if cid in seen_cards:
                    continue
                parsed = parse_card(c)
                if not parsed:
                    continue
                d, tm, title = parsed
                org.event_add(title, d, tm or "09:00", trello_id=cid, _sync=False)
                if not _NAME_RE.match(str(c.get("name") or "")):
                    # bring a plain card into the house format
                    try:
                        from plugins import trello_control as t
                        t._put(f"/cards/{cid}", name=card_name(d, tm, title))
                    except Exception:
                        pass
                created += 1
            _last_error = ""
            _last_sync = time.time()
            return (f"Trello sync: +{created} from Trello, {updated} updated, {removed} removed, "
                    f"{pushed} sent")
        except Exception as ex:
            _last_error = str(ex)[:160]
            return f"Trello sync failed: {_last_error}"


def status() -> dict:
    return {"enabled": enabled(), "last_sync": _last_sync, "last_error": _last_error, **config()}


# ── hooks called by the organizer on local changes ───────────────────────────

def on_event_added(e: dict) -> str | None:
    try:
        return push_event(e)
    except Exception as ex:
        _log(f"SYS: Trello sync — could not create the card: {str(ex)[:100]}")
        return None


def on_event_changed(e: dict) -> None:
    try:
        push_event(e)
    except Exception as ex:
        _log(f"SYS: Trello sync — could not update the card: {str(ex)[:100]}")


def on_event_removed(e: dict) -> None:
    try:
        archive_card(e.get("trello_id") or "")
    except Exception as ex:
        _log(f"SYS: Trello sync — could not archive the card: {str(ex)[:100]}")


# ── background loop ──────────────────────────────────────────────────────────

def start(log=None) -> None:
    global _thread, _log
    if log:
        _log = log
    if _thread and _thread.is_alive():
        return
    _stop.clear()

    def loop():
        last = ""
        while not _stop.wait(POLL_S if last else 5):
            if not enabled():
                last = "off"
                continue
            msg = sync_now()
            if msg != last and ("failed" in msg or any(ch in msg for ch in "123456789") and "+0 from Trello, 0 updated, 0 removed, 0 sent" not in msg):
                try:
                    _log("SYS: " + msg)
                except Exception:
                    pass
            last = msg

    _thread = threading.Thread(target=loop, daemon=True, name="agenda-sync")
    _thread.start()


def stop() -> None:
    _stop.set()
