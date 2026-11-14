"""Capa SQLite (WAL). Para PostgreSQL ver README (sección Escalamiento)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(
  code TEXT PRIMARY KEY, name TEXT, category TEXT, authority TEXT, severity TEXT,
  legal_basis TEXT, action TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS list_versions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, source_code TEXT, fetched_at TEXT, sha256 TEXT, filename TEXT,
  entry_count INTEGER, added INTEGER, changed INTEGER, removed INTEGER, status TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS entries(
  id INTEGER PRIMARY KEY AUTOINCREMENT, source_code TEXT NOT NULL, external_id TEXT NOT NULL,
  version_id INTEGER, content_hash TEXT, entity_type TEXT, primary_name TEXT, rfc TEXT, curp TEXT,
  dobs TEXT, country TEXT, program TEXT, status TEXT, remarks TEXT, active INTEGER DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_entries_src ON entries(source_code, external_id);
CREATE TABLE IF NOT EXISTS names(
  id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER NOT NULL, name TEXT, kind TEXT);
CREATE INDEX IF NOT EXISTS ix_names_entry ON names(entry_id);
CREATE TABLE IF NOT EXISTS subjects(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT UNIQUE, name TEXT, entity_type TEXT, rfc TEXT, curp TEXT,
  dob TEXT, country TEXT, role TEXT DEFAULT 'CLIENTE', parent_ref TEXT, risk_level TEXT DEFAULT 'BAJO',
  monitoring INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT, last_screened_at TEXT);
CREATE TABLE IF NOT EXISTS screenings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id INTEGER, kind TEXT, actor TEXT, created_at TEXT,
  query_json TEXT, result_json TEXT, max_level TEXT, lists_snapshot TEXT, evidence_hash TEXT);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id INTEGER, screening_id INTEGER, source_code TEXT,
  external_id TEXT, entry_hash TEXT, entry_snapshot TEXT, matched_name TEXT, score REAL, level TEXT,
  reasons TEXT, status TEXT DEFAULT 'ABIERTA', created_at TEXT, due_at TEXT,
  proposed_resolution TEXT, proposed_by TEXT, resolution TEXT, resolution_note TEXT,
  resolved_by TEXT, resolved_at TEXT, approved_by TEXT, approved_at TEXT);
CREATE INDEX IF NOT EXISTS ix_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS ix_alerts_subj ON alerts(subject_id, source_code, external_id);
CREATE TABLE IF NOT EXISTS whitelist(
  id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id INTEGER, source_code TEXT, external_id TEXT,
  entry_hash TEXT, reason TEXT, by_user TEXT, at TEXT, UNIQUE(subject_id, source_code, external_id));
CREATE TABLE IF NOT EXISTS operations(
  id INTEGER PRIMARY KEY AUTOINCREMENT, expediente TEXT NOT NULL, tipo_acto TEXT, actor TEXT, created_at TEXT,
  max_level TEXT, dictamen TEXT, result_json TEXT, evidence_hash TEXT);
CREATE INDEX IF NOT EXISTS ix_ops_exp ON operations(expediente);
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, role TEXT, key_hash TEXT UNIQUE, active INTEGER DEFAULT 1,
  created_at TEXT);
CREATE TABLE IF NOT EXISTS operation_parties(
  operation_id INTEGER, subject_id INTEGER, rol TEXT, PRIMARY KEY(operation_id, subject_id, rol));
CREATE TABLE IF NOT EXISTS audit_log(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT, detail TEXT, prev_hash TEXT, hash TEXT);
"""

