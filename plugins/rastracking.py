"""
Rastracking — the user's tracking platform, by voice (read-only API).

    "Jarvis, quanto foi trackeado hoje?"       "faturamento da semana no Rastracking"
    "Jarvis, quem vence hoje?"                 "quais clientes vencem essa semana?"
    "Jarvis, tem alguém esperando no suporte?" "qual o assunto?"  (subjects only on request)

Setup (⚙ → PLUGIN SETTINGS → RASTRACKING): in Rastracking go to
ADM → Configurações do Sistema → API Rastracking, create a key with the
support:read and clients:read permissions, paste it here, TEST CONNECTION.
Keys expire after 90 days. The key is stored in config/api_keys.json with the
others and is never written to the log.

Everything is read-only: this plugin cannot answer, resolve, or change
anything in Rastracking.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta

import requests

from memory.config_manager import get_plugin_config

NS = "rastracking"
BASE = "https://api.rastracking.com/api/integrations"
TIMEOUT = 15
MAX_PAGES = 40
TZ = "America/Sao_Paulo"

PLUGIN = {
    "name": "rastracking",
    "description": (
        "The user's Rastracking platform (sales tracking for their clients). Actions: "
        "tracked_revenue — how much was tracked (faturamento rastreado) across ALL clients "
        "in a period: today, yesterday, week, month, or a custom range — the total only, "
        "no client names; "
        "top_clients — which clients tracked the most in the period, ONLY when the user "
        "asks for the biggest/top clients; "
        "expiring_clients — which clients' plans expire today / this week / in a range, "
        "or are already overdue; "
        "support_pending — which clients sent a support message that is still waiting "
        "for a reply. By default it returns only names and waiting time; set "
        "with_subject=true ONLY when the user explicitly asks what the message/subject "
        "is ('qual o assunto', 'o que ele disse'). Use for 'quanto foi trackeado', "
        "'faturamento no Rastracking', 'quem vence hoje/essa semana', 'clientes "
        "vencidos', 'alguém esperando no suporte', 'mensagens sem resposta'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "tracked_revenue | top_clients | expiring_clients | support_pending"},
            "period": {"type": "STRING",
                       "description": "today (default) | yesterday | week | month | overdue "
                                      "(expiring_clients only) | custom (then give start and end)"},
            "start": {"type": "STRING", "description": "custom period start, YYYY-MM-DD"},
            "end": {"type": "STRING", "description": "custom period end, YYYY-MM-DD"},
            "with_subject": {"type": "BOOLEAN",
                             "description": "support_pending: include what each client wrote. "
                                            "Only when the user explicitly asks for the subject."},
        },
        "required": ["action"],
    },
}


# ── http ─────────────────────────────────────────────────────────────────────

class _NotConfigured(Exception):
    pass


def _key(values: dict | None = None) -> str:
    cfg = values if values is not None else get_plugin_config(NS)
    return str(cfg.get("api_key") or "").strip()


def _get(path: str, values: dict | None = None, **params) -> dict:
    key = _key(values)
    if not key:
        raise _NotConfigured
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    clean = {k: v for k, v in params.items() if v is not None and v != ""}
    for attempt in range(3):
        r = requests.get(f"{BASE}/{path}", headers=headers, params=clean, timeout=TIMEOUT)
        if r.status_code == 429 and attempt < 2:
            wait = r.headers.get("Retry-After")
            time.sleep(min(float(wait) if wait and wait.isdigit() else 2.0 * (attempt + 1), 10.0))
            continue
        if r.status_code >= 500 and attempt < 2:
            time.sleep(1.5 * (attempt + 1))
            continue
        break
    if r.status_code == 401:
        raise RuntimeError("Rastracking rejected the key (401): invalid, expired (90 days) or revoked")
    if r.status_code == 403:
        raise RuntimeError(f"Rastracking: the key lacks the permission for '{path}' (403) — "
                           "enable support:read / clients:read on the key")
    if r.status_code == 400:
        raise RuntimeError(f"Rastracking: bad request (400): {r.text[:120]}")
    r.raise_for_status()
    return r.json()


def _pages(path: str, values: dict | None = None, **params):
    """Yield every page of a cursor-paginated listing."""
    cursor = None
    for _ in range(MAX_PAGES):
        data = _get(path, values, cursor=cursor, **params)
        yield data
        if not data.get("hasMore") or not data.get("nextCursor"):
            return
        cursor = data["nextCursor"]


# ── dates ────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(TZ))
    except Exception:
        return datetime.now()


def _parse_dt(s) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d.astimezone() if d.tzinfo else d
    except Exception:
        return None


def _period(name: str, start: str = "", end: str = "") -> tuple[date, date, str]:
    today = _now().date()
    name = (name or "today").strip().lower()
    if name in ("custom", "range") or (start and end):
        try:
            a, b = date.fromisoformat(start), date.fromisoformat(end)
        except Exception:
            raise RuntimeError("custom period needs start and end as YYYY-MM-DD")
        if b < a:
            a, b = b, a
        return a, b, f"de {a:%d/%m} a {b:%d/%m}"
    if name in ("yesterday", "ontem"):
        d = today - timedelta(days=1)
        return d, d, "ontem"
    if name in ("week", "semana", "this_week"):
        a = today - timedelta(days=today.weekday())
        return a, a + timedelta(days=6), "esta semana"
    if name in ("month", "mes", "mês", "this_month"):
        a = today.replace(day=1)
        nxt = (a.replace(day=28) + timedelta(days=4)).replace(day=1)
        return a, nxt - timedelta(days=1), "este mês"
    if name in ("last7", "7days", "ultimos7"):
        return today - timedelta(days=6), today, "nos últimos 7 dias"
    return today, today, "hoje"


def _fmt(v: float) -> str:
    s = f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


from core.numwords import extenso as _extenso, money_text as _reais  # noqa: E402


def _ago(d: datetime | None) -> str:
    if not d:
        return ""
    secs = max(0, (datetime.now().astimezone() - d).total_seconds())
    if secs < 3600:
        return f"há {int(secs // 60)} min"
    if secs < 86400:
        return f"há {int(secs // 3600)} h"
    return f"há {int(secs // 86400)} dia(s)"


_pending_cards: list = [None]      # hologram cards produced by the last action


# ── actions ──────────────────────────────────────────────────────────────────

def tracked_revenue(period: str, start: str = "", end: str = "", values: dict | None = None,
                    top_clients: bool = False):
    a, b, label = _period(period, start, end)
    rec_amt = rec_n = att_amt = att_n = 0.0
    per_client = []
    n_clients = 0
    for page in _pages("clients", values, startDate=a.isoformat(), endDate=b.isoformat(), limit=100):
        for c in page.get("data") or []:
            n_clients += 1
            rv = c.get("revenue") or {}
            ra, rn = float(rv.get("recordedAmount") or 0), int(rv.get("recordedPurchases") or 0)
            aa, an = float(rv.get("attributedAmount") or 0), int(rv.get("attributedPurchases") or 0)
            rec_amt += ra; rec_n += rn; att_amt += aa; att_n += an
            if ra or aa:
                per_client.append((c.get("name") or "?", ra, rn, aa, an))
    per_client.sort(key=lambda t: -t[1])
    if top_clients:
        if not per_client:
            spoken = f"Nenhuma venda registrada {label}."
        else:
            top = ", ".join(f"{n} com {_reais(ra, cents=False)}" for n, ra, _, _, _ in per_client[:5])
            spoken = f"Maiores clientes {label}: {top}."
        _pending_cards[0] = [{"title": f"MAIORES CLIENTES {label}".upper(),
                              "lines": [f"{n}: {_fmt(ra)}" for n, ra, _, _, _ in per_client[:7]] or ["nenhuma venda"],
                              "hold": 30}]
    else:
        # Only the figure that was asked for. The per-client list is on the
        # panel and comes by voice only with action top_clients.
        spoken = (f"Trackeado {label}: {_reais(rec_amt, cents=False)} em {int(rec_n)} venda(s) "
                  f"registradas, de {n_clients} cliente(s).")
        if int(att_amt) != int(rec_amt):
            spoken += f" Atribuído a anúncios: {_reais(att_amt, cents=False)} em {int(att_n)}."
        _pending_cards[0] = [{"title": f"TRACKEADO {label}".upper(), "value": rec_amt, "fmt": "money",
                              "lines": [f"{int(rec_n)} vendas registradas",
                                        f"atribuído a anúncios: {_fmt(att_amt)} ({int(att_n)})",
                                        f"{n_clients} clientes"], "hold": 30}]
    panel = [f"RASTRACKING — trackeado {label} ({a:%d/%m/%Y} a {b:%d/%m/%Y})",
             f"Registrado: {_fmt(rec_amt)}  ({int(rec_n)} vendas)",
             f"Atribuído a anúncios: {_fmt(att_amt)}  ({int(att_n)} vendas)",
             f"Clientes consultados: {n_clients}", ""]
    for n, ra, rn, aa, an in per_client[:40]:
        panel.append(f"  • {n}: {_fmt(ra)} ({rn})  |  atribuído {_fmt(aa)} ({an})")
    if not per_client:
        panel.append("  (nenhuma venda registrada no período)")
    return spoken, "\n".join(panel)


def expiring_clients(period: str, start: str = "", end: str = "", values: dict | None = None):
    today = _now().date()
    name = (period or "today").strip().lower()
    if name in ("overdue", "vencidos", "atrasados"):
        params = dict(dueBefore=(today - timedelta(days=1)).isoformat())
        label = "já vencidos"
    else:
        a, b, label = _period(period, start, end)
        if a < today and name not in ("custom", "range"):
            a = today                                   # expiring = from today on
        params = dict(dueAfter=a.isoformat(), dueBefore=b.isoformat())
        label = {"hoje": "vencem hoje", "esta semana": "vencem esta semana",
                 "este mês": "vencem este mês"}.get(label, f"vencem {label}")
    rows = []
    for page in _pages("clients", values, limit=100, **params):
        for c in page.get("data") or []:
            if str(c.get("accountStatus") or "").upper() == "CANCELLED":
                continue
            due = _parse_dt(c.get("nextDueDate"))
            rows.append((c.get("name") or "?", due, c.get("daysUntilDue"),
                         (c.get("plan") or {}).get("displayName") if isinstance(c.get("plan"), dict) else "",
                         c.get("accountStatus") or "", bool(c.get("isActive"))))
    rows.sort(key=lambda r: (r[1] or datetime.max.replace(tzinfo=None)).replace(tzinfo=None))
    if not rows:
        _pending_cards[0] = [{"title": f"CLIENTES QUE {label}".upper(), "value": 0, "fmt": "int",
                              "unit": "clientes", "accent": "ok", "lines": ["nenhum"], "hold": 20}]
        return f"Nenhum cliente {label}.", f"RASTRACKING — clientes que {label}\n  (nenhum)"
    _pending_cards[0] = [{"title": f"CLIENTES QUE {label}".upper(), "value": len(rows), "fmt": "int",
                          "unit": "cliente(s)", "accent": "warn",
                          "lines": [f"{n}  ·  {due:%d/%m}" if due else n for n, due, *_ in rows[:7]],
                          "hold": 30}]
    names = ", ".join(r[0] for r in rows[:8]) + (f" e mais {len(rows) - 8}" if len(rows) > 8 else "")
    spoken = f"{len(rows)} cliente(s) {label}: {names}."
    panel = [f"RASTRACKING — clientes que {label} ({len(rows)})", ""]
    for n, due, days, plan, st, active in rows:
        when = f"{due:%d/%m}" if due else "sem data"
        d = f"{days} dia(s)" if isinstance(days, (int, float)) else ""
        panel.append(f"  • {n}: {when}  {d}  {plan or ''}  [{st}{'' if active else ', bloqueado'}]")
    return spoken, "\n".join(panel)


def support_pending(with_subject: bool = False, values: dict | None = None):
    items = []
    for page in _pages("support/conversations", values, awaitingReply="true", limit=100):
        for c in page.get("data") or []:
            if not c.get("awaitingReply") or not c.get("latestClientMessage"):
                continue
            m = c["latestClientMessage"]
            items.append(((c.get("client") or {}).get("name") or "?",
                          _parse_dt(m.get("createdAt") or c.get("lastClientMessageAt")),
                          str(m.get("body") or "").strip(), bool(m.get("hasImage")),
                          c.get("status") or ""))
    items.sort(key=lambda t: (t[1] or datetime.min.replace(tzinfo=None)).replace(tzinfo=None))
    if not items:
        _pending_cards[0] = [{"title": "SUPORTE", "value": 0, "fmt": "int", "unit": "aguardando",
                              "accent": "ok", "lines": ["ninguém na fila"], "hold": 20}]
        return "Ninguém aguardando resposta no suporte.", "RASTRACKING — suporte\n  (ninguém aguardando)"
    _pending_cards[0] = [{"title": "SUPORTE", "value": len(items), "fmt": "int",
                          "unit": "aguardando resposta", "accent": "warn",
                          "lines": [f"{n}  ·  {_ago(d)}" + (f"  —  {b[:60]}" if with_subject else "")
                                    for n, d, b, _, _ in items[:7]], "hold": 30}]
    who = "; ".join(f"{n} ({_ago(d)})" for n, d, _, _, _ in items[:8])
    spoken = f"{len(items)} cliente(s) aguardando resposta no suporte: {who}."
    if with_subject:
        subj = "; ".join(f"{n}: «{(b[:160] + '…') if len(b) > 160 else b}{' [imagem]' if img else ''}»"
                         for n, _, b, img, _ in items[:6])
        spoken += f" Assuntos: {subj}"
    else:
        spoken += " (Diga 'qual o assunto' se quiser que eu leia as mensagens.)"
    panel = [f"RASTRACKING — suporte: {len(items)} aguardando resposta", ""]
    for n, d, b, img, st in items:
        line = f"  • {n}  {_ago(d)}  [{st}]"
        if with_subject:
            line += f"\n      «{b[:300]}»" + (" [imagem]" if img else "")
        panel.append(line)
    return spoken, "\n".join(panel)


_last_brief: dict = {}


def last_briefing_data() -> dict:
    """Numbers behind the last briefing_summary() (for the hologram cards)."""
    return dict(_last_brief)


def briefing_summary() -> str:
    """One or two lines for the morning briefing: today's tracked revenue and
    how many clients are waiting in support. "" when the key is not set, so
    the briefing silently skips it; a short error line when the API fails."""
    if not _key():
        return ""
    out = []
    try:
        a, b, _label = _period("today")
        rec_amt = rec_n = att_amt = att_n = 0.0
        n_clients = 0
        for page in _pages("clients", None, startDate=a.isoformat(), endDate=b.isoformat(), limit=100):
            for c in page.get("data") or []:
                n_clients += 1
                rv = c.get("revenue") or {}
                rec_amt += float(rv.get("recordedAmount") or 0)
                rec_n += int(rv.get("recordedPurchases") or 0)
                att_amt += float(rv.get("attributedAmount") or 0)
                att_n += int(rv.get("attributedPurchases") or 0)
        # Whole reais, spelled out, no cents: this is read aloud in the briefing.
        line = f"Trackeado hoje: {_reais(rec_amt, cents=False)} em {int(rec_n)} vendas registradas"
        if int(att_amt) != int(rec_amt):
            line += f" ({_reais(att_amt, cents=False)} em {int(att_n)} atribuídas a anúncios)"
        out.append(line + ".")
        _last_brief.update(rec_amt=rec_amt, rec_n=int(rec_n), att_amt=att_amt, att_n=int(att_n),
                           clients=n_clients)
    except Exception as e:
        out.append(f"Trackeado hoje: não foi possível consultar ({str(e)[:80]}).")
    try:
        n = 0
        for page in _pages("support/conversations", None, awaitingReply="true", limit=100):
            n += sum(1 for c in (page.get("data") or [])
                     if c.get("awaitingReply") and c.get("latestClientMessage"))
        out.append(f"Suporte: {n} cliente(s) aguardando resposta." if n
                   else "Suporte: ninguém aguardando resposta.")
        _last_brief["support_n"] = n
    except Exception as e:
        out.append(f"Suporte: não foi possível consultar ({str(e)[:80]}).")
    return "\n".join(out)


# ── ⚙ settings ───────────────────────────────────────────────────────────────

def _test(values: dict):
    if not _key(values):
        return False, "Paste the Rastracking API key first (ADM → Configurações → API Rastracking)."
    notes, ok = [], True
    for path, label in (("clients", "clients:read"), ("support/conversations", "support:read")):
        try:
            d = _get(path, values, limit=1)
            n = len(d.get("data") or [])
            notes.append(f"{label} OK" + (f" ({'has data' if n else 'empty'})"))
        except RuntimeError as e:
            ok = False
            notes.append(f"{label} FAILED — {e}")
        except Exception as e:
            ok = False
            notes.append(f"{label} FAILED — {e}")
    return ok, "; ".join(notes)


PLUGIN_SETTINGS = {
    "namespace": NS,
    "title": "RASTRACKING (tracking platform)",
    "fields": [
        {"key": "api_key", "label": "API key (rs_api_… — support:read + clients:read)",
         "type": "password", "placeholder": "ADM → Configurações do Sistema → API Rastracking"},
    ],
    "action": {"label": "TEST CONNECTION", "run": _test},
}


# ── the tool ─────────────────────────────────────────────────────────────────

def run(parameters: dict, player=None, session_memory=None) -> str:
    action = (parameters.get("action") or "").strip().lower()
    period = str(parameters.get("period") or "today")
    start = str(parameters.get("start") or "")
    end = str(parameters.get("end") or "")
    ws = parameters.get("with_subject")
    with_subject = ws if isinstance(ws, bool) else str(ws).lower() in ("true", "1", "yes", "sim")
    try:
        if action in ("tracked_revenue", "revenue", "faturamento"):
            spoken, panel = tracked_revenue(period, start, end)
            title = "RASTRACKING — trackeado"
        elif action in ("top_clients", "maiores_clientes", "clients_ranking"):
            spoken, panel = tracked_revenue(period, start, end, top_clients=True)
            title = "RASTRACKING — maiores clientes"
        elif action in ("expiring_clients", "expiring", "vencimentos"):
            spoken, panel = expiring_clients(period, start, end)
            title = "RASTRACKING — vencimentos"
        elif action in ("support_pending", "support", "suporte"):
            spoken, panel = support_pending(with_subject)
            title = "RASTRACKING — suporte"
        else:
            return "Unknown action. Use tracked_revenue, expiring_clients or support_pending."
    except _NotConfigured:
        return ("Rastracking is not configured: paste the API key in ⚙ → PLUGIN SETTINGS → "
                "RASTRACKING and press TEST CONNECTION.")
    except RuntimeError as e:
        return str(e)
    except requests.RequestException as e:
        return f"Rastracking could not be reached: {e}"
    except Exception as e:
        return f"Rastracking lookup failed: {e}"
    if player is not None:
        try:
            if _pending_cards[0] and hasattr(player, "holo_cards"):
                player.holo_cards(_pending_cards[0])
            if hasattr(player, "show_content"):
                player.show_content(title, panel)
        except Exception:
            pass
    _pending_cards[0] = None
    return spoken
