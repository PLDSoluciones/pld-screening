"""Ejemplo mínimo de integración (Python 3, solo librería estándar).
  export PLD_URL=https://pld.sunotaria.mx ; export PLD_KEY=pld_xxx
  python tools/client_ejemplo.py tools/ejemplo_expediente.json
Códigos de salida: 0 = continuar, 10 = revisar antes de firmar, 20 = DETENER y escalar."""
import json
import os
import sys
import urllib.request

url, key = os.environ["PLD_URL"].rstrip("/"), os.environ["PLD_KEY"]
body = open(sys.argv[1], "rb").read()
req = urllib.request.Request(url + "/v1/operaciones", data=body, method="POST",
                             headers={"X-API-Key": key, "Content-Type": "application/json"})
r = json.load(urllib.request.urlopen(req, timeout=60))
print("DICTAMEN:", r["dictamen"], "| estado:", r["estado_actual"]["estado"], "| operación:", r["id_operacion"])
for h in r["hallazgos"]:
    print(" -", h["parte"], h["rol"], h["nivel"], h["listas"])
for a in r["advertencias"]:
    print(" ! ", a)
print("Constancia:", f"{url}/v1/operaciones/{r['id_operacion']}/constancia (requiere X-API-Key)")
sys.exit({"DETENER_Y_ESCALAR": 20, "REVISION_ANTES_DE_FIRMAR": 10}.get(r["dictamen"], 0))
