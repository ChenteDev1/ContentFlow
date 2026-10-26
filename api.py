"""API REST de ContentFlow sobre Azure Cosmos DB for MongoDB (IE9, IE10, IE11).

Aplicación externa que LEE y ESCRIBE en la base en tiempo real usando PyMongo.

    uvicorn api:app --reload --port 8000
    Documentación interactiva (Swagger): http://127.0.0.1:8000/docs
    Colección de Postman: postman/ContentFlow.postman_collection.json

Trazabilidad: cada petición recibe un X-Request-ID, se registra en
logs/contentflow.log (método, ruta, estado, milisegundos) y los errores de la
base se devuelven como JSON controlado sin exponer credenciales ni trazas.
"""
import time
import uuid

from fastapi import Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError, PyMongoError

import analitica_negocio as an
import servicios as s
from config import ConexionError, conectar_db, get_logger, mascarar
from validaciones import CATEGORIAS, OBJETIVOS, TIPOS_PUBLICACION, ErrorValidacion

log = get_logger("contentflow.api")
app = FastAPI(
    title="ContentFlow API",
    description="Integración de una aplicación externa con Azure Cosmos DB for MongoDB",
    version="1.0.0",
)

_db = None


def db():
    """Conexión perezosa y reutilizada. Si Azure no responde lanza ConexionError (-> 503)."""
    global _db
    if _db is None:
        _db = conectar_db()
    return _db


