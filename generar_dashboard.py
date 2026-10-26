"""Genera el panel HTML (dashboard/index.html) con la analítica de ContentFlow.

    python generar_dashboard.py            # lee de Azure Cosmos DB (requiere .env)
    python generar_dashboard.py --local    # calcula desde data/*.json (sin Azure)

El HTML resultante es un solo archivo, sin dependencias externas: se abre con
doble clic o se publica en GitHub Pages. Los datos quedan incrustados.
Ambas fuentes usan exactamente las mismas funciones de analitica_negocio.py.
"""
import argparse
import json
import os
import sys
from datetime import datetime

import analitica_negocio as an
import integridad
from config import COLECCIONES, DATA_DIR, ConexionError, conectar_db, usar_db

BASE = os.path.dirname(os.path.abspath(__file__))
PLANTILLA = os.path.join(BASE, "dashboard", "plantilla.html")
SALIDA = os.path.join(BASE, "dashboard", "index.html")


def base_local():
    """Base simulada cargada con los JSON del caso (los mismos que se cargan a Azure)."""
    import mongomock
    db = mongomock.MongoClient()["contentflow_local"]
    archivos = {"usuarios": "usuarios.json", "publicaciones": "publicaciones.json",
                "reacciones": "reacciones.json", "comentarios": "comentarios.json",
                "campañas": "campañas.json"}
    for col, archivo in archivos.items():
        with open(os.path.join(DATA_DIR, archivo), encoding="utf-8") as f:
            db[col].insert_many(json.load(f))
    usar_db(db)
    return db


def recopilar(db, fuente):
    por_objetivo, top_campanas, _ = an.impacto_campanas(db, 10)
    horas = an.horarios_publicacion(db)
    auditoria = integridad.auditar(db)
    return {
        "fuente": fuente,
        "generado": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "conteos": {c: db[c].count_documents({}) for c in COLECCIONES},
        "usuarios_activos": an.usuarios_mas_activos(db, 10),
        "pesos": an.PESOS_ACTIVIDAD,
        "contenido_popular": an.contenido_popular(db, 10),
        "categorias": an.popularidad_por_categoria(db),
        "reacciones_tipo": an.reacciones_por_tipo(db),
        "horas": horas,
        "franjas": an.franjas_horarias(horas),
        "campanas_objetivo": por_objetivo,
        "campanas_top": top_campanas,
        "audiencia": an.perfil_audiencia(db),
        "auditoria": {k: v["cantidad"] for k, v in auditoria.items()},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Genera dashboard/index.html")
    ap.add_argument("--local", action="store_true", help="usar data/*.json en vez de Azure")
    args = ap.parse_args(argv)
    try:
        if args.local:
            db, fuente = base_local(), "Archivos JSON del caso (mismos datos cargados en Cosmos DB)"
        else:
            db, fuente = conectar_db(), "Azure Cosmos DB for MongoDB · contentflow_db"
        datos = recopilar(db, fuente)
    except ConexionError as e:
        print(f"[ERROR CRÍTICO] {e}\nSugerencia: python generar_dashboard.py --local")
        return 1
    with open(PLANTILLA, encoding="utf-8") as f:
        html = f.read()
    # "</" se escapa para que el JSON nunca pueda cerrar la etiqueta <script>
    cargado = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    with open(SALIDA, "w", encoding="utf-8") as f:
        f.write(html.replace("/*__DATOS__*/null", cargado))
    print(f"Panel generado: {SALIDA}\nFuente: {fuente}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
