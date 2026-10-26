"""CRUD completo de ContentFlow sobre un caso de negocio real (IE7, IE8).

Escenario: "Lanzamiento de una publicación dentro de una campaña".
Un usuario nuevo se registra, publica, recibe reacciones y comentarios, la
publicación se asocia a una campaña, se edita, y finalmente se retira en
cascada. Involucra las 5 colecciones, reglas de integridad y casos de error.

Todo lo creado usa ids "*_demo_crud" y se limpia siempre (incluso si algo falla),
de modo que el script se puede repetir sin dejar rastro ni duplicados.

Uso:  python operaciones_crud.py
"""
import sys

from pymongo.errors import DuplicateKeyError, PyMongoError

import servicios as s
from config import COLECCIONES, ConexionError, conectar_db, get_logger
from validaciones import ErrorValidacion

log = get_logger("contentflow.crud")

USER = "user_demo_crud"
PUB = "pub_demo_crud"
CAMPANA = "camp_1"


class Reporte:
    def __init__(self):
        self.fallos = 0
        self.total = 0

    def paso(self, descripcion, condicion, detalle=""):
        self.total += 1
        if not condicion:
            self.fallos += 1
        marca = "OK    " if condicion else "FALLÓ "
        print(f"   [{marca}] {descripcion}" + (f" -> {detalle}" if detalle else ""))
        log.log(20 if condicion else 40, "%s | %s | %s", descripcion, condicion, detalle)

    def rechazo(self, descripcion, funcion, esperado=(ErrorValidacion, s.ReglaNegocio,
                                                      s.NoEncontrado, DuplicateKeyError)):
        """Verifica que una operación INVÁLIDA sea rechazada con el error correcto."""
        try:
            funcion()
        except esperado as e:
            self.paso(descripcion, True, f"{type(e).__name__}: {str(e)[:90]}")
        else:
            self.paso(descripcion, False, "la operación inválida fue aceptada")


def titulo(t):
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


def limpiar(db):
    """Elimina todo rastro del escenario (idempotente)."""
    db.reacciones.delete_many({"_id": {"$regex": "_demo_crud"}})
    db.comentarios.delete_many({"_id": {"$regex": "_demo_crud"}})
    db.campañas.update_many({"publicaciones_asociadas": PUB},
                            {"$pull": {"publicaciones_asociadas": PUB}})
    db.publicaciones.delete_many({"_id": PUB})
    db.usuarios.delete_many({"_id": USER})


def contar(db):
    return {c: db[c].count_documents({}) for c in COLECCIONES}


