"""Capa de negocio de ContentFlow: operaciones CRUD con reglas de integridad.

La usan operaciones_crud.py (scripts) y api.py (REST). Cosmos DB for MongoDB
no ofrece transacciones multi-colección, así que las reglas de integridad
(el usuario existe, la fecha es coherente, no hay duplicados, borrado en
cascada) se aplican aquí, en la aplicación.
"""
from pymongo.errors import OperationFailure

from config import get_logger
from validaciones import (
    ErrorValidacion, ahora_iso, nuevo_id,
    validar_comentario, validar_publicacion, validar_reaccion, validar_usuario,
)

log = get_logger("contentflow.servicios")


class NoEncontrado(LookupError):
    """El documento solicitado no existe."""


class ReglaNegocio(ValueError):
    """Entrada válida en formato pero que rompe una regla de integridad (HTTP 409/422)."""


# ------------------------------------------------------------------ lectura
def buscar(coleccion, filtro, proyeccion=None, orden=None, limite=0, salto=0):
    """find() con ordenamiento en el SERVIDOR cuando hay índice.

    Cosmos DB for MongoDB rechaza ordenar por un campo sin índice
    (OperationFailure). En ese caso se registra una advertencia y se ordena en
    memoria como respaldo. Devuelve (documentos, donde_se_ordeno).
    """
    if not orden:
        cursor = coleccion.find(filtro, proyeccion)
        if salto:
            cursor = cursor.skip(salto)
        if limite:
            cursor = cursor.limit(limite)
        return list(cursor), "sin orden"
    try:
        cur = coleccion.find(filtro, proyeccion).sort(orden)
        if salto:
            cur = cur.skip(salto)
        if limite:
            cur = cur.limit(limite)
        return list(cur), "servidor (índice)"
    except OperationFailure as e:
        log.warning("Sin índice para ordenar %s por %s; se ordena en memoria. Detalle: %s",
                    coleccion.name, orden, e)
        docs = list(coleccion.find(filtro, proyeccion))
        for campo, sentido in reversed(orden):
            docs.sort(key=lambda d, c=campo: str(d.get(c, "")), reverse=(sentido == -1))
        fin = salto + limite if limite else None
        return docs[salto:fin], "memoria (respaldo)"


def obtener(db, coleccion, _id):
    doc = db[coleccion].find_one({"_id": _id})
    if doc is None:
        raise NoEncontrado(f"{coleccion[:-1] if coleccion.endswith('s') else coleccion} '{_id}' no existe")
    return doc


# ------------------------------------------------------------------ creación
def crear_usuario(db, datos):
    doc = validar_usuario(datos)
    doc.setdefault("_id", nuevo_id("user"))
    if db.usuarios.find_one({"correo": doc["correo"]}, {"_id": 1}):
        raise ReglaNegocio(f"El correo {doc['correo']} ya está registrado")
    db.usuarios.insert_one(doc)  # DuplicateKeyError si _id repetido
    log.info("usuario creado %s", doc["_id"])
    return doc


def crear_publicacion(db, datos):
    datos = dict(datos)
    datos.setdefault("fecha_publicacion", ahora_iso())
    doc = validar_publicacion(datos)
    doc.setdefault("_id", nuevo_id("pub"))
    usuario = db.usuarios.find_one({"_id": doc["usuario_id"]}, {"fecha_registro": 1})
    if usuario is None:
        raise ReglaNegocio(f"El usuario '{doc['usuario_id']}' no existe (publicación huérfana)")
    if doc["fecha_publicacion"] < usuario["fecha_registro"]:
        raise ReglaNegocio("La publicación no puede ser anterior al registro del usuario "
                           f"({usuario['fecha_registro']})")
    db.publicaciones.insert_one(doc)
    log.info("publicación creada %s (usuario=%s)", doc["_id"], doc["usuario_id"])
    return doc


