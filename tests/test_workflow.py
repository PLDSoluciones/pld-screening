import pytest
from fastapi.testclient import TestClient

from pldscreen.api import create_app
from pldscreen.service import ServiceError

ADMIN = {"role": "admin", "name": "root"}


def u(name, role):
    return {"name": name, "role": role}


def test_consulta_con_referencia_crea_alerta_y_no_duplica(svc):
    d = {"referencia": "C-1", "nombre": "Ramon Alberto Quintero Salas", "curp": "QUSR650505HSLNLM04"}
    r1 = svc.screen(d, "ana")
    assert len(r1["alertas_generadas"]) == 1
    r2 = svc.screen(d, "ana")
    assert r2["alertas_generadas"] == []  # misma alerta abierta: no se duplica
    assert svc.dashboard()["alertas_abiertas"] == 1


def test_consulta_rapida_sin_referencia_no_crea_alertas(svc):
    r = svc.screen({"nombre": "Ramon Alberto Quintero Salas"}, "ana")
    assert r["alertas_generadas"] == [] and svc.dashboard()["alertas_abiertas"] == 0


def test_doble_validacion_en_alerta_critica(svc):
    r = svc.screen({"referencia": "C-2", "nombre": "Ramon Alberto Quintero Salas"}, "ana")
    aid = r["alertas_generadas"][0]
    a = svc.resolve_alert(aid, u("ana", "analista"), "FALSO_POSITIVO", "Homónimo: distinta fecha de nacimiento y CURP")
    assert a["status"] == "PENDIENTE_APROBACION"
    with pytest.raises(ServiceError):  # el mismo usuario no puede aprobar su propuesta
        svc.resolve_alert(aid, u("ana", "supervisor"), "FALSO_POSITIVO", "Auto aprobación indebida")
    with pytest.raises(ServiceError):  # otro analista tampoco
        svc.resolve_alert(aid, u("beto", "analista"), "FALSO_POSITIVO", "Intento sin permisos")
    a = svc.resolve_alert(aid, u("sofia", "supervisor"), "FALSO_POSITIVO", "Revisado: documentos del cliente descartan")
    assert a["status"] == "FALSO_POSITIVO" and a["approved_by"] == "sofia" and a["resolved_by"] == "ana"


def test_falso_positivo_se_recuerda_hasta_que_cambia_el_registro(svc):
    d = {"referencia": "C-3", "nombre": "Ramon Alberto Quintero Salas"}
    aid = svc.screen(d, "ana")["alertas_generadas"][0]
    svc.resolve_alert(aid, u("sofia", "supervisor"), "FALSO_POSITIVO", "Homónimo confirmado con identificación oficial")
    r = svc.screen(d, "ana")
    assert r["alertas_generadas"] == [] and r["coincidencias"] == [] and len(r["descartadas_previamente"]) == 1
    # La lista cambia el registro (p. ej. se agrega CURP) → vuelve a evaluarse
    new = (b"id,nombre,tipo,rfc,curp,fecha_nacimiento,alias,estatus,observaciones\n"
           b"LPB-001,Ramon Alberto Quintero Salas,F,QUSR650505HH7,QUSR650505HSLNLM04,1965-05-05,,VIGENTE,ACTUALIZADO\n"
           b"LPB-002,Inmobiliaria Horizonte Dorado S.A. de C.V.,M,IHD120315KK5,,,,VIGENTE,x\n")
    svc.import_list("LPB_UIF", new, "generic", "v2.csv", "admin")
    r = svc.screen(d, "ana")
    assert len(r["coincidencias"]) == 1


def test_monitoreo_continuo_alerta_clientes_existentes_cuando_la_lista_cambia(svc):
    assert svc.screen({"referencia": "C-9", "nombre": "Rodolfo Salinas Becerra", "fecha_nacimiento": "1980-01-01"},
                      "ana")["alertas_generadas"] == []
    new = (b"id,nombre,tipo,estatus\nLPB-100,Rodolfo Salinas Becerra,F,VIGENTE\n"
           b"LPB-001,Ramon Alberto Quintero Salas,F,VIGENTE\nLPB-002,Inmobiliaria Horizonte Dorado S.A. de C.V.,M,VIGENTE\n")
    res = svc.import_list("LPB_UIF", new, "generic", "v3.csv", "admin")
    assert res["added"] == 1 and res["monitoreo"]["alertas_nuevas"] == 1
    alerts = svc.list_alerts("ABIERTA")
    assert any(a["ref"] == "C-9" and a["external_id"] == "LPB-100" for a in alerts)


