# Guía paso a paso: de cero a prueba real

Orden recomendado: **Parte 1** (probar en su computadora con listas reales) → **Parte 2** (subir a GitHub) →
**Parte 3** (servidor con HTTPS) → **Parte 4** (integrar con su sistema) → **Parte 5** (plan de prueba real) →
**Parte 6** (pasar a operación). No avance de parte si la anterior no salió bien.

Tiempo aproximado: Parte 1 ≈ 45 min · Parte 2 ≈ 20 min · Parte 3 ≈ 1 h · Parte 5 ≈ 1 h.

---

## Parte 1 · Probar en su computadora (Windows o Mac) con listas reales

Sin servidor y sin costo. Las listas públicas (SAT, OFAC, ONU) se descargan desde **su** internet, así que aquí se
valida de verdad que las descargas funcionan.

1. **Instale Docker Desktop**: <https://www.docker.com/products/docker-desktop/>. En Windows acepte instalar WSL2 y reinicie. Ábralo y espere a que diga “Docker Desktop is running”.
2. **Descomprima** `pld-screening.zip` en una carpeta, por ejemplo `C:\pld-screening`.
3. Abra una terminal **dentro de esa carpeta** (Windows: clic derecho en un espacio vacío → “Abrir en Terminal”).
4. Cree su archivo de configuración:
   - Windows PowerShell: `copy .env.example .env`
   - Mac: `cp .env.example .env`
5. Construya el sistema (tarda unos minutos la primera vez):
   ```
   docker compose build
   ```
6. Cree el usuario administrador. **Copie y guarde la clave que imprime** (no se vuelve a mostrar):
   ```
   docker compose run --rm api python -m pldscreen init
   ```
7. Encienda el sistema:
   ```
   docker compose up -d
   ```
8. Descargue las listas públicas reales (OFAC, ONU, SAT 69-B y 69-B Bis):
   ```
   docker compose run --rm api python -m pldscreen update-lists
   ```
   Debe ver, por cada fuente, números de `total`, `added`… Si alguna dice `error`, vaya a *Solución de problemas* al final.
9. **Autoprueba con datos reales** (toma registros reales de las listas, les inventa errores típicos de captura y verifica que el sistema los encuentre):
   ```
   docker compose run --rm api python -m pldscreen selftest
   ```
   Debe terminar con `RESULTADO: APROBADO`. Guarde una captura de pantalla: es evidencia de validación.
10. Abra <http://localhost:8000>, pegue su clave en la esquina superior y entre a **Listas**: cada fuente cargada debe aparecer “OK”.
11. Vea casos reales para probar a mano:
    ```
    docker compose run --rm api python -m pldscreen muestra --n 3
    ```
    Copie un nombre de la lista SAT_69B y consúltelo en **Consulta rápida** (debe salir ALTA o EXACTA si lo captura completo con su RFC).

> **Alternativa sin Docker:** instale Python 3.10+, y en la carpeta: `python -m venv .venv`, activar (`.venv\Scripts\activate` en Windows, `source .venv/bin/activate` en Mac/Linux), `pip install -r requirements.txt`, `python -m pldscreen init`, `python -m pldscreen update-lists`, `python -m pldscreen serve`. El resto es igual (quite `docker compose run --rm api` de los comandos).

**La lista de Personas Bloqueadas (LPB) de la UIF no se descarga sola** (no es pública). Si usted tiene acceso por su canal oficial, ponga el archivo recibido en `data/inbox/LPB_UIF/` y ejecute `process-inbox` (ver Parte 6). En Docker, la carpeta está dentro del volumen; la forma más simple es la pantalla/endpoint de carga: `POST /v1/lists/LPB_UIF/upload` (ver `/docs`).

---

## Parte 2 · Subirlo a GitHub (repositorio privado)

> Versión ilustrada para principiantes, con prueba en la nube sin instalar nada: [`GUIA_GITHUB_PRINCIPIANTES.md`](GUIA_GITHUB_PRINCIPIANTES.md).

Para qué sirve: guardar el código con historial, ejecutar las pruebas automáticas en cada cambio y poder instalarlo en el servidor con un solo comando.

