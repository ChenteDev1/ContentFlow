"""Evaluación de eficiencia y mejoras con índices (IE6).

Mide, para cada consulta, ANTES y DESPUÉS de aplicar una mejora:
tiempo (mediana), volumen devuelto (bytes) y costo en RU (Cosmos DB).

Experimentos
  E1  Proyección: traer solo los campos necesarios vs. documento completo (volumen)
  E2  batch_size: pocos viajes de red vs. el tamaño de lote por defecto (101 docs)
  E3  Índice compuesto {dispositivo, genero} para el filtro de la consulta 1
  E4  Ordenar en servidor: sin índice (Cosmos lo rechaza) vs. índice {categoria, fecha_publicacion}
  E5  Índice compuesto para filtro + orden de campañas (consulta 3)

Uso:  python optimizacion_indices.py [--limpiar]
      --limpiar  elimina los índices creados al terminar (por defecto se conservan)
"""
import argparse
import json
import os
import sys

from pymongo.errors import PyMongoError

from config import RESULTADOS_DIR, ConexionError, conectar_db, get_logger
from metricas import medir_consulta

log = get_logger("contentflow.optimizacion")

INDICES = {
    "idx_usuarios_dispositivo_genero": ("usuarios", [("dispositivo", 1), ("genero", 1)]),
    "idx_publicaciones_categoria_fecha": ("publicaciones", [("categoria", 1), ("fecha_publicacion", -1)]),
    "idx_campanas_objetivo_likes": ("campañas", [("objetivo", 1), ("metricas_objetivo.likes", -1)]),
}


def _soltar_indices(db):
    for nombre, (col, _) in INDICES.items():
        try:
            db[col].drop_index(nombre)
        except PyMongoError:
            pass  # no existía


def _crear_indice(db, nombre):
    col, claves = INDICES[nombre]
    try:
        db[col].create_index(claves, name=nombre)
        return None
    except PyMongoError as e:
        log.warning("no se pudo crear %s: %s", nombre, e)
        return str(e)[:200]


def _fmt(m):
    if "error" in m:
        return f"RECHAZADA por el servidor: {m['error'][:90]}"
    ru = f"{m['ru']} RU" if m["ru"] is not None else "RU n/d"
    return (f"{m['ms_mediana']:>8} ms | {m['bytes']:>9,} B | {m['documentos']:>3} docs | {ru}"
            .replace(",", "."))


