"""Medición de eficiencia de consultas (IE6): tiempo, volumen devuelto y costo en RU.

* tiempo: mediana de N repeticiones (tras una ejecución de calentamiento) con
  time.perf_counter(). Una sola medición es poco confiable: incluye resolución
  de conexión, red variable, etc.
* volumen: bytes BSON de los documentos devueltos (aprox. de lo que viaja por red).
* RU: comando propio de Cosmos DB `getLastRequestStatistics` (None si no existe,
  p. ej. en MongoDB local o en las pruebas con mongomock).
"""
import statistics
import time

import bson
from pymongo.errors import PyMongoError


def ru_ultima_operacion(db):
    """Request Units de la última operación de esta conexión (solo Cosmos DB)."""
    try:
        r = db.command({"getLastRequestStatistics": 1})
        ru = r.get("RequestCharge")
        return round(float(ru), 2) if ru is not None else None
    except (PyMongoError, NotImplementedError, TypeError, ValueError):
        return None


def _valor(doc, campo):
    for parte in campo.split("."):
        doc = doc.get(parte, "") if isinstance(doc, dict) else ""
    return doc


def tamano_bytes(documentos):
    return sum(len(bson.encode(d)) for d in documentos)


def medir_consulta(db, coleccion, filtro, proyeccion=None, orden=None,
                   batch_size=None, repeticiones=5, limite=0, orden_en_memoria=None):
    """Ejecuta la consulta varias veces y resume su desempeño.

    `orden_en_memoria`: lista [(campo, sentido)] para ordenar en Python DENTRO de la
    medición (respaldo cuando el servidor no puede ordenar).

    Devuelve un dict. Si el servidor rechaza la consulta (p. ej. ordenar sin
    índice en Cosmos DB) devuelve {"error": "..."} en vez de lanzar.
    """
    col = db[coleccion]

    def una_vez():
        cur = col.find(filtro, proyeccion)
        if orden:
            cur = cur.sort(orden)
        if limite:
            cur = cur.limit(limite)
        if batch_size:
            cur = cur.batch_size(batch_size)
        t0 = time.perf_counter()
        docs = list(cur)
        for campo, sentido in reversed(orden_en_memoria or []):
            docs.sort(key=lambda d, c=campo: str(_valor(d, c)), reverse=(sentido == -1))
        return (time.perf_counter() - t0) * 1000, docs

    try:
        una_vez()  # calentamiento (conexión/TLS ya establecidos)
        tiempos, docs = [], []
        for _ in range(repeticiones):
            ms, docs = una_vez()
            tiempos.append(ms)
        return {
            "documentos": len(docs),
            "bytes": tamano_bytes(docs),
            "ms_mediana": round(statistics.median(tiempos), 2),
            "ms_min": round(min(tiempos), 2),
            "ms_max": round(max(tiempos), 2),
            "ru": ru_ultima_operacion(db),
            "repeticiones": repeticiones,
        }
    except PyMongoError as e:
        return {"error": str(e)[:300]}
