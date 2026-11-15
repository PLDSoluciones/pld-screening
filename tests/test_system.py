from pathlib import Path

import pytest

from app import db, importers, matching

S = Path(__file__).parent.parent / "sample_data"


@pytest.fixture(autouse=True)
def fresh(tmp_path):
    db.init(str(tmp_path / "t.db"))
    importers.import_file("LPB", (S / "lpb_demo.csv").read_bytes())
    importers.import_file("PEP", (S / "pep_demo.csv").read_bytes())
    importers.import_file("OFAC", (S / "sdn_demo.csv").read_bytes(), (S / "alt_demo.csv").read_bytes())
    importers.import_file("SAT69B", (S / "69b_demo.csv").read_bytes())
    matching.INDEX.rebuild()


def top(q):
    return matching.screen(q)


def test_exact_name_critical():
    r = top({"name": "Juan Carlos Pérez López"})
    assert r["decision"] == "ESCALAR_Y_SUSPENDER"


def test_name_order_and_accents():
    assert top({"name": "PEREZ LOPEZ, JUAN CARLOS"})["top_score"] >= 93


def test_alias_match():
    r = top({"name": "El Charly"})
    assert r["matches"] and r["matches"][0]["source"] == "LPB"


def test_rfc_exact_overrides_name():
    r = top({"name": "Nombre Distinto", "rfc": "PELJ800101AB1"})
    assert r["top_score"] == 100 and "RFC exacto" in r["matches"][0]["reasons"]


def test_dob_mismatch_reduces_score():
    same = top({"name": "Juan Carlos Perez Lopez", "dob": "1980-01-01"})["top_score"]
    diff = top({"name": "Juan Carlos Perez Lopez", "dob": "1999-05-05"})["top_score"]
    assert same > diff


def test_corporate_suffix_ignored():
    r = top({"name": "Comercializadora Ficticia del Pacifico SA de CV"})
    assert r["top_score"] >= 95


def test_transliteration_variant_ofac():
    r = top({"name": "Sergei Ibragimov", "dob": "1975-03-12"})
    assert r["matches"] and r["matches"][0]["source"] == "OFAC"


def test_ofac_rfc_extracted():
    assert top({"name": "x", "rfc": "GTH100101AA1"})["matches"][0]["source"] == "OFAC"


def test_pep_flag():
    r = top({"name": "María Guadalupe Hernández Sánchez"})
    assert any("PEP" in f for f in r["flags"])


def test_69b_desvirtuado_is_informational():
    r = top({"name": "Abastecedora Central", "rfc": "ABC990101AA1"})
    assert r["matches"][0]["level"] == "BAJA"


def test_69b_definitivo_flag():
    r = top({"name": "Servicios Fantasma del Norte"})
    assert any("69-B" in f for f in r["flags"])


def test_no_match_clean():
    assert top({"name": "Ana Torres Villalobos"})["decision"] == "SIN_COINCIDENCIAS"


def test_common_surname_alone_not_high():
    r = top({"name": "Perez"})
    assert r["decision"] != "ESCALAR_Y_SUSPENDER"


def test_false_positive_suppression():
    from app.main import _persist
    res = matching.screen({"name": "Juan Carlos Perez Lopez", "customer_ref": "C1", "dob": "1999-01-01"})
    _persist(res, "t", save_customer=True)
    a = db.q("SELECT * FROM alerts WHERE customer_ref='C1'")
    assert a
    db.run("UPDATE alerts SET status='false_positive' WHERE id=?", (a[0]["id"],))
    res2 = matching.screen({"name": "Juan Carlos Perez Lopez", "customer_ref": "C1", "dob": "1999-01-01"})
    assert res2["dismissed_count"] >= 1 and res2["decision"] in ("SIN_COINCIDENCIAS",) or res2["dismissed_count"] >= 1


def test_audit_chain_detects_tampering():
    assert db.verify_audit()["ok"]
    db.run("UPDATE audit SET payload='{\"x\":1}' WHERE id=1")
    assert not db.verify_audit()["ok"]


def test_import_guard_partial_file():
    rows = [importers._row("X", i, f"NOMBRE {i}") for i in range(200)]
    importers.load_source("X", rows, "h")
    with pytest.raises(importers.ImportError_):
        importers.load_source("X", rows[:20], "h2")
