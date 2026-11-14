"""Parsers de listas → registros homogéneos.

Registro: {external_id, entity_type ('F'|'M'|None), name, aliases[], rfc, curp, dobs[], country,
           program, status, remarks, active(bool)}
"""
from __future__ import annotations

import csv
import io
import re

from defusedxml import ElementTree as ET

from ..normalize import clean, normalize_curp, normalize_rfc


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _rec(external_id, name, **kw) -> dict:
    r = dict(external_id=str(external_id), entity_type=None, name=(name or "").strip(), aliases=[], rfc=None,
             curp=None, dobs=[], country=None, program=None, status=None, remarks=None, active=True)
    r.update(kw)
    r["rfc"] = normalize_rfc(r["rfc"])
    r["curp"] = normalize_curp(r["curp"])
    return r


# ------------------------------------------------------------------ OFAC SDN (SDN.CSV + ALT.CSV)
def _ofac_null(v: str) -> str:
    v = (v or "").strip()
    return "" if v == "-0-" else v


def parse_ofac(sdn_bytes: bytes, alt_bytes: bytes | None = None) -> list[dict]:
    """SDN.CSV sin encabezado: ent_num, SDN_Name, SDN_Type, Program, Title, ..., Remarks (12 columnas)."""
    alts: dict[str, list[str]] = {}
    if alt_bytes:
        for row in csv.reader(io.StringIO(decode(alt_bytes))):
            if len(row) >= 4:
                nm = _ofac_null(row[3])
                if nm:
                    alts.setdefault(row[0].strip(), []).append(_flip(nm))
    out = []
    for row in csv.reader(io.StringIO(decode(sdn_bytes))):
        if len(row) < 4 or not row[0].strip().isdigit():
            continue
        eid, nm, typ, prog = row[0].strip(), _ofac_null(row[1]), _ofac_null(row[2]).lower(), _ofac_null(row[3])
        remarks = _ofac_null(row[11]) if len(row) > 11 else ""
        if typ in ("vessel", "aircraft"):
            et = None
        elif typ == "individual":
            et = "F"
        else:
            et = "M"
        dobs = re.findall(r"DOB\s+([^;]+)", remarks)
        nat = re.search(r"nationality\s+([^;]+)", remarks, re.I)
        rfc = re.search(r"R\.?F\.?C\.?\s*(?:No\.?)?\s*([A-Z0-9&Ñ-]{12,15})", remarks, re.I)
        curp = re.search(r"C\.?U\.?R\.?P\.?\s*(?:No\.?)?\s*([A-Z0-9]{18})", remarks, re.I)
        out.append(_rec(eid, _flip(nm) if et == "F" else nm, entity_type=et, aliases=alts.get(eid, []),
                        rfc=rfc.group(1) if rfc else None, curp=curp.group(1) if curp else None,
                        dobs=[d.strip() for d in dobs], country=nat.group(1).strip() if nat else None,
                        program=prog, status="VIGENTE", remarks=remarks[:500]))
    return out


def _flip(name: str) -> str:
    """'PEREZ LOPEZ, Juan' → 'Juan PEREZ LOPEZ'."""
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return name


