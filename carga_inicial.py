import json
import os
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




# 1. Tu Connection String copiado desde Azure (Claves)
CONNECTION_STRING = os.getenv("COSMOS_CONNECTION_STRING", "mongodb://cosmos-contentflow-mongo-va:<PRIMARY_KEY>@cosmos-contentflow-mongo-va.mongo.cosmos.azure.com:10255/?ssl=true&replicaSet=globaldb&retrywrites=false&maxIdleTimeMS=120000&appName=@cosmos-contentflow-mongo-va@")

# 2. Nombre de la base de datos
DB_NAME = "contentflow_db"

# 3. Carpeta donde están los JSON
DATA_DIR = "data"

# 4. Mapeo de archivos y colecciones
archivos_colecciones = {
    "usuarios.json": "usuarios",
    "publicaciones.json": "publicaciones",
    "reacciones.json": "reacciones",
    "comentarios.json": "comentarios",
    "campañas.json": "campañas",
}


def cargar_datos():
  try:
    print("Conectando a Azure Cosmos DB...")
    client = MongoClient(CONNECTION_STRING)
    db = client[DB_NAME]
    print("¡Conexión exitosa a la base de datos!")

    for archivo, coleccion_nombre in archivos_colecciones.items():
      ruta_completa = os.path.join(DATA_DIR, archivo)

      if os.path.exists(ruta_completa):
        print(f"Leyendo archivo: {ruta_completa}...")
        with open(ruta_completa, "r", encoding="utf-8") as f:
          datos = json.load(f)

        coleccion = db[coleccion_nombre]

        # Limpiar colección previa para evitar duplicados
        coleccion.delete_many({})

        if datos:
          coleccion.insert_many(datos)
          print(
              f"-> Insertados {len(datos)} registros en '{coleccion_nombre}'."
          )
        else:
          print(f"-> El archivo {archivo} está vacío.")
      else:
        print(f"[ADVERTENCIA] No se encontró el archivo en '{ruta_completa}'.")

    print("\n¡Carga inicial completada con éxito!")

  except Exception as e:
    print(f"[ERROR] Ocurrió un error: {e}")


if __name__ == "__main__":
  cargar_datos()