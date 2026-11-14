# PLD Screening – Consulta automatizada de listas (LFPIORPI)

Sistema autoalojado para consultar **personas** (partes de una escritura/contrato, beneficiarios controladores,
representantes) contra listas de personas bloqueadas, sanciones y PEP, con monitoreo continuo, flujo de alertas con
doble validación, constancias por expediente y bitácora a prueba de alteraciones. Orientado a **notarías y sector
inmobiliario**; no calcula montos ni presenta avisos.

**¿No es desarrollador? Empiece aquí:** [`docs/GUIA_GITHUB_PRINCIPIANTES.md`](docs/GUIA_GITHUB_PRINCIPIANTES.md) (subir a GitHub y probar todo en la nube, sin instalar nada).

**Prueba real, nombres exactos y dónde obtener las APIs:** [`docs/GUIA_PRUEBA_REAL.md`](docs/GUIA_PRUEBA_REAL.md)

**Guía completa:** [`docs/GUIA_PASO_A_PASO.md`](docs/GUIA_PASO_A_PASO.md) (prueba local → GitHub → servidor HTTPS → integración → plan de prueba real) y
[`docs/SECTOR_NOTARIAL_INMOBILIARIO.md`](docs/SECTOR_NOTARIAL_INMOBILIARIO.md).

> **Aviso:** es una herramienta de apoyo. No sustituye al Oficial de Cumplimiento ni al asesor legal, y no está
> certificada por la UIF/SAT. Valide con ellos los plazos y obligaciones aplicables a su régimen
> (actividad vulnerable o entidad financiera) antes de usarla en producción.

---------------------------------------------------------------------------------------------------

## 1. Qué hace

| Capacidad | Detalle |
|---|---|
| **Fuentes** | LPB-UIF (carga por archivo), SAT 69-B (EFOS) y 69-B Bis (EDOS), OFAC SDN, ONU (CSNU), PEP, listas internas y cualquier CSV adicional |
| **Coincidencias** | RFC y CURP exactos (RFC base-10 con homoclave distinta); nombres difusos tolerantes a acentos, orden invertido, apellidos/segundo nombre omitidos, partículas (DE/DEL/LA), formas societarias (S.A. de C.V., SAPI, S. de R.L.), iniciales, erratas/transposiciones y transliteraciones (MOHAMED/MUHAMMAD, AL-QAIDA/ALQAIDA) |
| **Corroboración** | La fecha de nacimiento sube/baja el nivel (homónimos); nombres de un solo elemento nunca pasan de BAJA/MEDIA |
| **Explicable** | Cada coincidencia trae sus razones y su puntaje → sirve de sustento en el expediente |
| **Niveles** | EXACTA (identificador) · ALTA · MEDIA · BAJA (informativa) – umbrales configurables |
| **Monitoreo continuo** | Cuando una lista cambia, **solo las altas/cambios** se cruzan contra toda su cartera y generan alertas, sin esperar a que el cliente vuelva a operar |
| **Alertas** | Plazo de atención (SLA) con vencidas visibles; doble validación: un analista propone el cierre de alertas de alto riesgo y un supervisor *distinto* lo aprueba |
| **Memoria de falsos positivos** | Un falso positivo aprobado no vuelve a alertar… salvo que la autoridad modifique ese registro |
| **Expediente / operación** | `POST /v1/operaciones`: todas las partes de una escritura en una llamada → dictamen (`SIN_COINCIDENCIAS_RELEVANTES` / `REVISION_ANTES_DE_FIRMAR` / `DETENER_Y_ESCALAR`), advertencias del expediente (sin RFC/CURP, persona moral sin beneficiario controlador, fideicomiso incompleto), estado vivo que se actualiza al resolver alertas y constancia imprimible con firmas |
| **Riesgo país y PEP** | Jurisdicciones de alto riesgo (`data/country_risk.csv`, editable) y PEP declarado por el cliente elevan el riesgo sugerido |
| **Proveedor externo (API)** | Segunda verificación de PEP/sanciones por API (`PLD_EXT_PROVIDER=mock\|opensanctions\|dilisense`); `mock` prueba todo el flujo sin clave. Los fallos del proveedor no interrumpen la consulta local |
| **Prueba automática total** | `python -m pldscreen prueba-completa`: usuarios, descarga real de listas, autoprueba, expediente, doble validación, proveedor, bitácora y respaldo |
| **Autoprueba real** | `selftest` toma registros reales de las listas cargadas, les inventa errores de captura y mide cuántos encuentra; `muestra` imprime casos reales para probar a mano |
| **Evidencia** | Constancia imprimible por consulta con versiones de listas usadas y huella SHA-256 |
| **Bitácora** | Cadena de hashes (cualquier alteración se detecta con `verify-audit`); no guarda datos personales, solo referencias y huellas |
| **Seguridad de datos** | Rechaza archivos de lista truncados, XML malicioso (defusedxml), API keys con hash, roles analista < supervisor < admin |