# ------------------------------------------------------------------ middleware
@app.middleware("http")
async def trazabilidad(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.rid = rid
    t0 = time.perf_counter()
    try:
        respuesta = await call_next(request)
    except Exception:  # noqa: BLE001 - último recurso: nunca filtrar trazas al cliente
        log.exception("[%s] error no controlado en %s %s", rid, request.method, request.url.path)
        respuesta = JSONResponse({"error": "error_interno", "request_id": rid}, status_code=500)
    ms = (time.perf_counter() - t0) * 1000
    respuesta.headers["X-Request-ID"] = rid
    respuesta.headers["X-Process-Time-ms"] = f"{ms:.1f}"
    log.info("[%s] %s %s -> %s (%.1f ms)", rid, request.method, request.url.path,
             respuesta.status_code, ms)
    return respuesta


# ------------------------------------------------------------------ errores
def _json(request, status, error, detalle):
    return JSONResponse({"error": error, "detalle": detalle,
                         "request_id": getattr(request.state, "rid", None)}, status_code=status)


@app.exception_handler(ErrorValidacion)
async def _validacion(request, exc):
    log.warning("[%s] validación: %s", request.state.rid, exc.errores)
    return _json(request, 422, "validacion", exc.errores)


@app.exception_handler(s.NoEncontrado)
async def _no_encontrado(request, exc):
    return _json(request, 404, "no_encontrado", str(exc))


@app.exception_handler(s.ReglaNegocio)
async def _regla(request, exc):
    log.warning("[%s] regla de negocio: %s", request.state.rid, exc)
    return _json(request, 409, "regla_de_negocio", str(exc))


@app.exception_handler(DuplicateKeyError)
async def _duplicado(request, exc):
    return _json(request, 409, "id_duplicado", "Ya existe un documento con ese _id")


@app.exception_handler(ConexionError)
async def _sin_conexion(request, exc):
    log.error("[%s] sin conexión: %s", request.state.rid, mascarar(exc))
    return _json(request, 503, "base_de_datos_no_disponible",
                 "No hay conexión con Cosmos DB; reintente en unos segundos")


@app.exception_handler(PyMongoError)
async def _pymongo(request, exc):
    log.error("[%s] error de base de datos: %s", request.state.rid, mascarar(exc))
    return _json(request, 503, "error_base_de_datos", "La base de datos no pudo completar la operación")


# ------------------------------------------------------------------ salud
@app.get("/salud", tags=["Operación"])
def salud():
    """Ping real a Cosmos DB: confirma disponibilidad y mide la latencia."""
    t0 = time.perf_counter()
    base = db()
    base.command("ping")
    return {"estado": "ok", "base_de_datos": base.name,
            "latencia_ping_ms": round((time.perf_counter() - t0) * 1000, 1),
            "documentos": {c: base[c].count_documents({}) for c in
                           ("usuarios", "publicaciones", "reacciones", "comentarios", "campañas")}}


# ------------------------------------------------------------------ publicaciones
@app.get("/publicaciones", tags=["Publicaciones"])
def listar_publicaciones(
    categoria: str | None = Query(None, description=f"Una de {sorted(CATEGORIAS)}"),
    tipo: str | None = Query(None, description=f"Una de {sorted(TIPOS_PUBLICACION)}"),
    usuario_id: str | None = None,
    limite: int = Query(10, ge=1, le=100),
    pagina: int = Query(1, ge=1),
):
    """Lista paginada, de la más reciente a la más antigua, con filtros opcionales."""
    filtro = {}
    if categoria:
        if categoria not in CATEGORIAS:
            raise ErrorValidacion([f"categoria inválida: {categoria!r}"])
        filtro["categoria"] = categoria
    if tipo:
        if tipo not in TIPOS_PUBLICACION:
            raise ErrorValidacion([f"tipo inválido: {tipo!r}"])
        filtro["tipo"] = tipo
    if usuario_id:
        filtro["usuario_id"] = usuario_id
    docs, orden_en = s.buscar(db().publicaciones, filtro, None, [("fecha_publicacion", -1)],
                              limite, (pagina - 1) * limite)
    return {"pagina": pagina, "limite": limite, "orden_resuelto_en": orden_en,
            "total": db().publicaciones.count_documents(filtro), "datos": docs}


@app.get("/publicaciones/{pub_id}", tags=["Publicaciones"])
def obtener_publicacion(pub_id: str):
    pub = s.obtener(db(), "publicaciones", pub_id)
    pub["reacciones"] = db().reacciones.count_documents({"publicacion_id": pub_id})
    pub["comentarios"] = db().comentarios.count_documents({"publicacion_id": pub_id})
    return pub


@app.post("/publicaciones", status_code=201, tags=["Publicaciones"])
def crear_publicacion(cuerpo: dict = Body(..., examples=[{
        "usuario_id": "user_1", "contenido": "Nueva publicación desde la API",
        "categoria": "Tecnología", "tipo": "Texto", "hashtags": ["#Azure", "#NoSQL"]}])):
    return s.crear_publicacion(db(), cuerpo)


@app.put("/publicaciones/{pub_id}", tags=["Publicaciones"])
def actualizar_publicacion(pub_id: str, cuerpo: dict = Body(...)):
    return s.actualizar_publicacion(db(), pub_id, cuerpo)


@app.delete("/publicaciones/{pub_id}", tags=["Publicaciones"])
def eliminar_publicacion(pub_id: str):
    """Borrado en cascada (reacciones, comentarios y referencias en campañas)."""
    return {"eliminado": pub_id, **s.eliminar_publicacion(db(), pub_id)}


# ------------------------------------------------------------------ usuarios
@app.get("/usuarios/{user_id}", tags=["Usuarios"])
def obtener_usuario(user_id: str):
    return s.obtener(db(), "usuarios", user_id)


@app.post("/usuarios", status_code=201, tags=["Usuarios"])
def crear_usuario(cuerpo: dict = Body(...)):
    return s.crear_usuario(db(), cuerpo)


@app.put("/usuarios/{user_id}", tags=["Usuarios"])
def actualizar_usuario(user_id: str, cuerpo: dict = Body(...)):
    return s.actualizar_usuario(db(), user_id, cuerpo)


# ------------------------------------------------------------------ interacciones
@app.post("/reacciones", status_code=201, tags=["Interacciones"])
def crear_reaccion(cuerpo: dict = Body(..., examples=[{
        "usuario_id": "user_1", "publicacion_id": "pub_1", "tipo_reaccion": "Me gusta"}])):
    return s.crear_reaccion(db(), cuerpo)


@app.post("/comentarios", status_code=201, tags=["Interacciones"])
def crear_comentario(cuerpo: dict = Body(...)):
    return s.crear_comentario(db(), cuerpo)


@app.post("/comentarios/{comentario_id}/like", tags=["Interacciones"])
def like_comentario(comentario_id: str):
    return s.dar_like_comentario(db(), comentario_id)


# ------------------------------------------------------------------ campañas
@app.get("/campanas", tags=["Campañas"])
def listar_campanas(
    objetivo: str | None = Query(None, description=f"Uno de {sorted(OBJETIVOS)}"),
    likes_min: int = Query(0, ge=0),
    limite: int = Query(10, ge=1, le=100),
):
    filtro = {}
    if objetivo:
        if objetivo not in OBJETIVOS:
            raise ErrorValidacion([f"objetivo inválido: {objetivo!r}"])
        filtro["objetivo"] = objetivo
    if likes_min:
        filtro["metricas_objetivo.likes"] = {"$gte": likes_min}
    docs, orden_en = s.buscar(db().campañas, filtro, None, [("metricas_objetivo.likes", -1)], limite)
    return {"orden_resuelto_en": orden_en, "datos": docs}


@app.post("/campanas/{campana_id}/publicaciones/{pub_id}", tags=["Campañas"])
def asociar(campana_id: str, pub_id: str):
    nueva = s.asociar_publicacion_a_campana(db(), campana_id, pub_id)
    return {"campana": campana_id, "publicacion": pub_id, "asociacion_nueva": nueva}


# ------------------------------------------------------------------ analítica
@app.get("/analitica/usuarios-activos", tags=["Analítica"])
def usuarios_activos(top: int = Query(10, ge=1, le=50)):
    return an.usuarios_mas_activos(db(), top)


@app.get("/analitica/contenido-popular", tags=["Analítica"])
def contenido_popular(top: int = Query(10, ge=1, le=50)):
    return an.contenido_popular(db(), top)


@app.get("/analitica/horarios", tags=["Analítica"])
def horarios():
    return an.franjas_horarias(an.horarios_publicacion(db()))


@app.get("/analitica/campanas", tags=["Analítica"])
def impacto_campanas(top: int = Query(10, ge=1, le=50)):
    por_objetivo, mejores, _ = an.impacto_campanas(db(), top)
    return {"por_objetivo": por_objetivo, "mejores": mejores}
