"""Validación de entradas de ContentFlow (sin acceso a base de datos).

Se usa tanto en operaciones_crud.py como en la API REST, así hay una sola
fuente de verdad para las reglas. Cada validador devuelve un documento
"limpio" o lanza ErrorValidacion con TODOS los errores encontrados.
"""
import re
import uuid
from datetime import datetime

FORMATO_FECHA = "%Y-%m-%dT%H:%M:%S"  # mismo formato que los JSON del caso (19 caracteres)

CATEGORIAS = {"Deportes", "Cultura", "Entretenimiento", "Tecnología", "Educación"}
TIPOS_PUBLICACION = {"Video", "Texto", "Imagen"}
TIPOS_REACCION = {"Me gusta", "Me encanta", "Me enoja", "Me entristece"}
DISPOSITIVOS = {"Desktop", "Móvil", "Tablet"}
GENEROS = {"Masculino", "Femenino", "Otro"}
OBJETIVOS = {"Captar nuevos usuarios", "Aumentar engagement", "Promover contenido"}

_RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RE_HASHTAG = re.compile(r"^#\w{1,30}$", re.UNICODE)
_RE_ID = re.compile(r"^[A-Za-z]+_[A-Za-z0-9_]{1,40}$")


class ErrorValidacion(ValueError):
    """Entrada inválida. `errores` es la lista completa de problemas."""

    def __init__(self, errores):
        self.errores = list(errores)
        super().__init__("; ".join(self.errores))


def ahora_iso():
    """Fecha actual con el mismo formato que el dataset (sin microsegundos ni zona)."""
    return datetime.now().strftime(FORMATO_FECHA)


def nuevo_id(prefijo):
    return f"{prefijo}_{uuid.uuid4().hex[:10]}"


def parsear_fecha(valor):
    """Devuelve datetime o None si el texto no cumple YYYY-MM-DDTHH:MM:SS."""
    if not isinstance(valor, str):
        return None
    try:
        return datetime.strptime(valor, FORMATO_FECHA)
    except ValueError:
        return None


# ---------------------------------------------------------------- helpers
def _texto(d, campo, errores, minimo=1, maximo=2000, requerido=True):
    v = d.get(campo)
    if v is None:
        if requerido:
            errores.append(f"'{campo}' es obligatorio")
        return None
    if not isinstance(v, str):
        errores.append(f"'{campo}' debe ser texto")
        return None
    v = v.strip()
    if not (minimo <= len(v) <= maximo):
        errores.append(f"'{campo}' debe tener entre {minimo} y {maximo} caracteres")
    return v


def _opcion(d, campo, permitidos, errores, requerido=True):
    v = d.get(campo)
    if v is None:
        if requerido:
            errores.append(f"'{campo}' es obligatorio")
        return None
    if v not in permitidos:
        errores.append(f"'{campo}' inválido: {v!r}. Opciones: {sorted(permitidos)}")
    return v


def _fecha(d, campo, errores, requerido=True):
    v = d.get(campo)
    if v is None:
        if requerido:
            errores.append(f"'{campo}' es obligatorio (formato YYYY-MM-DDTHH:MM:SS)")
        return None
    if parsear_fecha(v) is None:
        errores.append(f"'{campo}' con formato inválido: {v!r} (use YYYY-MM-DDTHH:MM:SS)")
    return v


def _id_ref(d, campo, errores, requerido=True):
    v = d.get(campo)
    if v is None:
        if requerido:
            errores.append(f"'{campo}' es obligatorio")
        return None
    if not isinstance(v, str) or not _RE_ID.match(v):
        errores.append(f"'{campo}' con formato de id inválido: {v!r}")
    return v


def _rechazar_desconocidos(d, permitidos, errores):
    extra = sorted(set(d) - set(permitidos))
    if extra:
        errores.append(f"Campos no permitidos: {extra}")


def _cerrar(errores, doc):
    if errores:
        raise ErrorValidacion(errores)
    return doc


def _exigir_dict(d):
    if not isinstance(d, dict):
        raise ErrorValidacion(["El cuerpo debe ser un objeto JSON"])


