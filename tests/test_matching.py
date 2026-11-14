import pytest

from pldscreen.normalize import name_tokens, normalize_rfc, parse_dob, skeleton


def top(svc, **q):
    r = svc.screen(q, "test", persist=False)
    return r, (r["coincidencias"][0] if r["coincidencias"] else None)


def test_normalizacion():
    assert name_tokens("Constructora del Norte, S.A. de C.V.", True) == ("CONSTRUCTORA", "NORTE")
    assert name_tokens("MARÍA DE LA LUZ NÚÑEZ") == ("MARIA", "LUZ", "NUNEZ")
    assert skeleton("MOHAMED") == skeleton("MUHAMMAD") == skeleton("MOHAMMED")
    assert normalize_rfc("vah 710312 ab1") == "VAH710312AB1"
    assert parse_dob("DOB 12 Mar 1971") == (1971, 3, 12)


def test_ofac_formato_real_y_orden_invertido(svc):
    # SDN: "VARGAS ROLDAN, Hector Ernesto" → consulta en orden natural y con acentos
    r, m = top(svc, nombre="Héctor Ernesto Vargas Roldán")
    assert m and m["fuente"] == "OFAC_SDN" and m["nivel"] in ("ALTA", "EXACTA")
    r, m = top(svc, nombre="VARGAS ROLDAN HECTOR")  # sin segundo nombre, otro orden
    assert m and m["fuente"] == "OFAC_SDN" and m["puntaje"] >= 78


def test_alias_en_ofac(svc):
    r, m = top(svc, nombre="Hector Hernandez Roldan")
    assert m and m["fuente"] == "OFAC_SDN" and m["tipo_nombre"] == "alias"


def test_rfc_exacto_extraido_de_remarks_ofac(svc):
    r, m = top(svc, nombre="Nombre completamente distinto", rfc="VARH710312AB1")
    assert m and m["nivel"] == "EXACTA" and m["fuente"] == "OFAC_SDN"


def test_rfc_base_con_homoclave_distinta(svc):
    r, m = top(svc, nombre="Pedro Martinez Robles", rfc="PEMR800101AAA")
    assert m and m["fuente"] == "SAT_69B" and m["nivel"] in ("ALTA", "EXACTA")


def test_curp_exacta_lpb(svc):
    r, m = top(svc, curp="QUSR650505HSLNLM04")
    assert m and m["fuente"] == "LPB_UIF" and m["nivel"] == "EXACTA"
    assert r["resultado"] == "ALTA_PRIORIDAD_DETENER_OPERACION"


def test_persona_moral_con_forma_societaria_distinta(svc):
    r, m = top(svc, nombre="Facturadora Andina SA CV", tipo="M")
    assert m and m["fuente"] == "SAT_69B" and m["puntaje"] >= 93


def test_desvirtuado_no_alerta(svc):
    r, m = top(svc, nombre="Servicios Integrales del Norte SA de CV", tipo="M")
    assert m is None


def test_transliteracion_arabe(svc):
    r, m = top(svc, nombre="Mohammed Khalid Al Rahman")
    assert m and m["fuente"] == "OFAC_SDN"
    r, m = top(svc, nombre="Abdulkarim Alhashimi")  # unido, tal como alias ONU
    assert m and m["fuente"] == "ONU_CSNU" and m["nivel"] in ("ALTA", "EXACTA")


def test_homonimo_se_degrada_por_fecha_de_nacimiento(svc):
    base = {"nombre": "Laura Beatriz Fuentes Mendoza"}
    r1, m1 = top(svc, **base, fecha_nacimiento="1975-11-20")
    r2, m2 = top(svc, **base, fecha_nacimiento="1990-01-01")
    assert m1 and m1["fuente"] == "PEP" and m1["nivel"] == "ALTA"
    assert m2 is None or m2["puntaje"] < m1["puntaje"] - 10
    assert m2 is None or m2["nivel"] != "ALTA"


def test_nombre_comun_de_un_solo_elemento_no_es_alta(svc):
    r, m = top(svc, nombre="Armando")
    assert m is None or m["nivel"] in ("BAJA", "MEDIA")


def test_sin_coincidencias(svc):
    r, m = top(svc, nombre="Zoila Ramirez Cantu", fecha_nacimiento="1988-04-04")
    assert m is None and r["resultado"] == "SIN_COINCIDENCIAS_RELEVANTES"


@pytest.mark.parametrize("variante", ["Ramon Alberto Quintero Salas", "QUINTERO SALAS RAMON ALBERTO",
                                      "Ramón A. Quintero Salas", "Ramon Albreto Quintero Salas",  # transposición
                                      "Ramon Quintero"])
def test_variantes_detectadas_lpb(svc, variante):
    r, m = top(svc, nombre=variante)
    assert m and m["fuente"] == "LPB_UIF", variante
