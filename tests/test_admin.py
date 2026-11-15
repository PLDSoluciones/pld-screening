import sqlite3

import pytest
from fastapi.testclient import TestClient

from pldscreen.api import create_app
from pldscreen.config import Settings
from pldscreen.service import Service

REG = dict(nombre="Laura Méndez", organizacion="Notaría 5", tipo="NOTARIA", email="laura@ejemplo.mx",
           contrasena="DemoClave2026!", acepta=True)


@pytest.fixture()
def env(tmp_path):
    svc = Service(Settings(db_path=str(tmp_path / "t.db"), raw_dir=str(tmp_path / "r"), inbox_dir=str(tmp_path / "i")))
    svc.create_user("admin1", "admin", "AdminClave2026!")
    svc.create_user("ana", "analista", "ClaveAna2026!")
    return svc, TestClient(create_app(svc))


def tok(c, u, p):
    return {"X-API-Key": c.post("/v1/login", json={"usuario": u, "contrasena": p}).json()["token"]}


def test_cambiar_mi_contrasena(env):
    _, c = env
    h = tok(c, "ana", "ClaveAna2026!")
    assert c.post("/v1/me/password", json={"actual": "mala", "nueva": "OtraClave2026!"}, headers=h).status_code == 400
    assert c.post("/v1/me/password", json={"actual": "ClaveAna2026!", "nueva": "ClaveAna2026!"}, headers=h).status_code == 400
    assert c.post("/v1/me/password", json={"actual": "ClaveAna2026!", "nueva": "OtraClave2026!"}, headers=h).status_code == 200
    assert c.post("/v1/login", json={"usuario": "ana", "contrasena": "ClaveAna2026!"}).status_code == 401
    assert c.post("/v1/login", json={"usuario": "ana", "contrasena": "OtraClave2026!"}).status_code == 200


def test_demo_puede_cambiar_su_contrasena(env):
    _, c = env
    u = c.post("/v1/registro", json=REG).json()["usuario"]
    h = tok(c, u, REG["contrasena"])
    assert c.post("/v1/me/password", json={"actual": REG["contrasena"], "nueva": "NuevaClave2026!"}, headers=h).status_code == 200


def test_rol_y_ultimo_acceso(env):
    _, c = env
    ha = tok(c, "admin1", "AdminClave2026!")
    assert c.post("/v1/users/ana/rol", json={"rol": "supervisor"}, headers=ha).status_code == 200
    assert c.post("/v1/users/admin1/rol", json={"rol": "analista"}, headers=ha).status_code == 400
    assert c.post("/v1/users/ana/rol", json={"rol": "dios"}, headers=ha).status_code == 400
    us = {x["usuario"]: x for x in c.get("/v1/users", headers=ha).json()}
    assert us["ana"]["rol"] == "supervisor" and us["admin1"]["ultimo_acceso"]


def test_sistema_respaldo_y_permisos(env, tmp_path):
    _, c = env
    ha, hn = tok(c, "admin1", "AdminClave2026!"), tok(c, "ana", "ClaveAna2026!")
    s = c.get("/v1/sistema", headers=ha).json()
    assert s["version"] == "2.0" and s["totales"]["usuarios_activos"] == 2
    r = c.get("/v1/sistema/respaldo", headers=ha)
    assert r.status_code == 200 and r.content[:15] == b"SQLite format 3"
    f = tmp_path / "bk.db"
    f.write_bytes(r.content)
    assert sqlite3.connect(f).execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
    assert c.get("/v1/sistema", headers=hn).status_code == 403
    assert c.get("/v1/sistema/respaldo", headers=hn).status_code == 403


def test_depurar_demos(env):
    svc, c = env
    u = c.post("/v1/registro", json=REG).json()["usuario"]
    h = tok(c, u, REG["contrasena"])
    c.post("/v1/screen", json={"nombre": "Alguien Prueba"}, headers=h)
    ha = tok(c, "admin1", "AdminClave2026!")
    assert c.post("/v1/sistema/depurar-demos", headers=ha).json()["consultas_borradas"] == 0  # aún vigente
    svc.conn.execute("UPDATE customers SET demo_expira='2000-01-01T00:00:00+00:00'")
    assert c.post("/v1/sistema/depurar-demos", headers=ha).json()["consultas_borradas"] == 1
