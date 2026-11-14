import pytest
from fastapi.testclient import TestClient

from pldscreen import selftest
from pldscreen.api import create_app
from pldscreen.service import ServiceError

OP = {
    "expediente": "ESC-2026-0457", "tipo_acto": "COMPRAVENTA_INMUEBLE",
    "partes": [
        {"rol": "ENAJENANTE", "nombre": "Zoila Ramirez Cantu", "tipo": "F", "curp": "RACZ800101MDFMNL05",
         "fecha_nacimiento": "1980-01-01", "pais": "Mexico"},
        {"rol": "ADQUIRENTE", "nombre": "Inmobiliaria Nueva Era SA de CV", "tipo": "M", "rfc": "INE180101AB1",
         "relacionados": [{"rol": "BENEFICIARIO_CONTROLADOR", "nombre": "Ramon Alberto Quintero Salas",
                           "curp": "QUSR650505HSLNLM04"}]},
    ],
}


def test_operacion_limpia_con_advertencias(svc):
    op = {"expediente": "ESC-1", "tipo_acto": "DONACION", "partes": [
        {"rol": "DONANTE", "nombre": "Zoila Ramirez Cantu", "tipo": "F"},
        {"rol": "DONATARIO", "nombre": "Constructora Lomas SA de CV", "tipo": "M", "rfc": "CLO100101AA1"}]}
    r = svc.screen_operation(op, "ana")
    assert r["dictamen"] == "SIN_COINCIDENCIAS_RELEVANTES"
    txt = " ".join(r["advertencias"])
    assert "sin RFC ni CURP" in txt and "sin fecha de nacimiento" in txt and "beneficiario controlador" in txt


def test_operacion_con_beneficiario_controlador_en_lista_detiene(svc):
    r = svc.screen_operation(OP, "ana")
    assert r["dictamen"] == "DETENER_Y_ESCALAR" and r["nivel_maximo"] == "EXACTA"
    assert r["estado_actual"]["estado"] == "EN_REVISION"
    alerts = svc.list_alerts("ABIERTA")
    assert alerts and alerts[0]["external_id"] == "LPB-001"
    # el beneficiario controlador quedó como sujeto monitoreado con su CURP como referencia
    assert any(s["ref"] == "QUSR650505HSLNLM04" for s in svc.list_subjects())


def test_estado_vivo_al_resolver_alertas(svc):
    op = svc.screen_operation(OP, "ana")
    aid = svc.list_alerts("ABIERTA")[0]["id"]
    svc.resolve_alert(aid, {"name": "sofia", "role": "supervisor"}, "FALSO_POSITIVO",
                      "Homónimo: CURP y fecha de nacimiento no coinciden con el registro")
    assert svc.get_operation(op["id_operacion"])["estado_actual"]["estado"] == "LIBERADA_TRAS_REVISION"
    # el falso positivo aprobado aplica a la misma persona en un expediente nuevo
    r = svc.screen_operation({"expediente": "ESC-9", "tipo_acto": "PODER", "partes": [
        {"rol": "OTORGANTE", "nombre": "Ramon Alberto Quintero Salas", "curp": "QUSR650505HSLNLM04"}]}, "ana")
    assert r["nivel_maximo"] == "EXACTA" or r["dictamen"] != "DETENER_Y_ESCALAR"


def test_pais_de_alto_riesgo_y_pep(svc):
    r = svc.screen({"nombre": "Persona Sin Listas Uno", "pais": "Irán", "declara_pep": "EXTRANJERA"}, "ana")
    assert r["riesgo_sugerido"] == "ALTO" and len(r["factores_adicionales"]) == 2


def test_constancia_operacion(svc):
    svc.screen_operation(OP, "ana")
    h = svc.operation_constancia_html(svc.screen_operation(OP, "ana")["id_operacion"])
    assert "ESC-2026-0457" in h and "Advertencias" in h and "BENEFICIARIO_CONTROLADOR" in h and "LPB_UIF" in h


def test_validaciones(svc):
    with pytest.raises(ServiceError):
        svc.screen_operation({"folio": "", "tipo_acto": "X", "partes": [{"nombre": "a"}]}, "ana")
    with pytest.raises(ServiceError):
        svc.screen_operation({"folio": "F", "tipo_acto": "X", "partes": []}, "ana")


def test_api_operaciones(svc, keys):
    c = TestClient(create_app(svc))
    h = {"X-API-Key": keys["analista"]}
    r = c.post("/v1/operaciones", headers=h, json=OP)
    assert r.status_code == 200 and r.json()["dictamen"].startswith("DETENER")
    oid = r.json()["id_operacion"]
    assert c.get(f"/v1/operaciones/{oid}", headers=h).status_code == 200
    assert c.get("/v1/operaciones/9999", headers=h).status_code == 404
    assert "Constancia" in c.get(f"/v1/operaciones/{oid}/constancia", headers=h).text
    assert c.get("/v1/operaciones", headers=h).json()[0]["expediente"] == "ESC-2026-0457"


def test_selftest_con_listas_cargadas(svc):
    rep = selftest.run(svc, 50)
    assert rep["_aprobado"], selftest.format_report(rep)


def test_backup(svc, tmp_path):
    f = svc.backup(str(tmp_path / "bk"))
    import sqlite3
    assert sqlite3.connect(f).execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 13


def test_limitador_de_intentos_fallidos(svc):
    c = TestClient(create_app(svc))
    codes = [c.get("/v1/dashboard", headers={"X-API-Key": "mala"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
