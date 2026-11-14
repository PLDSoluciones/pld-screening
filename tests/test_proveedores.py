from pldscreen import providers
from pldscreen.config import Settings
from pldscreen.service import Service


def make(tmp_path, provider):
    s = Settings(db_path=str(tmp_path / "x.db"), raw_dir=str(tmp_path / "r"), inbox_dir=str(tmp_path / "i"),
                 country_risk_path=str(tmp_path / "c.csv"), ext_provider=provider, ext_api_key="k")
    return Service(s)


def test_mock_pep_genera_alerta_y_se_recuerda_el_falso_positivo(tmp_path):
    svc = make(tmp_path, "mock")
    d = {"referencia": "X-1", "nombre": "Rosa Elena Valdivia Camacho", "fecha_nacimiento": "1968-03-09"}
    r = svc.screen(d, "ana")
    assert r["proveedor_externo"]["estado"] == "OK"
    m = r["coincidencias"][0]
    assert m["fuente"] == "EXT_PEP" and m["nivel"] in ("ALTA", "EXACTA") and r["riesgo_sugerido"] == "ALTO"
    aid = r["alertas_generadas"][0]
    svc.resolve_alert(aid, {"name": "sofia", "role": "supervisor"}, "FALSO_POSITIVO", "No es la misma persona: revisado")
    r2 = svc.screen(d, "ana")
    assert r2["coincidencias"] == [] and len(r2["descartadas_previamente"]) == 1


def test_mock_variante_de_nombre_y_homonimo(tmp_path):
    svc = make(tmp_path, "mock")
    r = svc.screen({"nombre": "RIOS TREVIÑO GERARDO ANSELMO"}, "ana")
    assert r["coincidencias"] and r["coincidencias"][0]["fuente"] == "EXT_PEP"
    r = svc.screen({"nombre": "Oleg Danilov", "fecha_nacimiento": "1999-01-01"}, "ana")
    assert not r["coincidencias"] or r["coincidencias"][0]["nivel"] != "ALTA"


def test_sin_proveedor_no_cambia_nada(tmp_path):
    svc = make(tmp_path, "none")
    r = svc.screen({"nombre": "Rosa Elena Valdivia Camacho"}, "ana")
    assert r["proveedor_externo"]["estado"] == "NO_CONFIGURADO" and r["coincidencias"] == []


def test_falla_del_proveedor_no_rompe_la_consulta(tmp_path):
    svc = make(tmp_path, "opensanctions")
    svc.provider = type("Roto", (), {"name": "roto", "check": lambda self, q: (_ for _ in ()).throw(RuntimeError("timeout"))})()
    r = svc.screen({"nombre": "Alguien Cualquiera Prueba"}, "ana")
    assert r["proveedor_externo"]["estado"] == "ERROR" and "timeout" in r["proveedor_externo"]["detalle"]


def test_optar_por_no_consultar_externo(tmp_path):
    svc = make(tmp_path, "mock")
    r = svc.screen({"nombre": "Rosa Elena Valdivia Camacho", "externa": False}, "ana")
    assert r["coincidencias"] == []


def test_parse_opensanctions():
    js = {"responses": {"q": {"results": [{"id": "NK-1", "caption": "Juan Pérez López", "schema": "Person",
          "properties": {"name": ["Juan Pérez López", "J. Perez"], "birthDate": ["1970-01-01"], "country": ["mx"],
                         "topics": ["role.pep"]}, "datasets": ["mx_pep"], "score": 0.93, "match": True}]}}}
    h = providers.OpenSanctionsAPI.parse(js)[0]
    assert h["tipo"] == "PEP" and h["dobs"] == ["1970-01-01"] and "J. Perez" in h["aliases"] and h["score_proveedor"] == 0.93
    body = providers.OpenSanctionsAPI("k").request_body(providers.Query(name="Ana", entity_type="F", dob="1980-02-02"))
    assert body["queries"]["q"]["schema"] == "Person" and body["queries"]["q"]["properties"]["birthDate"] == ["1980-02-02"]


def test_parse_dilisense():
    js = {"found_records": [{"id": "d1", "source_type": "PEP", "name": "Ana Gómez", "alias_names": ["A. Gomez"],
                             "date_of_birth": ["01/02/1970"], "citizenship": ["MX"], "positions": ["Alcaldesa"]},
                            {"id": "d2", "source_type": "SANCTION", "name": "Otro", "source_id": "ofac"}]}
    h = providers.DilisenseAPI.parse(js)
    assert [x["tipo"] for x in h] == ["PEP", "SANCION"] and h[0]["aliases"] == ["A. Gomez"]


def test_prueba_completa_automatica(tmp_path, monkeypatch):
    from pldscreen import fullcheck
    from pldscreen.lists import fetch
    monkeypatch.setattr(fetch, "_get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin red en pruebas")))
    svc = make(tmp_path, "mock")
    lines = []
    ok = fullcheck.run(svc, out=lines.append)
    assert ok, "\n".join(lines)