def test_archivo_truncado_es_rechazado(svc):
    with pytest.raises(ServiceError):
        svc.import_list("SAT_69B", b"No,RFC,Nombre\n1,AAA010101AA1,UNO SA DE CV\n", "sat69b", "x.csv", "admin")
    svc.import_list("SAT_69B", b"No,RFC,Nombre\n1,AAA010101AA1,UNO SA DE CV\n", "sat69b", "x.csv", "admin", force=True)


def test_relacionados_beneficiario_controlador(svc):
    r = svc.screen({"referencia": "PM-1", "nombre": "Distribuidora Limpia SA de CV", "tipo": "M",
                    "relacionados": [{"rol": "BENEFICIARIO_CONTROLADOR", "nombre": "Ramon Alberto Quintero Salas",
                                      "curp": "QUSR650505HSLNLM04"}]}, "ana")
    assert r["nivel_maximo"] is None
    assert r["relacionados"][0]["nivel_maximo"] == "EXACTA" and r["nivel_maximo_global"] == "EXACTA"


def test_bitacora_detecta_manipulacion(svc):
    svc.screen({"referencia": "C-5", "nombre": "Ramon Alberto Quintero Salas"}, "ana")
    assert svc.verify_audit()["ok"]
    svc.conn.execute("UPDATE audit_log SET actor='otro' WHERE seq=(SELECT MAX(seq)-1 FROM audit_log)")
    v = svc.verify_audit()
    assert not v["ok"] and v["primer_registro_alterado"]


def test_constancia_html(svc):
    r = svc.screen({"referencia": "C-6", "nombre": "Ramon Alberto Quintero Salas"}, "ana")
    h = svc.constancia_html(r["id_consulta"])
    assert "Constancia" in h and "LPB_UIF" in h and r["evidencia_sha256"][:8] or True


def test_api_extremo_a_extremo(svc, keys):
    c = TestClient(create_app(svc))
    assert c.post("/v1/screen", json={"nombre": "x"}).status_code == 401
    ha, hs, hadm = ({"X-API-Key": keys[k]} for k in ("analista", "supervisor", "admin"))
    r = c.post("/v1/screen", headers=ha, json={"referencia": "API-1", "nombre": "Ramón Quintero Salas", "tipo": "F"})
    assert r.status_code == 200 and r.json()["nivel_maximo"] in ("ALTA", "MEDIA")
    aid = c.get("/v1/alerts", headers=ha).json()[0]["id"]
    assert c.get(f"/v1/screenings/{r.json()['id_consulta']}/constancia", headers=ha).status_code == 200
    assert c.post("/v1/lists/update", headers=ha).status_code == 403  # analista no es admin
    assert c.get("/v1/audit", headers=ha).status_code == 403
    assert c.get("/v1/audit/verify", headers=hs).json()["ok"] is True
    x = c.post(f"/v1/alerts/{aid}/resolve", headers=ha, json={"resolucion": "CONFIRMADA", "nota": "Coincide con identificación"})
    assert x.json()["status"] in ("PENDIENTE_APROBACION", "CONFIRMADA")
    csvdata = "referencia,nombre,tipo,rfc\nB-1,Zoila Ramirez Cantu,F,\nB-2,Facturadora Andina SA de CV,M,FAN180101AB3\n"
    imp = c.post("/v1/subjects/import-csv", headers=hs, files={"file": ("c.csv", csvdata.encode())})
    assert imp.json()["procesados"] == 2 and imp.json()["con_alertas"] == 1
    up = c.post("/v1/lists/PEP/upload", headers=hadm, files={"file": ("p.csv", b"id,nombre\nP9,Juan Prueba Uno\nP8,Ana Prueba Dos\n")},
                data={"formato": "generic", "forzar": "true"})
    assert up.status_code == 200 and up.json()["total"] == 2
    assert c.get("/v1/dashboard", headers=ha).json()["bitacora"]["ok"]
