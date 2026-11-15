# Recuperación de cuentas y contraseñas

**Un usuario olvidó su contraseña.** El administrador entra a *Usuarios* y pulsa **Restablecer**. El sistema genera una contraseña temporal de 12 caracteres, la muestra **una sola vez** y cierra las sesiones de ese usuario. Entréguela por un canal seguro (en persona o llamada, no por correo abierto). Al entrar, el usuario debe elegir una contraseña nueva antes de usar el sistema. La temporal no queda guardada en la bitácora.

**Usuarios nuevos.** Los que crea el administrador desde la página entran con la contraseña inicial y deben cambiarla en su primer ingreso. También ocurre si el admin usa «Cambiar contraseña».

**El administrador olvidó la suya.** Se recupera con acceso al servidor (Codespace o VPS), en la terminal del proyecto:

    python -m pldscreen set-password NOMBRE_ADMIN

Si no queda ningún administrador:

    python -m pldscreen create-user NUEVO_ADMIN admin

Por eso: proteja el acceso al servidor y mantenga **al menos dos administradores** (uno de respaldo).

**Clientes de demo.** Son usuarios como cualquier otro: el administrador usa *Restablecer* desde Usuarios (el usuario es la parte del correo antes de la @, visible en Clientes).

**No existe** el enlace «Olvidé mi contraseña» por correo: el sistema no envía correos. Si más adelante lo necesita, se agrega con un servicio SMTP.

## Desde la pantalla de inicio (v2.2)
- **¿Olvidó su contraseña?** está visible bajo el botón Entrar. El usuario escribe su nombre y queda una **solicitud** que el administrador ve en *Usuarios* (aviso amarillo y número en la pestaña). El sistema responde igual exista o no el usuario, para no revelar quién tiene cuenta. El admin verifica la identidad y pulsa *Restablecer ahora*.
- **Administrador sin otro admin:** defina `PLD_RECOVERY_CODE` (16 caracteres o más, guardado en lugar seguro) en `.env` y reinicie. Desde «¿Olvidó su contraseña?» → «Soy administrador» podrá fijar una contraseña nueva con ese código. Tiene límite de intentos. Sin el código configurado, la opción se desactiva.
