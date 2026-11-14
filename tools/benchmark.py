"""Benchmark sintético: latencia y recall/falsos positivos con variantes típicas de captura.
Uso: python tools/benchmark.py [N_registros]"""
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pldscreen.matching import Index, Query  # noqa: E402
from pldscreen.normalize import strip_accents  # noqa: E402

random.seed(7)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60000
SYL = ["BA", "RE", "TO", "MA", "LU", "SA", "PE", "GO", "NA", "RI", "CO", "VA", "DE", "MI", "LO", "FE", "TE", "JU", "AR", "EL", "ZA", "HU", "QUI", "GUE", "CHA", "XI"]
END = ["N", "S", "Z", "L", "R", "", "A", "O"]
def word(): return "".join(random.choice(SYL) for _ in range(random.randint(2, 3))) + random.choice(END)
GIVEN = [word() for _ in range(800)]; SUR = [word() for _ in range(2500)]

def person():
    g = random.choice(GIVEN) + (" " + random.choice(GIVEN) if random.random() < .4 else "")
    return f"{g} {random.choice(SUR)} {random.choice(SUR)}"

names = list({person() for _ in range(N)})
entries = [dict(id=i, source_code="X", external_id=str(i), entity_type="F", primary_name=n, rfc=None, curp=None,
                dobs=[], names=[(n, "primary")], content_hash="h") for i, n in enumerate(names)]
t = time.time(); idx = Index(entries); print(f"Índice de {len(idx):,} registros en {time.time()-t:.1f}s")

def typo(s):
    r = random.random(); w = list(s)
    i = random.randrange(len(w))
    if r < .25 and w[i] != " ": del w[i]
    elif r < .5 and i + 1 < len(w) and w[i] != " " and w[i+1] != " ": w[i], w[i+1] = w[i+1], w[i]
    elif r < .7: w.insert(i, random.choice("AEIOU"))
    return "".join(w)
def variants(n):
    t = n.split()
    return {"exacto": n, "orden invertido": " ".join(t[::-1]), "typo": typo(n), "sin 2o nombre": " ".join([t[0]] + t[-2:]) if len(t) > 3 else n,
            "solo 1er nombre+1er apellido": f"{t[0]} {t[-2]}" if len(t) >= 3 else n}

sample = random.sample(range(len(names)), 400)
res = {}; lat = []
for i in sample:
    for k, v in variants(names[i]).items():
        t0 = time.perf_counter(); ms = idx.search(Query(name=v, entity_type="F")); lat.append(time.perf_counter() - t0)
        hit = any(m.entry_id == i and m.level in ("ALTA", "MEDIA", "EXACTA") for m in ms)
        res.setdefault(k, []).append(hit)
for k, v in res.items(): print(f"Recall (≥MEDIA) {k:32s}: {100*sum(v)/len(v):5.1f}%")
fp = 0; tot = 400
for _ in range(tot):
    ms = idx.search(Query(name=person(), entity_type="F"))
    fp += any(m.level in ("ALTA", "MEDIA") for m in ms)
lat.sort()
print(f"Falsos positivos (nombres no listados, ≥MEDIA): {100*fp/tot:.1f}%")
print(f"Latencia por consulta: mediana {1000*lat[len(lat)//2]:.0f} ms · p95 {1000*lat[int(len(lat)*.95)]:.0f} ms")
