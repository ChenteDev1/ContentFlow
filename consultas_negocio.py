"""Consultas de LECTURA de ContentFlow (IE4, IE5, IE6).

Cada consulta responde a una pregunta de la gerencia e incluye filtro,
proyección y ordenamiento. Se mide tiempo (mediana de 5 ejecuciones), volumen
devuelto (bytes) y costo en RU. El ordenamiento se pide al SERVIDOR; si Cosmos
DB lo rechaza por falta de índice se usa memoria como respaldo y se avisa
(ver optimizacion_indices.py para crear los índices y medir la mejora).

Uso:  python consultas_negocio.py            # las 5 consultas
      python consultas_negocio.py 3          # solo la consulta 3
"""
import json
import os
import sys

from pymongo.errors import PyMongoError

from config import RESULTADOS_DIR, ConexionError, conectar_db, get_logger
from metricas import medir_consulta
from servicios import buscar

log = get_logger("contentflow.consultas")
MOSTRAR = 5

CONSULTAS = {
    1: {
        "titulo": "Usuarios Desktop masculinos (segmentación de audiencia)",
        "negocio": "Producto necesita el segmento de escritorio masculino para priorizar el "
                   "diseño web de pantalla ancha y campañas de patrocinio.",
        "coleccion": "usuarios",
        "filtro": {"dispositivo": "Desktop", "genero": "Masculino"},
        "proyeccion": {"_id": 0, "nombre": 1, "correo": 1, "pais": 1, "dispositivo": 1, "genero": 1},
        "orden": [("nombre", 1)],
        "formato": lambda d: f"{d['nombre']} | {d['correo']} | {d['pais']} | {d['dispositivo']}",
    },
    2: {
        "titulo": "Publicaciones de Deportes, de la más reciente a la más antigua",
        "negocio": "Editorial audita la cobertura de Deportes en orden cronológico inverso.",
        "coleccion": "publicaciones",
        "filtro": {"categoria": "Deportes"},
        "proyeccion": {"_id": 0, "usuario_id": 1, "categoria": 1, "tipo": 1,
                       "fecha_publicacion": 1, "hashtags": 1},
        "orden": [("fecha_publicacion", -1)],
        "formato": lambda d: f"{d['fecha_publicacion']} | {d['usuario_id']} | {d['tipo']} | {d['hashtags']}",
    },
    3: {
        "titulo": "Campañas de alto impacto (objetivo + métricas + fecha)",
        "negocio": "Marketing quiere las campañas de engagement/contenido iniciadas desde febrero "
                   "2025 con meta de al menos 500 likes, ordenadas por meta de likes.",
        "coleccion": "campañas",
        "filtro": {
            "objetivo": {"$in": ["Aumentar engagement", "Promover contenido"]},
            "metricas_objetivo.likes": {"$gte": 500},
            "fecha_inicio": {"$gte": "2025-02-01T00:00:00"},
        },
        "proyeccion": {"_id": 0, "nombre": 1, "objetivo": 1, "fecha_inicio": 1, "fecha_fin": 1,
                       "metricas_objetivo": 1},
        "orden": [("metricas_objetivo.likes", -1)],
        "formato": lambda d: (f"{d['nombre']} | {d['objetivo']} | inicio {d['fecha_inicio'][:10]} | "
                              f"likes meta {d['metricas_objetivo']['likes']}"),
    },
    4: {
        "titulo": "Videos recientes con hashtags de tendencia (búsqueda compuesta)",
        "negocio": "Contenido busca videos o imágenes de junio-julio 2025 con #cultura o #series "
                   "para armar una selección destacada.",
        "coleccion": "publicaciones",
        "filtro": {
            "tipo": {"$in": ["Video", "Imagen"]},
            "hashtags": {"$in": ["#cultura", "#series"]},
            "fecha_publicacion": {"$gte": "2025-06-01T00:00:00", "$lt": "2025-08-01T00:00:00"},
        },
        "proyeccion": {"_id": 1, "categoria": 1, "tipo": 1, "hashtags": 1, "fecha_publicacion": 1},
        "orden": [("fecha_publicacion", -1)],
        "formato": lambda d: f"{d['_id']} | {d['fecha_publicacion']} | {d['tipo']} | {d['categoria']} | {d['hashtags']}",
    },
    5: {
        "titulo": "Comentarios más valorados (Top 10 por likes)",
        "negocio": "Comunidad quiere moderar y destacar los comentarios con 90 o más likes.",
        "coleccion": "comentarios",
        "filtro": {"likes": {"$gte": 90}},
        "proyeccion": {"_id": 1, "usuario_id": 1, "publicacion_id": 1, "comentario": 1, "likes": 1},
        "orden": [("likes", -1)],
        "limite": 10,
        "formato": lambda d: f"{d['_id']} | {d['likes']} likes | {d['publicacion_id']} | {d['comentario'][:40]}",
    },
}


