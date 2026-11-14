"""Proveedores EXTERNOS de PEP/sanciones por API (segunda verificación, además de las listas locales).

  PLD_EXT_PROVIDER = none | mock | opensanctions | dilisense
  PLD_EXT_API_KEY  = clave del proveedor (no se guarda en la base)

* mock: respuestas simuladas, sin red ni clave. Sirve para probar TODO el flujo (alertas, doble validación, constancias).
* opensanctions / dilisense: adaptadores escritos con la documentación pública de cada API; **no pude probarlos en vivo**
  desde mi entorno (sin salida a internet). Si el proveedor cambia su formato, la consulta NO falla: el resultado trae
  proveedor_externo.estado = ERROR con el detalle, y se siguen usando las listas locales.
* Los puntajes del proveedor se recalculan con el motor propio para que los niveles sean comparables.
* LICENCIAS: revise si su contrato permite guardar los resultados (aquí se guardan en constancias y alertas).
  OpenSanctions: datos CC BY-NC (uso no comercial); el tamizaje de cumplimiento en una empresa es uso comercial.
"""
from __future__ import annotations

import httpx

from .matching import Query, name_score
from .normalize import name_tokens


class ProviderError(Exception):
    pass


def _hit(proveedor: str, id_: str, nombre: str, tipo: str, aliases=None, dobs=None, paises=None, detalle=None,
         score_proveedor=None) -> dict:
    return {"proveedor": proveedor, "id": str(id_), "nombre": nombre, "tipo": tipo, "aliases": aliases or [],
            "dobs": dobs or [], "paises": paises or [], "detalle": detalle or "", "score_proveedor": score_proveedor}


def rescore(hit: dict, q: Query) -> float:
    """Puntaje 0-100 con el motor propio contra el nombre y los alias que devolvió el proveedor."""
    org = True if q.entity_type == "M" else (False if q.entity_type == "F" else None)
    qt = name_tokens(q.name, org)
    best = 0.0
    for n in [hit["nombre"]] + list(hit["aliases"]):
        ct = name_tokens(n, org)
        if qt and ct:
            best = max(best, name_score(qt, ct))
    return best


class Provider:
    name = "none"

    def check(self, q: Query) -> list[dict]:
        raise NotImplementedError


class MockProvider(Provider):
    """Datos FICTICIOS para pruebas sin red."""
    name = "mock"
    DB = [
        _hit("mock", "MOCK-PEP-1", "Rosa Elena Valdivia Camacho", "PEP", dobs=["1968-03-09"], paises=["MX"],
             detalle="Ficticia – Presidenta municipal (prueba)"),
        _hit("mock", "MOCK-PEP-2", "Gerardo Anselmo Rios Treviño", "PEP", aliases=["Gerardo Rios T."], paises=["MX"],
             detalle="Ficticio – Diputado federal (prueba)"),
        _hit("mock", "MOCK-SAN-1", "Oleg Nikolaevich Danilov", "SANCION", aliases=["Oleg Danilov"], dobs=["1970"],
             detalle="Ficticio – sanción internacional (prueba)"),
    ]

    def check(self, q: Query) -> list[dict]:
        return [h for h in self.DB if rescore(h, q) >= 70]


class OpenSanctionsAPI(Provider):
    """POST {base}/match/default  (cabecera Authorization: ApiKey <clave>)."""
    name = "opensanctions"

    def __init__(self, key: str, base: str = "https://api.opensanctions.org", timeout: float = 20):
        self.key, self.base, self.timeout = key, base.rstrip("/"), timeout

    def request_body(self, q: Query) -> dict:
        schema = "Person" if q.entity_type == "F" else "Organization" if q.entity_type == "M" else "LegalEntity"
        props: dict = {"name": [q.name]}
        if q.dob and len(q.dob) >= 4:
            props["birthDate"] = [q.dob]
        if q.country and schema == "Person":
            props["nationality"] = [q.country]
        return {"queries": {"q": {"schema": schema, "properties": props}}}

    def check(self, q: Query) -> list[dict]:
        if not self.key:
            raise ProviderError("Falta PLD_EXT_API_KEY")
        try:
            r = httpx.post(f"{self.base}/match/default", params={"limit": 10, "threshold": 0.6},
                           headers={"Authorization": f"ApiKey {self.key}"}, json=self.request_body(q), timeout=self.timeout)
            r.raise_for_status()
            return self.parse(r.json())
        except httpx.HTTPError as e:
            raise ProviderError(f"OpenSanctions: {e}") from e

    @staticmethod
    def parse(js: dict) -> list[dict]:
        out = []
        for res in (js.get("responses") or {}).values():
            for it in res.get("results", []):
                p = it.get("properties", {})
                topics = set(it.get("topics") or p.get("topics") or [])
                tipo = ("PEP" if topics & {"role.pep", "role.rca"} else "SANCION" if "sanction" in topics
                        else "OTRO")
                names = p.get("name", []) or [it.get("caption", "")]
                out.append(_hit("opensanctions", it.get("id", ""), it.get("caption") or names[0], tipo,
                                aliases=(p.get("alias", []) + names[1:]), dobs=p.get("birthDate", []),
                                paises=p.get("country", []) + p.get("nationality", []),
                                detalle=", ".join(sorted(topics)) + " · " + ", ".join(it.get("datasets", [])[:4]),
                                score_proveedor=it.get("score")))
        return out


class DilisenseAPI(Provider):
    """GET {base}/v1/checkIndividual | checkEntity  (cabecera x-api-key)."""
    name = "dilisense"

    def __init__(self, key: str, base: str = "https://api.dilisense.com", timeout: float = 20):
        self.key, self.base, self.timeout = key, base.rstrip("/"), timeout

    def check(self, q: Query) -> list[dict]:
        if not self.key:
            raise ProviderError("Falta PLD_EXT_API_KEY")
        path = "checkEntity" if q.entity_type == "M" else "checkIndividual"
        params = {"names": q.name}
        if path == "checkIndividual" and q.dob and len(q.dob) == 10 and q.dob[4] == "-":
            params["dob"] = f"{q.dob[8:10]}/{q.dob[5:7]}/{q.dob[:4]}"
        try:
            r = httpx.get(f"{self.base}/v1/{path}", params=params, headers={"x-api-key": self.key}, timeout=self.timeout)
            r.raise_for_status()
            return self.parse(r.json())
        except httpx.HTTPError as e:
            raise ProviderError(f"Dilisense: {e}") from e

    @staticmethod
    def parse(js: dict) -> list[dict]:
        out = []
        for it in js.get("found_records", []):
            st = (it.get("source_type") or "").upper()
            tipo = "PEP" if "PEP" in st else "SANCION" if "SANCTION" in st else "OTRO"
            out.append(_hit("dilisense", it.get("id") or it.get("source_id", ""), it.get("name", ""), tipo,
                            aliases=it.get("alias_names") or [], dobs=it.get("date_of_birth") or [],
                            paises=it.get("citizenship") or [],
                            detalle=f"{st} · {it.get('source_id', '')} {', '.join(it.get('positions') or [])}".strip()))
        return out


def build(settings) -> Provider | None:
    name = (settings.ext_provider or "none").lower()
    if name == "mock":
        return MockProvider()
    if name == "opensanctions":
        return OpenSanctionsAPI(settings.ext_api_key, settings.ext_base_url or "https://api.opensanctions.org",
                                settings.ext_timeout)
    if name == "dilisense":
        return DilisenseAPI(settings.ext_api_key, settings.ext_base_url or "https://api.dilisense.com", settings.ext_timeout)
    return None