def _par(titulo, antes_txt, antes, despues_txt, despues):
    print(f"\n{titulo}")
    print(f"  ANTES   ({antes_txt}): {_fmt(antes)}")
    print(f"  DESPUÉS ({despues_txt}): {_fmt(despues)}")
    mejora = None
    if "error" not in antes and "error" not in despues and antes["ms_mediana"] > 0:
        mejora = round(100 * (antes["ms_mediana"] - despues["ms_mediana"]) / antes["ms_mediana"], 1)
        print(f"  Variación de tiempo: {mejora:+}%   "
              f"Variación de volumen: {despues['bytes'] - antes['bytes']:+,} B".replace(",", "."))
    return {"titulo": titulo, "antes": {"descripcion": antes_txt, **antes},
            "despues": {"descripcion": despues_txt, **despues}, "mejora_tiempo_pct": mejora}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Optimización con índices")
    ap.add_argument("--limpiar", action="store_true")
    args = ap.parse_args(argv)
    try:
        db = conectar_db()
    except ConexionError as e:
        print(f"[ERROR CRÍTICO] {e}")
        return 1

    resultados = []
    try:
        print("=" * 78)
        print(" EVALUACIÓN DE EFICIENCIA: tiempo (mediana de 5) | volumen | documentos | RU")
        print("=" * 78)
        _soltar_indices(db)  # parte de una línea base sin índices propios

        # E1 proyección
        f1 = {"dispositivo": "Desktop", "genero": "Masculino"}
        completo = medir_consulta(db, "usuarios", f1)
        proy = medir_consulta(db, "usuarios", f1, {"_id": 0, "nombre": 1, "correo": 1, "pais": 1})
        resultados.append(_par("E1 · Proyección (consulta 1)", "documento completo", completo,
                               "solo nombre, correo, país", proy))

        # E2 batch_size
        f3 = {}
        base = medir_consulta(db, "campañas", f3, {"_id": 0, "nombre": 1, "objetivo": 1})
        lote = medir_consulta(db, "campañas", f3, {"_id": 0, "nombre": 1, "objetivo": 1}, batch_size=500)
        resultados.append(_par("E2 · Tamaño de lote al leer 500 campañas", "lote por defecto (101)", base,
                               "batch_size=500", lote))

        # E3 índice para filtro
        sin = medir_consulta(db, "usuarios", f1, {"_id": 0, "nombre": 1, "correo": 1, "pais": 1})
        err = _crear_indice(db, "idx_usuarios_dispositivo_genero")
        con = medir_consulta(db, "usuarios", f1, {"_id": 0, "nombre": 1, "correo": 1, "pais": 1}) \
            if not err else {"error": err}
        resultados.append(_par("E3 · Índice compuesto para el filtro de la consulta 1",
                               "sin índice (recorre la colección)", sin,
                               "índice {dispositivo, genero}", con))

        # E4 ordenar en servidor
        f2 = {"categoria": "Deportes"}
        p2 = {"_id": 0, "usuario_id": 1, "tipo": 1, "fecha_publicacion": 1}
        orden = [("fecha_publicacion", -1)]
        sin_idx = medir_consulta(db, "publicaciones", f2, p2, orden)
        if "error" in sin_idx:  # respaldo: ordenar en Python (lo que hacía la versión anterior)
            sin_idx = {**medir_consulta(db, "publicaciones", f2, p2, orden_en_memoria=orden),
                       "nota": "el servidor rechazó el orden; se midió el respaldo en memoria",
                       "rechazo_servidor": sin_idx["error"]}
            antes_txt = "orden en memoria (el servidor rechaza ordenar sin índice)"
        else:
            antes_txt = "orden en servidor sin índice"
        err = _crear_indice(db, "idx_publicaciones_categoria_fecha")
        con_idx = medir_consulta(db, "publicaciones", f2, p2, orden) if not err else {"error": err}
        resultados.append(_par("E4 · Ordenamiento en servidor (consulta 2)", antes_txt, sin_idx,
                               "índice {categoria, fecha_publicacion desc}", con_idx))

        # E5 campañas filtro + orden
        f5 = {"objetivo": "Aumentar engagement", "metricas_objetivo.likes": {"$gte": 500}}
        p5 = {"_id": 0, "nombre": 1, "metricas_objetivo": 1}
        o5 = [("metricas_objetivo.likes", -1)]
        antes5 = medir_consulta(db, "campañas", f5, p5, o5)
        if "error" in antes5:
            antes5 = {**medir_consulta(db, "campañas", f5, p5, orden_en_memoria=o5),
                      "rechazo_servidor": antes5["error"]}
            antes5_txt = "orden en memoria (servidor rechaza sin índice)"
        else:
            antes5_txt = "orden en servidor sin índice"
        err = _crear_indice(db, "idx_campanas_objetivo_likes")
        despues5 = medir_consulta(db, "campañas", f5, p5, o5) if not err else {"error": err}
        resultados.append(_par("E5 · Filtro + orden en campañas (consulta 3)", antes5_txt, antes5,
                               "índice {objetivo, metricas_objetivo.likes desc}", despues5))

        os.makedirs(RESULTADOS_DIR, exist_ok=True)
        with open(os.path.join(RESULTADOS_DIR, "optimizacion_indices.json"), "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=2)
        print("\nResultados guardados en resultados/optimizacion_indices.json")
        print("Índices activos:", {c: [i["name"] for i in db[c].list_indexes()]
                                    for c in ("usuarios", "publicaciones", "campañas")})
        log.info("optimización completada: %s", [(r["titulo"], r["mejora_tiempo_pct"]) for r in resultados])
    except PyMongoError as e:
        log.exception("fallo en optimización")
        print(f"[ERROR BASE DE DATOS] {e}")
        return 1
    finally:
        if args.limpiar:
            _soltar_indices(db)
            print("Índices experimentales eliminados (--limpiar).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
