"""Analítica del caso ContentFlow (IE4, IE5): responde las 3 preguntas de la gerencia.

  1. ¿Quiénes son los usuarios más activos?
  2. ¿Cuáles son los contenidos más populares (y a qué hora conviene publicar)?
  3. ¿Qué impacto tienen las campañas?

Usa pipelines de agregación ($group, $sum, $avg, $sort, $limit, $substr) que
Cosmos DB for MongoDB soporta. Los "joins" entre colecciones se hacen en la
aplicación con consultas $in (más simple y predecible en RU que $lookup).
Cada función devuelve listas de dicts (las reutiliza la API); con --exportar
se generan CSV en exportes/ listos para Power BI.

Uso:  python analitica_negocio.py [--exportar]
"""
import argparse
import os
import sys

from pymongo.errors import OperationFailure, PyMongoError

from config import EXPORT_DIR, ConexionError, conectar_db, get_logger

log = get_logger("contentflow.analitica")

# Ponderación del índice de actividad: publicar pesa más que comentar y comentar más que reaccionar
PESOS_ACTIVIDAD = {"publicaciones": 3, "comentarios": 2, "reacciones": 1}


def _contar_por(db, coleccion, campo):
    """{valor_del_campo: cantidad} usando $group en el servidor."""
    filas = db[coleccion].aggregate([{"$group": {"_id": f"${campo}", "n": {"$sum": 1}}}])
    return {f["_id"]: f["n"] for f in filas}


# ------------------------------------------------------------ 1. usuarios activos
def usuarios_mas_activos(db, top=10):
    conteos = {col: _contar_por(db, col, "usuario_id") for col in PESOS_ACTIVIDAD}
    ids = set().union(*[set(c) for c in conteos.values()])
    filas = []
    for uid in ids:
        fila = {"usuario_id": uid}
        fila.update({col: conteos[col].get(uid, 0) for col in PESOS_ACTIVIDAD})
        fila["indice_actividad"] = sum(fila[col] * p for col, p in PESOS_ACTIVIDAD.items())
        filas.append(fila)
    filas.sort(key=lambda f: (-f["indice_actividad"], f["usuario_id"]))
    filas = filas[:top]
    info = {u["_id"]: u for u in db.usuarios.find(
        {"_id": {"$in": [f["usuario_id"] for f in filas]}},
        {"nombre": 1, "pais": 1, "dispositivo": 1})}
    for f in filas:
        u = info.get(f["usuario_id"], {})
        f.update(nombre=u.get("nombre"), pais=u.get("pais"), dispositivo=u.get("dispositivo"))
    return filas


# ------------------------------------------------------------ 2. contenido popular
def _interacciones_por_publicacion(db):
    reac = _contar_por(db, "reacciones", "publicacion_id")
    com = {}
    for f in db.comentarios.aggregate([{"$group": {"_id": "$publicacion_id", "n": {"$sum": 1},
                                                    "likes": {"$sum": "$likes"}}}]):
        com[f["_id"]] = (f["n"], f["likes"])
    return reac, com


def contenido_popular(db, top=10):
    reac, com = _interacciones_por_publicacion(db)
    filas = []
    for pid in set(reac) | set(com):
        n_com, likes_com = com.get(pid, (0, 0))
        filas.append({"publicacion_id": pid, "reacciones": reac.get(pid, 0),
                      "comentarios": n_com, "likes_en_comentarios": likes_com,
                      "interacciones": reac.get(pid, 0) + n_com})
    filas.sort(key=lambda f: (-f["interacciones"], -f["likes_en_comentarios"], f["publicacion_id"]))
    filas = filas[:top]
    info = {p["_id"]: p for p in db.publicaciones.find(
        {"_id": {"$in": [f["publicacion_id"] for f in filas]}},
        {"categoria": 1, "tipo": 1, "usuario_id": 1, "fecha_publicacion": 1})}
    for f in filas:
        p = info.get(f["publicacion_id"], {})
        f.update(categoria=p.get("categoria"), tipo=p.get("tipo"), autor=p.get("usuario_id"))
    return filas


def popularidad_por_categoria(db):
    """Interacciones por categoría y promedio por publicación."""
    reac, com = _interacciones_por_publicacion(db)
    cat_de = {p["_id"]: p["categoria"] for p in db.publicaciones.find({}, {"categoria": 1})}
    total_pubs = _contar_por(db, "publicaciones", "categoria")
    acum = {c: 0 for c in total_pubs}
    for pid, cat in cat_de.items():
        acum[cat] += reac.get(pid, 0) + com.get(pid, (0, 0))[0]
    filas = [{"categoria": c, "publicaciones": total_pubs[c], "interacciones": acum[c],
              "promedio_por_publicacion": round(acum[c] / total_pubs[c], 2)} for c in total_pubs]
    return sorted(filas, key=lambda f: -f["promedio_por_publicacion"])


