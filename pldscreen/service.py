"""Lógica de negocio: consultas, alertas con doble validación, monitoreo continuo, actualización de listas."""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import secrets
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db as dbm
from .config import Settings, get_settings
from .lists import fetch, loader, parsers
from .country import CountryRisk
from .matching import Index, Match, Query, level_rank
from .normalize import normalize_curp, normalize_rfc
from . import operations as ops
from . import providers

ROLES = {"analista": 1, "supervisor": 2, "admin": 3}

# Catálogos de apoyo para notarías e inmobiliarias (se aceptan otros valores libres)
ROLES_PARTE = ["COMPRADOR", "VENDEDOR", "ADQUIRENTE", "ENAJENANTE", "APODERADO", "REPRESENTANTE_LEGAL",
               "BENEFICIARIO_CONTROLADOR", "SOCIO_ACCIONISTA", "FIDEICOMITENTE", "FIDEICOMISARIO", "FIDUCIARIO",
               "DONANTE", "DONATARIO", "ARRENDADOR", "ARRENDATARIO", "OTORGANTE", "COMPARECIENTE", "TESTIGO", "OTRO"]
TIPOS_ACTO = ["COMPRAVENTA_INMUEBLE", "DONACION", "ADJUDICACION", "PERMUTA", "CONSTITUCION_SOCIEDAD",
              "MODIFICACION_SOCIEDAD", "FUSION_ESCISION", "FIDEICOMISO", "PODER", "HIPOTECA_GARANTIA",
              "ARRENDAMIENTO", "DESARROLLO_INMOBILIARIO", "PROMESA_COMPRAVENTA", "OTRO"]


