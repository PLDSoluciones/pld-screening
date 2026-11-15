"""Clientes y demos: registro público, demo limitada (días y consultas), conversión a plan pagado, panel del administrador."""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone

from . import db as dbm

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
TIPOS = ["NOTARIA", "INMOBILIARIA", "DESPACHO", "OTRO"]
# Rutas (método, prefijo) que puede usar una cuenta DEMO
DEMO_PERMITIDO = [("POST", "/v1/screen"), ("GET", "/v1/me"), ("POST", "/v1/logout"), ("GET", "/v1/lists"),
                  ("GET", "/v1/entries/"), ("GET", "/v1/screenings/")]


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _norm_user(email: str) -> str:
    return re.sub(r"[^a-z0-9._-]", "", email.lower().split("@")[0]) or "cliente"


class ClientesMixin:
    # --------------------------------------------------------------- alta
    def _unique_username(self, base: str) -> str:
        name, i = base[:30], 1
        while self.conn.execute("SELECT 1 FROM users WHERE name=?", (name,)).fetchone():
            i += 1
            name = f"{base[:26]}{i}"
        return name

    def registrar_cliente(self, d: dict, contrasena: str, origen: str = "FORMULARIO", actor: str = "registro",
                          plan: str = "DEMO") -> dict:
        from .service import ServiceError
        nombre = (d.get("nombre") or "").strip()
        org = (d.get("organizacion") or "").strip()
        email = (d.get("email") or "").strip().lower()
        if len(nombre) < 3 or len(org) < 2:
            raise ServiceError("Escriba su nombre y el de su notaría, inmobiliaria u organización")
        if not EMAIL_RE.match(email):
            raise ServiceError("Correo electrónico no válido")
        tipo = (d.get("tipo") or "OTRO").upper()
        tipo = tipo if tipo in TIPOS else "OTRO"
        self._check_password(contrasena)
        with self.lock:
            if self.conn.execute("SELECT 1 FROM customers WHERE email=? AND plan='DEMO'", (email,)).fetchone():
                raise ServiceError("Ya existe una demo con ese correo. Pida al administrador ampliarla o activarla.", 409)
        user = self._unique_username(_norm_user(email))
        self.create_user(user, "analista", contrasena)
        exp = (_utc() + timedelta(days=self.s.demo_dias)).isoformat(timespec="seconds") if plan == "DEMO" else None
        with self.lock, dbm.tx(self.conn):
            cur = self.conn.execute(
                "INSERT INTO customers(nombre,organizacion,tipo,email,telefono,user_name,plan,demo_expira,consultas_max,"
                "origen,notas,creado,pagado_en) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (nombre[:120], org[:160], tipo, email, (d.get("telefono") or "").strip()[:30], user, plan, exp,
                 self.s.demo_consultas if plan == "DEMO" else None, origen, (d.get("notas") or "")[:500], dbm.now(),
                 dbm.now() if plan == "PAGADO" else None))
            dbm.audit(self.conn, actor, "CLIENTE_REGISTRADO", {"id": cur.lastrowid, "usuario": user, "plan": plan,
                                                               "organizacion": org, "origen": origen})
        return {"usuario": user, "plan": plan, "demo_expira": exp, "consultas_max": self.s.demo_consultas if plan == "DEMO" else None}

    # --------------------------------------------------------------- estado
    def _estado(self, r, activo: bool) -> str:
        if not activo:
            return "SUSPENDIDO"
        if r["plan"] == "PAGADO":
            return "PAGADO"
        if r["demo_expira"] and r["demo_expira"] <= dbm.now():
            return "DEMO_VENCIDO"
        if r["consultas_max"] is not None and r["consultas_usadas"] >= r["consultas_max"]:
            return "DEMO_AGOTADO"
        return "DEMO_ACTIVO"

    def info_cuenta(self, usuario: str) -> dict | None:
        """None = usuario interno (sin registro de cliente)."""
        with self.lock:
            r = self.conn.execute("SELECT c.*, u.active FROM customers c JOIN users u ON u.name=c.user_name WHERE c.user_name=?",
                                  (usuario,)).fetchone()
        if not r:
            return None
        est = self._estado(r, bool(r["active"]))
        return {"plan": r["plan"], "estado": est, "demo_expira": r["demo_expira"], "consultas_max": r["consultas_max"],
                "consultas_usadas": r["consultas_usadas"], "organizacion": r["organizacion"],
                "contacto": self.s.contacto_ventas}

    def usar_consulta(self, usuario: str) -> None:
        with self.lock:
            self.conn.execute("UPDATE customers SET consultas_usadas=consultas_usadas+1, ultimo_acceso=? WHERE user_name=?",
                              (dbm.now(), usuario))

    def listar_clientes(self, estado: str | None = None, texto: str | None = None) -> list[dict]:
        with self.lock:
            rows = self.conn.execute("SELECT c.*, u.active FROM customers c LEFT JOIN users u ON u.name=c.user_name "
                                     "ORDER BY c.id DESC").fetchall()
        out = []
        for r in rows:
            e = self._estado(r, bool(r["active"]))
            if estado and e != estado.upper():
                continue
            blob = " ".join(str(r[k] or "") for k in ("nombre", "organizacion", "email", "telefono", "user_name")).lower()
            if texto and texto.lower() not in blob:
                continue
            out.append({"id": r["id"], "nombre": r["nombre"], "organizacion": r["organizacion"], "tipo": r["tipo"],
                        "email": r["email"], "telefono": r["telefono"], "usuario": r["user_name"], "plan": r["plan"],
                        "estado": e, "demo_expira": r["demo_expira"], "consultas_max": r["consultas_max"],
                        "consultas_usadas": r["consultas_usadas"], "origen": r["origen"], "notas": r["notas"],
                        "creado": r["creado"], "pagado_en": r["pagado_en"], "ultimo_acceso": r["ultimo_acceso"]})
        return out

    def resumen_clientes(self) -> dict:
        c = {"total": 0, "DEMO_ACTIVO": 0, "DEMO_VENCIDO": 0, "DEMO_AGOTADO": 0, "PAGADO": 0, "SUSPENDIDO": 0}
        for x in self.listar_clientes():
            c["total"] += 1
            c[x["estado"]] += 1
        return c

    def clientes_csv(self) -> str:
        buf = io.StringIO()
        buf.write("﻿")
        w = csv.writer(buf)
        cols = ["id", "nombre", "organizacion", "tipo", "email", "telefono", "usuario", "plan", "estado", "demo_expira",
                "consultas_usadas", "consultas_max", "origen", "creado", "pagado_en", "notas"]
        w.writerow(cols)
        for x in self.listar_clientes():
            w.writerow([("'" + str(x[k]) if str(x[k] or "")[:1] in "=+-@" and x[k] else (x[k] if x[k] is not None else ""))
                        for k in cols])
        return buf.getvalue()

    # --------------------------------------------------------------- acciones del administrador
    def accion_cliente(self, cid: int, accion: str, actor: str, valor: str | None = None) -> dict:
        from .service import ServiceError
        with self.lock:
            r = self.conn.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
        if not r:
            raise ServiceError("Cliente no encontrado", 404)
        with self.lock, dbm.tx(self.conn):
            if accion == "extender":
                base = max(_utc(), datetime.fromisoformat(r["demo_expira"])) if r["demo_expira"] else _utc()
                dias = float(valor or self.s.demo_dias)
                self.conn.execute("UPDATE customers SET demo_expira=?, consultas_max=COALESCE(consultas_max,0)+? WHERE id=?",
                                  ((base + timedelta(days=dias)).isoformat(timespec="seconds"), self.s.demo_consultas, cid))
            elif accion == "pagado":
                self.conn.execute("UPDATE customers SET plan='PAGADO', demo_expira=NULL, consultas_max=NULL, pagado_en=? WHERE id=?",
                                  (dbm.now(), cid))
            elif accion == "demo":
                self.conn.execute("UPDATE customers SET plan='DEMO', pagado_en=NULL, demo_expira=?, consultas_max=?, "
                                  "consultas_usadas=0 WHERE id=?",
                                  ((_utc() + timedelta(days=self.s.demo_dias)).isoformat(timespec="seconds"),
                                   self.s.demo_consultas, cid))
            elif accion == "nota":
                self.conn.execute("UPDATE customers SET notas=? WHERE id=?", ((valor or "")[:500], cid))
            elif accion in ("suspender", "reactivar"):
                self.conn.execute("UPDATE users SET active=? WHERE name=?", (0 if accion == "suspender" else 1, r["user_name"]))
                if accion == "suspender":
                    self.conn.execute("DELETE FROM sessions WHERE name=?", (r["user_name"],))
            else:
                raise ServiceError("Acción no válida")
            dbm.audit(self.conn, actor, "CLIENTE_" + accion.upper(), {"id": cid, "usuario": r["user_name"]})
        return {"ok": True}
