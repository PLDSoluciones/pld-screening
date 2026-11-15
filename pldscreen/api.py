"""API REST (FastAPI). Autenticación por cabecera X-API-Key con roles analista < supervisor < admin."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from .service import ROLES, Service, ServiceError

STATIC = Path(__file__).parent / "static"


class Persona(BaseModel):
    referencia: str | None = Field(None, description="ID del cliente/proveedor en su sistema. Si se envía, se guarda y se monitorea")
    nombre: str | None = Field(None, description="Nombre completo o razón social")
    nombres: str | None = None
    apellido_paterno: str | None = None
    apellido_materno: str | None = None
    tipo: str | None = Field(None, description="F=persona física, M=persona moral")
    rfc: str | None = None
    curp: str | None = None
    fecha_nacimiento: str | None = None
    pais: str | None = None
    rol: str | None = "CLIENTE"
    relacionados: list[dict[str, Any]] | None = Field(
        None, description="Beneficiarios controladores, representantes legales, socios… (mismos campos + 'rol')")
    crear_alertas: bool | None = Field(None, description="Por defecto True solo si hay 'referencia'")


class Operacion(BaseModel):
    expediente: str = Field(..., description="Número de escritura / instrumento / contrato / expediente")
    tipo_acto: str | None = Field(None, description="COMPRAVENTA_INMUEBLE, DONACION, FIDEICOMISO, CONSTITUCION_SOCIEDAD, PODER, ARRENDAMIENTO…")
    partes: list[dict[str, Any]] = Field(..., description="Cada parte: rol, nombre, tipo, rfc, curp, fecha_nacimiento, pais, "
                                                           "declara_pep, relacionados[] (beneficiarios controladores, representantes)")


class Login(BaseModel):
    usuario: str
    contrasena: str


class NuevoUsuario(BaseModel):
    usuario: str
    rol: str = Field(..., description="analista | supervisor | admin")
    contrasena: str = Field(..., min_length=10)


class NuevaContrasena(BaseModel):
    contrasena: str = Field(..., min_length=10)


class Resolucion(BaseModel):
    resolucion: str = Field(..., description="FALSO_POSITIVO | CONFIRMADA | DEVOLVER (solo supervisor, para regresar una propuesta)")
    nota: str = Field(..., min_length=10)


def create_app(service: Service | None = None) -> FastAPI:
    svc = service or Service()
    app = FastAPI(title="PLD Screening – Consulta de listas (LFPIORPI)", version="1.0.0")
    app.state.svc = svc

    fails: dict[str, deque] = defaultdict(deque)  # IP → instantes de intentos fallidos

    def _ip(request: Request) -> str:
        return (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()

    def _limit(ip: str) -> deque:
        q, now = fails[ip], time.time()
        while q and now - q[0] > 300:
            q.popleft()
        if len(q) >= 10:
            raise HTTPException(429, "Demasiados intentos fallidos; espere 5 minutos")
        return q

    def user(request: Request, x_api_key: str | None = Header(None)) -> dict:
        ip = _ip(request)
        q, now = _limit(ip), time.time()
        u = svc.authenticate(x_api_key)
        if not u:
            q.append(now)
            raise HTTPException(401, "API key inválida o ausente (cabecera X-API-Key)")
        return u

    def need(role: str):
        def dep(u: dict = Depends(user)) -> dict:
            if ROLES[u["role"]] < ROLES[role]:
                raise HTTPException(403, f"Requiere rol {role} o superior")
            return u
        return dep

    def run(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except ServiceError as e:
            raise HTTPException(e.status, str(e))

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(STATIC / "index.html")

    # ---- acceso por la página (usuario + contraseña)
    @app.post("/v1/login", summary="Inicia sesión (usuario y contraseña) y devuelve un token de 8 horas")
    def login(b: Login, request: Request):
        ip = _ip(request)
        q = _limit(ip)
        r = svc.login(b.usuario, b.contrasena)
        if not r:
            q.append(time.time())
            raise HTTPException(401, "Usuario o contraseña incorrectos")
        return r

    @app.post("/v1/logout", summary="Cierra la sesión")
    def logout(x_api_key: str | None = Header(None), u: dict = Depends(user)):
        svc.logout(x_api_key)
        return {"ok": True}

    @app.get("/v1/me", summary="Usuario de la sesión actual")
    def me(u: dict = Depends(user)):
        return {"usuario": u["name"], "rol": u["role"]}

    @app.get("/v1/users", summary="Lista de usuarios (admin)")
    def users(u: dict = Depends(need("admin"))):
        return svc.list_users()

    @app.post("/v1/users", summary="Crea un usuario con contraseña (admin)")
    def users_create(b: NuevoUsuario, u: dict = Depends(need("admin"))):
        run(svc.create_user, b.usuario, b.rol, b.contrasena)
        return {"ok": True, "usuario": b.usuario}

    @app.post("/v1/users/{name}/password", summary="Cambia la contraseña de un usuario (admin)")
    def users_pw(name: str, b: NuevaContrasena, u: dict = Depends(need("admin"))):
        run(svc.set_password, name, b.contrasena, u["name"])
        return {"ok": True}

    @app.post("/v1/users/{name}/{accion}", summary="Activa o desactiva un usuario (admin)")
    def users_toggle(name: str, accion: str, u: dict = Depends(need("admin"))):
        if accion not in ("activar", "desactivar"):
            raise HTTPException(404, "Acción no válida")
        if name == u["name"] and accion == "desactivar":
            raise HTTPException(400, "No puede desactivarse a sí mismo")
        run(svc.set_user_active, name, accion == "activar", u["name"])
        return {"ok": True}

    # ---- consultas
    @app.post("/v1/screen", summary="Consulta una persona (y sus relacionados) contra todas las listas")
    def screen(p: Persona, u: dict = Depends(need("analista"))):
        d = p.model_dump(exclude_none=True)
        return run(svc.screen, d, u["name"], persist=p.crear_alertas)

    @app.post("/v1/screen/batch", summary="Consulta por lote (JSON, máx. 1000)")
    def screen_batch(items: list[Persona], u: dict = Depends(need("analista"))):
        if len(items) > 1000:
            raise HTTPException(413, "Máximo 1000 por lote")
        out = []
        for p in items:
            try:
                r = svc.screen(p.model_dump(exclude_none=True), u["name"], persist=p.crear_alertas, kind="LOTE")
                out.append({"referencia": r["referencia"], "resultado": r["resultado"], "nivel_maximo": r["nivel_maximo"],
                            "id_consulta": r["id_consulta"], "coincidencias": len(r["coincidencias"])})
            except ServiceError as e:
                out.append({"referencia": p.referencia, "error": str(e)})
        return out

    @app.get("/v1/screenings/{sid}/constancia", response_class=HTMLResponse, summary="Constancia imprimible")
    def constancia(sid: int, u: dict = Depends(need("analista"))):
        return run(svc.constancia_html, sid)

    # ---- operaciones / expedientes (notarial / inmobiliario)
    @app.post("/v1/operaciones", summary="Consulta todas las partes de un expediente y emite dictamen consolidado")
    def operacion(o: Operacion, u: dict = Depends(need("analista"))):
        return run(svc.screen_operation, o.model_dump(), u["name"])

    @app.get("/v1/operaciones")
    def operaciones(expediente: str | None = None, limit: int = 100, u: dict = Depends(need("analista"))):
        return svc.list_operations(expediente, limit)

    @app.get("/v1/operaciones/{op_id}", summary="Resultado y estado vivo (se actualiza al resolver alertas)")
    def operacion_get(op_id: int, u: dict = Depends(need("analista"))):
        return run(svc.get_operation, op_id)

    @app.get("/v1/operaciones/{op_id}/constancia", response_class=HTMLResponse, summary="Constancia imprimible")
    def operacion_constancia(op_id: int, u: dict = Depends(need("analista"))):
        return run(svc.operation_constancia_html, op_id)

    # ---- sujetos / monitoreo
    @app.get("/v1/subjects")
    def subjects(limit: int = 100, offset: int = 0, riesgo: str | None = None, u: dict = Depends(need("analista"))):
        return svc.list_subjects(limit, offset, riesgo)

    @app.post("/v1/subjects/import-csv", summary="Carga masiva de clientes (CSV) y consulta inicial")
    async def import_subjects(file: UploadFile = File(...), u: dict = Depends(need("supervisor"))):
        return run(svc.import_subjects_csv, await file.read(), u["name"])

    @app.post("/v1/monitor/rescreen", summary="Re-consulta todos los sujetos contra todas las listas")
    def rescreen(u: dict = Depends(need("supervisor"))):
        return svc.rescreen_all(u["name"])

    # ---- alertas
    @app.get("/v1/alerts")
    def alerts(status: str | None = Query(None), limit: int = 100, offset: int = 0, u: dict = Depends(need("analista"))):
        return svc.list_alerts(status, limit, offset)

    @app.get("/v1/alerts/{aid}")
    def alert(aid: int, u: dict = Depends(need("analista"))):
        return run(svc.get_alert, aid)

    @app.post("/v1/alerts/{aid}/resolve", summary="Resolver alerta (doble validación en alertas de alto riesgo)")
    def resolve(aid: int, r: Resolucion, u: dict = Depends(need("analista"))):
        return run(svc.resolve_alert, aid, u, r.resolucion, r.nota)

    # ---- listas
    @app.get("/v1/lists")
    def lists(u: dict = Depends(need("analista"))):
        return svc.lists_status()

    @app.post("/v1/lists/update", summary="Descarga y aplica OFAC, ONU y SAT 69-B ahora")
    def update(u: dict = Depends(need("admin"))):
        return svc.update_lists(actor=u["name"])

    @app.post("/v1/lists/{source}/upload", summary="Carga una lista desde archivo (LPB, PEP, INTERNA, ...)")
    async def upload(source: str, file: UploadFile = File(...), formato: str = Form("generic"),
                     forzar: bool = Form(False), u: dict = Depends(need("admin"))):
        return run(svc.import_list, source.upper(), await file.read(), formato, file.filename or "carga", u["name"], forzar)

    @app.post("/v1/lists/inbox/process", summary="Procesa archivos depositados en data/inbox/<FUENTE>/")
    def inbox(u: dict = Depends(need("admin"))):
        return svc.process_inbox(u["name"])

    # ---- reportes y auditoría
    @app.get("/v1/dashboard")
    def dashboard(u: dict = Depends(need("analista"))):
        return svc.dashboard()

    @app.get("/v1/audit")
    def audit(limit: int = 100, u: dict = Depends(need("supervisor"))):
        return svc.audit_tail(limit)

    @app.get("/v1/audit/verify", summary="Verifica la integridad de la cadena de hashes de la bitácora")
    def verify(u: dict = Depends(need("supervisor"))):
        return svc.verify_audit()

    return app


def app_factory() -> FastAPI:  # uvicorn pldscreen.api:app_factory --factory
    return create_app()