1. Cree su cuenta en <https://github.com> y **active la verificación en dos pasos** (Settings → Password and authentication).
2. Instale Git: <https://git-scm.com/downloads> (todo por defecto).
3. En GitHub: botón **New repository** → nombre `pld-screening` → **Private** (obligatorio) → *no* marque README/gitignore → *Create repository*.
4. En la terminal, dentro de la carpeta del proyecto:
   ```
   git init
   git add .
   git status
   ```
   **Revise la lista de `git status`:** NO deben aparecer `.env`, ni archivos `.db`, ni `data/raw`, ni `data/inbox`. (El `.gitignore` incluido los excluye. Si aparecen, deténgase.)
   ```
   git commit -m "Version inicial"
   git branch -M main
   git remote add origin https://github.com/SU_USUARIO/pld-screening.git
   git push -u origin main
   ```
   La primera vez se abre el navegador para autorizar su cuenta.
   *(Prefiere interfaz gráfica: instale **GitHub Desktop** → File → Add local repository → Publish repository, marcando “Keep this code private”.)*
5. En GitHub abra la pestaña **Actions**: debe aparecer la corrida “Pruebas” en verde ✔. Si falla, abra el detalle y envíeme el error.

**Reglas de oro:** nunca suba `.env`, claves API, listas LPB/PEP reales, bases de datos ni respaldos. Datos de clientes jamás van en GitHub.

---

## Parte 3 · Servidor con HTTPS (producción)

Necesita: un servidor Linux (VPS) **Ubuntu 24.04, 2 vCPU y 2–4 GB de RAM, 40 GB** (DigitalOcean, Hetzner, AWS Lightsail, etc.; active el cifrado de disco/volumen si el proveedor lo ofrece) y un **dominio** (p. ej. `pld.sunotaria.mx`).

1. **DNS:** en su proveedor de dominio cree un registro **A**: `pld` → IP pública del servidor. Espere 5–30 min.
2. **Entre al servidor:** `ssh root@IP_DEL_SERVIDOR`.
3. **Llave de solo lectura para clonar su repo privado:**
   ```
   ssh-keygen -t ed25519 -f ~/.ssh/pld_deploy -N ""
   cat ~/.ssh/pld_deploy.pub
   ```
   Copie ese texto → GitHub → su repo → **Settings → Deploy keys → Add deploy key** (no marque “write access”).
   ```
   git config --global core.sshCommand "ssh -i ~/.ssh/pld_deploy -o StrictHostKeyChecking=accept-new"
   git clone git@github.com:SU_USUARIO/pld-screening.git
   cd pld-screening
   ```
4. **Prepare el servidor** (instala Docker, firewall y respaldo diario automático):
   ```
   bash deploy/instalar_servidor.sh
   ```
5. **Configure:**
   ```
   cp .env.example .env
   nano .env        # cambie DOMAIN=pld.sunotaria.mx por su dominio; Ctrl+O, Enter, Ctrl+X
   ```
6. **Encienda** (Caddy obtiene el certificado HTTPS solo):
   ```
   docker compose -f docker-compose.prod.yml up -d --build
   docker compose -f docker-compose.prod.yml exec api python -m pldscreen init     # guarde la clave admin
   docker compose -f docker-compose.prod.yml exec api python -m pldscreen update-lists
   docker compose -f docker-compose.prod.yml exec api python -m pldscreen selftest
   ```
7. Cree su **usuario administrador para la página** (el comando le pide la contraseña, mínimo 10 caracteres):
   ```
   docker compose -f docker-compose.prod.yml exec api python -m pldscreen create-user director admin
   ```
   Abra `https://pld.sunotaria.mx` → candado verde → entre con ese usuario y contraseña → revise **Listas**.
8. **Usuarios** (uno por persona; roles `analista`, `supervisor`, `admin`). Desde la página: pestaña **Usuarios** → *Nuevo usuario* (solo administradores). O por terminal:
   ```
   docker compose -f docker-compose.prod.yml exec api python -m pldscreen create-user sofia supervisor
   ```
   Cada persona entra con su usuario y contraseña; las sesiones duran 8 horas y se bloquean 5 minutos tras 10 intentos fallidos. La clave `pld_…` que imprime el comando es solo para integraciones con otros sistemas.
   Cree **al menos 2 analistas y 2 supervisores**: la doble validación exige que quien aprueba sea otra persona.
9. **Actualizar el sistema** cuando haya una versión nueva en GitHub:
   ```
   cd ~/pld-screening && git pull && docker compose -f docker-compose.prod.yml up -d --build
   ```
