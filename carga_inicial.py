"""Carga inicial de los 5 JSON a Azure Cosmos DB for MongoDB (idempotente).

Uso:
    python carga_inicial.py                 # valida, vacía y carga las 5 colecciones
    python carga_inicial.py --solo-validar  # solo revisa los JSON, no toca la base
    python carga_inicial.py --shard-key     # (opcional) crea colecciones con clave de partición

Mejoras frente a la versión anterior:
  * valida los archivos ANTES de borrar nada (si un JSON está roto no se pierde la colección),
  * ping + timeout de conexión, sin cadena de conexión por defecto en el código,
  * verifica que los documentos contados en la base coincidan con los del archivo,
  * log en logs/contentflow.log.
"""
import argparse
import json
import os
import sys
import time

from pymongo.errors import BulkWriteError, PyMongoError

from config import DATA_DIR, ConexionError, conectar_db, get_logger

log = get_logger("contentflow.carga")

ARCHIVOS = {
    "usuarios.json": "usuarios",
    "publicaciones.json": "publicaciones",
    "reacciones.json": "reacciones",
    "comentarios.json": "comentarios",
    "campañas.json": "campañas",
}

# Clave de partición propuesta por colección (solo se aplica con --shard-key).
# Criterio: alta cardinalidad + presente en las consultas más frecuentes.
SHARD_KEYS = {
    "usuarios": "_id",
    "publicaciones": "usuario_id",
    "reacciones": "publicacion_id",
    "comentarios": "publicacion_id",
    "campañas": "_id",
}


def leer_y_validar(nombre_archivo):
    """Lee un JSON y comprueba que sea una lista de objetos con _id único."""
    ruta = os.path.join(DATA_DIR, nombre_archivo)
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"No se encontró {ruta}")
    with open(ruta, "r", encoding="utf-8") as f:
        datos = json.load(f)
    if not isinstance(datos, list) or not datos:
        raise ValueError(f"{nombre_archivo} debe ser una lista JSON no vacía")
    if not all(isinstance(d, dict) and "_id" in d for d in datos):
        raise ValueError(f"{nombre_archivo}: todos los documentos deben ser objetos con '_id'")
    ids = [d["_id"] for d in datos]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{nombre_archivo}: hay _id repetidos")
    return datos


def crear_coleccion_particionada(db, coleccion):
    """Intenta crear la colección con shard key (comando de Cosmos DB for MongoDB)."""
    clave = SHARD_KEYS[coleccion]
    try:
        db.command({"shardCollection": f"{db.name}.{coleccion}", "key": {clave: "hashed"}})
        print(f"   shard key '{clave}' (hashed) configurada en '{coleccion}'")
        log.info("shard key %s configurada en %s", clave, coleccion)
    except PyMongoError as e:
        print(f"   [AVISO] no se pudo configurar shard key en '{coleccion}': {e}")
        log.warning("shardCollection falló en %s: %s", coleccion, e)


def cargar_datos(shard_key=False):
    inicio = time.perf_counter()
    print("Validando archivos JSON...")
    paquetes = {}
    for archivo, coleccion in ARCHIVOS.items():
        paquetes[coleccion] = leer_y_validar(archivo)
        print(f"  OK {archivo}: {len(paquetes[coleccion])} documentos")

    print("\nConectando a Azure Cosmos DB...")
    db = conectar_db()
    print(f"¡Conexión exitosa! Base de datos: {db.name}")

    resumen = {}
    for coleccion, datos in paquetes.items():
        print(f"\n[{coleccion}]")
        if shard_key:
            # la clave de partición solo puede definirse al crear la colección
            db.drop_collection(coleccion)
            crear_coleccion_particionada(db, coleccion)
        else:
            db[coleccion].delete_many({})  # idempotencia: estado inicial conocido
        try:
            db[coleccion].insert_many(datos, ordered=False)
        except BulkWriteError as e:
            log.error("insert_many parcial en %s: %s", coleccion, e.details.get("writeErrors", [])[:3])
            print(f"   [ERROR] inserción parcial: {len(e.details.get('writeErrors', []))} errores")
        en_base = db[coleccion].count_documents({})
        ok = en_base == len(datos)
        resumen[coleccion] = (len(datos), en_base, ok)
        print(f"-> Insertados {len(datos)} registros en '{coleccion}'. En base: {en_base} "
              f"[{'OK' if ok else 'NO COINCIDE'}]")
        log.info("carga %s: archivo=%s base=%s ok=%s", coleccion, len(datos), en_base, ok)

    total_ok = all(ok for _, _, ok in resumen.values())
    print("\n" + "=" * 60)
    print(f"Total en archivos: {sum(a for a, _, _ in resumen.values())} | "
          f"Total en base: {sum(b for _, b, _ in resumen.values())}")
    print(f"Duración: {time.perf_counter() - inicio:.1f} s")
    print("¡Carga inicial completada con éxito!" if total_ok
          else "[ADVERTENCIA] Hay colecciones con conteos distintos; revisa logs/contentflow.log")
    return total_ok


def main(argv=None):
    ap = argparse.ArgumentParser(description="Carga inicial de ContentFlow")
    ap.add_argument("--solo-validar", action="store_true", help="solo valida los JSON")
    ap.add_argument("--shard-key", action="store_true",
                    help="RECREA las colecciones (drop) definiendo clave de partición; experimental, verificar en Data Explorer")
    args = ap.parse_args(argv)
    try:
        if args.solo_validar:
            for archivo in ARCHIVOS:
                print(f"OK {archivo}: {len(leer_y_validar(archivo))} documentos válidos")
            return 0
        return 0 if cargar_datos(args.shard_key) else 2
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        log.error("archivo inválido: %s", e)
        print(f"[ERROR EN ARCHIVOS] {e}")
        return 1
    except ConexionError as e:
        print(f"[ERROR CRÍTICO] {e}")
        return 1
    except PyMongoError as e:
        log.exception("error de base de datos en la carga")
        print(f"[ERROR BASE DE DATOS] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
