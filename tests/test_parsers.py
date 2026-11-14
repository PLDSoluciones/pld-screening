from pathlib import Path

from pldscreen.lists import parsers

S = Path(__file__).resolve().parent.parent / "data" / "sample"


def test_ofac():
    recs = parsers.parse_ofac((S / "sdn_demo.csv").read_bytes(), (S / "alt_demo.csv").read_bytes())
    r = {x["external_id"]: x for x in recs}
    assert r["90001"]["name"] == "Hector Ernesto VARGAS ROLDAN" and r["90001"]["entity_type"] == "F"
    assert r["90001"]["rfc"] == "VARH710312AB1" and r["90001"]["curp"] is None or len(r["90001"]["curp"]) == 18
    assert r["90001"]["dobs"] == ["12 Mar 1971"] and "Hector HERNANDEZ ROLDAN" in r["90001"]["aliases"]
    assert r["90002"]["entity_type"] == "M" and r["90002"]["rfc"] == "CTR150820XY9"


def test_sat69b_latin1_y_estatus():
    recs = {x["external_id"]: x for x in parsers.parse_sat69b((S / "sat69b_demo.csv").read_bytes())}
    assert recs["FAN180101AB3"]["active"] and recs["PEMR800101XY2"]["active"]
    assert not recs["SIN170202ZZ1"]["active"]  # desvirtuado
    assert recs["FAN180101AB3"]["entity_type"] == "M" and recs["PEMR800101XY2"]["entity_type"] == "F"


def test_un():
    recs = parsers.parse_un((S / "un_demo.xml").read_bytes())
    ind = next(x for x in recs if x["entity_type"] == "F")
    assert ind["name"] == "ABDUL KARIM AL-HASHIMI" and "Abdulkarim Alhashimi" in ind["aliases"]
    assert ind["dobs"] == ["1972-07-01"]
    assert any(x["entity_type"] == "M" and "FLF" in x["aliases"] for x in recs)


def test_generico_separadores_y_alias():
    csv_ = "ID;Nombre;Alias\n1;Juan Perez;Juanito|JP\n".encode()
    r = parsers.parse_generic(csv_)[0]
    assert r["aliases"] == ["Juanito", "JP"]


def test_un_xml_malicioso_rechazado():
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><x>&b;</x>'
    import pytest
    with pytest.raises(Exception):
        parsers.parse_un(bomb)