10. **Respaldos:** el script crea cada noche una copia en `/var/lib/pld-backups` (últimas 30). **Copie esa carpeta fuera del servidor** (otro proveedor/NAS/almacenamiento cifrado) y haga una *prueba de restauración* al menos una vez: detenga el sistema, reemplace `pld.db` por una copia y encienda.

---

## Parte 4 · Integración con su sistema (escrituras, CRM, formularios)

El sistema es una API: su software envía las personas de un expediente y recibe un dictamen.

**1. Cree una clave para el sistema que integra** (rol `analista`):
```
... exec api python -m pldscreen create-user software_notarial analista
```
**2. Pruebe con el ejemplo incluido** (`tools/ejemplo_expediente.json`):
```
curl -X POST https://pld.sunotaria.mx/v1/operaciones \
  -H "X-API-Key: SU_CLAVE" -H "Content-Type: application/json" \
  --data @tools/ejemplo_expediente.json
```
o con Python: `PLD_URL=https://pld.sunotaria.mx PLD_KEY=SU_CLAVE python tools/client_ejemplo.py tools/ejemplo_expediente.json` (el código de salida es 0 continuar / 10 revisar / 20 detener).

**3. Campos por persona** (`partes[]`, y `relacionados[]` dentro de cada parte para beneficiarios controladores, representantes, apoderados, socios):

| Campo | Para qué |
|---|---|
| `rol` | ENAJENANTE, ADQUIRENTE, FIDEICOMITENTE, APODERADO, BENEFICIARIO_CONTROLADOR… |
| `nombre` (o `nombres`+`apellido_paterno`+`apellido_materno`) | Nombre completo o razón social |
| `tipo` | `F` física / `M` moral (si no, se deduce) |
| `rfc`, `curp` | **Identificadores exactos: dan certeza.** Capturar siempre que se tengan |
| `fecha_nacimiento` | Descarta homónimos |
| `pais` | Marca jurisdicciones de alto riesgo (`data/country_risk.csv`) |
| `declara_pep` | `""`, `"NACIONAL"` o `"EXTRANJERA"` (declaración del cliente) |

**4. Interprete la respuesta**

| `dictamen` | Qué hacer |
|---|---|
| `SIN_COINCIDENCIAS_RELEVANTES` | Puede continuar. Guarde la constancia. Revise `advertencias` (datos faltantes del expediente). |
| `REVISION_ANTES_DE_FIRMAR` | Un analista revisa las alertas **antes** de firmar/continuar. |
| `DETENER_Y_ESCALAR` | No firmar/continuar; escalar al encargado de cumplimiento. |

`estado_actual.estado` se **actualiza solo** cuando se resuelven las alertas: `EN_REVISION` → `LIBERADA_TRAS_REVISION` o `DETENER`. Consulte `GET /v1/operaciones/{id_operacion}` antes de firmar.

**5. Constancia para el expediente:** `GET /v1/operaciones/{id}/constancia` devuelve una página lista para imprimir/guardar como PDF (Ctrl+P). Desde la interfaz web, botón “Constancia imprimible”.

**6. Dónde conectarlo en su flujo:** (a) al capturar/identificar a las partes, (b) de nuevo justo antes de la firma o formalización, (c) la vigilancia continua queda sola: si una lista cambia y alguien de su cartera aparece, nace una alerta.

Documentación interactiva de todos los endpoints: `https://pld.sunotaria.mx/docs`.

---

## Parte 5 · Plan de prueba real (aceptación)

Marque cada fila. Use la terminal del servidor o de su computadora.

