"""
Cakto — revenue and orders from the user's sales platform, by voice.

    "Jarvis, quanto faturei este mês?"      "faturamento de setembro"
    "quanto vendi hoje?"                     "últimas vendas"

Setup (⚙ → PLUGIN SETTINGS → CAKTO): in the Cakto dashboard create an API
key with the "orders" (and "products") read scopes; paste client_id and
client_secret here; TEST CONNECTION. Tokens are fetched from
https://api.cakto.com.br/public_api/token/ and cached until they expire.

What counts as revenue: orders whose paidAt falls in the period and that were
not refunded or charged back; the figure is the sum of `amount`. The orders
list is paginated newest-first; pages are read until the period is covered
(capped), so a very large shop takes a few seconds.
"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta

import requests

from memory.config_manager import get_plugin_config

NS = "cakto"
BASE = "https://api.cakto.com.br/public_api"
TIMEOUT = 20
MAX_PAGES = 60           # safety cap when walking the order list

PLUGIN = {
    "name": "cakto_sales",
    "description": (
        "The user's sales platform (Cakto): revenue (faturamento) for this month, "
        "a given month or today, order counts, and the latest orders. Use for "
        "'quanto faturei', 'faturamento do mês', 'quantas vendas hoje', 'últimas "
        "vendas', anything about sales or revenue on Cakto. Amounts come back in "
        "reais; read them as money."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "month_revenue | today_revenue | last_orders | products"},
            "month": {"type": "STRING",
                      "description": "For month_revenue: YYYY-MM (default: current month)"},
            "limit": {"type": "INTEGER", "description": "For last_orders: how many (default 5)"},
        },
        "required": ["action"],
    },
}

_tok_lock = threading.Lock()
_token: dict = {"value": "", "exp": 0.0, "for": ""}


# ── auth ─────────────────────────────────────────────────────────────────────

def _creds(values: dict | None = None) -> tuple[str, str]:
    cfg = values if values is not None else get_plugin_config(NS)
    return (str(cfg.get("client_id") or "").strip(), str(cfg.get("client_secret") or "").strip())


def _fetch_token(cid: str, sec: str) -> tuple[str, float]:
    body = {"client_id": cid, "client_secret": sec}
    r = requests.post(f"{BASE}/token/", data=body, timeout=TIMEOUT,
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    if r.status_code == 400:
        # Some OAuth servers insist on the grant type; harmless to add.
        r = requests.post(f"{BASE}/token/", data={**body, "grant_type": "client_credentials"},
                          timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    tok = str(data.get("access_token") or "")
    if not tok:
        raise RuntimeError("token response had no access_token")
    ttl = float(data.get("expires_in") or 3600)
    return tok, time.time() + max(60.0, ttl - 60.0)


def _bearer(values: dict | None = None) -> dict:
    cid, sec = _creds(values)
    if not cid or not sec:
        raise _NotConfigured
    with _tok_lock:
        if _token["value"] and _token["for"] == cid and time.time() < _token["exp"]:
            return {"Authorization": f"Bearer {_token['value']}"}
        tok, exp = _fetch_token(cid, sec)
        _token.update(value=tok, exp=exp, **{"for": cid})
        return {"Authorization": f"Bearer {tok}"}


class _NotConfigured(Exception):
    pass


def _get(path: str, values: dict | None = None, **params):
    r = requests.get(f"{BASE}{path}", headers=_bearer(values), params=params, timeout=TIMEOUT)
    if r.status_code == 401:
        with _tok_lock:
            _token.update(value="", exp=0.0)
        r = requests.get(f"{BASE}{path}", headers=_bearer(values), params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# ── orders ───────────────────────────────────────────────────────────────────

def _parse_dt(s) -> datetime | None:
    if not s:
        return None
    try:
        s = str(s).replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        return d.astimezone() if d.tzinfo else d
    except Exception:
        return None


def _money(order: dict, key: str = "amount") -> float:
    v = order.get(key)
    try:
        v = float(v or 0.0)
    except Exception:
        return 0.0
    if str(get_plugin_config(NS).get("amounts") or "reais").lower().startswith("cent"):
        v = v / 100.0
    return v


def _fmt(v: float) -> str:
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _iter_orders(values: dict | None = None, stop_before: datetime | None = None):
    """Yield orders newest-first across pages; stop once a page is entirely
    older than `stop_before` (by createdAt) or the cap is hit."""
    page = 1
    while page <= MAX_PAGES:
        data = _get("/orders/", values, page=page)
        results = data.get("results") if isinstance(data, dict) else data
        if not results:
            return
        oldest = None
        for o in results:
            yield o
            c = _parse_dt(o.get("createdAt") or o.get("created_at"))
            if c and (oldest is None or c < oldest):
                oldest = c
        if stop_before and oldest and oldest < stop_before:
            return
        if isinstance(data, dict) and not data.get("next"):
            return
        page += 1


def _is_paid(o: dict) -> bool:
    st = str(o.get("status") or "").lower()
    if o.get("refundedAt") or o.get("chargedbackAt") or o.get("canceledAt"):
        return False
    if st in ("refunded", "chargedback", "chargeback", "canceled", "cancelled", "refused",
              "waiting_payment", "pending", "expired", "abandoned"):
        return False
    return bool(o.get("paidAt") or o.get("paid_at") or st in ("paid", "approved", "completed", "authorized"))


def _net(o: dict) -> float | None:
    """What the account actually receives for the order.

    Cakto lists every commission on the order; the producer's (and co-producer's)
    `commissionValue` is already net of platform fees. Without a commissions
    list, fall back to amount minus `fees`."""
    comms = o.get("commissions")
    if isinstance(comms, list) and comms:
        total, seen = 0.0, False
        for c in comms:
            if not isinstance(c, dict):
                continue
            if str(c.get("type") or "").lower() in ("producer", "coproducer", "co_producer"):
                try:
                    total += float(c.get("commissionValue") or 0.0); seen = True
                except Exception:
                    pass
        if seen:
            return total
    if o.get("fees") is not None:
        return _money(o) - _money(o, "fees")
    return None


def _paid_at(o: dict) -> datetime | None:
    return _parse_dt(o.get("paidAt") or o.get("paid_at") or o.get("approvedDate"))


def revenue(start: datetime, end: datetime, values: dict | None = None) -> dict:
    """Sum of paid orders with paidAt in [start, end)."""
    total, n, by_method, by_product = 0.0, 0, {}, {}
    net_total, net_seen = 0.0, False
    # Orders are paid at most a few days after creation (boleto); walk a bit
    # further back than the period start before stopping.
    for o in _iter_orders(values, stop_before=start - timedelta(days=10)):
        if not _is_paid(o):
            continue
        p = _paid_at(o)
        if not p or not (start <= p < end):
            continue
        amt = _money(o)
        total += amt; n += 1
        pm = str(o.get("paymentMethod") or o.get("payment_method") or "?").lower()
        by_method[pm] = by_method.get(pm, 0.0) + amt
        prod = o.get("product")
        pname = (prod.get("name") if isinstance(prod, dict) else str(prod or "")) or "?"
        by_product[pname] = by_product.get(pname, 0.0) + amt
        nv = _net(o)
        if nv is not None:
            net_total += nv; net_seen = True
    return {"total": total, "count": n, "by_method": by_method, "by_product": by_product,
            "net": net_total if net_seen else None}


def _month_bounds(ym: str | None) -> tuple[datetime, datetime, str]:
    today = date.today()
    if ym:
        y, m = (int(x) for x in ym.strip()[:7].split("-"))
    else:
        y, m = today.year, today.month
    start = datetime(y, m, 1).astimezone()
    end = (datetime(y + 1, 1, 1) if m == 12 else datetime(y, m + 1, 1)).astimezone()
    names = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
             "setembro", "outubro", "novembro", "dezembro"]
    return start, end, f"{names[m - 1]} de {y}"


def _describe(rep: dict, label: str, show, cards=None) -> str:
    if rep["count"] == 0:
        if cards:
            cards([{"title": f"CAKTO · {label}".upper(), "value": 0, "fmt": "money",
                    "lines": ["nenhuma venda paga"], "hold": 20}])
        return f"Nenhuma venda paga em {label}."
    top = sorted(rep["by_product"].items(), key=lambda kv: -kv[1])[:3]
    methods = ", ".join(f"{k}: {_fmt(v)}" for k, v in sorted(rep["by_method"].items(), key=lambda kv: -kv[1]))
    panel = [f"Faturamento — {label}", f"Bruto: {_fmt(rep['total'])}  ({rep['count']} vendas pagas)"]
    if rep["net"] is not None:
        panel.append(f"Líquido (comissão de produtor, já sem taxas): {_fmt(rep['net'])}")
    panel.append("Por meio: " + methods)
    panel.append("Por produto:")
    for k, v in sorted(rep["by_product"].items(), key=lambda kv: -kv[1])[:10]:
        panel.append(f"  • {k}: {_fmt(v)}")
    if cards:
        seq = [{"title": f"CAKTO · FATURAMENTO {label}".upper(), "value": rep["total"], "fmt": "money",
                "lines": [f"{rep['count']} vendas pagas"]
                         + ([f"líquido: {_fmt(rep['net'])}"] if rep["net"] is not None else [])
                         + [f"{k}: {_fmt(v)}" for k, v in sorted(rep["by_method"].items(), key=lambda kv: -kv[1])[:3]],
                "hold": 30}]
        if top:
            seq.append({"title": "PRINCIPAIS PRODUTOS",
                        "lines": [f"{k}: {_fmt(v)}" for k, v in top],
                        "keys": ["principais produtos", "produto"], "hold": 30})
        cards(seq)
    show("CAKTO — FATURAMENTO", "\n".join(panel))
    s = f"Faturamento de {label}: {_fmt(rep['total'])} em {rep['count']} venda{'s' if rep['count'] != 1 else ''}"
    if rep["net"] is not None:
        s += f", líquido {_fmt(rep['net'])}"
    if top:
        s += ". Principais produtos: " + ", ".join(f"{k} ({_fmt(v)})" for k, v in top)
    return s + "."


# ── settings panel ───────────────────────────────────────────────────────────

def _test(values: dict):
    cid, sec = _creds(values)
    if not cid or not sec:
        return False, "Enter client_id and client_secret first."
    try:
        with _tok_lock:
            _token.update(value="", exp=0.0)
        data = _get("/orders/", values, page=1)
        results = data.get("results") if isinstance(data, dict) else data
        n = data.get("count") if isinstance(data, dict) else len(results or [])
        if not results:
            return True, f"Connected. {n or 0} orders on the account (none to inspect yet)."
        o = results[0]
        keys = ", ".join(sorted(k for k in o.keys()))
        report = (f"Connected. {n} orders on the account. Newest: status={o.get('status')}, "
                  f"amount={o.get('amount')}, paidAt={o.get('paidAt')}. Fields: {keys}")
        _save_report(report, o)
        return True, (f"Conectado: {n} pedidos. Detalhes salvos em {REPORT_FILE} "
                      f"(mande esse arquivo para ajustar o plugin).")
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        body = (e.response.text[:160] if e.response is not None else "")
        return False, f"Cakto answered {code}: {body}"
    except Exception as e:
        return False, f"Connection failed: {e}"


import os
REPORT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "memory", "cakto_teste.txt")


def _save_report(report: str, sample: dict) -> None:
    """Write the connection report plus one order with long strings and e-mails
    masked, so the user can share it without exposing customer data."""
    try:
        import json
        PRIVATE = ("customer", "address", "shipping", "commissionedUsers", "checkoutUrl", "sck")
        masked = {}
        for k, v in sample.items():
            if k in PRIVATE:
                masked[k] = "…" if v is not None else None       # personal data: never written
            elif isinstance(v, dict):
                masked[k] = {kk: ("…" if isinstance(vv, str) and (len(vv) > 24 or "@" in vv) else vv)
                             for kk, vv in v.items()}
            elif isinstance(v, str) and ("@" in v or len(v) > 40):
                masked[k] = "…"
            else:
                masked[k] = v
        os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
        with open(REPORT_FILE, "w", encoding="utf-8") as fh:
            fh.write(report + "\n\nExemplo de pedido (textos longos e e-mails ocultados):\n")
            fh.write(json.dumps(masked, ensure_ascii=False, indent=2, default=str))
    except Exception:
        pass


PLUGIN_SETTINGS = {
    "namespace": NS,
    "title": "CAKTO (sales platform)",
    "fields": [
        {"key": "client_id", "label": "Client ID", "type": "password",
         "placeholder": "from Cakto → API keys (scopes: orders, products)"},
        {"key": "client_secret", "label": "Client secret", "type": "password",
         "placeholder": "shown once when the key is created"},
        {"key": "amounts", "label": "Amounts in the API are in", "type": "choice",
         "options": ["reais", "centavos"], "default": "reais"},
    ],
    "action": {"label": "TEST CONNECTION", "run": _test},
}


# ── the tool ─────────────────────────────────────────────────────────────────

def run(parameters: dict, player=None, session_memory=None) -> str:
    def show(title: str, text: str) -> None:
        if player is not None and hasattr(player, "show_content"):
            try:
                player.show_content(title, text)
            except Exception:
                pass
    def cards(seq) -> None:
        if player is not None and hasattr(player, "holo_cards"):
            try:
                player.holo_cards(seq)
            except Exception:
                pass
    action = (parameters.get("action") or "month_revenue").strip().lower()
    try:
        if action == "month_revenue":
            start, end, label = _month_bounds(parameters.get("month"))
            return _describe(revenue(start, end), label, show, cards)
        if action == "today_revenue":
            start = datetime.combine(date.today(), datetime.min.time()).astimezone()
            return _describe(revenue(start, start + timedelta(days=1)), "hoje", show, cards)
        if action == "last_orders":
            limit = int(parameters.get("limit") or 5)
            rows = []
            for o in _iter_orders():
                p = _paid_at(o) or _parse_dt(o.get("createdAt"))
                prod = o.get("product"); pname = prod.get("name") if isinstance(prod, dict) else str(prod or "")
                rows.append(f"{p.strftime('%d/%m %H:%M') if p else '--'}  {_fmt(_money(o))}  "
                            f"{o.get('status')}  {pname}")
                if len(rows) >= limit:
                    break
            show("CAKTO — ÚLTIMAS VENDAS", "\n".join(rows) or "Nenhuma.")
            return ("Nenhuma venda encontrada." if not rows else
                    f"Últimas {len(rows)} vendas: " + "; ".join(rows))
        if action == "products":
            data = _get("/products/")
            results = data.get("results") if isinstance(data, dict) else data
            names = [str(p.get("name") or p.get("id")) for p in (results or [])]
            return "Produtos: " + ", ".join(names[:15]) if names else "Nenhum produto."
        return f"Unknown Cakto action '{action}'."
    except _NotConfigured:
        return ("Cakto is not set up yet. Open the gear, PLUGIN SETTINGS, CAKTO, and enter "
                "the client_id and client_secret.")
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        if code in (401, 403):
            return "Cakto rejected the credentials or the scope. Check them in PLUGIN SETTINGS."
        return f"Cakto answered with an error ({code})."
    except requests.RequestException as e:
        return f"Could not reach Cakto: {e.__class__.__name__}."
    except Exception as e:
        return f"Cakto plugin failed: {e}"
