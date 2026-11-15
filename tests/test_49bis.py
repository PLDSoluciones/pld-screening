def test_carga_49bis_desde_inbox(svc, s_inbox=None):
    d = __import__("pathlib").Path(svc.s.inbox_dir) / "SAT_49BIS"
    d.mkdir(parents=True, exist_ok=True)
    (d / "49bis.csv").write_text(
        "rfc,nombre,tipo,estatus,observaciones\n"
        "AAA010101AAA,EMPRESA FICTICIA DE PRUEBA SA DE CV,M,VIGENTE,Oficio de ejemplo\n"
        "BBB020202BBB,OTRA FICTICIA SA DE CV,M,DESVIRTUADO,x\n", encoding="utf-8")
    r = svc.process_inbox("test")
    assert any(x.get("source") == "SAT_49BIS" and "error" not in x for x in r), r
    out = svc.screen({"nombre": "Empresa Ficticia de Prueba", "rfc": "AAA010101AAA", "tipo": "M"}, "t", persist=False)
    assert any(m["fuente"] == "SAT_49BIS" for m in out["coincidencias"])
    assert out["nivel_maximo"] in ("EXACTA", "ALTA")
    out2 = svc.screen({"nombre": "Otra Ficticia", "rfc": "BBB020202BBB", "tipo": "M"}, "t", persist=False)
    assert not any(m["fuente"] == "SAT_49BIS" for m in out2["coincidencias"])  # desvirtuado = inactivo


def test_estado_de_listas_no_marca_manuales_como_desactualizadas(svc):
    est = {x["code"]: x for x in svc.lists_status()}
    assert est["SAT_49BIS"]["modo"] == "MANUAL" and est["SAT_49BIS"]["estado"] == "SIN CARGAR"
    assert not est["SAT_49BIS"]["desactualizada"]
    assert est["EXT_PEP"]["modo"] == "API" and est["EXT_PEP"]["estado"] == "NO CONFIGURADA"
    assert est["OFAC_SDN"]["modo"] == "AUTOMATICA" and est["OFAC_SDN"]["estado"] == "OK"
    assert est["LPB_UIF"]["modo"] == "MANUAL" and est["LPB_UIF"]["estado"] == "OK"
