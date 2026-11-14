"""Descarga de fuentes públicas (OFAC, ONU, SAT 69-B y 69-B Bis). Las listas no públicas (LPB, PEP, internas)
se cargan desde archivos en data/inbox/<FUENTE>/ o por API/CLI. Cada URL admite alternativas separadas por coma."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import httpx

from ..config import Settings
from . import parsers
from .loader import import_records


def _get(urls: str, retries: int = 3) -> bytes:
    last = None
    for url in [u.strip() for u in urls.split(",") if u.strip()]:
        for i in range(retries):
            try:
                r = httpx.get(url, timeout=180, follow_redirects=True, headers={"User-Agent": "pld-screening/1.1"})
                r.raise_for_status()
                if not r.content:
                    raise ValueError("Respuesta vacía")
                return r.content
            except Exception as e:  # noqa: BLE001
                last = f"{url}: {e}"
                time.sleep(2 ** i)
    raise RuntimeError(f"No se pudo descargar ({last})")


def _save(settings: Settings, name: str, data: bytes) -> str:
    sha = hashlib.sha256(data).hexdigest()
    d = Path(settings.raw_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}_{time.strftime('%Y%m%d_%H%M%S')}_{sha[:8]}").write_bytes(data)  # evidencia de lo descargado
    return sha


def update_source(conn, settings: Settings, code: str, actor: str = "sistema") -> dict:
    kw = dict(actor=actor, min_shrink_ratio=settings.min_shrink_ratio)
    if code == "OFAC_SDN":
        sdn = _get(settings.url_ofac_sdn)
        alt = _get(settings.url_ofac_alt)
        sha = _save(settings, "OFAC_SDN", sdn + b"\n--ALT--\n" + alt)
        return import_records(conn, code, parsers.parse_ofac(sdn, alt), sha256=sha, filename="SDN+ALT", **kw)
    if code == "ONU_CSNU":
        data = _get(settings.url_un)
        return import_records(conn, code, parsers.parse_un(data), sha256=_save(settings, code, data),
                              filename="consolidated.xml", **kw)
    if code == "SAT_69B":
        data = _get(settings.url_sat_69b)
        return import_records(conn, code, parsers.parse_sat69b(data, "69-B"), sha256=_save(settings, code, data),
                              filename="Listado_completo_69-B.csv", **kw)
    if code == "SAT_69B_BIS":
        data = _get(settings.url_sat_69b_bis)
        return import_records(conn, code, parsers.parse_sat69b(data, "69-B Bis"), sha256=_save(settings, code, data),
                              filename="Listado_69_B_Bis_Completo.csv", **kw)
    raise ValueError(f"{code} no tiene descarga automática; cárguela desde archivo (inbox/API/CLI)")


AUTO_SOURCES = ["OFAC_SDN", "ONU_CSNU", "SAT_69B", "SAT_69B_BIS"]