Rendimiento medido (datos sintéticos, 60 000 registros, un núcleo): ~40 ms por consulta; recall ≥ MEDIA del 100 % en
variantes típicas (orden, erratas, sin segundo nombre) y 0 % de falsos positivos con nombres no listados
(`python tools/benchmark.py`). Con listas reales las cifras serán distintas: **calibre con sus propios datos** (sección 9).

---------------------------------------------------------------------------------------------------

## 2. Marco normativo y cómo se cubre

Resumen basado en fuentes secundarias (Holland & Knight, KPMG, IDC, Garrigues, etc., consultadas en noviembre de 2026).
**Verifique siempre el texto oficial en el DOF**, porque las reglas aún tienen plazos escalonados.

| Norma / hito | Qué exige (según los resúmenes) | Dónde lo cubre el sistema |
|---|---|---|
| Reforma a la LFPIORPI (jul-2025) | Identificación de beneficiario controlador (persona física); conservación 10 años | `relacionados`; bitácora y constancias sin borrado |
| Reforma al Reglamento (27-mar-2026) | Lista PEP integrada por medio electrónico coordinado por la UIF; el SAT puede sustentar sanciones en bases de datos de otras autoridades | Fuente `PEP` (carga por archivo hasta que la UIF habilite el medio); evidencias verificables |
| Modificación a las RCG (7-ago-2026; vigor general 30-nov-2026) | Enfoque basado en riesgos; clasificación bajo/medio/alto revisada al menos cada 6 meses; PEP extranjera = alto riesgo; avisos por sospecha en 24 h; notificaciones electrónicas | `riesgo_sugerido`, `rescreen`, alertas con SLA, constancias |
| 1-mar-2027 | Metodología de riesgo, manual actualizado, nuevo esquema de beneficiario controlador | Insumos: consulta de relacionados y riesgo sugerido |
| **1-jun-2027** | **Entrada en operación de mecanismos automatizados** | Este sistema es el mecanismo automatizado de consulta de listas; documéntelo en su manual |
| Art. 115 LIC y análogas (sector financiero) | Listas de personas bloqueadas: suspender y reportar | Fuente `LPB_UIF` con severidad CRÍTICA y SLA de 24 h (configurable) |

Los resúmenes consultados **no mencionan expresamente** una obligación de consultar OFAC/ONU para actividades
vulnerables: se incluyen como práctica basada en riesgo. El SLA de 24 h es el plazo del aviso por sospecha; confirme
el que aplica a su caso.

---------------------------------------------------------------------------------------------------

## 3. De dónde salen las listas (y qué debe hacer usted)

| Fuente | Acceso | Cómo se carga |
|---|---|---|
| OFAC SDN | Pública | **Automática** (`update-lists` / daemon) |
| ONU CSNU | Pública | **Automática** |
| SAT 69-B y 69-B Bis | Pública (datos abiertos del SAT) | **Automática** |
| Otras del SAT (art. 69, etc.) | Pública | Descargue el CSV → `import` (formato `generic`) |
| **LPB-UIF** | **No pública.** La UIF/SHCP la comunica a quien tiene acceso por su régimen | Usted deposita el archivo que reciba por su canal oficial en `data/inbox/LPB_UIF/` |
| PEP | La UIF integrará el medio electrónico; mientras tanto, su proveedor o su lista propia | `data/inbox/PEP/` |
| Listas internas | Suyas | `data/inbox/INTERNA/` |

