"""Jurisdicciones de alto riesgo (archivo CSV mantenido por el usuario: data/country_risk.csv).
Columnas: pais, alias (separados por |), nivel (ALTO|MEDIO), motivo. Actualícelo con la lista oficial vigente
(GAFI/FATF y la que publique la SHCP/UIF): el archivo incluido es solo un punto de partida."""
from __future__ import annotations

import csv
from pathlib import Path

from .normalize import clean


class CountryRisk:
    def __init__(self, path: str):
        self.map: dict[str, dict] = {}
        p = Path(path)
        if not p.exists():
            return
        with p.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                names = [r.get("pais", "")] + (r.get("alias") or "").split("|")
                info = {"pais": r.get("pais", "").strip(), "nivel": (r.get("nivel") or "ALTO").strip().upper(),
                        "motivo": (r.get("motivo") or "").strip()}
                for n in names:
                    if n.strip():
                        self.map[clean(n)] = info

    def lookup(self, country: str | None) -> dict | None:
        return self.map.get(clean(country)) if country else None
