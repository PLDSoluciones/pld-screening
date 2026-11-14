"""Motor de coincidencias: identificadores exactos + nombres difusos con corroboración.

Diseño (reduce falsos positivos y falsos negativos a la vez):
  1. Identificadores (RFC completo, RFC base-10 de persona física, CURP) → coincidencia EXACTA.
  2. Nombres: se recuperan candidatos con rapidfuzz (token_set) y con índice fonético
     (esqueleto consonántico) y se re-puntúan con un alineamiento token-a-token que exige
     cobertura de AMBOS lados (media armónica), tolera orden, acentos, partículas (DE/DEL/LA),
     formas societarias (S.A. DE C.V.), iniciales, transliteraciones y espacios/guiones (AL-QAIDA).
  3. Corroboración: fecha de nacimiento (sube/baja nivel) y tipo de persona (F/M).
  4. Cada coincidencia lleva su explicación (razones) para el expediente.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

from rapidfuzz import fuzz, process
from rapidfuzz.distance import DamerauLevenshtein

from .normalize import (dob_compare, name_tokens, normalize_curp, normalize_rfc, parse_dob, skeleton)

LEVELS = ["BAJA", "MEDIA", "ALTA", "EXACTA"]


def level_rank(level: str) -> int:
    return LEVELS.index(level)


@dataclass
class Query:
    name: str = ""
    entity_type: str | None = None  # 'F' persona física, 'M' persona moral
    rfc: str | None = None
    curp: str | None = None
    dob: str | None = None
    country: str | None = None


@dataclass
class Match:
    entry_id: int
    source_code: str
    external_id: str
    matched_name: str
    name_kind: str
    score: float
    level: str
    reasons: list[str] = field(default_factory=list)
    entry: dict = field(default_factory=dict)
    entry_hash: str | None = None  # para coincidencias externas (sin registro local)

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id, "fuente": self.source_code, "id_externo": self.external_id,
            "nombre_coincidente": self.matched_name, "tipo_nombre": self.name_kind,
            "puntaje": round(self.score, 1), "nivel": self.level, "razones": self.reasons,
            "registro": self.entry,
        }


@lru_cache(maxsize=500_000)
def tok_sim(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if len(a) == 1 or len(b) == 1:  # inicial vs. nombre completo
        return 0.8 if a[0] == b[0] else 0.0
    s = DamerauLevenshtein.normalized_similarity(a, b)
    sa, sb = skeleton(a), skeleton(b)
    if sa == sb and len(sa) >= 3 and min(len(a), len(b)) >= 4:
        s = max(s, 0.9)
    return s if s >= 0.75 else 0.0


def name_score(qt: tuple[str, ...], ct: tuple[str, ...]) -> float:
    if not qt or not ct:
        return 0.0
    pairs = []
    for i, a in enumerate(qt):
        for j, b in enumerate(ct):
            s = tok_sim(a, b)
            if s > 0:
                pairs.append((s, i, j))
    pairs.sort(reverse=True)
    uq, uc = set(), set()
    mq, mc = [0.0] * len(qt), [0.0] * len(ct)
    for s, i, j in pairs:
        if i in uq or j in uc:
            continue
        uq.add(i)
        uc.add(j)
        mq[i] = s
        mc[j] = s
    wq = sum(len(t) for t in qt)
    wc = sum(len(t) for t in ct)
    cq = sum(len(t) * m for t, m in zip(qt, mq)) / wq
    cc = sum(len(t) * m for t, m in zip(ct, mc)) / wc
    # Omitir UN segundo nombre es muy común (RAMON QUINTERO SALAS vs RAMON ALBERTO QUINTERO SALAS):
    # si un lado queda 100 % cubierto, hay ≥3 tokens coincidentes y sobra a lo más 1 token, se suaviza la penalización.
    strong = sum(1 for m in mq if m >= 0.9)
    if strong >= 3:
        if cq >= 0.98 and len(ct) - strong <= 1:
            cc = cc + (1 - cc) * 0.35
        elif cc >= 0.98 and len(qt) - strong <= 1:
            cq = cq + (1 - cq) * 0.35
    own = 0.0 if cq + cc == 0 else 200 * cq * cc / (cq + cc)
    jq, jc = "".join(qt), "".join(ct)
    compact = fuzz.ratio(jq, jc) if min(len(jq), len(jc)) >= 6 else 0.0
    return max(own, compact)


class Index:
    """Índice en memoria de los registros activos de todas las listas."""

    def __init__(self, entries: list[dict], th_alta=93.0, th_media=85.0, th_baja=78.0):
        self.th_alta, self.th_media, self.th_baja = th_alta, th_media, th_baja
        self.entries: dict[int, dict] = {}
        self.choices: list[str] = []
        self.n_tokens: list[tuple[str, ...]] = []
        self.n_entry: list[int] = []
        self.n_kind: list[str] = []
        self.n_raw: list[str] = []
        self.rfc: dict[str, list[int]] = defaultdict(list)
        self.rfc10: dict[str, list[int]] = defaultdict(list)
        self.curp: dict[str, list[int]] = defaultdict(list)
        self.phon: dict[str, set[int]] = defaultdict(set)
        for e in entries:
            self.add(e)

    def add(self, e: dict) -> None:
        eid = e["id"]
        self.entries[eid] = e
        org = True if e.get("entity_type") == "M" else (False if e.get("entity_type") == "F" else None)
        for raw, kind in e["names"]:
            toks = name_tokens(raw, org)
            if not toks:
                continue
            idx = len(self.choices)
            self.choices.append(" ".join(toks))
            self.n_tokens.append(toks)
            self.n_entry.append(eid)
            self.n_kind.append(kind)
            self.n_raw.append(raw)
            for t in toks:
                sk = skeleton(t)
                if len(sk) >= 3:
                    self.phon[sk].add(idx)
        r = normalize_rfc(e.get("rfc"))
        if r:
            self.rfc[r].append(eid)
            if len(r) == 13:
                self.rfc10[r[:10]].append(eid)
            else:
                self.rfc10[r[:9]].append(eid)
        c = normalize_curp(e.get("curp"))
        if c:
            self.curp[c].append(eid)

    def __len__(self) -> int:
        return len(self.entries)

    # ------------------------------------------------------------------ búsqueda
    def search(self, q: Query, min_score: float | None = None, max_results: int = 25) -> list[Match]:
        min_score = self.th_baja if min_score is None else min_score
        best: dict[int, Match] = {}

        def put(m: Match) -> None:
            cur = best.get(m.entry_id)
            if cur is None or (level_rank(m.level), m.score) > (level_rank(cur.level), cur.score):
                best[m.entry_id] = m

        # 1) Identificadores
        rfc, curp = normalize_rfc(q.rfc), normalize_curp(q.curp)
        if rfc:
            for eid in self.rfc.get(rfc, []):
                put(self._mk(eid, "RFC", "identificador", 100.0, "EXACTA", [f"RFC coincide exactamente ({rfc})"]))
            key = rfc[:10] if len(rfc) == 13 else rfc[:9]
            for eid in self.rfc10.get(key, []):
                if eid not in best:
                    put(self._mk(eid, "RFC", "identificador", 96.0, "ALTA",
                                 [f"RFC base ({key}) coincide; homoclave/dígito difieren o no disponibles"]))
        if curp:
            for eid in self.curp.get(curp, []):
                put(self._mk(eid, "CURP", "identificador", 100.0, "EXACTA", [f"CURP coincide exactamente ({curp})"]))

        # 2) Nombres
        org = True if q.entity_type == "M" else (False if q.entity_type == "F" else None)
        qt = name_tokens(q.name, org) if q.name else ()
        if qt:
            qn = " ".join(qt)
            cand: set[int] = set()
            for _, _, i in process.extract(qn, self.choices, scorer=fuzz.token_set_ratio,
                                           score_cutoff=60, limit=600):
                cand.add(i)
            hits: Counter = Counter()
            for t in qt:
                sk = skeleton(t)
                if len(sk) >= 3:
                    for i in self.phon.get(sk, ()):
                        hits[i] += 1
            need = 1 if len(qt) == 1 else 2
            cand.update(i for i, n in hits.items() if n >= need)

            qdob = parse_dob(q.dob)
            for i in cand:
                ct = self.n_tokens[i]
                sc = name_score(qt, ct)
                if sc < min_score - 15:
                    continue
                e = self.entries[self.n_entry[i]]
                reasons = []
                et = e.get("entity_type")
                is_person = (q.entity_type == "F") or (q.entity_type is None and et == "F")
                if is_person and (len(qt) == 1 or len(ct) == 1) and sc > 84:
                    sc = 84.0
                    reasons.append("Nombre de un solo elemento: nivel limitado, requiere dato adicional")
                if q.entity_type and et and q.entity_type != et and et in ("F", "M"):
                    sc -= 8
                    reasons.append(f"Tipo de persona distinto (consulta={q.entity_type}, lista={et})")
                # corroboración por fecha de nacimiento
                bonus = 0.0
                if qdob:
                    res = [dob_compare(qdob, parse_dob(d)) for d in e.get("dobs", [])]
                    res = [r for r in res if r]
                    if "full" in res:
                        bonus = 5.0
                        reasons.append("Fecha de nacimiento coincide completa")
                    elif "year" in res:
                        bonus = 2.0
                        reasons.append("Año de nacimiento coincide")
                    elif res and all(r == "mismatch" for r in res):
                        bonus = -15.0
                        reasons.append("Fecha de nacimiento NO coincide (posible homónimo)")
                total = max(0.0, min(99.0, sc + bonus))
                if total < min_score:
                    continue
                level = "ALTA" if total >= self.th_alta else "MEDIA" if total >= self.th_media else "BAJA"
                reasons.insert(0, f"Similitud de nombre {sc:.0f}/100 (“{self.n_raw[i]}” vs “{q.name}”)")
                put(self._mk(self.n_entry[i], self.n_raw[i], self.n_kind[i], total, level, reasons))

        out = sorted(best.values(), key=lambda m: (-level_rank(m.level), -m.score))
        return out[:max_results]

    def _mk(self, eid: int, name: str, kind: str, score: float, level: str, reasons: list[str]) -> Match:
        e = self.entries[eid]
        if name in ("RFC", "CURP"):
            name = e["primary_name"]
        return Match(eid, e["source_code"], e["external_id"], name, kind, score, level, reasons, self._summary(e))

    @staticmethod
    def _summary(e: dict) -> dict:
        return {k: e.get(k) for k in ("primary_name", "entity_type", "rfc", "curp", "dobs", "country",
                                      "program", "status", "remarks") if e.get(k) not in (None, [], "")}