> Las URLs de SAT se tomaron de la página oficial de datos abiertos del SAT y las de OFAC/ONU de sus portales, pero
> **no pude probar las descargas en vivo desde mi entorno** (sin salida a esos sitios); el código está probado con
> archivos de muestra en el formato de cada fuente. En su primera corrida ejecute `update-lists` y
> `selftest`; si una URL cambió, ajústela en `.env` (`PLD_URL_*`, admite varias separadas por coma).

CSV genérico (encabezados reconocidos, cualquier orden; `;` `,` tab o `|`):
`id, nombre | (nombres, apellido_paterno, apellido_materno), tipo (F/M), rfc, curp, fecha_nacimiento, pais, alias (separados por |), estatus, observaciones`.
Un `estatus` como BAJA/DESVIRTUADO/REMOVIDO desactiva el registro. Cada archivo es la **lista completa vigente** (reemplaza la anterior).

---------------------------------------------------------------------------------------------------

## 4. Instalación

### Opción A – Docker (recomendada)
```bash
cd pld-screening
cp .env.example .env          # ajuste si lo desea
docker compose build
docker compose run --rm api python -m pldscreen init     # imprime la API key del admin: GUÁRDELA
docker compose up -d                                       # API en http://127.0.0.1:8000 y worker de actualización
```

### Opción B – Servidor Linux/Windows con Python ≥ 3.10
```bash
cd pld-screening
python3 -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
set -a; source .env; set +a                               # opcional (Windows: defina las variables PLD_*)
python -m pldscreen init                                  # API key del admin
python -m pldscreen serve --port 8000                     # API + interfaz web
python -m pldscreen daemon                                # en otra terminal/servicio: actualiza listas cada PLD_UPDATE_EVERY_H h
```
Servicio systemd (Linux) para ambos: cree `pld-api.service` y `pld-worker.service` con `ExecStart=/ruta/.venv/bin/python -m pldscreen serve` / `... daemon`, `Restart=always`, `EnvironmentFile=/ruta/.env`.

---------------------------------------------------------------------------------------------------

## 5. Primer uso, paso a paso

1. **Probar con datos ficticios:** `python -m pldscreen demo` y abra `http://localhost:8000` → pegue su API key → consulte
   “Héctor Vargas Roldán” (OFAC ficticio), CURP `QUSR650505HSLNLM04` (LPB ficticio) o “Facturadora Andina” (SAT ficticio).
   *Los datos de `data/sample` son inventados.* Para empezar de cero, borre `data/pld.db` antes de cargar listas reales.
2. **Crear usuarios:** `python -m pldscreen create-user sofia supervisor` (roles: `analista`, `supervisor`, `admin`).
   Recomendado: al menos 2 analistas y 2 supervisores (la doble validación exige personas distintas).
3. **Cargar listas públicas:** `python -m pldscreen update-lists`.
4. **Cargar LPB / PEP / internas:** copie el archivo a `data/inbox/LPB_UIF/` (o `PEP/`, `INTERNA/`) y ejecute
   `python -m pldscreen process-inbox` (el daemon lo hace solo). También: `python -m pldscreen import LPB_UIF archivo.csv`
   o por API (`POST /v1/lists/LPB_UIF/upload`).
5. **Cargar su cartera existente:** CSV con `referencia,nombre,tipo,rfc,curp,fecha_nacimiento,pais,rol` →
   `POST /v1/subjects/import-csv` (supervisor). Genera consultas iniciales y alertas; desde ahí quedan en monitoreo.
6. **Verificar:** pestaña *Listas* (todas “OK”) y `python -m pldscreen verify-audit` (“ok: True”).

---------------------------------------------------------------------------------------------------

## 6. Integración con su sistema

```bash
curl -X POST https://su-dominio/v1/operaciones -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     --data @tools/ejemplo_expediente.json
```
Detalle de campos, dictámenes y ejemplo en Python (`tools/client_ejemplo.py`) en la
[guía paso a paso, Parte 4](docs/GUIA_PASO_A_PASO.md). Consulta de una sola persona: `POST /v1/screen`
(con `referencia` queda en monitoreo; sin ella es consulta rápida). Documentación interactiva en `/docs`.

