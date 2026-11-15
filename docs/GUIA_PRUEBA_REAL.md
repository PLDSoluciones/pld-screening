# Guía de prueba REAL (no simulada): nombres exactos y orden de pasos

## 0. ¿Está listo?

| Componente | Estado |
|---|---|
| Motor de coincidencias, alertas, doble validación, expedientes, constancias, bitácora, API, interfaz | **Probado** (50 pruebas automáticas + prueba en navegador) |
| Descarga automática de SAT 69-B / 69-B Bis, OFAC y ONU | **Escrita pero NO verificada en vivo** (desde mi entorno no hay acceso a esos sitios). Se valida en su primera corrida: paso 5 |
| Conectores Dilisense y OpenSanctions | **Escritos con su documentación pública, NO verificados en vivo.** Se validan en el paso 7 |
| Lista de Personas Bloqueadas (UIF) y lista PEP oficial | **No existen como API pública.** Se cargan desde archivo si usted tiene acceso oficial |
| Operación con clientes reales | **Todavía no.** Primero apruebe esta prueba, confirme su acceso oficial a la LPB, calibre umbrales y valide con su asesor |

Esta guía lo lleva a una **prueba real con datos públicos reales, en un entorno desechable y con datos ficticios de clientes**.

## 1. Nombres exactos (úselos tal cual)

| Qué | Nombre |
|---|---|
| Repositorio de GitHub | `pld-screening` (Visibilidad: **Private**) |
| Rama | `main` (la crea GitHub Desktop sola) |
| Mensaje del primer commit | `Version inicial` |
| Codespace | el que GitHub proponga (no hace falta nombrarlo) |
| Secreto de Codespaces 1 | `PLD_EXT_PROVIDER` → valor `dilisense` (o `opensanctions`) |
| Secreto de Codespaces 2 | `PLD_EXT_API_KEY` → valor: la clave que le dé el proveedor |
| Usuarios del sistema | `admin` (se crea solo), `analista1`, `analista2`, `supervisor1`, `supervisor2` |
| Carpeta para la LPB (si tiene acceso) | `data/inbox/LPB_UIF/` (cualquier nombre de archivo `.csv`) |
| Carpeta para PEP propias o de proveedor | `data/inbox/PEP/` |
| Carpeta para listas internas | `data/inbox/INTERNA/` |

**No debe crear carpetas ni secciones a mano:** el zip ya trae toda la estructura. Tras subirlo, la raíz del repositorio debe verse así
(si falta alguna, la subida quedó incompleta):

```
.devcontainer/   .github/   data/   deploy/   docs/   pldscreen/   tests/   tools/
.dockerignore   .env.example   .gitignore   Caddyfile   Dockerfile
README.md   docker-compose.prod.yml   docker-compose.yml   requirements.txt
```

## 2. Subir a GitHub (resumen; detalle con capturas de pantalla en `GUIA_GITHUB_PRINCIPIANTES.md`, Paso 2)

