"""Normalización de nombres, identificadores y fechas (español/árabe/inglés)."""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

STOP_TOKENS = {"DE", "DEL", "LA", "LAS", "LOS", "Y", "E", "VDA", "DA", "DAS", "DOS", "DI", "VAN", "VON", "DER"}

# Formas societarias que se eliminan al final del nombre de personas morales.
_LEGAL_FORMS = [
    "S A P I B DE C V", "S A P I DE C V", "SAPI DE CV", "SAPI B DE CV", "S A B DE C V", "SAB DE CV",
    "S DE R L DE C V", "S DE RL DE CV", "S DE R L", "S A DE C V", "SA DE CV", "S A P I", "SAPI", "SAB",
    "S R L DE C V", "SRL DE CV", "S C", "S A S", "SAS", "S A", "SA", "CV", "C V", "A C", "AC", "S R L", "SRL",
    "L L C", "LLC", "L T D", "LTD", "LIMITED", "INC", "CORP", "CORPORATION", "CO", "GMBH", "S P A", "SPA",
    "S A S DE C V", "SOCIEDAD ANONIMA", "SOCIEDAD CIVIL", "ASOCIACION CIVIL", "DE RL", "R L",
]
_LEGAL_SEQS = sorted((f.split() for f in _LEGAL_FORMS), key=len, reverse=True)

_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def clean(s: str) -> str:
    s = strip_accents(s or "").upper()
    s = s.replace("'", "").replace("`", "").replace("’", "")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_STRONG_SINGLE = {"SAPI", "SAB", "SRL", "LLC", "LTD", "INC", "CORP", "GMBH", "SAS", "SPA", "LIMITED", "CORPORATION"}
_STRONG_SEQS = [q for q in _LEGAL_SEQS if len(q) >= 3 or (len(q) == 1 and q[0] in _STRONG_SINGLE)
                or q in (["S", "A"], ["SA", "DE", "CV"], ["L", "L", "C"], ["S", "R", "L"])]


def _strip_legal(tokens: list[str], strong_only: bool = False, leading: bool = False) -> list[str]:
    """Quita la forma societaria al final y, si leading=True (persona moral conocida), también al inicio
    (p. ej. «S.A. DE C.V. GRUPO X» capturado al revés), tolerando conectores «DE» sueltos."""
    seqs = _STRONG_SEQS if strong_only else _LEGAL_SEQS
    changed = True
    while changed and len(tokens) > 1:
        changed = False
        for seq in seqs:
            n = len(seq)
            if len(tokens) > n and tokens[-n:] == seq:
                tokens = tokens[:-n]
                changed = True
                break
            if leading and len(tokens) > n and tokens[:n] == seq:
                tokens = tokens[n:]
                changed = True
                break
        if leading and not changed:
            if len(tokens) > 1 and tokens[0] in ("DE", "Y"):
                tokens, changed = tokens[1:], True
            elif len(tokens) > 1 and tokens[-1] in ("DE", "Y"):
                tokens, changed = tokens[:-1], True
    return tokens


def is_org_name(name: str) -> bool:
    toks = clean(name).split()
    return len(toks) > 1 and _strip_legal(list(toks), True) != toks


@lru_cache(maxsize=200_000)
def name_tokens(name: str, org: bool | None = None) -> tuple[str, ...]:
    """Tokens normalizados. org=None → se detecta por forma societaria."""
    toks = clean(name).split()
    if org is None:
        toks = _strip_legal(list(toks), strong_only=True)
    elif org:
        toks = _strip_legal(list(toks), leading=True)
    toks = [t for t in toks if t not in STOP_TOKENS] or toks
    return tuple(toks)


def normalize_name(name: str, org: bool | None = None) -> str:
    return " ".join(name_tokens(name, org))


_PHON = [
    (r"SCH", "S"), (r"CH", "X"), (r"SH", "X"), (r"KH", "K"), (r"PH", "F"), (r"GH", "G"), (r"TH", "T"),
    (r"QU", "K"), (r"GU(?=[EI])", "G"), (r"G(?=[EI])", "J"), (r"C(?=[EI])", "S"), (r"C", "K"), (r"Q", "K"),
    (r"Z", "S"), (r"V", "B"), (r"W", "B"), (r"LL", "Y"), (r"Y", "I"), (r"OU", "U"), (r"H", ""),
]


@lru_cache(maxsize=200_000)
def skeleton(token: str) -> str:
    """Clave fonética 'esqueleto consonántico' (tolera MOHAMED/MUHAMMAD, JOSE/YOSE, KATIA/CATIA)."""
    t = token
    for pat, rep in _PHON:
        t = re.sub(pat, rep, t)
    if not t:
        return ""
    out = [t[0]]
    prev = t[0]
    for ch in t[1:]:
        if ch not in "AEIOU" and ch != prev:
            out.append(ch)
        prev = ch
    return "".join(out)


# ---------------------------------------------------------------- identificadores
def normalize_rfc(rfc: str | None) -> str | None:
    if not rfc:
        return None
    r = re.sub(r"[^A-Z0-9&Ñ]", "", rfc.upper().replace(" ", ""))
    return r if len(r) in (12, 13) else None


def normalize_curp(curp: str | None) -> str | None:
    if not curp:
        return None
    c = re.sub(r"[^A-Z0-9]", "", curp.upper())
    return c if len(c) == 18 else None


# ---------------------------------------------------------------- fechas
def parse_dob(s: str | None) -> tuple[int | None, int | None, int | None] | None:
    """Devuelve (año, mes, día) con None en lo desconocido."""
    if not s:
        return None
    s = str(s).strip().upper()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return int(m[1]), int(m[2]), int(m[3])
    m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", s)
    if m:
        return int(m[3]), int(m[2]), int(m[1])
    m = re.search(r"(\d{1,2})\s+([A-Z]{3})[A-Z]*\s+(\d{4})", s)
    if m and m[2] in _MONTHS:
        return int(m[3]), _MONTHS[m[2]], int(m[1])
    m = re.search(r"([A-Z]{3})[A-Z]*\s+(\d{4})", s)
    if m and m[1] in _MONTHS:
        return int(m[2]), _MONTHS[m[1]], None
    m = re.search(r"\b(1[89]\d{2}|20\d{2})\b", s)
    if m:
        return int(m[1]), None, None
    return None


def dob_compare(a, b) -> str | None:
    """'full' | 'year' | 'mismatch' | None (sin dato comparable)."""
    if not a or not b or a[0] is None or b[0] is None:
        return None
    if a[0] != b[0]:
        return "mismatch"
    if a[1] and b[1] and a[2] and b[2]:
        return "full" if (a[1], a[2]) == (b[1], b[2]) else "mismatch"
    return "year"
