# Guía para principiantes: subir a GitHub y probar todo el sistema (sin instalar nada)

No necesita saber programar. Haremos tres cosas:
1. Crear su cuenta de GitHub y **subir** el sistema.
2. **Probarlo completo en la nube** con GitHub Codespaces (una computadora de GitHub que se abre en su navegador).
3. (Opcional) Conectar una **API gratuita de pruebas** de PEP/sanciones.

Tiempo: ≈ 45 minutos la primera vez. Costo: $0 (ver nota de cuotas en el paso 3.6).

**Vocabulario mínimo**

| Palabra | Qué significa |
|---|---|
| Repositorio | Una carpeta de proyecto guardada en GitHub |
| Commit | “Guardar una versión” con una nota |
| Publish / Push | Subir esas versiones a GitHub |
| Codespace | Computadora temporal en la nube, abierta en su navegador |
| Terminal | Ventana donde se escriben comandos (viene dentro del Codespace) |

> **Importante:** en las pruebas use **solo datos ficticios o públicos**. No escriba datos reales de clientes en Codespaces.

---

## Paso 1 · Crear su cuenta de GitHub

1. Entre a <https://github.com/signup>, escriba su correo, una contraseña, un nombre de usuario y complete el código de verificación.
2. **Active la verificación en dos pasos:** foto de perfil (arriba a la derecha) → *Settings* → *Password and authentication* → *Enable two-factor authentication*. Use una app como Google Authenticator. Guarde los códigos de recuperación.

## Paso 2 · Subir el sistema a GitHub (método recomendado: GitHub Desktop)

1. **Descargue GitHub Desktop**: <https://desktop.github.com/> → instálelo → *Sign in to GitHub.com* → inicie sesión.
2. **Descomprima** `pld-screening.zip` (clic derecho → *Extraer todo*) en una carpeta fácil, por ejemplo `C:\Users\SU_NOMBRE\Documents\pld-screening`. Entre a la carpeta y verifique que ve `README.md`, `pldscreen`, `docs`, etc. (si ve otra carpeta `pld-screening` adentro, use esa).
3. En GitHub Desktop: menú **File → Add local repository…** → **Choose…** → seleccione esa carpeta → *Add repository*.
4. Aparecerá un aviso *“This directory does not appear to be a Git repository”*. Haga clic en el enlace azul **create a repository**. Se abre una ventana: deje el nombre como está, **Git ignore: None** (el proyecto ya trae el suyo), **License: None** → **Create repository**.
5. A la izquierda verá la lista de archivos (unos 60). **Revise que NO aparezcan** `.env`, ni archivos que terminen en `.db`, ni la carpeta `data/raw`. (Si aparecen, no continúe y avíseme.)
6. Abajo a la izquierda, en *Summary*, escriba `Version inicial` y haga clic en el botón azul **Commit to main**.
7. Arriba haga clic en **Publish repository**. En la ventana:
   - Name: `pld-screening`
   - **Marque ✔ “Keep this code private”** (muy importante)
   - **Publish repository**.
8. Compruebe: entre a `https://github.com/SU_USUARIO/pld-screening`. Debe ver los archivos y un candado/etiqueta **Private**.
9. Abra la pestaña **Actions** del repositorio. Verá una corrida llamada **Pruebas**; en 2–5 minutos debe quedar con ✔ verde. Si sale ✘ rojo, haga clic en ella, copie el mensaje de error y envíemelo.

<details><summary>Método alternativo: subir desde el navegador (si no puede instalar nada)</summary>

1. GitHub → **+** (arriba a la derecha) → **New repository** → nombre `pld-screening` → **Private** → **Create repository**.
2. Clic en **uploading an existing file**. Abra su carpeta descomprimida y **arrastre el contenido** (no la carpeta contenedora) a la página. GitHub acepta hasta 100 archivos por vez: súbalos en 2–3 tandas (por ejemplo, primero `pldscreen` y `tests`, luego `docs`, `data`, `tools`, y al final los archivos sueltos).
3. Al final, en *Commit changes* escriba `Version inicial` → **Commit changes**.
4. **Verifique** que existan las carpetas ocultas `.github` y `.devcontainer`: algunos navegadores no las arrastran. Si faltan, use *Add file → Create new file*, escriba `.devcontainer/devcontainer.json` como nombre y pegue el contenido del archivo original (ídem `.github/workflows/ci.yml`). Sin `.devcontainer` el Paso 3 no se configura solo.
5. **No suba** `.env` ni bases de datos (el zip no las trae).
</details>

## Paso 3 · Probar TODO el sistema en la nube (Codespaces)

1. En la página de su repositorio haga clic en el botón verde **<> Code** → pestaña **Codespaces** → **Create codespace on main**.
2. Espere 2–4 minutos. Se abrirá una ventana parecida a un editor de código (Visual Studio Code) en su navegador. Abajo hay una **terminal** (si no la ve: menú ☰ → *Terminal* → *New Terminal*). Se instala solo todo lo necesario.
3. **Ejecute la prueba automática completa.** En la terminal escriba (o pegue) y presione Enter:
   ```
   python -m pldscreen prueba-completa
   ```
   Tarda 1–3 minutos. Verá líneas con ✔ o ✘:

   | Paso | Qué prueba |
   |---|---|
   | 1 Usuarios | Crea el administrador y guarda la clave en `data/clave_admin.txt` |
   | 2 Listas públicas | **Descarga las listas reales** de OFAC, ONU y SAT (Codespaces sí tiene internet) |
   | 3 LPB/PEP de prueba | Carga listas ficticias de personas bloqueadas y PEP (las reales no son públicas) |
   | 4 Autoprueba | Toma registros reales, les inventa errores de captura y mide si el sistema los encuentra |
   | 5 Expediente | Arma una escritura con un caso real de las listas → debe dar **DETENER_Y_ESCALAR** |
   | 6 Doble validación | Un analista propone cerrar una alerta, no puede aprobarse a sí mismo, un supervisor sí |
   | 7 Proveedor externo | Consulta la API si usted configuró una (si no, dice “omitido”) |
   | 8 Bitácora | Verifica que nadie alteró el historial |
   | 9 Respaldo | Genera una copia de seguridad |

   Al final debe decir **`TODO CORRECTO ✔`**. Si dice *“se usaron datos de demostración”* en el paso 2, es que alguna descarga falló: copie esas líneas y envíemelas (puede ser que una dirección oficial haya cambiado; se corrige en `.env`).