def escenario(db, r):
    base = contar(db)
    camp_antes = db.campañas.find_one({"_id": CAMPANA})
    print(f"Conteos iniciales: {base}")

    # ------------------------------------------------------------- CREATE
    titulo("1. CREATE · usuario, publicación, reacciones, comentarios y campaña")
    u = s.crear_usuario(db, {"_id": USER, "nombre": "Usuario Demo CRUD",
                             "correo": "demo.crud@duocuc.cl", "pais": "Chile",
                             "genero": "Otro", "dispositivo": "Móvil",
                             "fecha_registro": "2025-07-01T09:00:00"})
    r.paso("Usuario creado (insert_one)", db.usuarios.count_documents({"_id": USER}) == 1, u["_id"])

    p = s.crear_publicacion(db, {"_id": PUB, "usuario_id": USER,
                                 "contenido": "Lanzamos la selección de verano de ContentFlow",
                                 "categoria": "Tecnología", "tipo": "Video",
                                 "hashtags": ["#Azure", "#NoSQL"]})
    r.paso("Publicación creada con fecha en formato del dataset",
           len(p["fecha_publicacion"]) == 19, p["fecha_publicacion"])

    for i, (uid, tipo) in enumerate([("user_1", "Me gusta"), ("user_2", "Me encanta"),
                                     ("user_3", "Me gusta")], start=1):
        s.crear_reaccion(db, {"_id": f"react_{i}_demo_crud", "usuario_id": uid,
                              "publicacion_id": PUB, "tipo_reaccion": tipo})
    r.paso("3 reacciones insertadas",
           db.reacciones.count_documents({"publicacion_id": PUB}) == 3)

    for i, uid in enumerate(["user_4", USER], start=1):
        s.crear_comentario(db, {"_id": f"comm_{i}_demo_crud", "usuario_id": uid,
                                "publicacion_id": PUB, "comentario": f"Comentario demo {i}"})
    r.paso("2 comentarios insertados (likes inicia en 0)",
           db.comentarios.count_documents({"publicacion_id": PUB, "likes": 0}) == 2)

    nueva = s.asociar_publicacion_a_campana(db, CAMPANA, PUB)
    repetida = s.asociar_publicacion_a_campana(db, CAMPANA, PUB)
    r.paso("Asociada a la campaña; repetir no duplica ($addToSet)",
           nueva is True and repetida is False)

    # ------------------------------------------------------------- READ
    titulo("2. READ · lectura puntual, vista combinada y consulta por campaña")
    pub = s.obtener(db, "publicaciones", PUB)
    autor = s.obtener(db, "usuarios", pub["usuario_id"])
    reac = list(db.reacciones.find({"publicacion_id": PUB}, {"tipo_reaccion": 1}))
    coms = db.comentarios.count_documents({"publicacion_id": PUB})
    print(f"   Publicación {pub['_id']} de {autor['nombre']} ({autor['pais']}): "
          f"{len(reac)} reacciones, {coms} comentarios")
    r.paso("find_one por _id devuelve la publicación", pub["categoria"] == "Tecnología")
    r.paso("Vista combinada usuario + publicación + interacciones", len(reac) == 3 and coms == 2)
    en_campana = db.campañas.count_documents({"_id": CAMPANA, "publicaciones_asociadas": PUB})
    r.paso("La campaña referencia la publicación", en_campana == 1)

    # ------------------------------------------------------------- UPDATE
    titulo("3. UPDATE · $set, $inc y cambios en varias colecciones")
    ed = s.actualizar_publicacion(db, PUB, {"contenido": "Selección de verano EDITADA",
                                            "hashtags": ["#Azure", "#NoSQL", "#Verano"]})
    r.paso("update_one + $set sobre publicación",
           ed["contenido"].endswith("EDITADA") and "#Verano" in ed["hashtags"] and "fecha_edicion" in ed)
    r.paso("Los campos inmutables se conservan", ed["usuario_id"] == USER and
           ed["fecha_publicacion"] == p["fecha_publicacion"])
    nuevo_tipo = s.cambiar_reaccion(db, "react_1_demo_crud", "Me encanta")
    r.paso("Reacción cambiada de 'Me gusta' a 'Me encanta'", nuevo_tipo["tipo_reaccion"] == "Me encanta")
    s.dar_like_comentario(db, "comm_1_demo_crud")
    c2 = s.dar_like_comentario(db, "comm_1_demo_crud")
    r.paso("Likes incrementados de forma atómica ($inc): 0 -> 2", c2["likes"] == 2, f"likes={c2['likes']}")
    camp = s.sumar_metricas_campana(db, CAMPANA, likes=3, comentarios=2, compartidos=1)
    r.paso("Métricas de la campaña actualizadas con $inc anidado",
           camp["metricas_objetivo"]["likes"] == camp_antes["metricas_objetivo"]["likes"] + 3)
    us = s.actualizar_usuario(db, USER, {"dispositivo": "Desktop"})
    r.paso("Usuario cambia de dispositivo", us["dispositivo"] == "Desktop")

    # ------------------------------------------------------------- VALIDACIONES
    titulo("4. VALIDACIONES · la base debe rechazar datos inválidos (IE8)")
    r.rechazo("Categoría inexistente", lambda: s.crear_publicacion(
        db, {"usuario_id": USER, "contenido": "x", "categoria": "Cocina", "tipo": "Texto",
             "hashtags": ["#a"]}))
    r.rechazo("Hashtag mal formado y contenido vacío", lambda: s.crear_publicacion(
        db, {"usuario_id": USER, "contenido": "  ", "categoria": "Cultura", "tipo": "Texto",
             "hashtags": ["sin_numeral"]}))
    r.rechazo("Publicación de un usuario inexistente (huérfana)", lambda: s.crear_publicacion(
        db, {"usuario_id": "user_999999", "contenido": "x", "categoria": "Cultura",
             "tipo": "Texto", "hashtags": ["#a"]}))
    r.rechazo("Publicación anterior al registro del usuario", lambda: s.crear_publicacion(
        db, {"usuario_id": USER, "contenido": "x", "categoria": "Cultura", "tipo": "Texto",
             "hashtags": ["#a"], "fecha_publicacion": "2025-01-01T00:00:00"}))
    r.rechazo("Reacción duplicada del mismo usuario", lambda: s.crear_reaccion(
        db, {"usuario_id": "user_1", "publicacion_id": PUB, "tipo_reaccion": "Me enoja"}))
    r.rechazo("Comentario con fecha anterior a la publicación", lambda: s.crear_comentario(
        db, {"usuario_id": "user_4", "publicacion_id": PUB, "comentario": "x",
             "fecha": "2025-01-01T00:00:00"}))
    r.rechazo("Comentario sobre publicación inexistente", lambda: s.crear_comentario(
        db, {"usuario_id": "user_4", "publicacion_id": "pub_inexistente", "comentario": "x"}))
    r.rechazo("Correo ya registrado", lambda: s.crear_usuario(
        db, {"nombre": "Otro", "correo": "demo.crud@duocuc.cl", "pais": "Chile", "genero": "Otro",
             "dispositivo": "Móvil", "fecha_registro": "2025-07-02T09:00:00"}))
    r.rechazo("_id repetido (DuplicateKeyError de la base)", lambda: db.publicaciones.insert_one(
        {"_id": PUB, "usuario_id": USER}))
    r.rechazo("Modificar un campo inmutable", lambda: s.actualizar_publicacion(
        db, PUB, {"usuario_id": "user_1"}))
    r.rechazo("Actualizar un documento que no existe", lambda: s.actualizar_publicacion(
        db, "pub_no_existe", {"contenido": "x"}))
    r.rechazo("Borrar usuario con actividad registrada", lambda: s.eliminar_usuario(db, "user_1"))

    # ------------------------------------------------------------- DELETE
    titulo("5. DELETE · eliminación en cascada sin dejar huérfanos")
    # compensación: revertir las métricas sumadas a la campaña antes de borrar
    s.sumar_metricas_campana(db, CAMPANA, likes=-3, comentarios=-2, compartidos=-1)
    resumen = s.eliminar_publicacion(db, PUB)
    print(f"   Resumen de la cascada: {resumen}")
    r.paso("Publicación, 3 reacciones y 2 comentarios eliminados",
           resumen["publicaciones"] == 1 and resumen["reacciones"] == 3 and resumen["comentarios"] == 2)
    r.paso("La campaña dejó de referenciar la publicación",
           db.campañas.count_documents({"publicaciones_asociadas": PUB}) == 0)
    r.paso("Prueba negativa: find_one ya no encuentra la publicación",
           db.publicaciones.find_one({"_id": PUB}) is None)
    huerfanas = (db.reacciones.count_documents({"publicacion_id": PUB}) +
                 db.comentarios.count_documents({"publicacion_id": PUB}))
    r.paso("Cero reacciones/comentarios huérfanos (sin pérdida de contexto)", huerfanas == 0)
    # el usuario demo comentó su propia publicación; al borrarse en cascada ya no tiene actividad
    r.paso("Usuario demo sin actividad, ahora se puede eliminar", s.eliminar_usuario(db, USER) == 1)
    r.rechazo("Eliminar de nuevo la publicación ya borrada", lambda: s.eliminar_publicacion(db, PUB))

    # ------------------------------------------------------------- VERIFICACIÓN FINAL
    titulo("6. VERIFICACIÓN FINAL · el dataset quedó como al inicio")
    final = contar(db)
    print(f"   Conteos finales:   {final}")
    r.paso("Conteos finales iguales a los iniciales", final == base)
    camp_despues = db.campañas.find_one({"_id": CAMPANA})
    r.paso("Campaña restaurada a su estado original", camp_despues == camp_antes)


def main():
    titulo("CRUD COMPLETO · Escenario: lanzamiento de una publicación en campaña")
    try:
        db = conectar_db()
    except ConexionError as e:
        print(f"[ERROR CRÍTICO] {e}")
        return 1
    r = Reporte()
    try:
        limpiar(db)  # limpieza preventiva por si una ejecución anterior se interrumpió
        escenario(db, r)
    except PyMongoError as e:
        log.exception("error de base de datos durante el CRUD")
        print(f"[ERROR BASE DE DATOS] {e}")
        r.fallos += 1
    except (ErrorValidacion, s.ReglaNegocio, s.NoEncontrado) as e:
        log.exception("fallo inesperado en el flujo válido")
        print(f"[ERROR EN EL FLUJO] {type(e).__name__}: {e}")
        r.fallos += 1
    finally:
        try:
            limpiar(db)
        except PyMongoError as e:
            print(f"[ADVERTENCIA] no se pudo limpiar: {e}")
    titulo(f"RESULTADO: {r.total - r.fallos}/{r.total} verificaciones correctas")
    return 0 if r.fallos == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
