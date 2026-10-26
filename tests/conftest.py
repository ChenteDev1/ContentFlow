"""Fixtures: base simulada (mongomock) cargada con los 5 JSON reales del caso.

Las pruebas no necesitan Azure ni credenciales. Validan la lógica (consultas,
CRUD, integridad, API); los tiempos y RU reales se miden contra Cosmos DB.
"""
import json
import os
import sys

import mongomock
import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import config  # noqa: E402


def _cargar(db):
    for archivo, col in {"usuarios.json": "usuarios", "publicaciones.json": "publicaciones",
                         "reacciones.json": "reacciones", "comentarios.json": "comentarios",
                         "campañas.json": "campañas"}.items():
        with open(os.path.join(RAIZ, "data", archivo), encoding="utf-8") as f:
            db[col].insert_many(json.load(f))


@pytest.fixture()
def db():
    cliente = mongomock.MongoClient()
    base = cliente["contentflow_test"]
    _cargar(base)
    config.usar_db(base)
    yield base
    config.usar_db(None)
