"""Reglas auxiliares para expedientes/operaciones de notarías e inmobiliarias (solo consulta de personas)."""
from __future__ import annotations

ACTOS = {
    "COMPRAVENTA_INMUEBLE", "DONACION", "PERMUTA", "ADJUDICACION", "FIDEICOMISO", "CONSTITUCION_SOCIEDAD",
    "MODIFICACION_SOCIEDAD", "FUSION_ESCISION", "PODER", "ARRENDAMIENTO", "PROMESA_COMPRAVENTA",
    "DESARROLLO_INMOBILIARIO", "CREDITO_HIPOTECARIO", "OTRO",
}
ROLES_CONOCIDOS = {
    "ENAJENANTE", "ADQUIRENTE", "VENDEDOR", "COMPRADOR", "DONANTE", "DONATARIO", "FIDEICOMITENTE",
    "FIDEICOMISARIO", "FIDUCIARIO", "APODERADO", "REPRESENTANTE", "BENEFICIARIO_CONTROLADOR", "SOCIO",
    "ACCIONISTA", "ARRENDADOR", "ARRENDATARIO", "PROMITENTE_VENDEDOR", "PROMITENTE_COMPRADOR", "OTORGANTE",
    "CLIENTE", "PARTE", "OTRO",
}


def advertencias(acto: str | None, rol: str, res: dict) -> list[str]:
    """Faltantes del expediente detectables sin tocar listas (para que el notario/inmobiliaria los subsane)."""
    c = res["consulta"]
    nom = c["nombre"] or res["referencia"]
    tag = f"{rol} «{nom}»"
    out = []
    if rol not in ROLES_CONOCIDOS:
        out.append(f"{tag}: rol fuera del catálogo; se registró tal cual.")
    if not (c["rfc"] or c["curp"]):
        out.append(f"{tag}: sin RFC ni CURP; la consulta por nombre es menos confiable.")
    if c["tipo"] != "M" and not c["fecha_nacimiento"]:
        out.append(f"{tag}: sin fecha de nacimiento; no se pueden descartar homónimos.")
    if c["tipo"] == "M" and not any((r["consulta"].get("rol") or "") == "BENEFICIARIO_CONTROLADOR"
                                    for r in res.get("relacionados", [])):
        out.append(f"{tag}: persona moral sin beneficiario controlador capturado (identifíquelo o documente la excepción).")
    out += [f"{tag}: {f}" for f in res.get("factores_adicionales", [])]
    return out


def estado_vivo(conn, op_id: int, dictamen: str) -> dict:
    """Estado actual de la operación según las alertas abiertas/cerradas de las personas involucradas."""
    sids = [r[0] for r in conn.execute("SELECT DISTINCT subject_id FROM operation_parties WHERE operation_id=?", (op_id,))]
    counts = {}
    if sids:
        ph = ",".join("?" * len(sids))
        counts = {r["status"]: r["n"] for r in conn.execute(
            f"SELECT status, COUNT(*) n FROM alerts WHERE subject_id IN ({ph}) GROUP BY status", sids)}
    if counts.get("CONFIRMADA"):
        estado = "DETENER"
    elif counts.get("ABIERTA") or counts.get("PENDIENTE_APROBACION"):
        estado = "EN_REVISION"
    elif dictamen in ("DETENER_Y_ESCALAR", "REVISION_ANTES_DE_FIRMAR"):
        estado = "LIBERADA_TRAS_REVISION"
    else:
        estado = "CONTINUAR"
    return {"estado": estado, "alertas": counts}
