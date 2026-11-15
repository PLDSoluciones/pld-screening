"""Constancias imprimibles (HTML autónomo, tamaño carta) de consultas y expedientes."""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone

_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
_E = html.escape

_RESULT = {
    "SIN_COINCIDENCIAS_RELEVANTES": ("ok", "Sin coincidencias relevantes en las listas consultadas"),
    "ALTA_PRIORIDAD_DETENER_OPERACION": ("alta", "Alta prioridad: detener la operación y escalar al Oficial de Cumplimiento"),
    "REVISION_REQUERIDA": ("media", "Revisión requerida antes de continuar"),
    "DETENER_Y_ESCALAR": ("alta", "Detener y escalar al Oficial de Cumplimiento"),
    "REVISION_ANTES_DE_FIRMAR": ("media", "Revisión requerida antes de firmar"),
    "SIN_HALLAZGOS": ("ok", "Sin hallazgos en las listas consultadas"),
}
_NIVEL_CLASE = {"EXACTA": "alta", "ALTA": "alta", "MEDIA": "media", "BAJA": "baja"}

CSS = """
@page{size:Letter;margin:13mm 14mm 14mm}
*{box-sizing:border-box}
body{font:13px/1.45 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1b1f24;margin:0;background:#eef0f3}
.hoja{max-width:820px;margin:18px auto;background:#fff;padding:30px 36px;border:1px solid #d5d9df;border-radius:6px}
.bar{display:flex;justify-content:flex-end;gap:8px;max-width:820px;margin:14px auto 0}
.bar button{font:inherit;padding:7px 16px;border:1px solid #0b5cab;background:#0b5cab;color:#fff;border-radius:6px;cursor:pointer}
.enc{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;border-bottom:3px solid #0b5cab;padding-bottom:12px}
.marca{display:flex;gap:10px;align-items:center}.logo{width:42px;height:42px;border-radius:10px;background:#0b5cab;color:#fff;font-weight:800;display:grid;place-items:center;font-size:16px}
.marca b{display:block;font-size:17px;line-height:1.1}.marca span{color:#5b6572;font-size:12px}
.folio{text-align:right}.folio b{font-size:20px;color:#0b5cab;display:block;line-height:1.1}.folio span{color:#5b6572;font-size:12px}
h1{font-size:19px;margin:18px 0 2px}h2{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#5b6572;margin:20px 0 6px;border-bottom:1px solid #d5d9df;padding-bottom:3px}
.sub{color:#5b6572;margin:0 0 4px}.org{font-weight:600}
.banner{border:2px solid;border-radius:6px;padding:11px 14px;margin:14px 0 4px;font-size:15px;font-weight:700}
.banner small{display:block;font-weight:400;font-size:12px;margin-top:2px}
.ok{color:#067647;background:#ecfdf3;border-color:#067647}.media{color:#b54708;background:#fffaeb;border-color:#b54708}
.alta{color:#b42318;background:#fef3f2;border-color:#b42318}.baja{color:#8a6d00;background:#fffcf0;border-color:#8a6d00}
table{width:100%;border-collapse:collapse;margin:2px 0}th,td{padding:5px 8px;border:1px solid #cfd4db;text-align:left;vertical-align:top}
th{background:#f1f3f6;font-size:11.5px;color:#3d4651}tr{page-break-inside:avoid}
.kv th{width:30%;font-weight:600}.mut{color:#5b6572;font-size:11.5px}
.pill{display:inline-block;padding:0 7px;border:1px solid;border-radius:9px;font-size:11px;font-weight:700}
ul{margin:4px 0 4px 18px;padding:0}li{margin:2px 0}
.firmas{display:flex;gap:40px;margin-top:34px;page-break-inside:avoid}.firmas div{flex:1;border-top:1px solid #1b1f24;padding-top:4px;text-align:center;font-size:12px}
.pie{margin-top:22px;border-top:1px solid #d5d9df;padding-top:8px;color:#5b6572;font-size:11px}.hash{word-break:break-all;font-family:ui-monospace,Menlo,monospace;font-size:10.5px}
.pie b{color:#1b1f24}
@media print{body{background:#fff;font-size:12px}.pie{font-size:10px;margin-top:14px}.firmas{margin-top:26px}th,td{padding:3px 7px}h2{margin:14px 0 4px}.banner{margin:10px 0 2px}.bar{display:none}.hoja{border:0;margin:0;padding:0;max-width:none;border-radius:0}}
"""


def _local(iso: str | None, off_h: float, with_tz: bool = True) -> str:
    if not iso:
        return "—"
    try:
        d = datetime.fromisoformat(iso).astimezone(timezone.utc) + timedelta(hours=off_h)
    except ValueError:
        return _E(str(iso))
    s = f"{d.day:02d}/{_MESES[d.month - 1]}/{d.year} {d.hour:02d}:{d.minute:02d}"
    return s + (" (hora de México)" if with_tz and off_h == -6 else "") if with_tz else s


