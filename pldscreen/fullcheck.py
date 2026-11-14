"""Prueba automática de TODO el sistema:  python -m pldscreen prueba-completa
Crea usuarios, descarga listas reales (si hay internet; si no, usa datos ficticios), autoprueba, expediente de
ejemplo, doble validación, proveedor externo, bitácora y respaldo. Deja marcas PRUEBA-* en la base: úselo en una
instancia de prueba (para limpiar, borre data/pld.db)."""
from __future__ import annotations

import json
from pathlib import Path

from . import selftest

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample"


def run(svc, out=print) -> bool:
    rows: list[tuple[str, bool, str]] = []

    def step(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"EXCEPCIÓN: {e}"
        rows.append((name, ok, detail))
        out(f"{'✔' if ok else '✘'} {name}: {detail}")

    state: dict = {"demo": False}

    def usuarios():
        if svc.has_users():
            return True, "ya existían usuarios (no se creó clave nueva)"
        key = svc.create_user("admin", "admin")
        f = Path(svc.s.db_path).parent / "clave_admin.txt"
        f.write_text(key + "\n")
        return True, f"admin creado; clave guardada en {f} (NO la suba a GitHub)"

    def listas():
        res = svc.update_lists(actor="prueba-completa")
        okc = [r for r in res if "error" not in r]
        bad = [f"{r['source']}: {r['error'][:80]}" for r in res if "error" in r]
        if not okc:
            from .cli import demo
            demo(svc)
            state["demo"] = True
            return True, "SIN INTERNET/URLs: se cargaron listas FICTICIAS de demostración. Errores: " + " | ".join(bad)
        det = ", ".join(f"{r['source']}={r.get('total', '?')}" for r in okc)
        return not bad, det + (" · fallaron: " + " | ".join(bad) if bad else "")

    def lpb_pep_demo():
        if state["demo"]:
            return True, "ya cargadas con la demostración"
        from .cli import demo  # noqa: F401
        for code, fn in (("LPB_UIF", "lpb_demo.csv"), ("PEP", "pep_demo.csv")):
            svc.import_list(code, (SAMPLE / fn).read_bytes(), "generic", fn, "prueba-completa", force=True)
        return True, "LPB y PEP FICTICIAS cargadas (las reales las aporta usted)"

    def auto():
        rep = selftest.run(svc, 100)
        return rep["_aprobado"], selftest.format_report(rep).splitlines()[-1] + \
            f" · control negativo {rep['_control_negativo']['porcentaje']}%"

    def expediente():
        row = svc.conn.execute("SELECT primary_name,rfc,entity_type,source_code FROM entries WHERE active=1 AND "
                               "source_code IN ('SAT_69B','OFAC_SDN','LPB_UIF') AND rfc IS NOT NULL "
                               "ORDER BY RANDOM() LIMIT 1").fetchone()
        if not row:
            return False, "no hay registros con RFC para armar el caso"
        state["caso"] = dict(row)
        op = {"expediente": "PRUEBA-ESC-001", "tipo_acto": "COMPRAVENTA_INMUEBLE", "partes": [
            {"rol": "ENAJENANTE", "nombre": "Persona Limpia De Prueba", "tipo": "F", "fecha_nacimiento": "1985-05-05"},
            {"rol": "ADQUIRENTE", "nombre": "Inmobiliaria De Prueba SA de CV", "tipo": "M", "rfc": "IPR200101AB1",
             "relacionados": [{"rol": "BENEFICIARIO_CONTROLADOR", "nombre": row["primary_name"], "rfc": row["rfc"]}]}]}
        r = svc.screen_operation(op, "prueba-completa")
        state["op"] = r
        ok = r["dictamen"] == "DETENER_Y_ESCALAR"
        return ok, f"caso real {row['source_code']} «{row['primary_name'][:40]}» RFC {row['rfc']} → {r['dictamen']}"

    def doble_validacion():
        alerts = [a for a in svc.list_alerts("ABIERTA") if (a.get("ref") or "").startswith(state["caso"]["rfc"][:4])
                  or a["source_code"] == state["caso"]["source_code"]]
        if not alerts:
            return False, "no se generó la alerta esperada"
        aid = alerts[0]["id"]
        a = svc.resolve_alert(aid, {"name": "prueba_analista", "role": "analista"}, "FALSO_POSITIVO",
                              "Prueba automática de doble validación")
        if a["status"] != "PENDIENTE_APROBACION":
            return False, f"estado inesperado {a['status']}"
        try:
            svc.resolve_alert(aid, {"name": "prueba_analista", "role": "supervisor"}, "FALSO_POSITIVO",
                              "Auto-aprobación indebida")
            return False, "permitió auto-aprobación"
        except Exception:  # noqa: BLE001
            pass
        a = svc.resolve_alert(aid, {"name": "prueba_supervisor", "role": "supervisor"}, "FALSO_POSITIVO",
                              "Prueba automática: aprobación por otra persona")
        return a["status"] == "FALSO_POSITIVO", "propuesta → bloqueo de auto-aprobación → aprobación por otra persona"

    def externo():
        if not svc.provider:
            return True, "omitido (PLD_EXT_PROVIDER=none). Para probar sin clave use PLD_EXT_PROVIDER=mock"
        name = "Rosa Elena Valdivia Camacho" if svc.provider.name == "mock" else "Andrés Manuel López Obrador"
        r = svc.screen({"nombre": name, "externa": True}, "prueba-completa")
        st = r["proveedor_externo"]
        n = len(r["coincidencias"])
        return st["estado"] == "OK", f"{st['proveedor']}: {st['estado']} · {n} coincidencia(s) · {st['detalle']}"

    def bitacora():
        v = svc.verify_audit()
        return v["ok"], f"{v['registros']} registros encadenados"

    def respaldo():
        return True, svc.backup(str(Path(svc.s.db_path).parent / "backups"), 5)

    for n, f in (("1 Usuarios", usuarios), ("2 Listas públicas", listas), ("3 LPB/PEP de prueba", lpb_pep_demo),
                 ("4 Autoprueba con datos reales", auto), ("5 Expediente con caso real", expediente),
                 ("6 Doble validación", doble_validacion), ("7 Proveedor externo", externo),
                 ("8 Bitácora íntegra", bitacora), ("9 Respaldo", respaldo)):
        step(n, f)
    ok = all(r[1] for r in rows)
    out("\nRESULTADO GENERAL: " + ("TODO CORRECTO ✔" if ok else "HAY PASOS CON ERROR ✘ (revise arriba)"))
    if state["demo"]:
        out("AVISO: se usaron datos de demostración porque no hubo descarga; no valida las fuentes reales.")
    return ok
