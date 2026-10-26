"""Las consultas deben reproducir los conteos que ya se observaron en Azure (capturas)."""
import consultas_negocio as cn
import consultas_modificacion as cm
import analitica_negocio as an
from servicios import buscar


def correr(db, n):
    c = cn.CONSULTAS[n]
    docs, _ = buscar(db[c["coleccion"]], c["filtro"], c["proyeccion"], c["orden"], c.get("limite", 0))
    return docs


def test_consulta1_58_usuarios_ordenados(db):
    docs = correr(db, 1)
    assert len(docs) == 58
    nombres = [d["nombre"] for d in docs]
    assert nombres == sorted(nombres)
    assert "_id" not in docs[0]  # la proyección excluye _id


def test_consulta2_100_publicaciones_mas_reciente_primero(db):
    docs = correr(db, 2)
    assert len(docs) == 100
    fechas = [d["fecha_publicacion"] for d in docs]
    assert fechas == sorted(fechas, reverse=True)


def test_consulta3_filtra_de_verdad(db):
    docs = correr(db, 3)
    assert 0 < len(docs) < 500  # antes devolvía las 500 campañas
    assert all(d["metricas_objetivo"]["likes"] >= 500 for d in docs)
    assert all(d["objetivo"] != "Captar nuevos usuarios" for d in docs)
    likes = [d["metricas_objetivo"]["likes"] for d in docs]
    assert likes == sorted(likes, reverse=True)


def test_consulta4_y_5(db):
    assert len(correr(db, 4)) > 0
    top = correr(db, 5)
    assert len(top) == 10 and all(d["likes"] >= 90 for d in top)


def test_modificaciones_se_verifican_y_revierten(db):
    antes = db.campañas.find_one({"_id": "camp_1"})
    for fn in (cm.m1_destacar_campanas, cm.m2_hashtag_verano, cm.m3_like_atomico, cm.m4_cerrar_campana):
        assert fn(db, True) is True
    assert db.campañas.find_one({"_id": "camp_1"}) == antes
    assert db.campañas.count_documents({"estado": {"$exists": True}}) == 0


def test_analitica(db):
    activos = an.usuarios_mas_activos(db, 5)
    assert len(activos) == 5
    assert activos[0]["indice_actividad"] >= activos[-1]["indice_actividad"]
    assert len(an.contenido_popular(db)) == 10
    horas = an.horarios_publicacion(db)
    assert sum(h["publicaciones"] for h in horas) == 500
    assert sum(f["publicaciones"] for f in an.franjas_horarias(horas)) == 500
    por_obj, mejores, todas = an.impacto_campanas(db)
    assert sum(o["campañas"] for o in por_obj) == 500 and len(todas) == 500