# ---------------------------------------------------------------- entidades
def validar_usuario(d, parcial=False):
    _exigir_dict(d)
    e = []
    permitidos = {"_id", "nombre", "correo", "pais", "genero", "fecha_registro", "dispositivo"}
    _rechazar_desconocidos(d, permitidos, e)
    req = not parcial
    doc = {}
    if "_id" in d:
        doc["_id"] = _id_ref(d, "_id", e)
    for campo, maximo in (("nombre", 100), ("pais", 80)):
        if campo in d or req:
            doc[campo] = _texto(d, campo, e, 2, maximo)
    if "correo" in d or req:
        doc["correo"] = _texto(d, "correo", e, 5, 120)
        if doc["correo"] and not _RE_CORREO.match(doc["correo"]):
            e.append(f"'correo' con formato inválido: {doc['correo']!r}")
    if "genero" in d or req:
        doc["genero"] = _opcion(d, "genero", GENEROS, e)
    if "dispositivo" in d or req:
        doc["dispositivo"] = _opcion(d, "dispositivo", DISPOSITIVOS, e)
    if "fecha_registro" in d or req:
        doc["fecha_registro"] = _fecha(d, "fecha_registro", e)
    return _cerrar(e, {k: v for k, v in doc.items() if v is not None})


def validar_publicacion(d, parcial=False):
    _exigir_dict(d)
    e = []
    permitidos = {"_id", "usuario_id", "contenido", "fecha_publicacion", "categoria",
                  "hashtags", "tipo"}
    _rechazar_desconocidos(d, permitidos, e)
    req = not parcial
    doc = {}
    if "_id" in d:
        doc["_id"] = _id_ref(d, "_id", e)
    if "usuario_id" in d or req:
        doc["usuario_id"] = _id_ref(d, "usuario_id", e)
    if "contenido" in d or req:
        doc["contenido"] = _texto(d, "contenido", e, 1, 2000)
    if "fecha_publicacion" in d or req:
        doc["fecha_publicacion"] = _fecha(d, "fecha_publicacion", e)
    if "categoria" in d or req:
        doc["categoria"] = _opcion(d, "categoria", CATEGORIAS, e)
    if "tipo" in d or req:
        doc["tipo"] = _opcion(d, "tipo", TIPOS_PUBLICACION, e)
    if "hashtags" in d or req:
        h = d.get("hashtags")
        if not isinstance(h, list) or not (1 <= len(h) <= 10):
            e.append("'hashtags' debe ser una lista de 1 a 10 elementos")
        else:
            malos = [x for x in h if not isinstance(x, str) or not _RE_HASHTAG.match(x)]
            if malos:
                e.append(f"'hashtags' inválidos (deben ser tipo '#palabra'): {malos}")
            if len(set(h)) != len(h):
                e.append("'hashtags' contiene elementos repetidos")
            doc["hashtags"] = h
    return _cerrar(e, {k: v for k, v in doc.items() if v is not None})


def validar_reaccion(d):
    _exigir_dict(d)
    e = []
    _rechazar_desconocidos(d, {"_id", "usuario_id", "publicacion_id", "tipo_reaccion", "fecha"}, e)
    doc = {
        "usuario_id": _id_ref(d, "usuario_id", e),
        "publicacion_id": _id_ref(d, "publicacion_id", e),
        "tipo_reaccion": _opcion(d, "tipo_reaccion", TIPOS_REACCION, e),
        "fecha": _fecha(d, "fecha", e),
    }
    if "_id" in d:
        doc["_id"] = _id_ref(d, "_id", e)
    return _cerrar(e, {k: v for k, v in doc.items() if v is not None})


def validar_comentario(d):
    _exigir_dict(d)
    e = []
    _rechazar_desconocidos(d, {"_id", "usuario_id", "publicacion_id", "comentario", "fecha", "likes"}, e)
    doc = {
        "usuario_id": _id_ref(d, "usuario_id", e),
        "publicacion_id": _id_ref(d, "publicacion_id", e),
        "comentario": _texto(d, "comentario", e, 1, 500),
        "fecha": _fecha(d, "fecha", e),
    }
    likes = d.get("likes", 0)
    if isinstance(likes, bool) or not isinstance(likes, int) or likes < 0:
        e.append("'likes' debe ser un entero >= 0")
    else:
        doc["likes"] = likes
    if "_id" in d:
        doc["_id"] = _id_ref(d, "_id", e)
    return _cerrar(e, {k: v for k, v in doc.items() if v is not None})
