"""CLI: python -m pldscreen <comando>"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .service import Service, ServiceError

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pldscreen", description="Sistema de consulta de listas PLD/FT")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Crea la base de datos y el primer usuario admin")
    u = sub.add_parser("create-user", help="Crea un usuario/API key")
    u.add_argument("name")
    u.add_argument("role", choices=["analista", "supervisor", "admin"])
    u.add_argument("--password", help="Contraseña (mín. 10 caracteres) para entrar por la página. Si se omite, se pide en pantalla")
    sp = sub.add_parser("set-password", help="Asigna o cambia la contraseña de un usuario (se pide en pantalla)")
    sp.add_argument("name")
    sub.add_parser("update-lists", help="Descarga OFAC, ONU y SAT 69-B")
    sub.add_parser("process-inbox", help="Importa archivos de data/inbox/<FUENTE>/")
    i = sub.add_parser("import", help="Importa un archivo a una lista")
    i.add_argument("source")
    i.add_argument("file")
    i.add_argument("--format", default="generic", choices=["generic", "ofac", "un", "sat69b"])
    i.add_argument("--alt", help="ALT.CSV de OFAC (alias)")
    i.add_argument("--force", action="store_true")
    sub.add_parser("demo", help="Carga datos ficticios de ejemplo")
    s = sub.add_parser("screen", help="Consulta rápida desde terminal")
    s.add_argument("nombre")
    s.add_argument("--rfc")
    s.add_argument("--curp")
    s.add_argument("--dob")
    sub.add_parser("rescreen", help="Re-consulta todos los sujetos")
    st = sub.add_parser("selftest", help="Autoprueba con los datos reales ya cargados")
    st.add_argument("--n", type=int, default=150, help="registros por fuente")
    sub.add_parser("prueba-completa", help="Prueba automática de todo el sistema (use una instancia de prueba)")
    mu = sub.add_parser("muestra", help="Imprime registros REALES de las listas cargadas para usarlos como casos de prueba")
    mu.add_argument("--n", type=int, default=3)
    bk = sub.add_parser("backup", help="Respaldo consistente de la base")
    bk.add_argument("--dir", default="data/backups")
    bk.add_argument("--keep", type=int, default=30)
    sub.add_parser("verify-audit", help="Verifica la cadena de hashes de la bitácora")
    d = sub.add_parser("daemon", help="Actualiza listas periódicamente y procesa el inbox")
    d.add_argument("--once", action="store_true")
    sv = sub.add_parser("serve", help="Levanta la API")
    sv.add_argument("--host", default="0.0.0.0")
    sv.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)

    svc = Service()
    try:
        if a.cmd == "init":
            if svc.has_users():
                print("Ya existen usuarios. Use create-user para agregar más.")
            else:
                print("API key del administrador (guárdela, no se vuelve a mostrar):\n", svc.create_user("admin", "admin"))
        elif a.cmd == "create-user":
            import getpass
            pw = a.password or getpass.getpass("Contraseña para entrar por la página (mín. 10 caracteres; Enter = solo API key): ") or None
            print("API key (guárdela, no se vuelve a mostrar):\n", svc.create_user(a.name, a.role, pw))
            if pw:
                print(f"Usuario «{a.name}» ya puede entrar a la página con su contraseña.")
        elif a.cmd == "set-password":
            import getpass
            svc.set_password(a.name, getpass.getpass("Nueva contraseña (mín. 10 caracteres): "), "cli")
            print("Contraseña actualizada.")
        elif a.cmd == "update-lists":
            print(json.dumps(svc.update_lists(actor="cli"), indent=2, ensure_ascii=False))
        elif a.cmd == "process-inbox":
            print(json.dumps(svc.process_inbox("cli"), indent=2, ensure_ascii=False))
        elif a.cmd == "import":
            r = svc.import_list(a.source.upper(), Path(a.file).read_bytes(), a.format, Path(a.file).name, "cli",
                                a.force, Path(a.alt).read_bytes() if a.alt else None)
            print(json.dumps(r, indent=2, ensure_ascii=False))
        elif a.cmd == "demo":
            demo(svc)
        elif a.cmd == "screen":
            r = svc.screen({"nombre": a.nombre, "rfc": a.rfc, "curp": a.curp, "fecha_nacimiento": a.dob}, "cli", persist=False)
            print(json.dumps({k: r[k] for k in ("resultado", "nivel_maximo", "riesgo_sugerido", "coincidencias")},
                             indent=2, ensure_ascii=False))
        elif a.cmd == "selftest":
            from . import selftest
            rep = selftest.run(svc, a.n)
            print(selftest.format_report(rep))
            return 0 if rep["_aprobado"] else 3
        elif a.cmd == "prueba-completa":
            from . import fullcheck
            return 0 if fullcheck.run(svc) else 4
        elif a.cmd == "muestra":
            for code in ("LPB_UIF", "SAT_69B", "SAT_69B_BIS", "SAT_49BIS", "OFAC_SDN", "ONU_CSNU", "PEP", "INTERNA"):
                rows = svc.conn.execute("SELECT primary_name,entity_type,rfc,curp,dobs,external_id FROM entries "
                                        "WHERE source_code=? AND active=1 ORDER BY RANDOM() LIMIT ?", (code, a.n)).fetchall()
                if rows:
                    print(f"\n== {code} ==")
                    for r in rows:
                        print(f"  {r['primary_name']} | tipo={r['entity_type']} | RFC={r['rfc'] or '-'} | CURP={r['curp'] or '-'} | id={r['external_id']}")
        elif a.cmd == "backup":
            print("Respaldo creado:", svc.backup(a.dir, a.keep))
        elif a.cmd == "rescreen":
            print(svc.rescreen_all("cli"))
        elif a.cmd == "verify-audit":
            r = svc.verify_audit()
            print(r)
            return 0 if r["ok"] else 2
        elif a.cmd == "daemon":
            while True:
                print(time.strftime("%F %T"), "actualizando listas…", flush=True)
                print(json.dumps(svc.update_lists(actor="daemon"), ensure_ascii=False), flush=True)
                print(json.dumps(svc.process_inbox("daemon"), ensure_ascii=False), flush=True)
                if a.once:
                    break
                time.sleep(svc.s.update_interval_hours * 3600)
        elif a.cmd == "serve":
            import uvicorn
            from .api import create_app
            uvicorn.run(create_app(svc), host=a.host, port=a.port)
    except ServiceError as e:
        print("Error:", e, file=sys.stderr)
        return 1
    return 0


def demo(svc: Service) -> None:
    """Carga listas FICTICIAS (data/sample) para probar el sistema. No contienen personas reales."""
    for code, fn, fmt in (("LPB_UIF", "lpb_demo.csv", "generic"), ("PEP", "pep_demo.csv", "generic"),
                          ("SAT_69B", "sat69b_demo.csv", "sat69b"), ("ONU_CSNU", "un_demo.xml", "un")):
        r = svc.import_list(code, (SAMPLE / fn).read_bytes(), fmt, fn, "demo")
        print(code, {k: r[k] for k in ("total", "added", "changed", "removed")})
    r = svc.import_list("OFAC_SDN", (SAMPLE / "sdn_demo.csv").read_bytes(), "ofac", "sdn_demo.csv", "demo", False,
                        (SAMPLE / "alt_demo.csv").read_bytes())
    print("OFAC_SDN", {k: r[k] for k in ("total", "added", "changed", "removed")})
    print("Demo cargada. Pruebe: python -m pldscreen screen 'Ramon Quintero Salas'")


if __name__ == "__main__":
    sys.exit(main())
