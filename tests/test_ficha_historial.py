import json

import pytest
from fastapi.testclient import TestClient

from pldscreen.api import create_app
from pldscreen.service import ServiceError


@pytest.fixture()
def client(svc, keys):
    return TestClient(create_app(svc)), keys


def test_ficha_completa_de_coincidencia(svc):
    r = svc.screen({"nombre": "Ramon Quintero Salas"}, "ana")
    assert r["coincidencias"]
    ficha = svc.entry_detail(r["coincidencias"][0]["entry_id"])
    assert ficha["nombre"] and ficha["fuente"] and ficha["nombres"]
    assert ficha["fuente_detalle"]["authority"] and ficha["version_lista"]["entry_count"] >= 1
    assert isinstance(ficha["fechas_nacimiento"], list)
    with pytest.raises(ServiceError):
        svc.entry_detail(999999)


def test_historial_filtros_y_resultado_completo(svc):
    a = svc.screen({"nombre": "Ramon Quintero Salas"}, "ana")
    svc.screen({"nombre": "Persona Totalmente Inventada Xyz"}, "beto")
    todos = svc.screening_history()
    assert len(todos) >= 2 and todos[0]["id"] > todos[1]["id"]
    assert [x for x in svc.screening_history(texto="quintero") if x["nombre"].lower().startswith("ramon")]
    assert not svc.screening_history(texto="no_existe_jamas")
    assert svc.screening_history(texto="100%") == []          # comodines escapados: no coincide con todo
    assert all(x["nivel_maximo"] == a["nivel_maximo"] for x in svc.screening_history(nivel=a["nivel_maximo"]))
    assert svc.get_screening(a["id_consulta"])["evidencia_sha256"] == a["evidencia_sha256"]


def test_csv_evita_inyeccion_de_formulas(svc):
    svc.screen({"nombre": "=HYPERLINK(\"http://x\")"}, "ana")
    csv_text = svc.history_csv()
    assert csv_text.startswith("﻿id,fecha")
    assert "'=HYPERLINK" in csv_text and ",=HYPERLINK" not in csv_text


def test_dashboard_ampliado(svc):
    svc.screen({"nombre": "Ramon Quintero Salas", "referencia": "C-1"}, "ana")
    d = svc.dashboard()
    assert d["consultas_hoy"] >= 1 and len(d["consultas_7_dias"]) == 7
    assert d["consultas_7_dias"][-1]["consultas"] >= 1
    assert isinstance(d["alertas_por_fuente"], dict) and "listas_desactualizadas" in d


def test_api_permisos(client):
    c, k = client
    ha, hs = {"X-API-Key": k["analista"]}, {"X-API-Key": k["supervisor"]}
    sid = c.post("/v1/screen", json={"nombre": "Ramon Quintero Salas"}, headers=ha).json()
    assert c.get("/v1/screenings", headers=ha).status_code == 200
    assert c.get(f"/v1/screenings/{sid['id_consulta']}", headers=ha).json()["resultado"]
    assert c.get(f"/v1/entries/{sid['coincidencias'][0]['entry_id']}", headers=ha).status_code == 200
    assert c.get("/v1/screenings/export.csv", headers=ha).status_code == 403     # solo supervisor
    r = c.get("/v1/screenings/export.csv", headers=hs)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert c.get("/v1/entries/1").status_code == 401


def test_dia_local_usa_zona_de_mexico(svc):
    ini, fin, etiqueta = svc._dia_local(0)
    assert ini.endswith("+00:00") and ini[11:19] == "06:00:00"      # medianoche de CDMX = 06:00 UTC
    assert fin > ini and len(etiqueta) == 10
    assert [x["fecha"] for x in svc._consultas_por_dia(3)] == [svc._dia_local(2)[2], svc._dia_local(1)[2], etiqueta]


def test_filtro_de_fechas_en_hora_local(svc):
    svc.screen({"nombre": "Ramon Quintero Salas"}, "ana")
    hoy = svc._dia_local(0)[2]
    assert svc.screening_history(desde=hoy, hasta=hoy)
    assert not svc.screening_history(hasta=svc._dia_local(1)[2])      # ayer: aún no había consultas
    with pytest.raises(ServiceError):
        svc.screening_history(desde="ayer")
