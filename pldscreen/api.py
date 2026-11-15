"""API REST (FastAPI). Autenticación por cabecera X-API-Key con roles analista < supervisor < admin."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import re
import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
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


class Registro(BaseModel):
    nombre: str = Field(..., max_length=120)
    organizacion: str = Field(..., max_length=160)
    tipo: str | None = "OTRO"
    email: str = Field(..., max_length=200)
    telefono: str | None = Field(None, max_length=30)
    contrasena: str = Field(..., min_length=10, max_length=200)
    acepta: bool = False
    web: str | None = Field(None, description="Campo trampa anti-bots: debe ir vacío")


class AltaCliente(BaseModel):
    nombre: str
    organizacion: str
    tipo: str | None = "OTRO"
    email: str
    telefono: str | None = None
    notas: str | None = None
    plan: str = "DEMO"
    contrasena: str = Field(..., min_length=10)


class AccionCliente(BaseModel):
    valor: str | None = None


class CambioContrasena(BaseModel):
    actual: str
    nueva: str = Field(..., min_length=10, max_length=200)


class CambioRol(BaseModel):
    rol: str


class Resolucion(BaseModel):
    resolucion: str = Field(..., description="FALSO_POSITIVO | CONFIRMADA | DEVOLVER (solo supervisor, para regresar una propuesta)")
    nota: str = Field(..., min_length=10)


def create_app(service: Service | None = None) -> FastAPI:
    svc = service or Service()
    app = FastAPI(title="PLD Screening – Consulta de listas (LFPIORPI)", version="2.0.0")
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

    reg_hits: dict[str, deque] = defaultdict(deque)  # IP → instantes de registros (máx. 5 por hora)
    SCREEN_ID = re.compile(r"^/v1/screenings/\d+(/constancia)?$")
    DEMO_OK = [("POST", re.compile(r"^/v1/screen$")), ("GET", re.compile(r"^/v1/me$")), ("POST", re.compile(r"^/v1/logout$")), ("POST", re.compile(r"^/v1/me/password$")),
               ("GET", re.compile(r"^/v1/lists$")), ("GET", re.compile(r"^/v1/entries/\d+$")), ("GET", SCREEN_ID)]

    def user(request: Request, x_api_key: str | None = Header(None)) -> dict:
        ip = _ip(request)
        q, now = _limit(ip), time.time()
        u = svc.authenticate(x_api_key)
        if not u:
            q.append(now)
            raise HTTPException(401, "API key inválida o ausente (cabecera X-API-Key)")
        cuenta = svc.info_cuenta(u["name"])
        u["demo"] = bool(cuenta and cuenta["plan"] == "DEMO")
        u["cuenta"] = cuenta
        if u["demo"]:
            path, m = request.url.path, request.method
            libre = path in ("/v1/me", "/v1/logout", "/v1/me/password")
            if not libre:
                if cuenta["estado"] == "DEMO_VENCIDO":
                    raise HTTPException(402, "Su demo terminó. Para seguir usando el sistema contacte a ventas para adquirir la versión completa.")
                if not any(m == mm and rx.match(path) for mm, rx in DEMO_OK):
                    raise HTTPException(403, "Esta función no está incluida en la demo. Disponible en la versión completa.")
                if m == "POST" and path == "/v1/screen" and cuenta["estado"] == "DEMO_AGOTADO":
                    raise HTTPException(402, "Agotó las consultas de su demo. Contacte a ventas para adquirir la versión completa.")
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
        r = {"usuario": u["name"], "rol": u["role"]}
        if u.get("cuenta"):
            r["cuenta"] = u["cuenta"]
        return r

    @app.post("/v1/me/password", summary="Cambia la contraseña propia (pide la actual)")
    def me_pw(b: CambioContrasena, request: Request, u: dict = Depends(user)):
        q = _limit(_ip(request))
        try:
            svc.cambiar_mi_contrasena(u["name"], b.actual, b.nueva)
        except ServiceError as e:
            if e.status == 400 and "actual" in str(e):
                q.append(time.time())
            raise HTTPException(e.status, str(e))
        return {"ok": True}

    @app.post("/v1/users/{name}/rol", summary="Cambia el rol de un usuario (admin)")
    def users_rol(name: str, b: CambioRol, u: dict = Depends(need("admin"))):
        if name == u["name"]:
            raise HTTPException(400, "No puede cambiar su propio rol")
        run(svc.set_role, name, b.rol, u["name"])
        return {"ok": True}

    @app.get("/v1/sistema", summary="Estado del sistema (admin)")
    def sistema(u: dict = Depends(need("admin"))):
        return svc.estado_sistema()

    @app.get("/v1/sistema/respaldo", summary="Descarga un respaldo consistente de la base (admin)")
    def respaldo(u: dict = Depends(need("admin"))):
        nombre, datos = svc.respaldo_bytes(u["name"])
        return Response(datos, media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

    @app.post("/v1/sistema/depurar-demos", summary="Borra consultas de demos vencidas hace más de 30 días (admin)")
    def depurar(u: dict = Depends(need("admin"))):
        return svc.depurar_demos(30, u["name"])

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

    # ---- registro de prospectos (público) y panel de clientes (admin)
    @app.get("/v1/registro/config", summary="Datos públicos del formulario de registro")
    def registro_cfg():
        return {"abierto": svc.s.registro_abierto, "dias": svc.s.demo_dias, "consultas": svc.s.demo_consultas,
                "contacto": svc.s.contacto_ventas}

    @app.post("/v1/registro", summary="Registro público: crea una cuenta de demo limitada")
    def registro(b: Registro, request: Request):
        if not svc.s.registro_abierto:
            raise HTTPException(403, "El registro de demos está cerrado. Contacte a ventas.")
        if b.web:  # bot
            return {"ok": True}
        if not b.acepta:
            raise HTTPException(400, "Debe aceptar los términos de la demo")
        ip, now = _ip(request), time.time()
        q = reg_hits[ip]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= 5:
            raise HTTPException(429, "Demasiados registros desde esta red; intente más tarde")
        r = run(svc.registrar_cliente, b.model_dump(), b.contrasena, "FORMULARIO", "registro")
        q.append(now)
        return r

    @app.get("/v1/clientes", summary="Panel de clientes y demos (admin)")
    def clientes(estado: str | None = None, texto: str | None = None, u: dict = Depends(need("admin"))):
        return svc.listar_clientes(estado, texto)

    @app.get("/v1/clientes/resumen", summary="Totales por estado (admin)")
    def clientes_resumen(u: dict = Depends(need("admin"))):
        return svc.resumen_clientes()

    @app.get("/v1/clientes/export.csv", summary="Exporta clientes a CSV (admin)")
    def clientes_csv(u: dict = Depends(need("admin"))):
        return Response(svc.clientes_csv(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="clientes.csv"'})

    @app.post("/v1/clientes", summary="Alta manual de un cliente (admin)")
    def clientes_alta(b: AltaCliente, u: dict = Depends(need("admin"))):
        if b.plan not in ("DEMO", "PAGADO"):
            raise HTTPException(400, "Plan inválido")
        return run(svc.registrar_cliente, b.model_dump(), b.contrasena, "ALTA_MANUAL", u["name"], b.plan)

    @app.post("/v1/clientes/{cid}/{accion}", summary="Extender demo, activar pago, suspender… (admin)")
    def clientes_accion(cid: int, accion: str, b: AccionCliente | None = None, u: dict = Depends(need("admin"))):
        return run(svc.accion_cliente, cid, accion, u["name"], b.valor if b else None)

    # ---- consultas
    @app.post("/v1/screen", summary="Consulta una persona (y sus relacionados) contra todas las listas")
    def screen(p: Persona, u: dict = Depends(need("analista"))):
        d = p.model_dump(exclude_none=True)
        if u.get("demo"):  # la demo no guarda sujetos ni alertas ni consulta relacionados
            d.pop("referencia", None)
            d.pop("relacionados", None)
            r = run(svc.screen, d, u["name"], persist=False)
            svc.usar_consulta(u["name"])
            return r
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

    @app.get("/v1/screenings", summary="Historial de consultas con filtros")
    def historial(texto: str | None = None, nivel: str | None = None, fuente: str | None = None,
                  desde: str | None = None, hasta: str | None = None, tipo: str | None = None,
                  limit: int = 100, offset: int = 0, u: dict = Depends(need("analista"))):
        return svc.screening_history(texto, nivel, fuente, desde, hasta, tipo, limit, offset)

    @app.get("/v1/screenings/export.csv", summary="Exporta el historial filtrado a CSV (supervisor)")
    def historial_csv(texto: str | None = None, nivel: str | None = None, fuente: str | None = None,
                      desde: str | None = None, hasta: str | None = None, tipo: str | None = None,
                      u: dict = Depends(need("supervisor"))):
        return Response(svc.history_csv(texto=texto, nivel=nivel, fuente=fuente, desde=desde, hasta=hasta, tipo=tipo),
                        media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="historial_consultas.csv"'})

    @app.get("/v1/screenings/{sid}", summary="Resultado completo de una consulta anterior")
    def consulta_get(sid: int, u: dict = Depends(need("analista"))):
        return run(svc.get_screening, sid, u["name"] if u.get("demo") else None)

    @app.get("/v1/entries/{entry_id}", summary="Ficha completa de un registro de lista")
    def ficha(entry_id: int, u: dict = Depends(need("analista"))):
        return run(svc.entry_detail, entry_id)

    @app.get("/v1/screenings/{sid}/constancia", response_class=HTMLResponse, summary="Constancia imprimible")
    def constancia(sid: int, u: dict = Depends(need("analista"))):
        return run(svc.constancia_html, sid, u["name"] if u.get("demo") else None, bool(u.get("demo")))

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