4. **Abra la interfaz web.** En la terminal:
   ```
   python -m pldscreen serve --port 8000
   ```
   Aparecerá una ventanita *“Your application running on port 8000 is available”* → **Open in Browser**. (Si no: pestaña **PORTS** abajo → fila 8000 → ícono del globo 🌐.)
5. En la página web, pegue la clave del administrador. Para verla, abra **otra terminal** (ícono **+** de la terminal) y escriba:
   ```
   cat data/clave_admin.txt
   ```
   Copie el texto que empieza con `pld_` y péguelo en el campo *API key* arriba a la derecha de la página.
6. **Pruebe a mano:** pestaña **Listas** (verá cuántos registros trae cada fuente), **Consulta rápida** y **Expediente** (capture dos partes y un beneficiario controlador). Para obtener nombres reales de las listas para probar, en la terminal: `python -m pldscreen muestra --n 3`.
7. **Cuotas y apagado.** Cuentas gratuitas incluyen 120 horas de cómputo y 15 GB-mes de almacenamiento al mes; sin tarjeta registrada, al agotarse se bloquea el uso (no se cobra). Cuando termine: <https://github.com/codespaces> → ⋯ junto a su codespace → **Stop codespace**. Al borrarlo se pierde la base de prueba (es lo deseado con datos ficticios).

## Paso 4 · (Opcional) Probar con una API gratuita real de PEP/sanciones

Estado de las opciones gratuitas (consultado en noviembre de 2026; las condiciones cambian, léalas antes de registrarse):

| Proveedor | Qué ofrece para probar | Detalle importante |
|---|---|---|
| **Simulado (`mock`)** | Datos ficticios, sin registro | Solo para ensayar el flujo: se activa con `export PLD_EXT_PROVIDER=mock`. **No es una prueba real** |
| **Dilisense** | Plan *Starter*: 100 consultas gratis, luego €0.10 por consulta | Cubre sanciones y PEP internacionales/nacionales; **no confirma cobertura de México** en su página: justo eso debe medir |
| **OpenSanctions** | Créditos gratis para evaluar la API (empresas); datos masivos gratis solo para uso **no comercial** | Para una notaría/empresa, el tamizaje de cumplimiento cuenta como uso comercial: la licencia de producción es de pago |

**Cómo conectar uno (ejemplo Dilisense):**
1. Regístrese en el sitio del proveedor y copie su API key.
2. En Codespaces, detenga el servidor (Ctrl+C) y escriba, cambiando `SU_CLAVE`:
   ```
   export PLD_EXT_PROVIDER=dilisense
   export PLD_EXT_API_KEY=SU_CLAVE
   python -m pldscreen prueba-completa
   ```
   (Para OpenSanctions use `PLD_EXT_PROVIDER=opensanctions`.) En el paso 7 debe decir `dilisense: OK`.
3. **Guarde la clave sin escribirla cada vez:** GitHub → su foto → *Settings* → *Codespaces* → *New secret* (nombre `PLD_EXT_API_KEY`, valor su clave, repositorio `pld-screening`). **Nunca** escriba la clave dentro de un archivo que suba a GitHub.
4. Haga una consulta de un PEP **mexicano conocido** (por ejemplo, el gobernador de su estado) en *Consulta rápida*: aparecerá con fuente `EXT_PEP`. Así mide si el proveedor cubre México.

> Los adaptadores de Dilisense y OpenSanctions están escritos con su documentación pública, pero **no los pude probar en vivo**. Si en el paso 7 sale `ERROR`, el sistema sigue funcionando con las listas locales; copie el texto del error y envíemelo para ajustarlo.

## Paso 5 · Cuando haya una versión nueva del sistema

1. Descomprima el nuevo zip **encima** de su carpeta (reemplazar archivos).
2. GitHub Desktop mostrará los archivos cambiados → escriba un resumen (“Actualización”) → **Commit to main** → **Push origin**.
3. Para llevarlo al Codespace: ábralo → terminal → `git pull`.

## Problemas frecuentes

| Qué ve | Qué hacer |
|---|---|
| En GitHub Desktop aparece `.env` en la lista de cambios | No haga commit. Avíseme: algo falló con `.gitignore` |
| *Actions* sale en rojo | Haga clic en la corrida → copie el error |
| No aparece el botón **Codespaces** | Pestaña **Code** → debe estar su sesión iniciada; revise que esté en su repositorio privado |
| `python: command not found` | Se está en otra terminal; ábrala desde el Codespace (☰ → Terminal → New Terminal) |
| La página web no abre | Pestaña **PORTS** → puerto 8000 → globo 🌐; verifique que el comando `serve` siga corriendo |
| “API key inválida” | Copió espacios de más o es otra clave; vuelva a ejecutar `cat data/clave_admin.txt` |
| Demasiados intentos (429) | Espere 5 minutos |
| Se acabó la cuota gratuita | Espere al mes siguiente, o pruebe en su computadora con la Parte 1 de `GUIA_PASO_A_PASO.md` |