---------------------------------------------------------------------------------------------------

## 7. Operación diaria

1. Revise *Alertas* ordenadas por vencimiento (las vencidas se marcan).
2. Compare el registro de la lista contra el expediente (nombre completo, fecha de nacimiento, RFC/CURP, domicilio).
3. **Falso positivo / Confirmada** con justificación (≥10 caracteres). En alertas ALTA/EXACTA o de fuentes críticas, el analista *propone* y un supervisor distinto *aprueba o devuelve*.
4. **Confirmada:** el cliente pasa a riesgo ALTO; siga su manual (suspensión, aviso, reporte). El sistema **no presenta avisos** al portal del SAT/UIF: esa captura es manual.
5. Semanalmente: `/v1/audit/verify` y revisión de listas “DESACTUALIZADA”.

---------------------------------------------------------------------------------------------------

## 8. Puesta en producción (lista de verificación)

- [ ] **HTTPS** delante de la API (no exponga el puerto 8000). Ejemplo con Caddy: `pld.suempresa.mx { reverse_proxy 127.0.0.1:8000 }`.
- [ ] Acceso restringido por VPN/IP; una API key por persona/sistema; rote las keys de quien salga.
- [ ] **Cifrado en disco** (LUKS/BitLocker/volumen cifrado del proveedor): la base contiene datos personales (LFPDPPP).
- [ ] **Respaldos** diarios de `/data` (`pld.db`, `raw/`) con prueba de restauración; conserve **10 años** (consultas, constancias, bitácora).
- [ ] Guarde cada tanto el `ultimo_hash` de la bitácora fuera del servidor (ancla externa contra manipulación).
- [ ] Documente el sistema en su Manual de Políticas Internas (criterios de coincidencia, umbrales, roles, doble validación) y capacite a los usuarios.
- [ ] Incluya el sistema en su auditoría anual (requisito de las RCG).
- [ ] Monitoree el worker (`docker compose logs worker`): las fallas de descarga quedan en bitácora como `ACTUALIZACION_FALLIDA`.

**Escalamiento:** SQLite con WAL soporta cientos de miles de sujetos y decenas de consultas concurrentes en un servidor. Para alta
disponibilidad o varios nodos, migre `db.py` a PostgreSQL (el esquema es estándar) y mantenga el índice en memoria por nodo.

---------------------------------------------------------------------------------------------------

## 9. Calibración (hágala antes de operar)

1. Con sus listas reales, consulte una muestra de 200–500 clientes conocidos y de sus alertas históricas.
2. Ajuste en `.env`: `PLD_TH_ALTA/MEDIA/BAJA` y `PLD_ALERT_MIN_LEVEL`. Más bajo = más alertas y menos riesgo de omisión.
3. Ejecute `python -m pldscreen rescreen` tras cambiar umbrales para re-evaluar toda la cartera.
4. Registre el criterio elegido y su justificación (lo pedirá el auditor).

## 10. Pruebas

`pip install -r requirements.txt && pytest -q tests/test_matching.py tests/test_parsers.py tests/test_workflow.py tests/test_operaciones.py`
→ 50 pruebas (normalización, coincidencias, parsers, alertas, doble validación, monitoreo, expedientes, bitácora, API, seguridad).
Además: `python tools/benchmark.py` (rendimiento sintético) y `python -m pldscreen selftest` (con datos reales).

## 11. Limitaciones conocidas

* Descargas automáticas de OFAC/ONU/SAT no verificadas en vivo (ver sección 3). Los parsers se probaron con muestras en el formato publicado por cada fuente; si una autoridad cambia su formato, el parser fallará de forma visible y conservará la versión anterior.
* No valida RFC/CURP contra los servicios del SAT/RENAPO, no consulta fuentes de medios adversos, ni presenta avisos en el portal.
* “Mejor que el mercado” no está demostrado con comparaciones frente a productos comerciales; lo que sí está medido y probado son las capacidades de la sección 1.
* Transliteraciones de idiomas no latinos (árabe, cirílico, chino) dependen de la forma romanizada que publique la lista.
