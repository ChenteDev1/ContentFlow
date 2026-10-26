import pytest
from pymongo.errors import DuplicateKeyError

import operaciones_crud
import servicios as s
from validaciones import ErrorValidacion


def test_escenario_crud_completo_pasa_y_no_deja_rastro(db):
    antes = operaciones_crud.contar(db)
    assert operaciones_crud.main() == 0
    assert operaciones_crud.contar(db) == antes


def test_el_escenario_es_repetible(db):
    assert operaciones_crud.main() == 0
    assert operaciones_crud.main() == 0


def nueva_pub(db, **extra):
    d = {"usuario_id": "user_1", "contenido": "x", "categoria": "Cultura", "tipo": "Texto",
         "hashtags": ["#a"], "fecha_publicacion": "2026-01-01T00:00:00"}
    d.update(extra)
    return s.crear_publicacion(db, d)


def test_publicacion_huerfana_rechazada(db):
    with pytest.raises(s.ReglaNegocio):
        nueva_pub(db, usuario_id="user_9999")
    assert db.publicaciones.count_documents({}) == 500


def test_reaccion_duplicada_rechazada(db):
    p = nueva_pub(db)
    s.crear_reaccion(db, {"usuario_id": "user_2", "publicacion_id": p["_id"], "tipo_reaccion": "Me gusta"})
    with pytest.raises(s.ReglaNegocio):
        s.crear_reaccion(db, {"usuario_id": "user_2", "publicacion_id": p["_id"], "tipo_reaccion": "Me enoja"})


def test_eliminar_en_cascada_sin_huerfanos(db):
    p = nueva_pub(db)
    s.crear_reaccion(db, {"usuario_id": "user_2", "publicacion_id": p["_id"], "tipo_reaccion": "Me gusta"})
    s.crear_comentario(db, {"usuario_id": "user_2", "publicacion_id": p["_id"], "comentario": "hola"})
    s.asociar_publicacion_a_campana(db, "camp_5", p["_id"])
    r = s.eliminar_publicacion(db, p["_id"])
    assert r["reacciones"] == 1 and r["comentarios"] == 1 and r["campañas_actualizadas"] == 1
    assert db.reacciones.count_documents({"publicacion_id": p["_id"]}) == 0
    assert p["_id"] not in db.campañas.find_one({"_id": "camp_5"})["publicaciones_asociadas"]


def test_campos_inmutables(db):
    with pytest.raises(ErrorValidacion):
        s.actualizar_publicacion(db, "pub_1", {"fecha_publicacion": "2026-01-01T00:00:00"})


def test_id_duplicado_lo_rechaza_la_base(db):
    with pytest.raises(DuplicateKeyError):
        s.crear_publicacion(db, {"_id": "pub_1", "usuario_id": "user_1", "contenido": "x",
                                 "categoria": "Cultura", "tipo": "Texto", "hashtags": ["#a"],
                                 "fecha_publicacion": "2026-01-01T00:00:00"})


def test_buscar_cae_a_memoria_si_el_servidor_rechaza_el_orden(db, monkeypatch):
    """Simula el comportamiento de Cosmos DB: ordenar sin índice lanza OperationFailure."""
    from pymongo.errors import OperationFailure

    class SinIndice:
        name = "publicaciones"

        def find(self, filtro, proy=None):
            return Cursor(db.publicaciones.find(filtro, proy))

    class Cursor:
        def __init__(self, c):
            self.c = c

        def sort(self, *a, **k):
            raise OperationFailure("The index path corresponding to the specified order-by item is excluded.")

        def __iter__(self):
            return iter(self.c)

    docs, donde = s.buscar(SinIndice(), {"categoria": "Deportes"}, None, [("fecha_publicacion", -1)])
    assert donde.startswith("memoria") and len(docs) == 100
    fechas = [d["fecha_publicacion"] for d in docs]
    assert fechas == sorted(fechas, reverse=True)