def ejecutar_consulta(db, numero):
    c = CONSULTAS[numero]
    print("\n" + "=" * 70)
    print(f"CONSULTA {numero}: {c['titulo']}")
    print("=" * 70)
    print(f"Caso de negocio: {c['negocio']}")
    print(f"Colección: {c['coleccion']}")
    print(f"Filtro:     {json.dumps(c['filtro'], ensure_ascii=False)}")
    print(f"Proyección: {list(c['proyeccion'])}")
    print(f"Orden:      {c['orden']}" + (f" (límite {c['limite']})" if c.get("limite") else ""))
    print("-" * 70)

    col = db[c["coleccion"]]
    docs, donde = buscar(col, c["filtro"], c["proyeccion"], c["orden"], c.get("limite", 0))
    if not docs:
        print("[AVISO] No se encontraron registros con esos criterios.")
        log.info("consulta %s sin resultados", numero)
        return None
    for d in docs[:MOSTRAR]:
        print("-", c["formato"](d))
    if len(docs) > MOSTRAR:
        print(f"... y {len(docs) - MOSTRAR} documentos adicionales.")

    m = medir_consulta(db, c["coleccion"], c["filtro"], c["proyeccion"],
                       c["orden"] if donde.startswith("servidor") else None,
                       limite=0 if donde.startswith("memoria") else c.get("limite", 0),
                       orden_en_memoria=c["orden"] if donde.startswith("memoria") else None)
    print("-" * 70)
    print(f"Total encontrados: {len(docs)} documentos")
    print(f"Ordenamiento resuelto en: {donde}")
    if "error" in m:
        print(f"[AVISO] No se pudo medir: {m['error']}")
    else:
        print(f"Tiempo (mediana de {m['repeticiones']}): {m['ms_mediana']} ms "
              f"(min {m['ms_min']} / máx {m['ms_max']})")
        print(f"Volumen devuelto: {m['bytes']:,} bytes".replace(",", "."))
        print(f"Costo: {m['ru']} RU" if m["ru"] is not None else "Costo: RU no disponible en este motor")
    log.info("consulta %s: docs=%s orden=%s medicion=%s", numero, len(docs), donde, m)
    return {"consulta": numero, "titulo": c["titulo"], "documentos": len(docs),
            "orden_en": donde, **m}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    numeros = [int(a) for a in argv if a.isdigit() and int(a) in CONSULTAS] or sorted(CONSULTAS)
    try:
        db = conectar_db()
        resultados = []
        for n in numeros:
            try:
                r = ejecutar_consulta(db, n)
                if r:
                    resultados.append(r)
            except PyMongoError as e:
                log.exception("consulta %s falló", n)
                print(f"[ERROR BASE DE DATOS] Consulta {n} falló: {e}")
        os.makedirs(RESULTADOS_DIR, exist_ok=True)
        with open(os.path.join(RESULTADOS_DIR, "consultas_lectura.json"), "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=2)
        print("\nResultados guardados en resultados/consultas_lectura.json")
        return 0
    except ConexionError as e:
        print(f"[ERROR CRÍTICO] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
