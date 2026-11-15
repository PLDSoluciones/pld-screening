"""Cuenta propia, estado del sistema, respaldo descargable, depuración de demos y cambio de rol."""
from __future__ import annotations

import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db as dbm

VERSION = "2.0"


class AdminMixin:
    def cambiar_mi_contrasena(self, usuario: str, actual: str, nueva: str) -> None:
        from .service import ServiceError
        with self.lock:
            r = self.conn.execute("SELECT pw_hash,pw_salt FROM users WHERE name=? AND active=1", (usuario,)).fetchone()
        if not r or not r["pw_hash"] or not secrets.compare_digest(self._pw_hash(actual or "", r["pw_salt"]), r["pw_hash"]):
            raise ServiceError("La contraseña actual no es correcta", 400)
        if nueva == actual:
            raise ServiceError("La nueva contraseña debe ser distinta de la actual")
        self.set_password(usuario, nueva, usuario)  # valida largo y cierra las demás sesiones

    def restablecer_contrasena(self, name: str, actor: str) -> str:
        """Genera una contraseña temporal aleatoria (se muestra una sola vez); el usuario deberá cambiarla al entrar."""
        alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"  # sin caracteres ambiguos
        temporal = "".join(secrets.choice(alfabeto) for _ in range(12))
        self.set_password(name, temporal, actor, forzar_cambio=True)
        return temporal

    # ---- recuperación desde la pantalla de inicio de sesión
    def solicitar_restablecimiento(self, usuario: str) -> None:
        """Registra una solicitud para que el administrador restablezca la contraseña. No revela si el usuario existe."""
        usuario = (usuario or "").strip()[:60]
        with self.lock, dbm.tx(self.conn):
            ok = self.conn.execute("SELECT 1 FROM users WHERE name=? AND active=1", (usuario,)).fetchone()
            ya = self.conn.execute("SELECT 1 FROM password_requests WHERE usuario=? AND estado='PENDIENTE'", (usuario,)).fetchone()
            if ok and not ya:
                self.conn.execute("INSERT INTO password_requests(usuario,creado) VALUES(?,?)", (usuario, dbm.now()))
                dbm.audit(self.conn, "anonimo", "RESTABLECIMIENTO_SOLICITADO", {"usuario": usuario})

    def solicitudes_restablecimiento(self) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT id,usuario,creado FROM password_requests WHERE estado='PENDIENTE' ORDER BY id")]

    def recuperar_admin(self, usuario: str, codigo: str, nueva: str) -> bool:
        """Cambia la contraseña de un ADMIN con el código secreto del servidor (PLD_RECOVERY_CODE). False = código/usuario incorrecto."""
        from .service import ServiceError
        cod = self.s.recovery_code or ""
        if len(cod) < 16:
            raise ServiceError("La recuperación por código no está configurada en este servidor", 403)
        with self.lock:
            r = self.conn.execute("SELECT 1 FROM users WHERE name=? AND role='admin' AND active=1", (usuario,)).fetchone()
        if not secrets.compare_digest((codigo or "").encode(), cod.encode()) or not r:
            return False
        self.set_password(usuario, nueva, "recuperacion", forzar_cambio=False)
        return True

    def set_role(self, name: str, role: str, actor: str) -> None:
        from .service import ROLES, ServiceError
        if role not in ROLES:
            raise ServiceError(f"Rol inválido. Use: {', '.join(ROLES)}")
        with self.lock, dbm.tx(self.conn):
            cur = self.conn.execute("UPDATE users SET role=? WHERE name=?", (role, name))
            if cur.rowcount == 0:
                raise ServiceError("Usuario no encontrado", 404)
            self.conn.execute("DELETE FROM sessions WHERE name=?", (name,))  # el nuevo rol aplica al volver a entrar
            dbm.audit(self.conn, actor, "ROL_CAMBIADO", {"usuario": name, "rol": role})

    def ultimos_accesos(self) -> dict[str, str]:
        with self.lock:
            return {r["actor"]: r["m"] for r in self.conn.execute(
                "SELECT actor, MAX(ts) m FROM audit_log WHERE action='INICIO_SESION' GROUP BY actor")}

    def estado_sistema(self) -> dict:
        c = self.conn
        with self.lock:
            n = lambda q: c.execute(q).fetchone()[0]  # noqa: E731
            hoy = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
            ult = c.execute("SELECT MAX(fetched_at) FROM list_versions WHERE status='OK'").fetchone()[0]
            dbp = Path(self.s.db_path)
            size = dbp.stat().st_size if dbp.exists() else 0
            return {
                "version": VERSION, "hora_servidor_utc": dbm.now(), "zona_horaria_horas": self.s.tz_offset_hours,
                "base_datos": {"archivo": str(dbp), "mb": round(size / 1_048_576, 2)},
                "totales": {"consultas": n("SELECT COUNT(*) FROM screenings"),
                            "consultas_24h": c.execute("SELECT COUNT(*) FROM screenings WHERE created_at>=?", (hoy,)).fetchone()[0],
                            "personas_monitoreadas": n("SELECT COUNT(*) FROM subjects"),
                            "alertas_abiertas": n("SELECT COUNT(*) FROM alerts WHERE status IN ('ABIERTA','PROPUESTA')"),
                            "usuarios_activos": n("SELECT COUNT(*) FROM users WHERE active=1"),
                            "clientes": n("SELECT COUNT(*) FROM customers"),
                            "registros_en_listas": n("SELECT COUNT(*) FROM entries WHERE active=1")},
                "ultima_carga_listas": ult,
                "actualizacion_automatica": os.getenv("PLD_AUTO_UPDATE", "1") == "1",
                "proveedor_externo": self.provider.name if self.provider else None,
                "registro_demos_abierto": self.s.registro_abierto,
                "respaldos": self._respaldos_info(),
            }

    def _respaldos_info(self) -> dict:
        d = Path("data/backups")
        fs = sorted(d.glob("pld_*.db")) if d.exists() else []
        return {"cantidad": len(fs), "ultimo": fs[-1].name if fs else None}

    def respaldo_bytes(self, actor: str) -> tuple[str, bytes]:
        """Copia consistente de la base lista para descargar (admin)."""
        import sqlite3
        nombre = f"pld_respaldo_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.db"
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / nombre
            with self.lock:
                out = sqlite3.connect(dest)
                self.conn.backup(out)
                out.close()
                with dbm.tx(self.conn):
                    dbm.audit(self.conn, actor, "RESPALDO_DESCARGADO", {"archivo": nombre})
            return nombre, dest.read_bytes()

    def depurar_demos(self, dias: int, actor: str) -> dict:
        """Borra las consultas hechas por cuentas de demo vencidas hace más de `dias` días (minimización de datos)."""
        corte = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat(timespec="seconds")
        with self.lock, dbm.tx(self.conn):
            users = [r["user_name"] for r in self.conn.execute(
                "SELECT user_name FROM customers WHERE plan='DEMO' AND demo_expira IS NOT NULL AND demo_expira<?", (corte,))]
            borradas = 0
            for u in users:
                borradas += self.conn.execute("DELETE FROM screenings WHERE actor=?", (u,)).rowcount
            dbm.audit(self.conn, actor, "DEPURACION_DEMOS", {"cuentas": len(users), "consultas_borradas": borradas, "dias": dias})
        return {"cuentas": len(users), "consultas_borradas": borradas}