# ------------------------------------------------------------------ ONU (consolidated.xml)
def parse_un(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out = []

    def t(node, tag):
        x = node.find(tag)
        return (x.text or "").strip() if x is not None and x.text else ""

    for node in root.iter("INDIVIDUAL"):
        name = " ".join(filter(None, (t(node, f) for f in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME"))))
        aliases = [a.text.strip() for a in node.iter("ALIAS_NAME") if a.text and a.text.strip()]
        dobs = []
        for d in node.iter("INDIVIDUAL_DATE_OF_BIRTH"):
            v = t(d, "DATE") or t(d, "YEAR")
            if v:
                dobs.append(v)
        nat_node = node.find("NATIONALITY")
        country = ", ".join(v.text.strip() for v in nat_node.iter("VALUE") if v.text) if nat_node is not None else None
        out.append(_rec(t(node, "DATAID") or t(node, "REFERENCE_NUMBER"), name, entity_type="F", aliases=aliases,
                        dobs=dobs, country=country, program=t(node, "UN_LIST_TYPE"), status="VIGENTE",
                        remarks=t(node, "COMMENTS1")[:500]))
    for node in root.iter("ENTITY"):
        aliases = [a.text.strip() for a in node.iter("ALIAS_NAME") if a.text and a.text.strip()]
        out.append(_rec(t(node, "DATAID") or t(node, "REFERENCE_NUMBER"), t(node, "FIRST_NAME"), entity_type="M",
                        aliases=aliases, program=t(node, "UN_LIST_TYPE"), status="VIGENTE",
                        remarks=t(node, "COMMENTS1")[:500]))
    return out


# ------------------------------------------------------------------ SAT 69-B / 69-B Bis
_SAT_ACTIVE = {"PRESUNTO", "DEFINITIVO"}


def parse_sat69b(data: bytes, program: str = "69-B") -> list[dict]:
    """CSV del SAT: el encabezado no está en la primera línea; se localiza la fila que contiene 'RFC'."""
    rows = list(csv.reader(io.StringIO(decode(data))))
    h = next((i for i, r in enumerate(rows) if any(clean(c) == "RFC" for c in r)), None)
    if h is None:
        raise ValueError("No se encontró el encabezado 'RFC' en el archivo del SAT")
    head = [clean(c) for c in rows[h]]

    def col(*keys):
        for i, c in enumerate(head):
            if all(k in c for k in keys):
                return i
        return None

    c_rfc, c_nom, c_sit = col("RFC"), col("NOMBRE"), col("SITUACION")
    if c_rfc is None or c_nom is None:
        raise ValueError("Columnas RFC/Nombre no encontradas en el archivo del SAT")
    out = []
    for r in rows[h + 1:]:
        if len(r) <= max(c_rfc, c_nom) or not r[c_rfc].strip():
            continue
        sit = r[c_sit].strip() if c_sit is not None and c_sit < len(r) else ""
        rfc = normalize_rfc(r[c_rfc])
        if not rfc:
            continue
        out.append(_rec(rfc, r[c_nom], entity_type="M" if len(rfc) == 12 else "F", rfc=rfc, status=sit.upper(),
                        program=program, active=clean(sit) in _SAT_ACTIVE or not sit,
                        remarks=f"Situación del contribuyente: {sit}"))
    return out


# ------------------------------------------------------------------ CSV genérico (LPB, PEP, internas, UE, RU…)
_ALIASES = {
    "id": {"ID", "ID EXTERNO", "CLAVE", "FOLIO", "NO", "NUMERO"},
    "name": {"NOMBRE", "NOMBRE COMPLETO", "RAZON SOCIAL", "NAME", "DENOMINACION"},
    "given": {"NOMBRES", "NOMBRE S", "GIVEN NAME"},
    "pat": {"APELLIDO PATERNO", "PRIMER APELLIDO", "PATERNO"},
    "mat": {"APELLIDO MATERNO", "SEGUNDO APELLIDO", "MATERNO"},
    "type": {"TIPO", "TIPO PERSONA", "TYPE"},
    "rfc": {"RFC"},
    "curp": {"CURP"},
    "dob": {"FECHA NACIMIENTO", "FECHA DE NACIMIENTO", "NACIMIENTO", "DOB"},
    "country": {"PAIS", "NACIONALIDAD", "COUNTRY"},
    "aliases": {"ALIAS", "ALIAS AKA", "OTROS NOMBRES", "AKA"},
    "status": {"ESTATUS", "ESTADO", "STATUS", "SITUACION"},
    "remarks": {"OBSERVACIONES", "NOTAS", "REMARKS", "CARGO", "COMENTARIOS"},
}


def parse_generic(data: bytes, source_code: str = "GEN") -> list[dict]:
    text = decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        return []
    head = [clean(c) for c in rows[0]]
    idx = {}
    for key, names in _ALIASES.items():
        for i, h in enumerate(head):
            if h in names and key not in idx:
                idx[key] = i

    def g(r, k):
        i = idx.get(k)
        return r[i].strip() if i is not None and i < len(r) else ""

    out = []
    for n, r in enumerate(rows[1:], 1):
        if not any(c.strip() for c in r):
            continue
        name = g(r, "name") or " ".join(filter(None, (g(r, "given"), g(r, "pat"), g(r, "mat"))))
        if not name:
            continue
        typ = g(r, "type").upper()[:1]
        typ = {"F": "F", "P": "F", "M": "M", "E": "M", "O": "M"}.get(typ)
        rfc = g(r, "rfc")
        if typ is None and normalize_rfc(rfc):
            typ = "M" if len(normalize_rfc(rfc)) == 12 else "F"
        st = g(r, "status")
        active = clean(st) not in {"BAJA", "INACTIVO", "INACTIVA", "DESVIRTUADO", "SENTENCIA FAVORABLE", "REMOVIDO", "DELISTED"}
        out.append(_rec(g(r, "id") or f"{source_code}-{n}", name, entity_type=typ,
                        aliases=[a.strip() for a in re.split(r"[|;]", g(r, "aliases")) if a.strip()],
                        rfc=rfc, curp=g(r, "curp"), dobs=[d.strip() for d in re.split(r"[|;]", g(r, "dob")) if d.strip()],
                        country=g(r, "country") or None, status=st or "VIGENTE", active=active,
                        remarks=g(r, "remarks")[:500] or None))
    return out
