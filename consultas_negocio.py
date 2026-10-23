import os
import time
from pymongo import MongoClient

# Cargar variables de entorno desde .env si existe en el directorio del script
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                os.environ.setdefault(k.strip(), v)



from pymongo.errors import PyMongoError

# 1. Conexión a Azure Cosmos DB for MongoDB
CONNECTION_STRING = os.getenv("COSMOS_CONNECTION_STRING", "mongodb://cosmos-contentflow-mongo-va:<PRIMARY_KEY>@cosmos-contentflow-mongo-va.mongo.cosmos.azure.com:10255/?ssl=true&replicaSet=globaldb&retrywrites=false&maxIdleTimeMS=120000&appName=@cosmos-contentflow-mongo-va@")
DB_NAME = "contentflow_db"


def conectar_db():
  """Conexión tolerante a fallos de red con tiempo de espera controlado."""
  try:
    client = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client[DB_NAME]
  except PyMongoError as e:
    print(f"[ERROR CRÍTICO] Falló la conexión con Cosmos DB: {e}")
    return None


# ==============================================================================
# CONSULTA 1: Colección 'usuarios' (Filtro compuesto, proyección y ordenamiento)
# ==============================================================================
def consulta_1_usuarios(db):
  filtro = {"dispositivo": "Desktop", "genero": "Masculino"}
  proyeccion = {
      "_id": 0,
      "nombre": 1,
      "correo": 1,
      "pais": 1,
      "dispositivo": 1,
      "genero": 1,
  }

  print("\n" + "=" * 65)
  print(f"CONSULTA 1: Usuarios con filtro {filtro}")
  print("=" * 65)

  try:
    inicio = time.perf_counter()

    cursor = db.usuarios.find(filtro, proyeccion)
    resultados = list(cursor)

    # Ordenamiento en memoria por 'nombre'
    resultados = sorted(resultados, key=lambda x: x.get("nombre", "").lower())

    fin = time.perf_counter()
    tiempo_ms = (fin - inicio) * 1000

    if not resultados:
      print("[AVISO] No se encontraron registros con esos criterios.")
      return

    for u in resultados[:6]:
      print(
          f"- {u.get('nombre')} | {u.get('correo')} | {u.get('pais')} |"
          f" {u.get('dispositivo')}"
      )

    if len(resultados) > 6:
      print(f"... y {len(resultados) - 6} usuarios adicionales.")

    print("-" * 65)
    print(f"Total encontrados: {len(resultados)} documentos")
    print(f"Tiempo de ejecución: {tiempo_ms:.2f} ms")
    print("=" * 65)

  except PyMongoError as pe:
    print(f"[ERROR BASE DE DATOS] Falló la consulta 1: {pe}")
  except Exception as ex:
    print(f"[ERROR INESPERADO] {ex}")


# ==============================================================================
# CONSULTA 2: Colección 'publicaciones' (Filtro por categoría y ordenamiento temporal)
# ==============================================================================
def consulta_2_publicaciones(db):
  print("\n" + "=" * 65)
  print("CONSULTA 2: Publicaciones por Categoría ('Deportes')")
  print("=" * 65)

  try:
    filtro = {"categoria": "Deportes"}
    proyeccion = {
        "_id": 0,
        "usuario_id": 1,
        "categoria": 1,
        "tipo": 1,
        "fecha_publicacion": 1,
        "contenido": 1,
    }

    inicio = time.perf_counter()

    cursor = db.publicaciones.find(filtro, proyeccion)
    resultados = list(cursor)

    # Ordenamiento en memoria por fecha descendente
    resultados = sorted(
        resultados,
        key=lambda x: str(x.get("fecha_publicacion", "")),
        reverse=True,
    )

    fin = time.perf_counter()
    tiempo_ms = (fin - inicio) * 1000

    if not resultados:
      print("[AVISO] No hubo publicaciones para el criterio seleccionado.")
      return

    for idx, pub in enumerate(resultados[:5], 1):
      contenido_corto = (
          (pub.get("contenido", "")[:45] + "...")
          if len(pub.get("contenido", "")) > 45
          else pub.get("contenido", "")
      )
      print(
          f"{idx}. Usuario: {pub.get('usuario_id')} | Fecha:"
          f" {pub.get('fecha_publicacion')} | Tipo: {pub.get('tipo')} |"
          f" {contenido_corto}"
      )

    if len(resultados) > 5:
      print(f"... y {len(resultados) - 5} publicaciones adicionales.")

    print("-" * 65)
    print(f"Total encontrados: {len(resultados)} documentos")
    print(f"Tiempo de ejecución: {tiempo_ms:.2f} ms")
    print("=" * 65)

  except PyMongoError as pe:
    print(f"[ERROR BASE DE DATOS] Falló la consulta 2: {pe}")
  except Exception as ex:
    print(f"[ERROR INESPERADO] {ex}")