def _page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{_E(title)}</title><style>{CSS}</style></head><body>"
            '<div class="bar"><button onclick="window.print()">Imprimir / Guardar como PDF</button></div>'
            f'<div class="hoja">{body}</div></body></html>')


def _enc(titulo: str, folio_txt: str, fecha_txt: str, org: str) -> str:
    return (f'<div class="enc"><div class="marca"><div class="logo">PLD</div><div><b>PLD Soluciones</b>'
            f"<span>Consultas de listas negras</span></div></div>"
            f'<div class="folio"><span>{_E(folio_txt)}</span><b>{_E(fecha_txt)}</b></div></div>'
            f"<h1>{_E(titulo)}</h1>" + (f'<p class="sub">Emitida para: <span class="org">{_E(org)}</span></p>' if org else ""))


def _banner(clase: str, texto: str, detalle: str = "") -> str:
    return f'<div class="banner {clase}">{_E(texto)}' + (f"<small>{_E(detalle)}</small>" if detalle else "") + "</div>"


def _kv(rows: list[tuple[str, object]]) -> str:
    rows = [(k, v) for k, v in rows if v not in (None, "", [], {})]
    return '<table class="kv">' + "".join(f"<tr><th>{_E(k)}</th><td>{_E(str(v))}</td></tr>" for k, v in rows) + "</table>"


def _listas(snapshot: dict, off: float) -> str:
    if not snapshot:
        return "<p class='mut'>Sin información de versiones.</p>"
    return ("<table><tr><th>Lista</th><th>Versión</th><th>Cargada</th><th>Registros</th></tr>" + "".join(
        f"<tr><td>{_E(k)}</td><td>{v.get('version')}</td><td>{_local(v.get('fecha_carga'), off, False)}</td>"
        f"<td>{v.get('registros')}</td></tr>" for k, v in sorted(snapshot.items())) + "</table>")


def _match_row(m: dict) -> str:
    reg = m.get("registro") or {}
    det = " · ".join(x for x in (
        f"RFC {reg['rfc']}" if reg.get("rfc") else "", f"CURP {reg['curp']}" if reg.get("curp") else "",
        ("Nac. " + ", ".join(map(str, reg["dobs"]))) if reg.get("dobs") else "",
        f"Estatus {reg['status']}" if reg.get("status") else "", f"País {reg['country']}" if reg.get("country") else "",
        f"ID en la fuente {m.get('id_externo')}" if m.get("id_externo") else "") if x)
    cl = _NIVEL_CLASE.get(m.get("nivel"), "baja")
    return (f"<tr><td><b>{_E(str(m.get('fuente')))}</b></td><td><b>{_E(str(m.get('nombre_coincidente')))}</b>"
            f"{'<div class=mut>' + _E(det) + '</div>' if det else ''}"
            f"{'<div class=mut>' + _E(str(reg['remarks'])) + '</div>' if reg.get('remarks') else ''}</td>"
            f"<td>{m.get('puntaje')}</td><td><span class='pill {cl}'>{_E(str(m.get('nivel')))}</span></td>"
            f"<td>{_E('; '.join(m.get('razones') or []))}</td></tr>")


def _firmas(elaboro: str) -> str:
    return (f'<div class="firmas"><div>Elaboró<br><b>{_E(elaboro or "")}</b></div>'
            "<div>Revisó / Oficial de Cumplimiento</div></div>")


def _pie(huella: str, off: float) -> str:
    ahora = _local(datetime.now(timezone.utc).isoformat(), off)
    return (f'<div class="pie"><b>Huella SHA-256 de la evidencia:</b> <span class="hash">{_E(huella or "")}</span><br>'
            f"Documento generado el {ahora}. La consulta de listas es un apoyo: la decisión final corresponde al titular o al "
            "Oficial de Cumplimiento. Una coincidencia por nombre no confirma identidad; valide con documentos oficiales. "
            "Conserve esta constancia en el expediente por el plazo legal aplicable (10 años según la reforma a la LFPIORPI de 2025; "
            "valide con su asesor).</div>")