1. Cuenta en <https://github.com/signup> y verificación en dos pasos.
2. Instale **GitHub Desktop** (<https://desktop.github.com>) e inicie sesión.
3. Descomprima el zip. **File → Add local repository… → Choose…** → elija la carpeta `pld-screening` → clic en **create a repository** → deje todo por defecto (*Git ignore: None*, *License: None*) → **Create repository**.
4. Revise la lista de cambios: **no deben aparecer** `.env`, archivos `.db` ni `clave_admin.txt`.
5. Summary: `Version inicial` → **Commit to main** → **Publish repository** → marque ✔ **Keep this code private** → **Publish**.
6. En github.com → su repositorio → pestaña **Actions** → la corrida **Pruebas** debe terminar en ✔ verde.

## 3. Obtener las APIs REALES

Las fuentes **oficiales no usan API ni clave**: el sistema las descarga solo.

| Fuente | Cómo se obtiene | ¿Clave? |
|---|---|---|
| SAT 69-B / 69-B Bis | Descarga automática desde datos abiertos del SAT | No |
| OFAC (EE. UU.) | Descarga automática del Tesoro | No |
| ONU | Descarga automática del Consejo de Seguridad | No |
| **Lista de Personas Bloqueadas (UIF)** | Canal oficial UIF/SAT/SHCP. **Pregunte por escrito** si su notaría/inmobiliaria tiene acceso y en qué formato. Ningún proveedor comercial debe vendérsela | No hay API |
| **PEP oficial (UIF)** | Aplicación “Consulta PEP 2.0” con e.firma (según los resúmenes consultados, disponible a partir de ≈ agosto de 2027). No tiene API | No hay API |

**Art. 49 Bis CFF (CFDI falsos, vigente desde 2026).** El SAT lo publica con oficios individuales en el DOF y en su portal; a la fecha **no hay archivo oficial consolidado** (el apartado de Datos Abiertos solo trae 69, 69-B y 69-B Bis). Por eso el sistema lo carga desde un archivo que **usted mantiene**:
1. Copie `data/plantillas/SAT_49BIS.csv` a `data/inbox/SAT_49BIS/` (cualquier nombre `.csv`).
2. Capture una fila por contribuyente publicado (columnas `rfc,nombre,tipo,estatus,observaciones`), tomando los datos **del oficio del DOF o del portal del SAT**. En *observaciones* anote el número de oficio y la fecha.
3. Cada vez que haya un oficio nuevo, agregue la fila al **mismo archivo completo** (con un nombre que ordene después, p. ej. `49bis_2026-11-14.csv`) y ejecute `python -m pldscreen process-inbox`. El archivo más reciente reemplaza al anterior, por eso debe contener la lista completa.
4. No use listas de terceros (blogs, Excel de despachos) como fuente única: son útiles para enterarse, pero la evidencia es el DOF.

APIs comerciales para PEP/sanciones (para complementar, no para sustituir lo oficial):

| Proveedor | Cómo obtener la clave | Para activarlo en este sistema |
|---|---|---|
| **Dilisense** | Entre a <https://dilisense.com>, botón **Try Free**, regístrese y copie su API key (plan *Starter*: 100 consultas gratis) | `PLD_EXT_PROVIDER=dilisense` y `PLD_EXT_API_KEY=su_clave` |
| **OpenSanctions** | Entre a <https://www.opensanctions.org>, sección de la API / *Licensing*, “Sign up with free credits”, copie su API key. Los datos masivos son solo no comerciales | `PLD_EXT_PROVIDER=opensanctions` y `PLD_EXT_API_KEY=su_clave` |
| Otros (World-Check, Dow Jones, LexisNexis, ComplyAdvantage…) | Solicite demo/prueba a ventas; no hay planes gratuitos confirmados | Pídame el adaptador cuando elija |

Las condiciones gratuitas cambian: léalas al registrarse. Verifique en su contrato si puede **guardar** los resultados (el sistema los guarda en alertas y constancias).

## 4. Guardar la clave de forma segura (sin escribirla en archivos)

1. GitHub → su foto → **Settings** → **Codespaces** → **Secrets** → **New secret**.
2. *Name:* `PLD_EXT_PROVIDER`, *Value:* `dilisense` → *Repository access:* **Select repositories** → `pld-screening` → **Add secret**.
3. Repita con *Name:* `PLD_EXT_API_KEY`, *Value:* su clave.

## 5. Primera corrida real

1. Repositorio → **<> Code** → **Codespaces** → **Create codespace on main** (si ya tenía uno abierto, deténgalo y vuelva a crearlo para que lea los secretos).
2. En la terminal inferior:
   ```
   python -m pldscreen prueba-completa
   ```
3. **Criterios para darla por buena (prueba real):**
   - Paso 2 **sin** el texto “se cargaron listas FICTICIAS de demostración”, y con totales (`OFAC_SDN=…`, `ONU_CSNU=…`, `SAT_69B=…`, `SAT_69B_BIS=…`).
   - Paso 4: `APROBADO`.
   - Paso 5: caso real del SAT/OFAC → `DETENER_Y_ESCALAR`.
   - Paso 7: `dilisense: OK` (o `opensanctions: OK`), **no** `mock`.
   - Resultado general `TODO CORRECTO ✔`.
4. Si algo sale ✘: copie las líneas del paso y envíemelas. Lo más probable es una dirección oficial que cambió (se corrige con `PLD_URL_…` en `.env`) o un detalle del formato de un proveedor.

## 6. Pruebas manuales (30 min)

1. Cree su usuario: `python -m pldscreen create-user director admin` (pide una contraseña de 10+ caracteres). Luego `python -m pldscreen serve --port 8000` → abrir el puerto 8000 → entre con `director` y su contraseña. (La clave de `data/clave_admin.txt` ya no se pega en la página; sirve solo para integraciones.)
2. `python -m pldscreen muestra --n 5` → copie nombres reales del SAT y de OFAC → **Consulta rápida** (con nombre solo, y con RFC).
3. Consulte un PEP mexicano **público y conocido** (p. ej., el titular de un gobierno estatal) → debe salir `EXT_PEP`. Si el proveedor no lo encuentra, **esa es su respuesta sobre cobertura en México**.
4. Pestaña **Expediente**: dos partes y un beneficiario controlador → constancia imprimible.
5. Cree usuarios en la pestaña **Usuarios** de la página (`analista1`, `analista2`, `supervisor1`, `supervisor2`) y pruebe la doble validación entrando con cada uno.

## 7. Qué NO hacer en esta etapa

- No escribir datos de clientes reales.
- No volver público el repositorio ni el puerto 8000 del Codespace.
- No escribir la API key en ningún archivo del repositorio.
- No considerar el resultado como cumplimiento regulatorio hasta tener la LPB/PEP oficiales resueltas y validación de su asesor.
