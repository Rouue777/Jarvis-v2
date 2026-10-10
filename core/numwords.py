"""
Numbers → Portuguese words, for the voice.

A speech voice stumbles on "380.789,00" (reads the dots as pauses, the comma
as "vírgula", or spells digits). Screens keep the digits; whatever is sent to
a voice goes through `speakable()` first, which rewrites money and large
numbers as words: "R$ 380.789,00" → "trezentos e oitenta mil, setecentos e
oitenta e nove reais". Times (22h00, 10:30), dates (10/10/2026), small counts
(896 vendas) and codes (#37) are left alone — voices read those fine.
"""
from __future__ import annotations

import re

_UNI = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
        "onze", "doze", "treze", "catorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
_DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_CEN = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos",
        "setecentos", "oitocentos", "novecentos"]


def _grupo(n: int) -> str:
    """1..999 in Portuguese words."""
    if n == 100:
        return "cem"
    c, r = divmod(n, 100)
    d, u = divmod(r, 10)
    parts = []
    if c:
        parts.append(_CEN[c])
    if r:
        if r < 20:
            parts.append(_UNI[r])
        else:
            parts.append(_DEZ[d] + (f" e {_UNI[u]}" if u else ""))
    return " e ".join(parts)


def extenso(n: int) -> str:
    """Whole number in Portuguese words (voices read '374.105' badly; they
    read 'trezentos e setenta e quatro mil cento e cinco' perfectly)."""
    n = int(n)
    total = n
    if n == 0:
        return "zero"
    groups = []                                   # (value, singular, plural)
    for div, sing, plur in ((10 ** 9, "bilhão", "bilhões"), (10 ** 6, "milhão", "milhões"),
                            (10 ** 3, "mil", "mil")):
        q, n = divmod(n, div)
        if q:
            if div == 1000:
                groups.append("mil" if q == 1 else f"{_grupo(q)} mil")
            else:
                groups.append(f"um {sing}" if q == 1 else f"{_grupo(q)} {plur}")
    # Commas between the magnitude groups give the voice a beat to breathe:
    # "trezentos e setenta e nove mil, novecentos e oitenta e três".
    if n:
        # The pause (comma) only earns its place from five digits up; "mil
        # duzentos e cinquenta" flows better without it.
        big = total >= 10000
        sep = " e " if (n < 100 or n % 100 == 0) and groups else (", " if big else " ")
        return sep.join([(", " if big else " ").join(groups), _grupo(n)]) if groups else _grupo(n)
    return " e ".join(groups) if len(groups) > 1 else groups[0]


def reais(v: float, cents: bool = True) -> str:
    """Money for the voice: 'trezentos e setenta e três mil e oitocentos e
    noventa reais' (+ 'e setenta centavos' when cents=True and non-zero)."""
    v = float(v or 0)
    inteiro = int(v)
    cent = int(round((v - inteiro) * 100))
    if cent == 100:
        inteiro, cent = inteiro + 1, 0
    palavras = extenso(inteiro)
    de = " de" if palavras.endswith(("milhão", "milhões", "bilhão", "bilhões")) else ""
    txt = f"{palavras}{de} {'real' if inteiro == 1 else 'reais'}"
    if cents and cent:
        txt += f" e {extenso(cent)} centavo{'s' if cent != 1 else ''}"
    return txt




# money first (so the number inside it is not matched twice), then bare
# numbers with thousands separators or 5+ digits. Not preceded/followed by
# things that make it a time, date, version or code.
_TAIL = r"(?![\w/:-])(?!\.\d)(?!,\d)"      # not part of a longer number, time, date or code
_MONEY = re.compile(r"(?<![\w/:.,-])R\$\s?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?" + _TAIL)
_NUM = re.compile(r"(?<![\w/:.,#-])(\d{1,3}(?:\.\d{3})+|\d{5,})(?:,(\d{1,2}))?" + _TAIL)
_TRAIL_REAIS = re.compile(r"^\s*(reais|real)\b", re.IGNORECASE)


def _to_int(s: str) -> int:
    return int(s.replace(".", ""))


def hybrid(n: int) -> str:
    """Digits in short groups with the magnitude words: 386855 → "386 mil 855".
    A cloned voice reads three-digit numbers reliably but trips over a long
    run of number words; this keeps every piece short."""
    n = int(n)
    if n < 1000:
        return str(n)
    parts = []
    bi, n = divmod(n, 10 ** 9)
    mi, n = divmod(n, 10 ** 6)
    mil, rest = divmod(n, 1000)
    if bi:
        parts.append(f"{bi} {'bilhão' if bi == 1 else 'bilhões'}")
    if mi:
        parts.append(f"{mi} {'milhão' if mi == 1 else 'milhões'}")
    if mil:
        parts.append("mil" if mil == 1 else f"{mil} mil")
    if rest:
        parts.append(f"e {rest}" if (rest < 100 or rest % 100 == 0) else str(rest))
    return " ".join(parts)


def reais_hybrid(v: float, cents: bool = True) -> str:
    v = float(v or 0)
    inteiro = int(v)
    cent = int(round((v - inteiro) * 100))
    if cent == 100:
        inteiro, cent = inteiro + 1, 0
    w = hybrid(inteiro)
    de = " de" if w.endswith(("milhão", "milhões", "bilhão", "bilhões")) else ""
    txt = f"{w}{de} {'real' if inteiro == 1 else 'reais'}"
    if cents and cent:
        txt += f" e {cent} centavo{'s' if cent != 1 else ''}"
    return txt


def speakable(text: str, style: str = "words") -> str:
    """Rewrite money and big numbers in `text` for a voice. style="words"
    spells them out fully; style="hybrid" keeps digits in short groups
    ("386 mil 855 reais"), which cloned voices pronounce more reliably."""
    if not text or not any(ch.isdigit() for ch in text):
        return text
    money_fn = reais_hybrid if style == "hybrid" else reais
    int_fn = hybrid if style == "hybrid" else extenso

    def money(m):
        whole = _to_int(m.group(1))
        cents = int((m.group(2) or "0").ljust(2, "0"))
        return money_fn(whole + cents / 100.0, cents=bool(cents))

    out = _MONEY.sub(money, text)

    def number(m):
        whole = _to_int(m.group(1))
        cents = m.group(2)
        rest = out[m.end():]
        if _TRAIL_REAIS.match(rest):                # "380789,00 reais" → words + (the word stays)
            c = int((cents or "0").ljust(2, "0"))
            w = money_fn(whole + c / 100.0, cents=bool(c))
            return w[: -len(" reais")] if w.endswith(" reais") else w
        if cents:
            c = int(cents.ljust(2, "0"))
            return int_fn(whole) + (f" vírgula {c}" if c else "")
        return int_fn(whole)

    return _NUM.sub(number, out)


def money_text(v: float, cents: bool = True) -> str:
    """Money for a TOOL RESULT or briefing line, i.e. text a model will read
    aloud. With Gemini Live the model is the voice, so it gets words. With the
    economy brain the voice is a separate step that converts digits itself
    (per engine), so the model gets plain digits it will copy faithfully."""
    try:
        from memory.config_manager import get_brain_engine
        economy = get_brain_engine() == "economy"
    except Exception:
        economy = False
    if economy:
        v = float(v or 0)
        s = f"{v:,.2f}" if cents else f"{int(v):,}"
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {s}"
    return reais(v, cents=cents)
