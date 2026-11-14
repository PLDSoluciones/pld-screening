# Uso en notarías, corredurías y sector inmobiliario

Alcance del sistema: **consulta de personas** en listas (y vigilancia continua de esas personas). No calcula montos,
umbrales ni UMA, no presenta avisos (DECLARANOT / portal del SAT) y no sustituye el manual de PLD.

> Los datos normativos de esta guía provienen de resúmenes de despachos y portales (BHR, KYC Systems, IDC, Holland &
> Knight) consultados en noviembre de 2026, no del texto oficial. **Valide con el DOF y con su asesor.**

## A quién aplica (según los resúmenes)

| Figura | Fracción (Art. 17 LFPIORPI) | Ejemplos |
|---|---|---|
| Fedatarios públicos | XII, apartado A | Notarios y corredores públicos en transmisión o constitución de derechos reales sobre inmuebles, poderes, constitución/modificación de sociedades, fideicomisos |
| Intermediarios inmobiliarios | V | Agentes y corredores de bienes raíces, comercialización y arrendamiento |
| Desarrollo inmobiliario | V Bis | Quien recibe aportaciones para construir o fraccionar |
| Servicios profesionales | XI | Abogados/contadores que participan en compraventas por cuenta de clientes |

## Qué personas capturar en cada acto

| Acto | Partes (`rol`) | Relacionados a capturar |
|---|---|---|
| Compraventa / donación / permuta / adjudicación | ENAJENANTE, ADQUIRENTE (o VENDEDOR/COMPRADOR, DONANTE/DONATARIO) | Representantes/apoderados; **beneficiario controlador** si es persona moral |
| Fideicomiso | FIDEICOMITENTE, FIDUCIARIO, FIDEICOMISARIO | Beneficiarios controladores de cada uno (el sistema advierte si falta fideicomitente o fideicomisario) |
| Constitución / modificación de sociedad, fusión, escisión | SOCIO, ACCIONISTA, REPRESENTANTE | Beneficiario controlador (≥25 % de participación o control efectivo, según los resúmenes de las RCG) |
| Poderes | OTORGANTE, APODERADO | Representante legal si el otorgante es persona moral |
| Arrendamiento / promesa / comercialización | ARRENDADOR, ARRENDATARIO, PROMITENTE_VENDEDOR, PROMITENTE_COMPRADOR | Representantes y beneficiario controlador |

Use los **mismos RFC/CURP** cada vez que aparezca la persona: así es un solo sujeto, queda en vigilancia continua y su
falso positivo ya resuelto se recuerda.

## Qué verifica el sistema por persona

1. Listas: LPB (si la cargó), SAT 69-B y 69-B Bis, OFAC, ONU, PEP, internas.
2. Identificadores exactos (RFC/CURP) y nombres con variantes (orden, acentos, segundo nombre omitido, razón social con otra forma societaria).
3. Fecha de nacimiento (descarta homónimos).
4. País de nacionalidad/residencia contra `data/country_risk.csv` (jurisdicciones de alto riesgo).
5. PEP declarado por el cliente (`declara_pep`); PEP extranjera → riesgo sugerido ALTO.
6. Advertencias del expediente: persona sin RFC/CURP, sin fecha de nacimiento, persona moral sin beneficiario controlador, fideicomiso incompleto.

Los resúmenes consultados indican que el expediente debe poder demostrar la revisión contra la lista consolidada de
la ONU, la lista de jurisdicciones de alto riesgo y el seguimiento de PEP. La **constancia de expediente** deja esa
evidencia con versiones de listas y huella SHA-256.

## Flujo recomendado en la notaría / inmobiliaria

1. **Apertura del expediente:** capture a todas las partes y consulte (`POST /v1/operaciones`). Imprima/guarde la constancia.
2. **Si el dictamen es REVISION o DETENER:** el encargado de cumplimiento atiende las alertas (pestaña Alertas): compara con la documentación (identificación, CURP, RFC, fecha de nacimiento) y resuelve. El analista propone, el supervisor aprueba.
3. **Antes de la firma:** vuelva a consultar `GET /v1/operaciones/{id}`; si `estado_actual` es `DETENER` o `EN_REVISION`, no se formaliza.
4. **Aviso:** si procede, la presentación sigue siendo manual en DECLARANOT/portal del SAT; el sistema solo aporta el sustento.
5. **Conservación:** constancias, expedientes y bitácora por 10 años (respaldo fuera del servidor).
6. **Vigilancia:** el sistema revisa solo cada actualización de listas contra todas las personas ya consultadas.

## Multi-notaría

Una instalación = una notaría/inmobiliaria (sus datos no se mezclan). Si una empresa de software atiende varias,
despliegue una instancia por cliente (mismo código, distinto dominio y volumen).