def reacciones_por_tipo(db):
    c = _contar_por(db, "reacciones", "tipo_reaccion")
    return sorted(({"tipo_reaccion": k, "cantidad": v} for k, v in c.items()),
                  key=lambda f: -f["cantidad"])


# ------------------------------------------------------------ horarios
def horarios_publicacion(db):
    """Publicaciones e interacciones recibidas según la hora de publicación (00-23)."""
    try:
        por_hora = {f["_id"]: f["n"] for f in db.publicaciones.aggregate(
            [{"$group": {"_id": {"$substr": ["$fecha_publicacion", 11, 2]}, "n": {"$sum": 1}}}])}
        metodo = "servidor ($substr)"
    except OperationFailure as e:
        log.warning("$substr no disponible, se calcula la hora en la aplicación: %s", e)
        por_hora = {}
        for p in db.publicaciones.find({}, {"fecha_publicacion": 1}):
            h = p["fecha_publicacion"][11:13]
            por_hora[h] = por_hora.get(h, 0) + 1
        metodo = "aplicación"
    reac, com = _interacciones_por_publicacion(db)
    inter_hora = {}
    for p in db.publicaciones.find({}, {"fecha_publicacion": 1}):
        h = p["fecha_publicacion"][11:13]
        inter_hora[h] = inter_hora.get(h, 0) + reac.get(p["_id"], 0) + com.get(p["_id"], (0, 0))[0]
    filas = [{"hora": h, "publicaciones": n, "interacciones": inter_hora.get(h, 0),
              "interacciones_por_publicacion": round(inter_hora.get(h, 0) / n, 2)}
             for h, n in sorted(por_hora.items())]
    log.info("horarios calculados vía %s", metodo)
    return filas


def franjas_horarias(filas_hora):
    franjas = {"Madrugada (00-05)": range(0, 6), "Mañana (06-11)": range(6, 12),
               "Tarde (12-17)": range(12, 18), "Noche (18-23)": range(18, 24)}
    salida = []
    for nombre, rango in franjas.items():
        sel = [f for f in filas_hora if int(f["hora"]) in rango]
        pubs = sum(f["publicaciones"] for f in sel)
        inter = sum(f["interacciones"] for f in sel)
        salida.append({"franja": nombre, "publicaciones": pubs, "interacciones": inter,
                       "interacciones_por_publicacion": round(inter / pubs, 2) if pubs else 0})
    return sorted(salida, key=lambda f: -f["interacciones_por_publicacion"])


# ------------------------------------------------------------ 3. campañas
def impacto_campanas(db, top=10):
    """Metas por objetivo y engagement REAL observado en las publicaciones asociadas."""
    por_objetivo = [
        {"objetivo": f["_id"], "campañas": f["n"],
         "meta_likes_prom": round(f["likes"], 1), "meta_comentarios_prom": round(f["coms"], 1),
         "meta_compartidos_prom": round(f["comp"], 1)}
        for f in db.campañas.aggregate([{"$group": {
            "_id": "$objetivo", "n": {"$sum": 1},
            "likes": {"$avg": "$metricas_objetivo.likes"},
            "coms": {"$avg": "$metricas_objetivo.comentarios"},
            "comp": {"$avg": "$metricas_objetivo.compartidos"}}}, {"$sort": {"_id": 1}}])]
    reac, com = _interacciones_por_publicacion(db)
    detalle = []
    for c in db.campañas.find({}, {"nombre": 1, "objetivo": 1, "publicaciones_asociadas": 1,
                                    "metricas_objetivo": 1}):
        pubs = c.get("publicaciones_asociadas", [])
        inter = sum(reac.get(p, 0) + com.get(p, (0, 0))[0] for p in pubs)
        meta = c["metricas_objetivo"]["likes"] + c["metricas_objetivo"]["comentarios"]
        detalle.append({"campaña": c["_id"], "nombre": c["nombre"], "objetivo": c["objetivo"],
                        "publicaciones": len(pubs), "interacciones_observadas": inter,
                        "meta_likes_mas_comentarios": meta,
                        "cumplimiento_pct": round(100 * inter / meta, 2) if meta else 0})
    detalle.sort(key=lambda f: (-f["interacciones_observadas"], f["campaña"]))
    return por_objetivo, detalle[:top], detalle