def _verificar_contexto(db, doc, entidad):
    """Valida usuario y publicación existentes y que la fecha no preceda a la publicación."""
    usuario = db.usuarios.find_one({"_id": doc["usuario_id"]}, {"fecha_registro": 1})
    if usuario is None:
        raise ReglaNegocio(f"El usuario '{doc['usuario_id']}' no existe")
    pub = db.publicaciones.find_one({"_id": doc["publicacion_id"]}, {"fecha_publicacion": 1})
    if pub is None:
        raise ReglaNegocio(f"La publicación '{doc['publicacion_id']}' no existe "
                           f"({entidad} sin contexto)")
    if doc["fecha"] < pub["fecha_publicacion"]:
        raise ReglaNegocio(f"La fecha del {entidad} ({doc['fecha']}) no puede ser anterior a la "
                           f"publicación ({pub['fecha_publicacion']})")
    if doc["fecha"] < usuario["fecha_registro"]:
        raise ReglaNegocio(f"La fecha del {entidad} es anterior al registro del usuario")


def crear_reaccion(db, datos):
    datos = dict(datos)
    datos.setdefault("fecha", ahora_iso())
    doc = validar_reaccion(datos)
    doc.setdefault("_id", nuevo_id("react"))
    _verificar_contexto(db, doc, "reacción")
    if db.reacciones.find_one({"usuario_id": doc["usuario_id"],
                               "publicacion_id": doc["publicacion_id"]}, {"_id": 1}):
        raise ReglaNegocio("El usuario ya reaccionó a esta publicación (use actualizar_reaccion)")
    db.reacciones.insert_one(doc)
    log.info("reacción creada %s", doc["_id"])
    return doc


def crear_comentario(db, datos):
    datos = dict(datos)
    datos.setdefault("fecha", ahora_iso())
    doc = validar_comentario(datos)
    doc.setdefault("_id", nuevo_id("comm"))
    _verificar_contexto(db, doc, "comentario")
    db.comentarios.insert_one(doc)
    log.info("comentario creado %s", doc["_id"])
    return doc


# ------------------------------------------------------------- actualización
_INMUTABLES_PUB = {"_id", "usuario_id", "fecha_publicacion"}


def actualizar_publicacion(db, pub_id, cambios):
    """Actualiza solo campos editables. Devuelve el documento resultante."""
    if not isinstance(cambios, dict) or not cambios:
        raise ErrorValidacion(["Debe indicar al menos un campo a modificar"])
    prohibidos = sorted(_INMUTABLES_PUB & set(cambios))
    if prohibidos:
        raise ErrorValidacion([f"Campos inmutables, no se pueden modificar: {prohibidos}"])
    limpios = validar_publicacion(cambios, parcial=True)
    limpios["fecha_edicion"] = ahora_iso()
    res = db.publicaciones.update_one({"_id": pub_id}, {"$set": limpios})
    if res.matched_count == 0:
        raise NoEncontrado(f"publicación '{pub_id}' no existe")
    log.info("publicación %s actualizada (campos=%s, modificados=%s)",
             pub_id, sorted(limpios), res.modified_count)
    return db.publicaciones.find_one({"_id": pub_id})


def actualizar_usuario(db, user_id, cambios):
    if not isinstance(cambios, dict) or not cambios:
        raise ErrorValidacion(["Debe indicar al menos un campo a modificar"])
    if "_id" in cambios or "fecha_registro" in cambios:
        raise ErrorValidacion(["'_id' y 'fecha_registro' son inmutables"])
    limpios = validar_usuario(cambios, parcial=True)
    if "correo" in limpios and db.usuarios.find_one(
            {"correo": limpios["correo"], "_id": {"$ne": user_id}}, {"_id": 1}):
        raise ReglaNegocio(f"El correo {limpios['correo']} ya pertenece a otro usuario")
    res = db.usuarios.update_one({"_id": user_id}, {"$set": limpios})
    if res.matched_count == 0:
        raise NoEncontrado(f"usuario '{user_id}' no existe")
    return db.usuarios.find_one({"_id": user_id})


