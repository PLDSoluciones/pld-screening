"""Registro de demos, límites, aislamiento y panel de clientes."""
import pytest
from fastapi.testclient import TestClient

from pldscreen import db as dbm
from pldscreen.api import create_app
from pldscreen.config import Settings
from pldscreen.lists import loader
from pldscreen.service import Service

REG = dict(nombre="Laura Méndez", organizacion="Notaría 5 (prueba)", tipo="NOTARIA", email="laura@ejemplo.mx",
           telefono="5555555555", contrasena="DemoClave2026!", acepta=True)


@pytest.fixture()
def env(tmp_path):
    s = Settings(db_path=str(tmp_path / "t.db"), raw_dir=str(tmp_path / "raw"), inbox_dir=str(tmp_path / "in"),
                 demo_consultas=3, demo_dias=2)
    svc = Service(s)
    svc.create_user("admin1", "admin", "AdminClave2026!")
    return svc, TestClient(create_app(svc))


def tok(c, u, p):
    r = c.post("/v1/login", json={"usuario": u, "contrasena": p})
    assert r.status_code == 200
    return {"X-API-Key": r.json()["token"]}


def test_registro_y_demo(env):
    svc, c = env
    r = c.post("/v1/registro", json=REG)
    assert r.status_code == 200 and r.json()["plan"] == "DEMO"
    h = tok(c, r.json()["usuario"], REG["contrasena"])
    me = c.get("/v1/me", headers=h).json()
    assert me["cuenta"]["estado"] == "DEMO_ACTIVO" and me["cuenta"]["consultas_max"] == 3


def test_registro_valida(env):
    _, c = env
    assert c.post("/v1/registro", json={**REG, "acepta": False}).status_code == 400
    assert c.post("/v1/registro", json={**REG, "email": "malo"}).status_code == 400
    assert c.post("/v1/registro", json={**REG, "contrasena": "corta"}).status_code == 422
    assert c.post("/v1/registro", json={**REG, "web": "http://spam"}).json() == {"ok": True}  # bot: no crea nada
    assert c.post("/v1/registro", json=REG).status_code == 200
    assert c.post("/v1/registro", json=REG).status_code == 409  # correo repetido


def test_demo_limites_y_funciones(env):
    svc, c = env
    u = c.post("/v1/registro", json=REG).json()["usuario"]
    h = tok(c, u, REG["contrasena"])
    for _ in range(3):
        assert c.post("/v1/screen", json={"nombre": "Juan Perez", "referencia": "X1"}, headers=h).status_code == 200
    assert c.post("/v1/screen", json={"nombre": "Juan Perez"}, headers=h).status_code == 402
    for ruta in ("/v1/screenings", "/v1/alerts", "/v1/audit", "/v1/users", "/v1/clientes", "/v1/dashboard"):
        assert c.get(ruta, headers=h).status_code in (402, 403)
    assert svc.conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0] == 0  # la demo no guarda sujetos


def test_demo_vencida(env):
    svc, c = env
    u = c.post("/v1/registro", json=REG).json()["usuario"]
    h = tok(c, u, REG["contrasena"])
    svc.conn.execute("UPDATE customers SET demo_expira='2000-01-01T00:00:00+00:00'")
    assert c.post("/v1/screen", json={"nombre": "Juan Perez"}, headers=h).status_code == 402
    assert c.get("/v1/me", headers=h).json()["cuenta"]["estado"] == "DEMO_VENCIDO"


def test_demo_no_ve_consultas_ajenas(env):
    svc, c = env
    ha = tok(c, "admin1", "AdminClave2026!")
    sid = c.post("/v1/screen", json={"nombre": "Persona Interna"}, headers=ha).json()["id_consulta"]
    u = c.post("/v1/registro", json=REG).json()["usuario"]
    h = tok(c, u, REG["contrasena"])
    assert c.get(f"/v1/screenings/{sid}", headers=h).status_code == 404
    assert c.get(f"/v1/screenings/{sid}/constancia", headers=h).status_code == 404
    mio = c.post("/v1/screen", json={"nombre": "Otra Persona"}, headers=h).json()["id_consulta"]
    r = c.get(f"/v1/screenings/{mio}/constancia", headers=h)
    assert r.status_code == 200 and "VERSIÓN DE DEMOSTRACIÓN" in r.text


def test_panel_admin(env):
    svc, c = env
    c.post("/v1/registro", json=REG)
    ha = tok(c, "admin1", "AdminClave2026!")
    lst = c.get("/v1/clientes", headers=ha).json()
    assert len(lst) == 1 and lst[0]["estado"] == "DEMO_ACTIVO"
    cid = lst[0]["id"]
    assert c.get("/v1/clientes/resumen", headers=ha).json()["DEMO_ACTIVO"] == 1
    assert c.post(f"/v1/clientes/{cid}/extender", headers=ha).status_code == 200
    assert c.post(f"/v1/clientes/{cid}/suspender", headers=ha).status_code == 200
    assert c.get("/v1/clientes?estado=SUSPENDIDO", headers=ha).json()[0]["id"] == cid
    assert c.post("/v1/login", json={"usuario": lst[0]["usuario"], "contrasena": REG["contrasena"]}).status_code == 401
    c.post(f"/v1/clientes/{cid}/reactivar", headers=ha)
    assert c.post(f"/v1/clientes/{cid}/pagado", headers=ha).status_code == 200
    assert c.get("/v1/clientes", headers=ha).json()[0]["estado"] == "PAGADO"
    hc = tok(c, lst[0]["usuario"], REG["contrasena"])
    assert c.get("/v1/screenings", headers=hc).status_code == 200  # ya sin restricciones de demo
    assert "laura@ejemplo.mx" in c.get("/v1/clientes/export.csv", headers=ha).text
    assert c.get("/v1/clientes", headers=hc).status_code == 403  # no es admin


def test_registro_cerrado(env, tmp_path):
    svc, c = env
    svc.s.registro_abierto = False
    assert c.post("/v1/registro", json=REG).status_code == 403
