# Clientes y demos

**Registro público.** En la pantalla de inicio de sesión aparece «Solicite una demo gratuita». El prospecto llena nombre, organización, correo y contraseña, y acepta las condiciones. Se crea una cuenta de rol *analista* con demo de `PLD_DEMO_DIAS` días y `PLD_DEMO_CONSULTAS` consultas.

**Qué incluye la demo:** consulta individual contra las listas, ficha del registro y constancia con marca «VERSIÓN DE DEMOSTRACIÓN». **No incluye:** lotes, expedientes, alertas, historial, auditoría ni guardado de personas. La demo solo ve sus propias consultas.

**Panel del administrador (pestaña Clientes):** totales por estado, búsqueda, exportar a CSV, alta manual, y por cliente: *Extender demo*, *Marcar como pagado* (quita los límites), *Volver a demo*, *Suspender/Reactivar* y *Nota*. Todo queda en la bitácora de auditoría.

**Estados:** Demo activa · Demo vencida · Consultas agotadas · Pagado · Suspendido.

## Límites que debe conocer
- Todos los clientes **comparten la misma base de datos**. Un cliente *Pagado* con acceso completo vería el historial y expedientes de los demás. Para clientes de pago use **una instalación (y base) por cliente**, o pida que se agregue aislamiento por cliente.
- No se verifica el correo (no hay envío de correos configurado): cualquiera puede registrar una cuenta. El registro tiene límite de 5 por hora por red y un campo anti-bots; si hay abuso, ponga `PLD_REGISTRO_ABIERTO=0` o suspenda la cuenta.
- Los cobros no están integrados: «Marcar como pagado» es manual.
- Publique su propio aviso de privacidad y términos antes de abrir el registro al público.