# ------------------------------------------------------------ audiencia
def perfil_audiencia(db, top_paises=8):
    """Perfil de la audiencia: dispositivo, género y países con más usuarios."""
    def agrupar(campo, limite=0):
        filas = [{campo: f["_id"], "usuarios": f["n"]} for f in db.usuarios.aggregate(
            [{"$group": {"_id": f"${campo}", "n": {"$sum": 1}}}])]
        filas.sort(key=lambda f: (-f["usuarios"], str(f[campo])))
        return filas[:limite] if limite else filas
    return {"dispositivo": agrupar("dispositivo"), "genero": agrupar("genero"),
            "paises": agrupar("pais", top_paises)}


# ------------------------------------------------------------ presentación
def _tabla(titulo, filas, columnas):
    print("\n" + "=" * 78)
    print(titulo)
    print("=" * 78)
    if not filas:
        print("(sin datos)")
        return
    print(" | ".join(f"{c}" for c in columnas))
    print("-" * 78)
    for f in filas:
        print(" | ".join(str(f.get(c, "")) for c in columnas))


def exportar_csv(nombre, filas):
    import pandas as pd  # pandas se usa solo para exportar a Power BI
    os.makedirs(EXPORT_DIR, exist_ok=True)
    ruta = os.path.join(EXPORT_DIR, f"{nombre}.csv")
    pd.DataFrame(filas).to_csv(ruta, index=False, encoding="utf-8-sig")
    return ruta


def main(argv=None):
    ap = argparse.ArgumentParser(description="Analítica de negocio de ContentFlow")
    ap.add_argument("--exportar", action="store_true", help="genera CSV en exportes/ para Power BI")
    args = ap.parse_args(argv)
    try:
        db = conectar_db()
        activos = usuarios_mas_activos(db)
        _tabla("1) USUARIOS MÁS ACTIVOS (índice = 3·publicaciones + 2·comentarios + 1·reacciones)",
               activos, ["usuario_id", "nombre", "pais", "publicaciones", "comentarios",
                         "reacciones", "indice_actividad"])
        popular = contenido_popular(db)
        _tabla("2a) CONTENIDOS MÁS POPULARES (reacciones + comentarios)", popular,
               ["publicacion_id", "categoria", "tipo", "reacciones", "comentarios",
                "likes_en_comentarios", "interacciones"])
        cats = popularidad_por_categoria(db)
        _tabla("2b) POPULARIDAD POR CATEGORÍA", cats,
               ["categoria", "publicaciones", "interacciones", "promedio_por_publicacion"])
        tipos = reacciones_por_tipo(db)
        _tabla("2c) REACCIONES POR TIPO", tipos, ["tipo_reaccion", "cantidad"])
        horas = horarios_publicacion(db)
        franjas = franjas_horarias(horas)
        _tabla("2d) HORARIOS: INTERACCIONES POR PUBLICACIÓN SEGÚN FRANJA", franjas,
               ["franja", "publicaciones", "interacciones", "interacciones_por_publicacion"])
        por_obj, top_camp, todas = impacto_campanas(db)
        _tabla("3a) CAMPAÑAS: METAS PROMEDIO POR OBJETIVO", por_obj,
               ["objetivo", "campañas", "meta_likes_prom", "meta_comentarios_prom",
                "meta_compartidos_prom"])
        _tabla("3b) CAMPAÑAS CON MÁS INTERACCIONES OBSERVADAS (Top 10)", top_camp,
               ["campaña", "nombre", "objetivo", "publicaciones", "interacciones_observadas",
                "meta_likes_mas_comentarios", "cumplimiento_pct"])
        if args.exportar:
            print("\nExportando CSV para Power BI...")
            for nombre, filas in {"usuarios_activos": activos, "contenido_popular": popular,
                                  "popularidad_categoria": cats, "reacciones_tipo": tipos,
                                  "horarios_hora": horas, "horarios_franja": franjas,
                                  "campanas_objetivo": por_obj, "campanas_detalle": todas}.items():
                print("->", exportar_csv(nombre, filas))
        return 0
    except ConexionError as e:
        print(f"[ERROR CRÍTICO] {e}")
        return 1
    except PyMongoError as e:
        log.exception("fallo en analítica")
        print(f"[ERROR BASE DE DATOS] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