| # | Prueba | Cómo | Resultado esperado |
|---|---|---|---|
| 1 | Listas descargadas | Pestaña **Listas** | OFAC, ONU, SAT_69B (y BIS) con registros y fecha de hoy |
| 2 | Autoprueba | `... pldscreen selftest` | `APROBADO`; control negativo ≤ 2 % |
| 3 | Caso real SAT | `muestra --n 5`, tome un SAT_69B; consulte **solo el nombre** | Alerta ALTA/MEDIA con fuente SAT_69B |
| 4 | Mismo caso por RFC | Consulte nombre inventado + ese RFC | Nivel **EXACTA** |
| 5 | Caso real OFAC | Tome un OFAC de `muestra`; capture nombre en otro orden y sin acentos | Detectado (OFAC_SDN) |
| 6 | Homónimo | El mismo OFAC con fecha de nacimiento distinta | Baja de nivel y razón “NO coincide” |
| 7 | Persona limpia | Consulte a una persona conocida sin antecedentes | `SIN_COINCIDENCIAS_RELEVANTES` |
| 8 | Expediente completo | Pestaña **Expediente** o `ejemplo_expediente.json` | Dictamen + advertencias + constancia imprimible |
| 9 | Beneficiario controlador | Persona moral con un BC tomado de `muestra` | Dictamen `DETENER_Y_ESCALAR` o `REVISION…` |
| 10 | Doble validación | Con analista cierre como falso positivo una alerta ALTA | Queda `PENDIENTE_APROBACION`; el mismo usuario no puede aprobar; supervisor sí |
| 11 | Monitoreo | Cargue una lista `INTERNA` que incluya a un cliente ya consultado | Nace alerta sin volver a consultar al cliente |
| 12 | Bitácora | `... pldscreen verify-audit` | `ok: True` |
| 13 | Respaldo | `... pldscreen backup` y restaure en otra carpeta | Archivo `.db` consistente |
| 14 | Seguridad | Clave incorrecta 11 veces | Primero 401, luego 429 |
| 15 | Volumen | Envíe 100 expedientes con un script | < 1 s por expediente |

Guarde las constancias y capturas: son su evidencia de validación del mecanismo automatizado (las RCG fijan el 1 de junio de 2027 para su entrada en operación; confirme el texto oficial).

---

## Parte 6 · Pasar a operación

- [ ] Cargar **LPB** (si tiene acceso) y **PEP** (su proveedor o lista propia; la UIF anunció la aplicación “Consulta PEP 2.0”: verifique su disponibilidad y alcance en fuentes oficiales). Copie el CSV a `data/inbox/LPB_UIF/` o `data/inbox/PEP/` dentro del volumen y ejecute `... pldscreen process-inbox` (o súbalo con `POST /v1/lists/{FUENTE}/upload`).
- [ ] Revisar `data/country_risk.csv` contra la lista vigente de jurisdicciones de alto riesgo (el archivo incluido es solo un arranque) y reiniciar.
- [ ] Calibrar umbrales con casos reales (README §9) y dejar por escrito el criterio.
- [ ] Cargar su cartera/expedientes vigentes: `POST /v1/subjects/import-csv`.
- [ ] Crear usuarios nominales, capacitar, y documentar el sistema en el manual de políticas internas.
- [ ] Respaldo fuera del servidor probado; HTTPS activo; `.env` solo en el servidor.
- [ ] Definir con su encargado de cumplimiento los plazos internos (`PLD_SLA_*`) y qué hacer ante una alerta confirmada (el sistema **no** presenta avisos en el portal del SAT).

---

## Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `update-lists` marca `error ... 403/404/timeout` | La autoridad cambió la URL o bloquea la red | Abra la URL en su navegador; si cambió, actualice `PLD_URL_*` en `.env` y reinicie. Mientras tanto descargue el archivo y use `... pldscreen import SAT_69B archivo.csv --format sat69b` |
| `Rechazado: la nueva versión tiene N registros vs M` | Archivo truncado (protección activa) | Vuelva a descargar; si es correcto: `import ... --force` |
| La lista aparece DESACTUALIZADA | El worker no corre o no hay internet | `docker compose ... logs worker` |
| Se perdió la clave admin | No se guarda en claro | Cree otro admin desde el servidor: `... create-user nuevo_admin admin` |
| `Cannot connect to the Docker daemon` | Docker Desktop apagado | Ábralo y espere a que inicie |
| El puerto 8000 está ocupado | Otro programa | Cambie `127.0.0.1:8000:8000` por `127.0.0.1:8080:8000` en `docker-compose.yml` |
| HTTPS no emite certificado | DNS aún no apunta al servidor o puertos 80/443 cerrados | Verifique el registro A y el firewall; `docker compose -f docker-compose.prod.yml logs caddy` |
| Demasiadas alertas | Umbrales bajos | Suba `PLD_TH_*` o `PLD_ALERT_MIN_LEVEL=ALTA` y ejecute `rescreen` |