# ==============================================================================
# CONSULTA 3: Colección 'campañas' (Operadores relacionales de presupuesto)
# ==============================================================================
def consulta_3_campañas(db):
  """Consulta de Negocio 3:

  - Colección: campañas
  - Filtro: Campañas de marketing con alto presupuesto (operador $gte)
  - Proyección: omite _id, mostrando nombre, presupuesto, estado y fechas
  - Ordenamiento en memoria: de mayor a menor presupuesto
  - Medición de latencia con time.perf_counter()
  """
  print("\n" + "=" * 65)
  print(
      "CONSULTA 3: Campañas de Marketing con Alta Inversión (Presupuesto >= $5.000)"
  )
  print("=" * 65)

  try:
    # 1. Inspección defensiva para identificar nombres exactos de campos en 'campañas'
    muestra = db.campañas.find_one({}, {"_id": 0})
    if not muestra:
      print(
          "[AVISO] No se encontraron documentos en la colección 'campañas'."
      )
      return

    campos = list(muestra.keys())

    # Detectar el campo de presupuesto numérico (presupuesto, budget, monto, etc.)
    campo_monto = next(
        (
            k
            for k in ["presupuesto", "budget", "monto", "inversion"]
            if k in campos
        ),
        None,
    )

    # Si existe campo de presupuesto, filtramos con operador relacional $gte
    filtro = {}
    if campo_monto:
      filtro = {campo_monto: {"$gte": 5000}}
      print(f"[FILTRO APLICADO]: {campo_monto} >= 5000")
    else:
      print(
          f"[CAMPOS DETECTADOS EN CAMPAÑAS]: {campos} (se listarán registros"
          " generales)"
      )

    # 2. Proyección
    proyeccion = {"_id": 0}
    for k in campos:
      proyeccion[k] = 1

    inicio = time.perf_counter()

    cursor = db.campañas.find(filtro, proyeccion)
    resultados = list(cursor)

    # Ordenamiento en memoria: de mayor a menor inversión
    if campo_monto:
      resultados = sorted(
          resultados, key=lambda x: x.get(campo_monto, 0), reverse=True
      )

    fin = time.perf_counter()
    tiempo_ms = (fin - inicio) * 1000

    if not resultados:
      print(
          "[AVISO] No se encontraron campañas con ese umbral. Ajustando"
          " filtro a >= 1000..."
      )
      cursor = db.campañas.find(
          {campo_monto: {"$gte": 1000}} if campo_monto else {}, proyeccion
      )
      resultados = list(cursor)
      if campo_monto:
        resultados = sorted(
            resultados, key=lambda x: x.get(campo_monto, 0), reverse=True
        )

    # Mostrar las primeras 5 campañas ordenadas
    for idx, c in enumerate(resultados[:5], 1):
      linea = " | ".join(
          f"{k}: {v}"
          for k, v in c.items()
          if k
          in [
              campo_monto,
              "nombre",
              "nombre_campaña",
              "estado",
              "fecha_inicio",
              "objetivo",
          ]
          or len(str(v)) <= 30
      )
      print(f"{idx}. {linea}")

    if len(resultados) > 5:
      print(f"... y {len(resultados) - 5} campañas adicionales.")

    print("-" * 65)
    print(f"Total encontrados: {len(resultados)} documentos")
    print(f"Tiempo de ejecución: {tiempo_ms:.2f} ms")
    print("=" * 65)

  except PyMongoError as pe:
    print(f"[ERROR BASE DE DATOS] Falló la consulta 3: {pe}")
  except Exception as ex:
    print(f"[ERROR INESPERADO] {ex}")


# ==============================================================================
# EJECUCIÓN GENERAL
# ==============================================================================
if __name__ == "__main__":
  db = conectar_db()
  if db is not None:
    consulta_1_usuarios(db)
    consulta_2_publicaciones(db)
    consulta_3_campañas(db)