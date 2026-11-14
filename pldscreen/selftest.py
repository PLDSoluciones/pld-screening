"""Autoprueba con DATOS REALES: toma registros de las listas ya cargadas (OFAC, ONU, SAT, LPB…), les genera
variantes típicas de captura y verifica que el motor los encuentre. Sirve para validar su instalación el día 1
y después de cada cambio de umbrales:  python -m pldscreen selftest"""
from __future__ import annotations

import random
import unicodedata
from collections import defaultdict

from .matching import Query, level_rank
from .normalize import name_tokens


def _typo(tok: str, rnd: random.Random) -> str:
    i = rnd.randrange(1, len(tok) - 1)
    return tok[:i] + tok[i + 1] + tok[i] + tok[i + 2:] if rnd.random() < .5 else tok[:i] + tok[i + 1:]


def run(svc, n_per_source: int = 150, seed: int = 1) -> dict:
    rnd = random.Random(seed)
    idx = svc.index()
    groups = defaultdict(list)  # tokens ordenados → ids (homónimos exactos cuentan como acierto)
    by_source = defaultdict(list)
    for eid, e in idx.entries.items():
        org = True if e["entity_type"] == "M" else (False if e["entity_type"] == "F" else None)
        toks = name_tokens(e["primary_name"], org)
        groups[tuple(sorted(toks))].append(eid)
        if len(toks) >= 2:
            by_source[e["source_code"]].append((eid, e, toks))
    report: dict = {}
    for src, items in by_source.items():
        sample = rnd.sample(items, min(n_per_source, len(items)))
        stats: dict[str, list[bool]] = defaultdict(list)
        for eid, e, toks in sample:
            et = e["entity_type"]
            raw = e["primary_name"]
            ok_ids = set(groups[tuple(sorted(toks))])
            variants = {
                "exacto": raw,
                "orden invertido": " ".join(reversed(raw.split())),
                "sin acentos/minúsculas": "".join(c for c in unicodedata.normalize("NFD", raw.lower())
                                                  if not unicodedata.combining(c)),
            }
            if len(toks) >= 4:
                variants["sin un nombre intermedio"] = " ".join(list(toks[:1]) + list(toks[2:]))
            long_tok = [t for t in toks if len(t) >= 5]
            if long_tok:
                t = rnd.choice(long_tok)
                variants["errata de captura"] = " ".join(_typo(x, rnd) if x == t else x for x in toks)
            for k, v in variants.items():
                ms = idx.search(Query(name=v, entity_type=et))
                stats[k].append(any(m.entry_id in ok_ids and level_rank(m.level) >= level_rank("MEDIA") for m in ms))
            if e.get("rfc"):
                ms = idx.search(Query(name="NOMBRE QUE NO COINCIDE", rfc=e["rfc"]))
                stats["solo RFC"].append(any(m.entry_id == eid and m.level == "EXACTA" for m in ms))
        report[src] = {k: {"n": len(v), "recall": round(100 * sum(v) / len(v), 1)} for k, v in stats.items()}
    # control negativo: nombres armados con tokens reales mezclados de entradas distintas
    all_toks = [t for items in by_source.values() for _, _, toks in items for t in toks]
    fp = tot = 0
    for _ in range(300 if all_toks else 0):
        q = " ".join(rnd.sample(all_toks, 3))
        ms = idx.search(Query(name=q, entity_type="F"))
        fp += any(level_rank(m.level) >= level_rank("MEDIA") for m in ms)
        tot += 1
    report["_control_negativo"] = {"consultas": tot, "con_alerta_MEDIA_o_mayor": fp,
                                   "porcentaje": round(100 * fp / tot, 1) if tot else None}
    base = [v["recall"] for s, d in report.items() if not s.startswith("_")
            for k, v in d.items() if k in ("exacto", "orden invertido", "sin acentos/minúsculas")]
    report["_aprobado"] = bool(base) and min(base) >= 99.0
    return report


def format_report(r: dict) -> str:
    lines = []
    for src, d in r.items():
        if src.startswith("_"):
            continue
        lines.append(f"\n{src}")
        for k, v in d.items():
            lines.append(f"  {k:28s} {v['recall']:6.1f}%   (n={v['n']})")
    c = r["_control_negativo"]
    lines.append(f"\nControl negativo: {c['con_alerta_MEDIA_o_mayor']}/{c['consultas']} nombres inventados dieron alerta "
                 f"({c['porcentaje']}%)")
    lines.append("RESULTADO: " + ("APROBADO" if r["_aprobado"] else "REVISAR (algún recall base < 99 %)"))
    return "\n".join(lines)