class ServiceError(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


def _canon(o) -> str:
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _utc() -> datetime:
    return datetime.now(timezone.utc)


class Service:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.s.ensure_dirs()
        self.lock = threading.RLock()
        self.conn = dbm.connect(self.s.db_path)
        dbm.init_db(self.conn)
        self._index: Index | None = None
        self._index_key = None
        self._sources: dict[str, dict] = {}
        cr = Path(self.s.country_risk_path)
        if not cr.exists():
            cr.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(Path(__file__).with_name("country_default.csv"), cr)
        self.countries = CountryRisk(self.s.country_risk_path)
        self.provider = providers.build(self.s)

    # ------------------------------------------------------------------ usuarios
    def create_user(self, name: str, role: str) -> str:
        if role not in ROLES:
            raise ServiceError(f"Rol inválido. Use: {', '.join(ROLES)}")
        key = "pld_" + secrets.token_urlsafe(32)
        with self.lock, dbm.tx(self.conn):
            self.conn.execute("INSERT INTO users(name,role,key_hash,created_at) VALUES(?,?,?,?)",
                              (name, role, hashlib.sha256(key.encode()).hexdigest(), dbm.now()))
            dbm.audit(self.conn, "sistema", "USUARIO_CREADO", {"usuario": name, "rol": role})
        return key

    def authenticate(self, key: str | None) -> dict | None:
        if not key:
            return None
        with self.lock:
            r = self.conn.execute("SELECT name,role FROM users WHERE key_hash=? AND active=1",
                                  (hashlib.sha256(key.encode()).hexdigest(),)).fetchone()
        return dict(r) if r else None

    def has_users(self) -> bool:
        with self.lock:
            return self.conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    # ------------------------------------------------------------------ índice
    def index(self) -> Index:
        with self.lock:
            key = self.conn.execute("SELECT COALESCE(MAX(id),0) m, COUNT(*) c FROM list_versions").fetchone()
            key = (key["m"], key["c"])
            if self._index is None or key != self._index_key:
                self._index = self._build_index("1=1")
                self._index_key = key
                self._sources = {r["code"]: dict(r) for r in self.conn.execute("SELECT * FROM sources")}
            return self._index

    def _build_index(self, where: str, params: tuple = ()) -> Index:
        names: dict[int, list] = {}
        for r in self.conn.execute(
                f"SELECT n.entry_id, n.name, n.kind FROM names n JOIN entries e ON e.id=n.entry_id "
                f"WHERE e.active=1 AND {where}", params):
            names.setdefault(r["entry_id"], []).append((r["name"], r["kind"]))
        entries = []
        for r in self.conn.execute(f"SELECT * FROM entries e WHERE e.active=1 AND {where}", params):
            d = dict(r)
            d["dobs"] = json.loads(d["dobs"] or "[]")
            d["names"] = names.get(d["id"], [])
            entries.append(d)
        return Index(entries, self.s.th_alta, self.s.th_media, self.s.th_baja)

    # ------------------------------------------------------------------ consulta
    @staticmethod
    def _query(d: dict) -> Query:
        name = d.get("nombre") or d.get("razon_social") or " ".join(
            filter(None, (d.get("nombres"), d.get("apellido_paterno"), d.get("apellido_materno"))))
        tipo = (d.get("tipo") or "").upper()[:1] or None
        tipo = {"F": "F", "M": "M", "P": "F"}.get(tipo) if tipo else None
        return Query(name=name or "", entity_type=tipo, rfc=d.get("rfc"), curp=d.get("curp"),
                     dob=d.get("fecha_nacimiento"), country=d.get("pais"))

    def screen(self, data: dict, actor: str = "sistema", persist: bool | None = None, kind: str = "CONSULTA") -> dict:
        """persist: crear/actualizar el sujeto y generar alertas. Por defecto, solo si se envía 'referencia'."""
        q = self._query(data)
        if not (q.name or q.rfc or q.curp):
            raise ServiceError("Se requiere nombre, RFC o CURP")
        ref = (data.get("referencia") or "").strip() or None
        persist = bool(ref) if persist is None else persist
        with self.lock:
            idx = self.index()
            result = self._screen_one(idx, q, data, ref, actor, persist, kind)
            rel_results = []
            for i, rel in enumerate(data.get("relacionados") or [], 1):
                rrole = (rel.get("rol") or "RELACIONADO").upper()
                rref = (rel.get("referencia") or normalize_curp(rel.get("curp")) or normalize_rfc(rel.get("rfc"))
                        or (f"{ref}:{rrole}:{i}" if ref else None))
                rq = self._query(rel)
                if not (rq.name or rq.rfc or rq.curp):
                    continue
                rd = dict(rel, rol=rrole, parent_ref=ref)
                rel_results.append(self._screen_one(idx, rq, rd, rref, actor, persist and bool(rref), kind))
            result["relacionados"] = rel_results
            if rel_results:
                worst = max([result["nivel_maximo"]] + [r["nivel_maximo"] for r in rel_results],
                            key=lambda l: -1 if l is None else level_rank(l))
                result["nivel_maximo_global"] = worst
        return result

    def _screen_one(self, idx: Index, q: Query, data: dict, ref, actor, persist, kind) -> dict:
        matches = idx.search(q)
        ext_state = {"proveedor": None, "estado": "NO_CONFIGURADO", "detalle": ""}
        if self.provider and data.get("externa", True) is not False and q.name:
            try:
                hits = self.provider.check(q)
                for h in hits:
                    m = self._ext_match(h, q)
                    if m:
                        matches.append(m)
                ext_state = {"proveedor": self.provider.name, "estado": "OK", "detalle": f"{len(hits)} registro(s) devueltos"}
            except Exception as e:  # noqa: BLE001  (la consulta local no debe fallar por el proveedor)
                ext_state = {"proveedor": self.provider.name, "estado": "ERROR", "detalle": str(e)[:300]}
        matches.sort(key=lambda m: (-level_rank(m.level), -m.score))
        subject_id = None
        discarded: list[Match] = []
        if persist and ref:
            subject_id = self._upsert_subject(ref, q, data)
            keep = []
            for m in matches:
                if self._is_whitelisted(subject_id, m, idx):
                    discarded.append(m)
                else:
                    keep.append(m)
            matches = keep
        max_level = max((m.level for m in matches), key=level_rank, default=None)
        riesgo, acciones = self._risk(matches)
        riesgo, acciones, extras = self._apply_extras(riesgo, acciones, q, data)
        resultado = ("ALTA_PRIORIDAD_DETENER_OPERACION" if max_level in ("ALTA", "EXACTA")
                     else "REVISION_REQUERIDA" if max_level == "MEDIA" else "SIN_COINCIDENCIAS_RELEVANTES")
        snapshot = self._lists_snapshot()
        out = {
            "fecha": dbm.now(), "referencia": ref, "consulta": {
                "nombre": q.name, "tipo": q.entity_type, "rfc": normalize_rfc(q.rfc) or q.rfc,
                "curp": normalize_curp(q.curp) or q.curp, "fecha_nacimiento": q.dob, "pais": q.country,
                "rol": data.get("rol"), "expediente": data.get("expediente")},
            "resultado": resultado, "nivel_maximo": max_level, "riesgo_sugerido": riesgo,
            "acciones_recomendadas": acciones, "factores_adicionales": extras,
            "coincidencias": [self._m_out(m) for m in matches],
            "descartadas_previamente": [self._m_out(m) for m in discarded],
            "listas_consultadas": snapshot, "proveedor_externo": ext_state,
        }
        out["evidencia_sha256"] = hashlib.sha256(_canon(out).encode()).hexdigest()
        with dbm.tx(self.conn):
            cur = self.conn.execute(
                "INSERT INTO screenings(subject_id,kind,actor,created_at,query_json,result_json,max_level,lists_snapshot,"
                "evidence_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                (subject_id, kind, actor, out["fecha"], _canon(out["consulta"]), _canon(out), max_level,
                 _canon(snapshot), out["evidencia_sha256"]))
            sid = cur.lastrowid
            out["id_consulta"] = sid
            alerts = []
            if persist and subject_id:
                alerts = self._create_alerts(subject_id, sid, matches, idx)
                rl = {"BAJO": 0, "MEDIO": 1, "ALTO": 2}
                cur_r = self.conn.execute("SELECT risk_level FROM subjects WHERE id=?", (subject_id,)).fetchone()[0]
                if rl[riesgo] > rl.get(cur_r, 0):
                    self.conn.execute("UPDATE subjects SET risk_level=? WHERE id=?", (riesgo, subject_id))
                self.conn.execute("UPDATE subjects SET last_screened_at=? WHERE id=?", (out["fecha"], subject_id))
            qh = hashlib.sha256(_canon(out["consulta"]).encode()).hexdigest()[:16]
            dbm.audit(self.conn, actor, kind, {"id_consulta": sid, "referencia": ref, "consulta_hash": qh,
                                               "nivel_maximo": max_level, "alertas": alerts,
                                               "evidencia_sha256": out["evidencia_sha256"]})
        out["alertas_generadas"] = alerts
        out["subject_id"] = subject_id
        return out

    def _ext_match(self, h: dict, q: Query) -> Match | None:
        sc = providers.rescore(h, q)
        if sc < self.s.th_baja:
            return None
        reasons = [f"Proveedor externo {h['proveedor']}: {h['tipo']} · {h['detalle']}".strip(" ·"),
                   f"Similitud de nombre {sc:.0f}/100 (“{h['nombre']}” vs “{q.name}”)"]
        if h.get("score_proveedor") is not None:
            reasons.append(f"Puntaje del proveedor: {h['score_proveedor']}")
        total = min(sc, 99.0)
        if q.dob and h["dobs"]:
            from .normalize import dob_compare, parse_dob
            res = [r for r in (dob_compare(parse_dob(q.dob), parse_dob(d)) for d in h["dobs"]) if r]
            if "full" in res:
                total = min(99.0, total + 5)
                reasons.append("Fecha de nacimiento coincide completa")
            elif res and all(r == "mismatch" for r in res):
                total -= 15
                reasons.append("Fecha de nacimiento NO coincide (posible homónimo)")
        if total < self.s.th_baja:
            return None
        level = "ALTA" if total >= self.s.th_alta else "MEDIA" if total >= self.s.th_media else "BAJA"
        entry = {"primary_name": h["nombre"], "program": h["tipo"], "dobs": h["dobs"], "country": ", ".join(h["paises"]),
                 "remarks": h["detalle"]}
        eh = hashlib.sha256(_canon([h["id"], h["nombre"], h["aliases"], h["dobs"], h["tipo"]]).encode()).hexdigest()[:24]
        src = "EXT_PEP" if h["tipo"] == "PEP" else "EXT_SANC"
        return Match(-1, src, f"{h['proveedor']}:{h['id']}", h["nombre"], "externo", total, level, reasons, entry, eh)

    def _apply_extras(self, riesgo: str, acciones: list[str], q: Query, data: dict):
        """País de alto riesgo y PEP declarado por el cliente (insumos del enfoque basado en riesgos)."""
        rank = {"BAJO": 0, "MEDIO": 1, "ALTO": 2}
        extras = []
        info = self.countries.lookup(q.country)
        if info:
            extras.append(f"Jurisdicción de alto riesgo: {info['pais']} ({info['motivo']})")
            acciones.append("País en lista de jurisdicciones de alto riesgo: aplicar debida diligencia reforzada.")
            if rank[info["nivel"] if info["nivel"] in rank else "ALTO"] > rank[riesgo]:
                riesgo = info["nivel"] if info["nivel"] in rank else "ALTO"
        pep = data.get("declara_pep")
        if isinstance(pep, str):
            pep = pep.strip().upper()
        if pep in (True, "SI", "SÍ", "TRUE", "1", "NACIONAL", "EXTRANJERA", "EXTRANJERO"):
            foreign = pep in ("EXTRANJERA", "EXTRANJERO")
            extras.append("PEP extranjera declarada" if foreign else "PEP declarada por el cliente")
            acciones.append("PEP: seguimiento intensificado" + (" y riesgo ALTO (PEP extranjera)." if foreign else "."))
            need = "ALTO" if foreign else "MEDIO"
            if rank[need] > rank[riesgo]:
                riesgo = need
        return riesgo, acciones, extras

    @staticmethod
    def _m_out(m: Match) -> dict:
        return m.to_dict()

    def _lists_snapshot(self) -> dict:
        rows = self.conn.execute(
            "SELECT source_code, MAX(id) v, MAX(fetched_at) f, entry_count c FROM list_versions WHERE status='OK' "
            "GROUP BY source_code").fetchall()
        return {r["source_code"]: {"version": r["v"], "fecha_carga": r["f"], "registros": r["c"]} for r in rows}

    def _risk(self, matches: list[Match]) -> tuple[str, list[str]]:
        acts: list[str] = []
        risk = "BAJO"
        for m in matches:
            src = self._sources.get(m.source_code, {})
            hi = m.level in ("ALTA", "EXACTA")
            if hi or (src.get("category") == "PEP" and level_rank(m.level) >= 1):
                risk = "ALTO"
            elif level_rank(m.level) >= 1 and risk == "BAJO":
                risk = "MEDIO"
            if level_rank(m.level) >= 1 and src.get("action"):
                a = f"[{m.source_code}] {src['action']}"
                if a not in acts:
                    acts.append(a)
        if risk == "BAJO" and not matches:
            acts.append("Sin coincidencias relevantes: continuar con el proceso normal y conservar la constancia.")
        return risk, acts

    # ------------------------------------------------------------------ sujetos
    def _upsert_subject(self, ref: str, q: Query, d: dict) -> int:
        row = self.conn.execute("SELECT id FROM subjects WHERE ref=?", (ref,)).fetchone()
        t = dbm.now()
        with dbm.tx(self.conn):
            if row:
                self.conn.execute(
                    "UPDATE subjects SET name=?,entity_type=?,rfc=?,curp=?,dob=?,country=?,updated_at=? WHERE id=?",
                    (q.name, q.entity_type, normalize_rfc(q.rfc), normalize_curp(q.curp), q.dob, q.country, t, row["id"]))
                return row["id"]
            c = self.conn.execute(
                "INSERT INTO subjects(ref,name,entity_type,rfc,curp,dob,country,role,parent_ref,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ref, q.name, q.entity_type, normalize_rfc(q.rfc), normalize_curp(q.curp), q.dob, q.country,
                 d.get("rol") or "CLIENTE", d.get("parent_ref"), t, t))
            return c.lastrowid

    def list_subjects(self, limit=100, offset=0, risk=None) -> list[dict]:
        with self.lock:
            sql, p = "SELECT * FROM subjects", []
            if risk:
                sql += " WHERE risk_level=?"
                p.append(risk)
            sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
            return [dict(r) for r in self.conn.execute(sql, (*p, limit, offset))]

    def import_subjects_csv(self, data: bytes, actor: str) -> dict:
        """Columnas: referencia,nombre,tipo,rfc,curp,fecha_nacimiento,pais,rol"""
        rows = list(csv.DictReader(io.StringIO(parsers.decode(data))))
        summary = {"procesados": 0, "con_alertas": 0, "errores": []}
        for n, r in enumerate(rows, 2):
            r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
            try:
                res = self.screen(r, actor=actor, persist=bool(r.get("referencia")), kind="CARGA_MASIVA")
                summary["procesados"] += 1
                if res["alertas_generadas"]:
                    summary["con_alertas"] += 1
            except ServiceError as e:
                summary["errores"].append(f"Fila {n}: {e}")
        return summary

    def rescreen_all(self, actor: str = "sistema") -> dict:
        """Re-consulta todos los sujetos con monitoreo activo contra TODAS las listas (p. ej., tras cambiar umbrales)."""
        with self.lock:
            subs = [dict(r) for r in self.conn.execute("SELECT * FROM subjects WHERE monitoring=1")]
        n = alerts = 0
        for s in subs:
            res = self.screen({"referencia": s["ref"], "nombre": s["name"], "tipo": s["entity_type"], "rfc": s["rfc"],
                               "curp": s["curp"], "fecha_nacimiento": s["dob"], "pais": s["country"], "rol": s["role"]},
                              actor=actor, persist=True, kind="MONITOREO_COMPLETO")
            n += 1
            alerts += len(res["alertas_generadas"])
        return {"sujetos": n, "alertas_nuevas": alerts}

    # ------------------------------------------------------------------ alertas
    def _is_whitelisted(self, subject_id: int, m: Match, idx: Index) -> bool:
        e = {"content_hash": m.entry_hash} if m.entry_id < 0 else idx.entries[m.entry_id]
        r = self.conn.execute("SELECT entry_hash FROM whitelist WHERE subject_id=? AND source_code=? AND external_id=?",
                              (subject_id, m.source_code, m.external_id)).fetchone()
        return bool(r and r["entry_hash"] == e["content_hash"])

    def _create_alerts(self, subject_id: int, screening_id: int, matches: list[Match], idx: Index) -> list[int]:
        ids = []
        min_rank = level_rank(self.s.alert_min_level)
        for m in matches:
            if level_rank(m.level) < min_rank:
                continue
            dup = self.conn.execute(
                "SELECT id FROM alerts WHERE subject_id=? AND source_code=? AND external_id=? "
                "AND status IN ('ABIERTA','PENDIENTE_APROBACION')", (subject_id, m.source_code, m.external_id)).fetchone()
            if dup:
                continue
            e = {"content_hash": m.entry_hash} if m.entry_id < 0 else idx.entries[m.entry_id]
            sev = self._sources.get(m.source_code, {}).get("severity")
            urgent = m.level in ("ALTA", "EXACTA") and sev in ("CRITICA", "ALTA")
            hours = self.s.sla_critica_hours if urgent else self.s.sla_revision_hours
            due = (_utc() + timedelta(hours=hours)).isoformat(timespec="seconds")
            c = self.conn.execute(
                "INSERT INTO alerts(subject_id,screening_id,source_code,external_id,entry_hash,entry_snapshot,matched_name,"
                "score,level,reasons,created_at,due_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (subject_id, screening_id, m.source_code, m.external_id, e["content_hash"], _canon(m.entry),
                 m.matched_name, m.score, m.level, _canon(m.reasons), dbm.now(), due))
            ids.append(c.lastrowid)
        return ids

    def list_alerts(self, status: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
        with self.lock:
            sql = ("SELECT a.*, s.ref, s.name AS subject_name, s.role AS subject_role, "
                   "json_extract(sc.query_json,'$.expediente') AS expediente FROM alerts a "
                   "LEFT JOIN subjects s ON s.id=a.subject_id LEFT JOIN screenings sc ON sc.id=a.screening_id")
            p: list = []
            if status:
                sql += " WHERE a.status=?"
                p.append(status)
            sql += " ORDER BY a.due_at ASC LIMIT ? OFFSET ?"
            now = dbm.now()
            out = []
            for r in self.conn.execute(sql, (*p, limit, offset)):
                d = self._alert_dict(r)
                d["vencida"] = d["status"] in ("ABIERTA", "PENDIENTE_APROBACION") and d["due_at"] < now
                out.append(d)
            return out

    @staticmethod
    def _alert_dict(r) -> dict:
        d = dict(r)
        d["reasons"] = json.loads(d["reasons"] or "[]")
        d["entry_snapshot"] = json.loads(d["entry_snapshot"] or "{}")
        return d

    def get_alert(self, alert_id: int) -> dict:
        with self.lock:
            r = self.conn.execute(
                "SELECT a.*, s.ref, s.name AS subject_name, s.role AS subject_role, "
                "json_extract(sc.query_json,'$.expediente') AS expediente FROM alerts a "
                "LEFT JOIN subjects s ON s.id=a.subject_id LEFT JOIN screenings sc ON sc.id=a.screening_id "
                "WHERE a.id=?", (alert_id,)).fetchone()
            if not r:
                raise ServiceError("Alerta no encontrada", 404)
            return self._alert_dict(r)

    def resolve_alert(self, alert_id: int, user: dict, resolution: str, note: str) -> dict:
        """Doble validación: un analista propone el cierre de alertas de alto riesgo; un supervisor distinto lo aprueba."""
        resolution = (resolution or "").upper()
        if resolution not in ("FALSO_POSITIVO", "CONFIRMADA", "DEVOLVER"):
            raise ServiceError("resolucion debe ser FALSO_POSITIVO, CONFIRMADA o DEVOLVER")
        if len((note or "").strip()) < 10:
            raise ServiceError("Se requiere una justificación de al menos 10 caracteres")
        with self.lock:
            a = self.get_alert(alert_id)
            if a["status"] not in ("ABIERTA", "PENDIENTE_APROBACION"):
                raise ServiceError(f"La alerta ya está en estado {a['status']}", 409)
            sev = self._sources.get(a["source_code"], {}).get("severity") if self._sources else None
            if sev is None:
                self.index()
                sev = self._sources.get(a["source_code"], {}).get("severity")
            high = a["level"] in ("ALTA", "EXACTA") or sev == "CRITICA"
            role = ROLES[user["role"]]
            t = dbm.now()
            with dbm.tx(self.conn):
                if a["status"] == "ABIERTA":
                    if resolution == "DEVOLVER":
                        raise ServiceError("La alerta no está pendiente de aprobación")
                    if high and role < ROLES["supervisor"]:
                        self.conn.execute("UPDATE alerts SET status='PENDIENTE_APROBACION',proposed_resolution=?,"
                                          "proposed_by=?,resolution_note=? WHERE id=?",
                                          (resolution, user["name"], note, alert_id))
                        dbm.audit(self.conn, user["name"], "ALERTA_PROPUESTA",
                                  {"alerta": alert_id, "propuesta": resolution, "nota": note})
                        return self.get_alert(alert_id)
                else:  # PENDIENTE_APROBACION
                    if role < ROLES["supervisor"]:
                        raise ServiceError("Solo un supervisor puede aprobar", 403)
                    if user["name"] == a["proposed_by"]:
                        raise ServiceError("La aprobación debe hacerla una persona distinta a quien propuso", 403)
                    if resolution == "DEVOLVER":
                        self.conn.execute("UPDATE alerts SET status='ABIERTA',proposed_resolution=NULL,proposed_by=NULL "
                                          "WHERE id=?", (alert_id,))
                        dbm.audit(self.conn, user["name"], "ALERTA_DEVUELTA", {"alerta": alert_id, "nota": note})
                        return self.get_alert(alert_id)
                self.conn.execute(
                    "UPDATE alerts SET status=?,resolution=?,resolution_note=?,resolved_by=?,resolved_at=?,"
                    "approved_by=?,approved_at=? WHERE id=?",
                    (resolution, resolution, note, a["proposed_by"] or user["name"], t,
                     user["name"] if a["status"] == "PENDIENTE_APROBACION" else None,
                     t if a["status"] == "PENDIENTE_APROBACION" else None, alert_id))
                if resolution == "FALSO_POSITIVO" and a["subject_id"]:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO whitelist(subject_id,source_code,external_id,entry_hash,reason,by_user,at)"
                        " VALUES(?,?,?,?,?,?,?)",
                        (a["subject_id"], a["source_code"], a["external_id"], a["entry_hash"], note, user["name"], t))
                if resolution == "CONFIRMADA" and a["subject_id"]:
                    self.conn.execute("UPDATE subjects SET risk_level='ALTO' WHERE id=?", (a["subject_id"],))
                dbm.audit(self.conn, user["name"], "ALERTA_CERRADA",
                          {"alerta": alert_id, "resolucion": resolution, "nota": note, "fuente": a["source_code"],
                           "id_externo": a["external_id"]})
            return self.get_alert(alert_id)

    # ------------------------------------------------------------------ listas
    def lists_status(self) -> list[dict]:
        with self.lock:
            self.index()
            out = []
            for s in self._sources.values():
                v = self.conn.execute(
                    "SELECT * FROM list_versions WHERE source_code=? AND status='OK' ORDER BY id DESC LIMIT 1",
                    (s["code"],)).fetchone()
                age_h = None
                if v:
                    age_h = round((_utc() - datetime.fromisoformat(v["fetched_at"])).total_seconds() / 3600, 1)
                out.append({**s, "ultima_version": dict(v) if v else None, "antiguedad_horas": age_h,
                            "desactualizada": (age_h is None) or (age_h > 48 and s["code"] in fetch.AUTO_SOURCES)})
            return out

    def import_list(self, source: str, data: bytes, fmt: str = "generic", filename: str = "carga_manual",
                    actor: str = "sistema", force: bool = False, alt_data: bytes | None = None) -> dict:
        sha = hashlib.sha256(data).hexdigest()
        Path(self.s.raw_dir).mkdir(parents=True, exist_ok=True)
        (Path(self.s.raw_dir) / f"{source}_{_utc().strftime('%Y%m%d_%H%M%S')}_{sha[:8]}").write_bytes(data)
        try:
            recs = {"ofac": lambda: parsers.parse_ofac(data, alt_data), "un": lambda: parsers.parse_un(data),
                    "sat69b": lambda: parsers.parse_sat69b(data),
                    "generic": lambda: parsers.parse_generic(data, source)}[fmt]()
        except KeyError:
            raise ServiceError(f"Formato desconocido: {fmt}")
        except Exception as e:  # noqa: BLE001
            raise ServiceError(f"No se pudo leer el archivo: {e}")
        with self.lock:
            try:
                res = loader.import_records(self.conn, source, recs, sha256=sha, filename=filename, actor=actor,
                                            min_shrink_ratio=self.s.min_shrink_ratio, force=force)
            except ValueError as e:
                raise ServiceError(str(e), 422)
            res["monitoreo"] = self._monitor_delta(source, res.get("delta_external_ids", []), actor)
        res.pop("delta_external_ids", None)
        return res

    def update_lists(self, sources: list[str] | None = None, actor: str = "sistema") -> list[dict]:
        out = []
        for code in sources or fetch.AUTO_SOURCES:
            try:
                with self.lock:
                    res = fetch.update_source(self.conn, self.s, code, actor)
                    res["monitoreo"] = self._monitor_delta(code, res.get("delta_external_ids", []), actor)
                res.pop("delta_external_ids", None)
                out.append(res)
            except Exception as e:  # noqa: BLE001
                with self.lock, dbm.tx(self.conn):
                    dbm.audit(self.conn, actor, "ACTUALIZACION_FALLIDA", {"fuente": code, "error": str(e)[:300]})
                out.append({"source": code, "error": str(e)})
        return out

    def process_inbox(self, actor: str = "sistema") -> list[dict]:
        """Importa archivos depositados en data/inbox/<FUENTE>/ (LPB, PEP, INTERNA, ...) y los archiva."""
        fmt_for = {"SAT_69B": "sat69b", "SAT_69B_BIS": "generic", "ONU_CSNU": "un"}
        res = []
        base = Path(self.s.inbox_dir)
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            code = d.name.upper()
            files = sorted(f for f in d.iterdir() if f.is_file() and f.suffix.lower() in (".csv", ".xml", ".txt"))
            if not files:
                continue
            f = files[-1]  # el más reciente por nombre = versión vigente completa
            try:
                r = self.import_list(code, f.read_bytes(), fmt_for.get(code, "generic"), f.name, actor)
                r["archivo"] = f.name
                res.append(r)
                done = d / "procesados"
                done.mkdir(exist_ok=True)
                for x in files:
                    shutil.move(str(x), str(done / x.name))
            except ServiceError as e:
                res.append({"source": code, "archivo": f.name, "error": str(e)})
        return res

    def _monitor_delta(self, source: str, external_ids: list[str], actor: str) -> dict:
        """Monitoreo continuo: solo las altas/cambios de la lista se cruzan contra TODOS los sujetos vigentes."""
        if not external_ids:
            return {"sujetos": 0, "alertas_nuevas": 0}
        ids = list(external_ids)
        entries = []
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            ph = ",".join("?" * len(chunk))
            tmp = self._build_index(f"e.source_code=? AND e.external_id IN ({ph})", (source, *chunk))
            entries.extend(tmp.entries.values())
        delta_idx = Index(entries, self.s.th_alta, self.s.th_media, self.s.th_baja)
        if not self._sources:
            self._sources = {r["code"]: dict(r) for r in self.conn.execute("SELECT * FROM sources")}
        subs = [dict(r) for r in self.conn.execute("SELECT * FROM subjects WHERE monitoring=1")]
        n_alerts = 0
        for s in subs:
            q = Query(name=s["name"], entity_type=s["entity_type"], rfc=s["rfc"], curp=s["curp"], dob=s["dob"],
                      country=s["country"])
            matches = [m for m in delta_idx.search(q) if not self._is_whitelisted(s["id"], m, delta_idx)]
            if not any(level_rank(m.level) >= level_rank(self.s.alert_min_level) for m in matches):
                continue
            out = {"fecha": dbm.now(), "referencia": s["ref"], "monitoreo_fuente": source,
                   "coincidencias": [m.to_dict() for m in matches], "listas_consultadas": self._lists_snapshot()}
            max_level = max((m.level for m in matches), key=level_rank)
            with dbm.tx(self.conn):
                cur = self.conn.execute(
                    "INSERT INTO screenings(subject_id,kind,actor,created_at,query_json,result_json,max_level,"
                    "lists_snapshot,evidence_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                    (s["id"], "MONITOREO_LISTA", actor, out["fecha"], _canon({"ref": s["ref"]}), _canon(out), max_level,
                     _canon(out["listas_consultadas"]), hashlib.sha256(_canon(out).encode()).hexdigest()))
                created = self._create_alerts(s["id"], cur.lastrowid, matches, delta_idx)
                n_alerts += len(created)
                if created:
                    dbm.audit(self.conn, actor, "MONITOREO_ALERTA", {"referencia": s["ref"], "fuente": source,
                                                                     "alertas": created})
        return {"sujetos": len(subs), "alertas_nuevas": n_alerts}

    # ------------------------------------------------------------------ reportes
    def dashboard(self) -> dict:
        with self.lock:
            c = lambda sql, *p: self.conn.execute(sql, p).fetchone()[0]  # noqa: E731
            now = dbm.now()
            return {
                "sujetos": c("SELECT COUNT(*) FROM subjects"),
                "consultas": c("SELECT COUNT(*) FROM screenings"),
                "alertas_abiertas": c("SELECT COUNT(*) FROM alerts WHERE status='ABIERTA'"),
                "alertas_pendientes_aprobacion": c("SELECT COUNT(*) FROM alerts WHERE status='PENDIENTE_APROBACION'"),
                "alertas_vencidas": c("SELECT COUNT(*) FROM alerts WHERE status IN ('ABIERTA','PENDIENTE_APROBACION') "
                                      "AND due_at<?", now),
                "alertas_confirmadas": c("SELECT COUNT(*) FROM alerts WHERE status='CONFIRMADA'"),
                "falsos_positivos": c("SELECT COUNT(*) FROM alerts WHERE status='FALSO_POSITIVO'"),
                "registros_en_listas": c("SELECT COUNT(*) FROM entries WHERE active=1"),
                "bitacora": dbm.verify_audit(self.conn),
            }

    def backup(self, directory: str, keep: int = 30) -> str:
        """Copia consistente de la base (API de respaldo de SQLite) con rotación."""
        import sqlite3
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        dest = d / f"pld_{_utc().strftime('%Y%m%d_%H%M%S')}.db"
        with self.lock:
            out = sqlite3.connect(dest)
            self.conn.backup(out)
            out.close()
        for old in sorted(d.glob("pld_*.db"))[:-keep]:
            old.unlink()
        return str(dest)

    def audit_tail(self, limit: int = 100) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT seq,ts,actor,action,detail,hash FROM audit_log ORDER BY seq DESC LIMIT ?", (limit,))]

    def verify_audit(self) -> dict:
        with self.lock:
            return dbm.verify_audit(self.conn)

    # ------------------------------------------------------------------ expedientes (notarías / inmobiliarias)
    def screen_operation(self, data: dict, actor: str) -> dict:
        """Consulta TODAS las partes de un expediente/operación y emite un dictamen consolidado.

        data: {expediente, tipo_acto, partes:[{rol, nombre|nombres+apellidos, tipo, rfc, curp, fecha_nacimiento,
               pais, referencia?, relacionados?:[...]}]}
        Solo consulta personas; no calcula montos ni presenta avisos.
        """
        exp = str(data.get("expediente") or "").strip()
        partes = data.get("partes") or []
        if not exp or len(exp) > 100:
            raise ServiceError("Se requiere 'expediente' (máx. 100 caracteres)")
        if not partes:
            raise ServiceError("Se requiere al menos una parte en 'partes'")
        if len(partes) > 50:
            raise ServiceError("Máximo 50 partes por expediente")
        acto = str(data.get("tipo_acto") or "").strip().upper() or None
        results, levels, hallazgos, advert, links = [], [], [], [], []
        if acto and acto not in ops.ACTOS:
            advert.append(f"Tipo de acto '{acto}' fuera del catálogo; se registró tal cual.")
        for i, p in enumerate(partes, 1):
            rol = str(p.get("rol") or "PARTE").strip().upper()
            curp, rfc = normalize_curp(p.get("curp")), normalize_rfc(p.get("rfc"))
            # Referencia estable por persona (CURP/RFC) → una persona = un sujeto monitoreado en todos sus expedientes
            ref = (p.get("referencia") or "").strip() or (f"P-{curp}" if curp else f"P-{rfc}" if rfc else f"{exp}:{rol}:{i}")
            d = dict(p, referencia=ref, rol=rol, expediente=exp)
            d["relacionados"] = [dict(r, expediente=exp) for r in (p.get("relacionados") or [])]
            res = self.screen(d, actor, persist=True, kind="EXPEDIENTE")
            results.append(res)
            advert += ops.advertencias(acto, rol, res)
            for r in [res] + res.get("relacionados", []):
                if r.get("subject_id"):
                    links.append((r["subject_id"], (r["consulta"].get("rol") or rol)))
                levels.append(r["nivel_maximo"])
                if r["coincidencias"]:
                    hallazgos.append({
                        "parte": r["consulta"]["nombre"], "rol": r["consulta"].get("rol") or rol,
                        "nivel": r["nivel_maximo"], "alertas": r["alertas_generadas"],
                        "listas": sorted({m["fuente"] for m in r["coincidencias"]}),
                        "acciones": r["acciones_recomendadas"]})
        if acto == "FIDEICOMISO":
            roles = {(r["consulta"].get("rol") or "") for r in results}
            advert += [f"Fideicomiso sin parte con rol {n} capturada." for n in ("FIDEICOMITENTE", "FIDEICOMISARIO")
                       if n not in roles]
        worst = max((l for l in levels if l), key=level_rank, default=None)
        dictamen = ("DETENER_Y_ESCALAR" if worst in ("ALTA", "EXACTA")
                    else "REVISION_ANTES_DE_FIRMAR" if worst == "MEDIA" else "SIN_COINCIDENCIAS_RELEVANTES")
        resumen = {
            "expediente": exp, "tipo_acto": acto, "fecha": dbm.now(), "dictamen": dictamen, "nivel_maximo": worst,
            "personas_consultadas": len(levels),
            "partes": [{"id_consulta": r["id_consulta"], "rol": r["consulta"].get("rol"), "nombre": r["consulta"]["nombre"],
                        "referencia": r["referencia"], "resultado": r["resultado"], "nivel_maximo": r["nivel_maximo"],
                        "relacionados": [{"id_consulta": x["id_consulta"], "rol": x["consulta"].get("rol"),
                                          "nombre": x["consulta"]["nombre"], "resultado": x["resultado"],
                                          "nivel_maximo": x["nivel_maximo"]} for x in r.get("relacionados", [])]}
                      for r in results],
            "hallazgos": hallazgos, "advertencias": advert, "listas_consultadas": self._lists_snapshot(),
        }
        resumen["evidencia_sha256"] = hashlib.sha256(_canon(resumen).encode()).hexdigest()
        with self.lock, dbm.tx(self.conn):
            c = self.conn.execute(
                "INSERT INTO operations(expediente,tipo_acto,actor,created_at,max_level,dictamen,result_json,evidence_hash)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (exp, acto, actor, resumen["fecha"], worst, dictamen, _canon(resumen), resumen["evidencia_sha256"]))
            resumen["id_operacion"] = c.lastrowid
            for sid, rl in set(links):
                self.conn.execute("INSERT OR IGNORE INTO operation_parties VALUES(?,?,?)", (c.lastrowid, sid, rl))
            dbm.audit(self.conn, actor, "EXPEDIENTE_CONSULTADO", {
                "id_operacion": c.lastrowid, "expediente": exp, "tipo_acto": acto, "dictamen": dictamen,
                "personas": len(levels), "evidencia_sha256": resumen["evidencia_sha256"]})
        resumen["estado_actual"] = self.get_operation(resumen["id_operacion"])["estado_actual"]
        return resumen

    def list_operations(self, expediente: str | None = None, limit: int = 100) -> list[dict]:
        with self.lock:
            sql, p = "SELECT id,expediente,tipo_acto,actor,created_at,max_level,dictamen,evidence_hash FROM operations", []
            if expediente:
                sql += " WHERE expediente=?"
                p.append(expediente)
            rows = [dict(r) for r in self.conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*p, limit))]
            for r in rows:
                r["estado_actual"] = ops.estado_vivo(self.conn, r["id"], r["dictamen"])["estado"]
            return rows

    def get_operation(self, op_id: int) -> dict:
        with self.lock:
            r = self.conn.execute("SELECT result_json, dictamen FROM operations WHERE id=?", (op_id,)).fetchone()
            if not r:
                raise ServiceError("Operación no encontrada", 404)
            d = json.loads(r["result_json"])
            d["id_operacion"] = op_id
            d["estado_actual"] = ops.estado_vivo(self.conn, op_id, r["dictamen"])
        return d

    def operation_constancia_html(self, op_id: int) -> str:
        d = self.get_operation(op_id)
        e = html.escape
        rows = ""
        for p in d["partes"]:
            rows += (f"<tr><td>{e(str(p['rol'] or ''))}</td><td>{e(p['nombre'])}</td><td>{e(p['resultado'])}</td>"
                     f"<td>{e(str(p['nivel_maximo'] or '—'))}</td><td>#{p['id_consulta']}</td></tr>")
            for x in p["relacionados"]:
                rows += (f"<tr><td>↳ {e(str(x['rol'] or ''))}</td><td>{e(x['nombre'])}</td><td>{e(x['resultado'])}</td>"
                         f"<td>{e(str(x['nivel_maximo'] or '—'))}</td><td>#{x['id_consulta']}</td></tr>")
        hall = "".join(f"<li><b>{e(h['parte'])}</b> ({e(str(h['rol']))}) – nivel {e(str(h['nivel']))}, listas: "
                       f"{e(', '.join(h['listas']))}; alertas: {e(', '.join(map(str, h['alertas'])) or 'ya abiertas')}</li>"
                       for h in d["hallazgos"]) or "<li>Sin hallazgos</li>"
        adv = "".join(f"<li>{e(a)}</li>" for a in d.get("advertencias", [])) or "<li>Ninguna</li>"
        listas = "".join(f"<li>{e(k)}: versión {v['version']} ({e(str(v['fecha_carga']))}, {v['registros']} registros)</li>"
                         for k, v in d["listas_consultadas"].items())
        return f"""<!doctype html><html lang="es"><meta charset="utf-8"><title>Constancia expediente {e(d['expediente'])}</title>
<style>body{{font:14px system-ui;max-width:900px;margin:2rem auto;padding:0 1rem}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #bbb;padding:6px;text-align:left}}th{{background:#eee}}.k{{color:#555}}</style>
<h1>Constancia de consulta de listas – Expediente {e(d['expediente'])}</h1>
<p><b>Folio de operación:</b> {d['id_operacion']} · <b>Acto:</b> {e(str(d['tipo_acto'] or '—'))} · <b>Fecha (UTC):</b> {e(d['fecha'])}
 · <b>Personas consultadas:</b> {d['personas_consultadas']}</p>
<h2>Dictamen: {e(d['dictamen'])}</h2>
<table><tr><th>Rol</th><th>Persona</th><th>Resultado</th><th>Nivel</th><th>Consulta</th></tr>{rows}</table>
<p><b>Estado actual (considera la revisión de alertas):</b> {e(d['estado_actual']['estado'])}</p>
<h3>Hallazgos</h3><ul>{hall}</ul>
<h3>Advertencias para el expediente</h3><ul>{adv}</ul>
<h3>Versiones de listas utilizadas</h3><ul>{listas}</ul>
<p class="k">Huella SHA-256: {e(d['evidencia_sha256'])}<br>
Agregue esta constancia al expediente/protocolo. La consulta de listas es un apoyo: la decisión final corresponde al
titular de la notaría o al Oficial de Cumplimiento. Conserve por el plazo legal (10 años según la reforma de 2025).</p>
<div style="margin-top:50px;display:flex;gap:60px"><div style="border-top:1px solid #000;width:260px;text-align:center">Elaboró</div>
<div style="border-top:1px solid #000;width:260px;text-align:center">Encargado de cumplimiento</div></div></html>"""

    def constancia_html(self, screening_id: int) -> str:
        with self.lock:
            r = self.conn.execute("SELECT * FROM screenings WHERE id=?", (screening_id,)).fetchone()
        if not r:
            raise ServiceError("Consulta no encontrada", 404)
        res = json.loads(r["result_json"])
        e = html.escape
        rows = "".join(
            f"<tr><td>{e(m['fuente'])}</td><td>{e(str(m['nombre_coincidente']))}</td><td>{m['puntaje']}</td>"
            f"<td>{e(m['nivel'])}</td><td>{e('; '.join(m['razones']))}</td></tr>" for m in res.get("coincidencias", []))
        listas = "".join(f"<li>{e(k)}: versión {v['version']} ({e(str(v['fecha_carga']))}, {v['registros']} registros)</li>"
                         for k, v in (res.get("listas_consultadas") or {}).items())
        c = res.get("consulta", {})
        return f"""<!doctype html><html lang="es"><meta charset="utf-8"><title>Constancia de consulta #{screening_id}</title>
<style>body{{font:14px system-ui;max-width:900px;margin:2rem auto;padding:0 1rem}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #bbb;padding:6px;text-align:left}}th{{background:#eee}}.k{{color:#555}}</style>
<h1>Constancia de consulta en listas – PLD/FT</h1>
<p><b>Folio:</b> {screening_id} · <b>Fecha (UTC):</b> {e(r['created_at'])} · <b>Tipo:</b> {e(r['kind'])} · <b>Usuario:</b> {e(r['actor'])}</p>
<h3>Datos consultados</h3><p>{e(json.dumps(c, ensure_ascii=False))}</p>
<h3>Resultado: {e(res.get('resultado', ''))}</h3>
<table><tr><th>Lista</th><th>Nombre coincidente</th><th>Puntaje</th><th>Nivel</th><th>Razones</th></tr>{rows or '<tr><td colspan=5>Sin coincidencias</td></tr>'}</table>
<h3>Versiones de listas utilizadas</h3><ul>{listas}</ul>
<p class="k">Huella SHA-256 de la evidencia: {e(r['evidence_hash'] or '')}<br>
Conserve esta constancia en el expediente del cliente por el plazo legal aplicable (10 años según la reforma a la LFPIORPI de 2025).</p></html>"""