def cambiar_reaccion(db, reaccion_id, tipo_reaccion):
    limpio = validar_reaccion({"usuario_id": "x_1", "publicacion_id": "x_1",
                               "tipo_reaccion": tipo_reaccion, "fecha": ahora_iso()})
    res = db.reacciones.update_one({"_id": reaccion_id},
                                   {"$set": {"tipo_reaccion": limpio["tipo_reaccion"]}})
    if res.matched_count == 0:
        raise NoEncontrado(f"reacción '{reaccion_id}' no existe")
    return db.reacciones.find_one({"_id": reaccion_id})


def dar_like_comentario(db, comentario_id, cantidad=1):
    """Incremento atómico ($inc): evita perder likes si dos usuarios coinciden."""
    res = db.comentarios.find_one_and_update(
        {"_id": comentario_id}, {"$inc": {"likes": cantidad}}, return_document=True)
    if res is None:
        raise NoEncontrado(f"comentario '{comentario_id}' no existe")
    return res


def asociar_publicacion_a_campana(db, campana_id, pub_id):
    """$addToSet evita duplicar la publicación dentro de la campaña (idempotente)."""
    if db.publicaciones.find_one({"_id": pub_id}, {"_id": 1}) is None:
        raise ReglaNegocio(f"La publicación '{pub_id}' no existe; no se puede asociar")
    res = db.campañas.update_one({"_id": campana_id},
                                 {"$addToSet": {"publicaciones_asociadas": pub_id}})
    if res.matched_count == 0:
        raise NoEncontrado(f"campaña '{campana_id}' no existe")
    return res.modified_count == 1  # False => ya estaba asociada


def sumar_metricas_campana(db, campana_id, likes=0, comentarios=0, compartidos=0):
    res = db.campañas.find_one_and_update(
        {"_id": campana_id},
        {"$inc": {"metricas_objetivo.likes": likes,
                  "metricas_objetivo.comentarios": comentarios,
                  "metricas_objetivo.compartidos": compartidos}},
        return_document=True)
    if res is None:
        raise NoEncontrado(f"campaña '{campana_id}' no existe")
    return res


# ----------------------------------------------------------------- eliminación
def eliminar_publicacion(db, pub_id):
    """Borrado en cascada: evita reacciones/comentarios huérfanos (pérdida de contexto).

    Orden: primero los dependientes y las referencias en campañas, al final la
    publicación. Si algo falla a mitad de camino, la publicación sigue existiendo
    y la operación puede reintentarse sin dejar huérfanos (es idempotente).
    """
    if db.publicaciones.find_one({"_id": pub_id}, {"_id": 1}) is None:
        raise NoEncontrado(f"publicación '{pub_id}' no existe")
    r = db.reacciones.delete_many({"publicacion_id": pub_id}).deleted_count
    c = db.comentarios.delete_many({"publicacion_id": pub_id}).deleted_count
    k = db.campañas.update_many({"publicaciones_asociadas": pub_id},
                                {"$pull": {"publicaciones_asociadas": pub_id}}).modified_count
    p = db.publicaciones.delete_one({"_id": pub_id}).deleted_count
    resumen = {"publicaciones": p, "reacciones": r, "comentarios": c, "campañas_actualizadas": k}
    log.info("publicación %s eliminada en cascada: %s", pub_id, resumen)
    return resumen


def eliminar_usuario(db, user_id):
    """No permite borrar usuarios con actividad (conserva el historial analítico)."""
    if db.usuarios.find_one({"_id": user_id}, {"_id": 1}) is None:
        raise NoEncontrado(f"usuario '{user_id}' no existe")
    actividad = {
        "publicaciones": db.publicaciones.count_documents({"usuario_id": user_id}),
        "reacciones": db.reacciones.count_documents({"usuario_id": user_id}),
        "comentarios": db.comentarios.count_documents({"usuario_id": user_id}),
    }
    if any(actividad.values()):
        raise ReglaNegocio(f"El usuario tiene actividad registrada {actividad}; no se elimina")
    return db.usuarios.delete_one({"_id": user_id}).deleted_count


__all__ = [n for n in dir() if not n.startswith("_")]
