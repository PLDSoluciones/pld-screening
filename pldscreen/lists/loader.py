"""Importación versionada de listas: diff, protección contra archivos truncados y bitácora."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from ..db import audit, now, tx
from . import parsers


def _chash(rec: dict) -> str:
    keep = {k: rec.get(k) for k in ("name", "aliases", "rfc", "curp", "dobs", "country", "status", "active",
                                    "entity_type", "program")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def import_records(conn: sqlite3.Connection, source_code: str, records: list[dict], *, sha256: str = "",
                   filename: str = "", actor: str = "sistema", min_shrink_ratio: float = 0.5,
                   force: bool = False) -> dict:
    """Reemplaza los registros de la fuente por los nuevos. Devuelve el diff (incluye delta a monitorear)."""
    if not conn.execute("SELECT 1 FROM sources WHERE code=?", (source_code,)).fetchone():
        raise ValueError(f"Fuente desconocida: {source_code}")
    if not records:
        raise ValueError("El archivo no contiene registros; se conserva la versión anterior")

    # Deduplicar por external_id (última ocurrencia gana)
    recs = {r["external_id"]: r for r in records}
    prev = {r["external_id"]: r["content_hash"] for r in conn.execute(
        "SELECT external_id, content_hash FROM entries WHERE source_code=?", (source_code,))}
    if prev and len(recs) < len(prev) * min_shrink_ratio and not force:
        raise ValueError(
            f"Rechazado: la nueva versión tiene {len(recs)} registros vs {len(prev)} actuales "
            f"(<{int(min_shrink_ratio * 100)}%). Posible archivo truncado. Use force=True si es correcto.")

    last = conn.execute("SELECT sha256 FROM list_versions WHERE source_code=? AND status='OK' ORDER BY id DESC LIMIT 1",
                        (source_code,)).fetchone()
    if last and sha256 and last["sha256"] == sha256:
        return {"source": source_code, "unchanged": True, "added": 0, "changed": 0, "removed": 0,
                "total": len(prev), "delta_external_ids": []}

    new_hash = {k: _chash(v) for k, v in recs.items()}
    added = [k for k in recs if k not in prev]
    changed = [k for k in recs if k in prev and prev[k] != new_hash[k]]
    removed = [k for k in prev if k not in recs]

    with tx(conn):
        cur = conn.execute(
            "INSERT INTO list_versions(source_code,fetched_at,sha256,filename,entry_count,added,changed,removed,status,notes)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (source_code, now(), sha256, filename, len(recs), len(added), len(changed), len(removed), "OK",
             json.dumps({"added": added[:500], "changed": changed[:500], "removed": removed[:500]})))
        vid = cur.lastrowid
        conn.execute("DELETE FROM names WHERE entry_id IN (SELECT id FROM entries WHERE source_code=?)", (source_code,))
        conn.execute("DELETE FROM entries WHERE source_code=?", (source_code,))
        for k, r in recs.items():
            c = conn.execute(
                "INSERT INTO entries(source_code,external_id,version_id,content_hash,entity_type,primary_name,rfc,curp,"
                "dobs,country,program,status,remarks,active) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (source_code, k, vid, new_hash[k], r["entity_type"], r["name"], r["rfc"], r["curp"],
                 json.dumps(r["dobs"], ensure_ascii=False), r["country"], r["program"], r["status"], r["remarks"],
                 1 if r["active"] else 0))
            eid = c.lastrowid
            names = [(r["name"], "primary")] + [(a, "alias") for a in r["aliases"] if a]
            conn.executemany("INSERT INTO names(entry_id,name,kind) VALUES(?,?,?)", [(eid, n, kd) for n, kd in names])
        audit(conn, actor, "LISTA_ACTUALIZADA", {
            "fuente": source_code, "version": vid, "sha256": sha256, "archivo": filename, "total": len(recs),
            "altas": len(added), "modificados": len(changed), "bajas": len(removed)})
    return {"source": source_code, "unchanged": False, "version": vid, "added": len(added), "changed": len(changed),
            "removed": len(removed), "total": len(recs), "delta_external_ids": added + changed}


FORMATS = {"ofac", "un", "sat69b", "generic"}


def import_file(conn, source_code: str, path: str, fmt: str = "generic", alt_path: str | None = None, **kw) -> dict:
    data = Path(path).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if fmt == "ofac":
        recs = parsers.parse_ofac(data, Path(alt_path).read_bytes() if alt_path else None)
    elif fmt == "un":
        recs = parsers.parse_un(data)
    elif fmt == "sat69b":
        recs = parsers.parse_sat69b(data)
    elif fmt == "generic":
        recs = parsers.parse_generic(data, source_code)
    else:
        raise ValueError(f"Formato desconocido: {fmt}")
    return import_records(conn, source_code, recs, sha256=sha, filename=Path(path).name, **kw)