SOURCES = [
    dict(code="LPB_UIF", name="Lista de Personas Bloqueadas (UIF/SHCP)", category="LPB", authority="UIF-SHCP",
         severity="CRITICA",
         legal_basis="Art. 115 Ley de Instituciones de Crédito y disposiciones análogas del sector financiero. "
                     "Lista no pública: cárguela solo si su enlace con la UIF/SHCP le habilita el acceso.",
         action="Suspender de inmediato el acto/operación/servicio, escalar al Oficial de Cumplimiento y "
                "reportar dentro del plazo aplicable a su régimen (configurado en 24 h; validar)."),
    dict(code="SAT_69B", name="SAT Art. 69-B CFF – Operaciones inexistentes (EFOS)", category="SAT", authority="SAT",
         severity="ALTA", legal_basis="Art. 69-B Código Fiscal de la Federación. Listado público del SAT.",
         action="Escalar a Oficial de Cumplimiento; reforzar debida diligencia; evaluar aviso por sospecha."),
    dict(code="SAT_69B_BIS", name="SAT Art. 69-B Bis CFF – Enajenación ilegal de bienes (EDOS)", category="SAT",
         authority="SAT", severity="ALTA", legal_basis="Art. 69-B Bis CFF. Listado público del SAT.",
         action="Escalar a Oficial de Cumplimiento; reforzar debida diligencia."),
    dict(code="OFAC_SDN", name="OFAC – Specially Designated Nationals (EE.UU.)", category="SANCIONES",
         authority="OFAC/US Treasury", severity="ALTA",
         legal_basis="Referencia internacional; aplicación basada en riesgo (no es por sí misma obligación mexicana).",
         action="Escalar a Oficial de Cumplimiento; aplicar política interna de sanciones."),
    dict(code="ONU_CSNU", name="ONU – Lista consolidada del Consejo de Seguridad", category="SANCIONES",
         authority="ONU", severity="CRITICA",
         legal_basis="Resoluciones del CSNU (sanciones financieras dirigidas). Referencia internacional.",
         action="Escalar de inmediato a Oficial de Cumplimiento; validar obligación de congelamiento aplicable."),
    dict(code="PEP", name="Personas Políticamente Expuestas", category="PEP", authority="UIF / interna",
         severity="MEDIA",
         legal_basis="Reglamento LFPIORPI (reforma 27-mar-2026) y RCG (publicadas 7-ago-2026): "
                     "lista PEP integrada por medio electrónico coordinado por la UIF. Cargue su propia lista mientras tanto.",
         action="Clasificar riesgo ALTO y aplicar debida diligencia reforzada (según RCG)."),
    dict(code="EXT_PEP", name="Proveedor externo – PEP (API)", category="PEP", authority="Proveedor comercial",
         severity="MEDIA", legal_basis="Base comercial del proveedor; no es la lista oficial de la UIF (Consulta PEP 2.0).",
         action="Verificar con la declaración del cliente y fuentes públicas; clasificar riesgo ALTO si es PEP extranjera."),
    dict(code="EXT_SANC", name="Proveedor externo – Sanciones (API)", category="SANCIONES", authority="Proveedor comercial",
         severity="ALTA", legal_basis="Base comercial del proveedor.", action="Escalar a Oficial de Cumplimiento."),
    dict(code="INTERNA", name="Lista interna de la organización", category="INTERNA", authority="Propia",
         severity="MEDIA", legal_basis="Política interna.", action="Aplicar política interna."),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for s in SOURCES:
        conn.execute(
            "INSERT OR IGNORE INTO sources(code,name,category,authority,severity,legal_basis,action) VALUES(?,?,?,?,?,?,?)",
            (s["code"], s["name"], s["category"], s["authority"], s["severity"], s["legal_basis"], s["action"]))


@contextmanager
def tx(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


# ------------------------------------------------------------ bitácora con cadena de hashes
def _canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def audit(conn: sqlite3.Connection, actor: str, action: str, detail: dict | None = None) -> None:
    """Debe llamarse dentro de tx(). Encadena SHA-256: alterar un registro invalida los siguientes."""
    row = conn.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    prev = row["hash"] if row else "GENESIS"
    ts = now()
    d = _canon(detail or {})
    h = hashlib.sha256(f"{prev}|{ts}|{actor}|{action}|{d}".encode()).hexdigest()
    conn.execute("INSERT INTO audit_log(ts,actor,action,detail,prev_hash,hash) VALUES(?,?,?,?,?,?)",
                 (ts, actor, action, d, prev, h))


def verify_audit(conn: sqlite3.Connection) -> dict:
    prev = "GENESIS"
    n = 0
    for r in conn.execute("SELECT * FROM audit_log ORDER BY seq"):
        h = hashlib.sha256(f"{prev}|{r['ts']}|{r['actor']}|{r['action']}|{r['detail']}".encode()).hexdigest()
        if r["prev_hash"] != prev or r["hash"] != h:
            return {"ok": False, "registros": n, "primer_registro_alterado": r["seq"]}
        prev = r["hash"]
        n += 1
    return {"ok": True, "registros": n, "ultimo_hash": prev}