def render_consulta(folio: int, row, res: dict, settings) -> str:
    off, org = settings.tz_offset_hours, getattr(settings, "org_name", "")
    c = res.get("consulta", {}) or {}
    clase, texto = _RESULT.get(res.get("resultado"), ("media", str(res.get("resultado", "")).replace("_", " ").capitalize()))
    ms = res.get("coincidencias") or []
    body = _enc("Constancia de consulta en listas – PLD/FT", f"Folio de consulta", f"No. {folio}", org)
    body += _banner(clase, texto, f"Riesgo sugerido: {res.get('riesgo_sugerido', '—')}" +
                    (f" · Nivel máximo de coincidencia: {res.get('nivel_maximo')}" if res.get("nivel_maximo") else ""))
    body += "<h2>Datos de la consulta</h2>" + _kv([
        ("Fecha y hora", f"{_local(row['created_at'], off)} · UTC {row['created_at']}"),
        ("Tipo de consulta", row["kind"]), ("Consultó", row["actor"]),
        ("Nombre / razón social", c.get("nombre")),
        ("Tipo de persona", {"F": "Persona física", "M": "Persona moral"}.get(c.get("tipo"), c.get("tipo"))),
        ("RFC", c.get("rfc")), ("CURP", c.get("curp")), ("Fecha de nacimiento", c.get("fecha_nacimiento")),
        ("País", c.get("pais")), ("Rol en el acto", c.get("rol")), ("Expediente", c.get("expediente"))])
    body += "<h2>Coincidencias encontradas</h2>"
    body += ("<table><tr><th>Lista</th><th>Registro en la lista</th><th>Puntaje</th><th>Nivel</th><th>Razones</th></tr>"
             + "".join(_match_row(m) for m in ms) + "</table>") if ms else "<p class='mut'>No se encontraron coincidencias.</p>"
    if res.get("descartadas_previamente"):
        body += f"<p class='mut'>{len(res['descartadas_previamente'])} coincidencia(s) previamente descartada(s) como falso positivo por el supervisor.</p>"
    if res.get("acciones_recomendadas"):
        body += "<h2>Acciones recomendadas</h2><ul>" + "".join(f"<li>{_E(a)}</li>" for a in res["acciones_recomendadas"]) + "</ul>"
    if res.get("factores_adicionales"):
        body += "<h2>Factores adicionales de riesgo</h2><ul>" + "".join(f"<li>{_E(a)}</li>" for a in res["factores_adicionales"]) + "</ul>"
    pe = res.get("proveedor_externo") or {}
    if pe.get("proveedor"):
        body += f"<p class='mut'>Proveedor externo: {_E(str(pe.get('proveedor')))} – {_E(str(pe.get('estado')))} {_E(str(pe.get('detalle') or ''))}</p>"
    body += "<h2>Listas y versiones utilizadas</h2>" + _listas(res.get("listas_consultadas") or {}, off)
    body += _firmas(row["actor"]) + _pie(row["evidence_hash"] or res.get("evidencia_sha256"), off)
    return _page(f"Constancia de consulta No. {folio}", body)


def render_operacion(d: dict, settings) -> str:
    off, org = settings.tz_offset_hours, getattr(settings, "org_name", "")
    clase, texto = _RESULT.get(d["dictamen"], ("media", d["dictamen"].replace("_", " ").capitalize()))
    body = _enc("Constancia de consulta de listas – Expediente", "Folio de operación", f"No. {d['id_operacion']}", org)
    body += _banner(clase, f"Dictamen: {texto}", f"Estado actual (considera la revisión de alertas): {d['estado_actual']['estado']}")
    body += "<h2>Datos del expediente</h2>" + _kv([
        ("Expediente / escritura", d["expediente"]), ("Tipo de acto", str(d.get("tipo_acto") or "").replace("_", " ").capitalize()),
        ("Fecha y hora", _local(d["fecha"], off)), ("Personas consultadas", d["personas_consultadas"]),
        ("Nivel máximo de coincidencia", d.get("nivel_maximo"))])
    rows = ""
    for p in d["partes"]:
        for x, sangria in [(p, "")] + [(r, "↳ ") for r in p["relacionados"]]:
            nv = x.get("nivel_maximo")
            rows += (f"<tr><td>{sangria}{_E(str(x['rol'] or ''))}</td><td><b>{_E(x['nombre'])}</b></td>"
                     f"<td>{_E(str(x['resultado']).replace('_', ' ').capitalize())}</td>"
                     f"<td>{('<span class=%s>%s</span>' % ('pill ' + _NIVEL_CLASE.get(nv, 'baja'), _E(nv))) if nv else '—'}</td>"
                     f"<td>#{x['id_consulta']}</td></tr>")
    body += ("<h2>Personas que intervienen</h2><table><tr><th>Rol</th><th>Persona</th><th>Resultado</th><th>Nivel</th>"
             f"<th>Consulta</th></tr>{rows}</table>")
    if d["hallazgos"]:
        body += "<h2>Hallazgos</h2><ul>" + "".join(
            f"<li><b>{_E(h['parte'])}</b> ({_E(str(h['rol']))}) – nivel {_E(str(h['nivel']))}; listas: {_E(', '.join(h['listas']))}; "
            f"alertas: {_E(', '.join(map(str, h['alertas'])) or 'ya abiertas')}</li>" for h in d["hallazgos"]) + "</ul>"
    else:
        body += "<h2>Hallazgos</h2><p class='mut'>Sin hallazgos.</p>"
    if d.get("advertencias"):
        body += "<h2>Advertencias para el expediente</h2><ul>" + "".join(f"<li>{_E(a)}</li>" for a in d["advertencias"]) + "</ul>"
    body += "<h2>Listas y versiones utilizadas</h2>" + _listas(d["listas_consultadas"], off)
    body += _firmas("") + _pie(d["evidencia_sha256"], off)
    return _page(f"Constancia expediente {d['expediente']}", body)
