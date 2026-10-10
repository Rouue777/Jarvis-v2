"""
Gemini accounts — the fallback keys, and a test for each.

The PRIMARY key is the one the setup screen asked for (gemini_api_key). The
keys entered here are used ONLY while the primary is resting after a failure
(quota, prepaid credit gone, or key rejected); the primary is tried again
after its rest period. See core/gemini.py for the rest lengths.

    ⚙ → PLUGIN SETTINGS → GEMINI ACCOUNTS → secondary / tertiary key → TEST
"""
from core.gemini import api_keys, key_status

NAMESPACE = "gemini"

PLUGIN = {
    "name": "gemini_accounts_status",
    "description": (
        "Reports which Gemini account is in use (primary or a fallback), which "
        "ones are resting after a quota/credit failure and for how long. Use when "
        "the user asks which Gemini key/account is active or why the fallback is "
        "being used."
    ),
    "parameters": {"type": "OBJECT", "properties": {}, "required": []},
}


def _test(values: dict):
    import requests
    results = []
    for label in ("secondary_key", "tertiary_key"):
        key = str(values.get(label) or "").strip()
        if not key:
            continue
        try:
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                             params={"key": key, "pageSize": 1}, timeout=12)
            if r.status_code == 400 and "API key not valid" in r.text:
                results.append(f"{label.split('_')[0]}: rejected")
            elif r.status_code >= 400:
                results.append(f"{label.split('_')[0]}: HTTP {r.status_code}")
            else:
                results.append(f"{label.split('_')[0]}: OK")
        except Exception as e:
            results.append(f"{label.split('_')[0]}: {e.__class__.__name__}")
    if not results:
        return False, "Enter at least a secondary key."
    ok = all(x.endswith("OK") for x in results)
    return ok, "; ".join(results) + f". Keys configured in total: {len(api_keys(refresh=True))}."


PLUGIN_SETTINGS = {
    "namespace": NAMESPACE,
    "title": "GEMINI ACCOUNTS (fallbacks — used only when the primary fails)",
    "fields": [
        {"key": "secondary_key", "label": "Secondary Gemini key", "type": "password",
         "placeholder": "AIza… from another AI Studio project"},
        {"key": "tertiary_key", "label": "Third Gemini key (optional)", "type": "password",
         "placeholder": "AIza…"},
    ],
    "action": {"label": "TEST KEYS", "run": _test},
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    return "Gemini accounts — " + key_status() + "."
