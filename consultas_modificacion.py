"""Consultas de MODIFICACIÓN de ContentFlow (IE4, IE5, IE7).

Cada modificación: (1) cuenta lo que va a tocar, (2) la ejecuta, (3) verifica el
resultado y (4) por defecto la REVIERTE para dejar el dataset como estaba
(use --conservar para dejar los cambios).

  M1  update_many  Marca campañas de engagement con meta alta como "Destacada" ($set)
  M2  update_many  Agrega el hashtag #VeranoDeportivo a videos de Deportes de julio ($addToSet)
  M3  update_one   Suma 1 like a un comentario de forma atómica ($inc)
  M4  update_one   Cierra una campaña: ajusta fecha_fin y suma compartidos (varios operadores)

Uso:  python consultas_modificacion.py [--conservar]
"""
import argparse
import sys

from pymongo.errors import PyMongoError

from config import ConexionError, conectar_db, get_logger

log = get_logger("contentflow.modificacion")


def _titulo(texto):
    print("\n" + "=" * 70)
    print(texto)
    print("=" * 70)


def m1_destacar_campanas(db, revertir):
    _titulo("M1 · update_many + $set: campañas 'Destacadas'")
    filtro = {"objetivo": "Aumentar engagement", "metricas_objetivo.likes": {"$gte": 900}}
    db.campañas.update_many({"estado": "Destacada"}, {"$unset": {"estado": ""}})  # estado limpio
    previstas = db.campañas.count_documents(filtro)
    res = db.campañas.update_many(filtro, {"$set": {"estado": "Destacada"}})
    verificadas = db.campañas.count_documents({"estado": "Destacada"})
    print(f"Coinciden con el filtro: {previstas} | matched={res.matched_count} "
          f"modified={res.modified_count} | verificadas en base: {verificadas}")
    ok = previstas == res.matched_count == res.modified_count == verificadas
    if revertir:
        r = db.campañas.update_many({"estado": "Destacada"}, {"$unset": {"estado": ""}})
        print(f"Reversión ($unset): {r.modified_count} documentos restaurados")
    return ok


def m2_hashtag_verano(db, revertir):
    _titulo("M2 · update_many + $addToSet: hashtag de temporada")
    etiqueta = "#VeranoDeportivo"
    filtro = {"categoria": "Deportes", "tipo": "Video",
              "fecha_publicacion": {"$gte": "2025-06-15T00:00:00"}}
    previstas = db.publicaciones.count_documents(filtro)
    res = db.publicaciones.update_many(filtro, {"$addToSet": {"hashtags": etiqueta}})
    # Idempotencia: repetir no duplica el hashtag
    repetido = db.publicaciones.update_many(filtro, {"$addToSet": {"hashtags": etiqueta}})
    con_etiqueta = db.publicaciones.count_documents({"hashtags": etiqueta})
    print(f"Coinciden: {previstas} | modificadas: {res.modified_count} | "
          f"segunda ejecución modificó: {repetido.modified_count} (debe ser 0) | "
          f"con el hashtag: {con_etiqueta}")
    ok = previstas == res.modified_count == con_etiqueta and repetido.modified_count == 0
    if revertir:
        r = db.publicaciones.update_many({"hashtags": etiqueta}, {"$pull": {"hashtags": etiqueta}})
        print(f"Reversión ($pull): {r.modified_count} documentos restaurados")
    return ok


def m3_like_atomico(db, revertir):
    _titulo("M3 · update_one + $inc: like atómico en un comentario")
    antes = db.comentarios.find_one({"_id": "comm_1"}, {"likes": 1})
    if antes is None:
        print("[AVISO] comm_1 no existe; se omite")
        return False
    res = db.comentarios.update_one({"_id": "comm_1"}, {"$inc": {"likes": 1}})
    despues = db.comentarios.find_one({"_id": "comm_1"}, {"likes": 1})
    print(f"likes antes={antes['likes']} después={despues['likes']} (matched={res.matched_count})")
    ok = despues["likes"] == antes["likes"] + 1
    if revertir:
        db.comentarios.update_one({"_id": "comm_1"}, {"$inc": {"likes": -1}})
        print("Reversión ($inc -1): "
              f"likes={db.comentarios.find_one({'_id': 'comm_1'}, {'likes': 1})['likes']}")
    return ok


def m4_cerrar_campana(db, revertir):
    _titulo("M4 · update_one con $set + $inc: cierre de campaña")
    original = db.campañas.find_one({"_id": "camp_1"})
    if original is None:
        print("[AVISO] camp_1 no existe; se omite")
        return False
    res = db.campañas.update_one(
        {"_id": "camp_1"},
        {"$set": {"estado": "Cerrada", "fecha_fin": "2025-06-01T00:00:00"},
         "$inc": {"metricas_objetivo.compartidos": 25}})
    nuevo = db.campañas.find_one({"_id": "camp_1"})
    print(f"modified={res.modified_count} | estado={nuevo.get('estado')} | "
          f"compartidos {original['metricas_objetivo']['compartidos']} -> "
          f"{nuevo['metricas_objetivo']['compartidos']}")
    ok = (nuevo["estado"] == "Cerrada" and
          nuevo["metricas_objetivo"]["compartidos"] == original["metricas_objetivo"]["compartidos"] + 25)
    if revertir:
        db.campañas.replace_one({"_id": "camp_1"}, original)
        print(f"Reversión (replace_one con copia original): estado="
              f"{db.campañas.find_one({'_id': 'camp_1'}).get('estado')}")
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description="Consultas de modificación de ContentFlow")
    ap.add_argument("--conservar", action="store_true", help="no revertir los cambios")
    args = ap.parse_args(argv)
    try:
        db = conectar_db()
        resultados = {}
        for nombre, fn in (("M1", m1_destacar_campanas), ("M2", m2_hashtag_verano),
                           ("M3", m3_like_atomico), ("M4", m4_cerrar_campana)):
            try:
                resultados[nombre] = fn(db, not args.conservar)
            except PyMongoError as e:
                log.exception("%s falló", nombre)
                print(f"[ERROR BASE DE DATOS] {nombre}: {e}")
                resultados[nombre] = False
        print("\n" + "=" * 70)
        for k, v in resultados.items():
            print(f"{k}: {'OK' if v else 'FALLÓ'}")
        log.info("modificaciones: %s", resultados)
        return 0 if all(resultados.values()) else 2
    except ConexionError as e:
        print(f"[ERROR CRÍTICO] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
