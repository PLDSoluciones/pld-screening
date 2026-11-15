import pytest
from fastapi.testclient import TestClient

from pldscreen.api import create_app
from pldscreen.service import ServiceError


@pytest.fixture()
def client(svc):
    svc.create_user("admin1", "admin", "ClaveAdmin2026!")
    svc.create_user("ana", "analista", "ClaveAna2026!")
    svc.create_user("solo_api", "analista")  # sin contraseña
    return TestClient(create_app(svc))


def login(c, u, p):
    return c.post("/v1/login", json={"usuario": u, "contrasena": p})


def test_login_ok_y_uso_de_sesion(client):
    r = login(client, "ana", "ClaveAna2026!")
    assert r.status_code == 200 and r.json()["rol"] == "analista"
    tok = r.json()["token"]
    h = {"X-API-Key": tok}
    assert client.get("/v1/me", headers=h).json() == {"usuario": "ana", "rol": "analista", "debe_cambiar_contrasena": False}
    assert client.post("/v1/screen", json={"nombre": "Persona Inventada Cualquiera"}, headers=h).status_code == 200
    assert client.get("/v1/users", headers=h).status_code == 403      # analista no administra usuarios
    assert client.post("/v1/logout", headers=h).status_code == 200
    assert client.get("/v1/me", headers=h).status_code == 401          # sesión cerrada


def test_login_incorrecto(client):
    assert login(client, "ana", "mala").status_code == 401
    assert login(client, "noexiste", "ClaveAna2026!").status_code == 401
    assert login(client, "solo_api", "").status_code == 401           # sin contraseña no entra por la web


def test_bloqueo_por_intentos(client):
    for _ in range(10):
        assert login(client, "ana", "x").status_code == 401
    assert login(client, "ana", "ClaveAna2026!").status_code == 429


def test_admin_crea_usuarios_y_contrasena_minima(client):
    h = {"X-API-Key": login(client, "admin1", "ClaveAdmin2026!").json()["token"]}
    assert client.post("/v1/users", json={"usuario": "nuevo", "rol": "supervisor", "contrasena": "corta"}, headers=h).status_code == 422
    assert client.post("/v1/users", json={"usuario": "nuevo", "rol": "supervisor", "contrasena": "UnaClaveLarga1"}, headers=h).status_code == 200
    assert client.post("/v1/users", json={"usuario": "nuevo", "rol": "supervisor", "contrasena": "UnaClaveLarga1"}, headers=h).status_code == 409
    assert login(client, "nuevo", "UnaClaveLarga1").status_code == 200
    # cambiar contraseña invalida sesiones previas
    tok = login(client, "nuevo", "UnaClaveLarga1").json()["token"]
    assert client.post("/v1/users/nuevo/password", json={"contrasena": "OtraClaveLarga2"}, headers=h).status_code == 200
    assert client.get("/v1/me", headers={"X-API-Key": tok}).status_code == 401
    assert login(client, "nuevo", "OtraClaveLarga2").status_code == 200
    # desactivar
    assert client.post("/v1/users/nuevo/desactivar", headers=h).status_code == 200
    assert login(client, "nuevo", "OtraClaveLarga2").status_code == 401
    assert client.post("/v1/users/admin1/desactivar", headers=h).status_code == 400


def test_bitacora_no_guarda_contrasenas(svc):
    svc.create_user("x1", "analista", "SecretaLarga123")
    svc.login("x1", "SecretaLarga123")
    assert "SecretaLarga123" not in " ".join(r["detail"] for r in svc.audit_tail(100))
    assert svc.verify_audit()["ok"]


def test_contrasena_corta_servicio(svc):
    with pytest.raises(ServiceError):
        svc.create_user("x2", "analista", "corta")
