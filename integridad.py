"""Auditoría de integridad y calidad de datos (IE8).

Detecta los problemas típicos de una base NoSQL sin llaves foráneas:
  * huérfanos (pérdida de contexto): reacciones/comentarios/publicaciones/campañas
    que apuntan a documentos que no existen,
  * duplicados: dos reacciones del mismo usuario a la misma publicación, correos repetidos,
  * inconsistencias temporales: actividad anterior al registro del usuario o a la
    publicación comentada/reaccionada, campañas con fin anterior al inicio.

Uso:
    python integridad.py                  # solo informa (no modifica nada)
    python integridad.py --aplicar        # aplica las correcciones seguras
Las correcciones NUNCA borran datos de negocio: los duplicados se eliminan
conservando la reacción más antigua y las inconsistencias temporales se
MARCAN con revision_temporal=true para que un analista las revise.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

from pymongo.errors import PyMongoError

from config import RESULTADOS_DIR, ConexionError, conectar_db, get_logger

log = get_logger("contentflow.integridad")
MUESTRA = 5


def _ids(db, coleccion):
    return {d["_id"] for d in db[coleccion].find({}, {"_id": 1})}


def auditar(db):
    """Devuelve {hallazgo: {"cantidad": n, "ejemplos": [...]}} sin modificar la base."""
    usuarios = {u["_id"]: u for u in db.usuarios.find({}, {"fecha_registro": 1, "correo": 1})}
    pubs = {p["_id"]: p for p in db.publicaciones.find({}, {"usuario_id": 1, "fecha_publicacion": 1})}
    reacs = list(db.reacciones.find({}))
    coms = list(db.comentarios.find({}))
    camps = list(db.campañas.find({}))

    h = {}

    def registrar(nombre, ids):
        h[nombre] = {"cantidad": len(ids), "ejemplos": sorted(ids)[:MUESTRA]}

    # --- huérfanos / pérdida de contexto
    registrar("publicaciones_con_usuario_inexistente",
              [p["_id"] for p in pubs.values() if p["usuario_id"] not in usuarios])
    registrar("reacciones_con_usuario_o_publicacion_inexistente",
              [r["_id"] for r in reacs
               if r["usuario_id"] not in usuarios or r["publicacion_id"] not in pubs])
    registrar("comentarios_con_usuario_o_publicacion_inexistente",
              [c["_id"] for c in coms
               if c["usuario_id"] not in usuarios or c["publicacion_id"] not in pubs])
    registrar("campañas_con_publicaciones_inexistentes",
              [c["_id"] for c in camps
               if any(p not in pubs for p in c.get("publicaciones_asociadas", []))])

    # --- duplicados
    por_par = defaultdict(list)
    for r in reacs:
        por_par[(r["usuario_id"], r["publicacion_id"])].append(r["_id"])
    registrar("reacciones_duplicadas_mismo_usuario_y_publicacion",
              [f"{u}->{p}: {ids}" for (u, p), ids in por_par.items() if len(ids) > 1])
    por_correo = defaultdict(list)
    for u in usuarios.values():
        por_correo[u["correo"].lower()].append(u["_id"])
    registrar("usuarios_con_correo_duplicado",
              [c for c, ids in por_correo.items() if len(ids) > 1])

    # --- inconsistencias temporales
    registrar("publicaciones_anteriores_al_registro_del_usuario",
              [p["_id"] for p in pubs.values()
               if p["usuario_id"] in usuarios
               and p["fecha_publicacion"] < usuarios[p["usuario_id"]]["fecha_registro"]])
    registrar("reacciones_anteriores_a_su_publicacion",
              [r["_id"] for r in reacs
               if r["publicacion_id"] in pubs and r["fecha"] < pubs[r["publicacion_id"]]["fecha_publicacion"]])
    registrar("comentarios_anteriores_a_su_publicacion",
              [c["_id"] for c in coms
               if c["publicacion_id"] in pubs and c["fecha"] < pubs[c["publicacion_id"]]["fecha_publicacion"]])
    registrar("reacciones_anteriores_al_registro_del_usuario",
              [r["_id"] for r in reacs
               if r["usuario_id"] in usuarios and r["fecha"] < usuarios[r["usuario_id"]]["fecha_registro"]])
    registrar("comentarios_anteriores_al_registro_del_usuario",
              [c["_id"] for c in coms
               if c["usuario_id"] in usuarios and c["fecha"] < usuarios[c["usuario_id"]]["fecha_registro"]])
    registrar("campañas_con_fin_anterior_al_inicio",
              [c["_id"] for c in camps if c["fecha_fin"] < c["fecha_inicio"]])
    registrar("comentarios_con_likes_invalidos",
              [c["_id"] for c in coms
               if not isinstance(c.get("likes"), int) or isinstance(c.get("likes"), bool) or c["likes"] < 0])
    log.info("auditoría: %s", {k: v["cantidad"] for k, v in h.items()})
    return h


def corregir_duplicados_reacciones(db):
    """Elimina reacciones repetidas conservando la más antigua. Devuelve cuántas borró."""
    por_par = defaultdict(list)
    for r in db.reacciones.find({}, {"usuario_id": 1, "publicacion_id": 1, "fecha": 1}):
        por_par[(r["usuario_id"], r["publicacion_id"])].append(r)
    borradas = 0
    for reacs in por_par.values():
        if len(reacs) > 1:
            reacs.sort(key=lambda r: (r["fecha"], r["_id"]))
            ids = [r["_id"] for r in reacs[1:]]
            borradas += db.reacciones.delete_many({"_id": {"$in": ids}}).deleted_count
    log.info("duplicados de reacciones eliminados: %s", borradas)
    return borradas


def marcar_inconsistencias_temporales(db):
    """Marca (no borra) documentos con fechas incoherentes para su revisión."""
    marcados = {}
    completos = _ids_temporales(db)
    for coleccion, ids in completos.items():
        if ids:
            res = db[coleccion].update_many({"_id": {"$in": sorted(ids)}},
                                            {"$set": {"revision_temporal": True}})
            marcados[coleccion] = res.modified_count
    log.info("documentos marcados con revision_temporal: %s", marcados)
    return marcados


def _ids_temporales(db):
    usuarios = {u["_id"]: u["fecha_registro"] for u in db.usuarios.find({}, {"fecha_registro": 1})}
    pubs = {p["_id"]: p for p in db.publicaciones.find({}, {"usuario_id": 1, "fecha_publicacion": 1})}
    out = {"publicaciones": set(), "reacciones": set(), "comentarios": set()}
    for p in pubs.values():
        if p["fecha_publicacion"] < usuarios.get(p["usuario_id"], ""):
            out["publicaciones"].add(p["_id"])
    for col, campo in (("reacciones", "fecha"), ("comentarios", "fecha")):
        for d in db[col].find({}, {"usuario_id": 1, "publicacion_id": 1, "fecha": 1}):
            pub = pubs.get(d["publicacion_id"])
            if (pub and d["fecha"] < pub["fecha_publicacion"]) or d["fecha"] < usuarios.get(d["usuario_id"], ""):
                out[col].add(d["_id"])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Auditoría de integridad de ContentFlow")
    ap.add_argument("--aplicar", action="store_true",
                    help="elimina reacciones duplicadas y marca inconsistencias temporales")
    args = ap.parse_args(argv)
    try:
        db = conectar_db()
        print("=" * 70)
        print(" AUDITORÍA DE INTEGRIDAD Y CALIDAD DE DATOS")
        print("=" * 70)
        hallazgos = auditar(db)
        for nombre, info in hallazgos.items():
            estado = "OK " if info["cantidad"] == 0 else "!! "
            print(f"{estado}{nombre:<58} {info['cantidad']:>4}")
            for ej in info["ejemplos"][:3]:
                print(f"      ejemplo: {ej}")
        if args.aplicar:
            print("\n[CORRECCIÓN] Aplicando soluciones seguras...")
            print(f"-> Reacciones duplicadas eliminadas: {corregir_duplicados_reacciones(db)}")
            print(f"-> Documentos marcados revision_temporal=true: "
                  f"{marcar_inconsistencias_temporales(db)}")
            print("\n[VERIFICACIÓN] Re-auditando...")
            despues = auditar(db)
            print(f"-> Duplicados restantes: "
                  f"{despues['reacciones_duplicadas_mismo_usuario_y_publicacion']['cantidad']}")
        os.makedirs(RESULTADOS_DIR, exist_ok=True)
        with open(os.path.join(RESULTADOS_DIR, "auditoria_integridad.json"), "w", encoding="utf-8") as f:
            json.dump(hallazgos, f, ensure_ascii=False, indent=2)
        print("\nReporte guardado en resultados/auditoria_integridad.json")
        return 0
    except ConexionError as e:
        print(f"[ERROR CRÍTICO] {e}")
        return 1
    except PyMongoError as e:
        log.exception("fallo en auditoría")
        print(f"[ERROR BASE DE DATOS] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
