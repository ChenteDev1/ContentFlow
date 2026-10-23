import os
import datetime
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

# 1. Configuración de Conexión
CONNECTION_STRING = os.getenv("COSMOS_CONNECTION_STRING", "mongodb://cosmos-contentflow-mongo-va:<PRIMARY_KEY>@cosmos-contentflow-mongo-va.mongo.cosmos.azure.com:10255/?ssl=true&replicaSet=globaldb&retrywrites=false&maxIdleTimeMS=120000&appName=@cosmos-contentflow-mongo-va@")
DB_NAME = "contentflow_db"


def conectar_db():
  """Establece conexión tolerante a fallos de red con Azure Cosmos DB."""
  try:
    client = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client[DB_NAME]
  except PyMongoError as e:
    print(f"[ERROR CRÍTICO] Conexión fallida: {e}")
    return None


def ejecutar_crud(db):
  coleccion = db["publicaciones"]
  id_prueba = "pub_evaluacion_test_01"

  print("=" * 65)
  print(" INICIO DE OPERACIONES CRUD - COLECCIÓN 'PUBLICACIONES'")
  print("=" * 65)

  # -------------------------------------------------------------
  # 1. CREATE (insert_one)
  # -------------------------------------------------------------
  print("\n[1. CREATE] Insertando nueva publicación de prueba...")
  documento_nuevo = {
      "_id": id_prueba,
      "usuario_id": "user_100",
      "contenido": "Publicación de prueba para validación CRUD en Azure Cosmos DB.",
      "fecha_publicacion": datetime.datetime.now(datetime.timezone.utc).isoformat(),
      "categoria": "Tecnología",
      "hashtags": ["#Azure", "#NoSQL", "#DuocUC"],
      "tipo": "Texto",
  }

  try:
    # Limpieza preventiva en caso de ejecuciones repetidas
    coleccion.delete_one({"_id": id_prueba})

    resultado_insert = coleccion.insert_one(documento_nuevo)
    if resultado_insert.inserted_id:
      print(
          f"-> Documento insertado con éxito con _id:"
          f" '{resultado_insert.inserted_id}'"
      )
    else:
      print("[ALERTA] No se pudo confirmar la inserción.")
  except PyMongoError as e:
    print(f"[ERROR EN CREATE] Falló la inserción: {e}")
    return

  # -------------------------------------------------------------
  # 2. READ (find_one)
  # -------------------------------------------------------------
  print("\n[2. READ] Consultando el documento recién insertado...")
  try:
    doc_encontrado = coleccion.find_one({"_id": id_prueba})
    if doc_encontrado:
      print("-> Documento recuperado exitosamente:")
      print(f"   _id:        {doc_encontrado.get('_id')}")
      print(f"   Categoría:  {doc_encontrado.get('categoria')}")
      print(f"   Contenido:  {doc_encontrado.get('contenido')}")
      print(f"   Hashtags:   {doc_encontrado.get('hashtags')}")
    else:
      print("[ALERTA] Documento no encontrado.")
  except PyMongoError as e:
    print(f"[ERROR EN READ] Falló la lectura: {e}")

  # -------------------------------------------------------------
  # 3. UPDATE (update_one)
  # -------------------------------------------------------------
  print("\n[3. UPDATE] Modificando el contenido y agregando métricas...")
  cambios = {
      "$set": {
          "contenido": "Contenido actualizado: prueba de modificación verificada en Cosmos DB.",
          "estado_moderacion": "Aprobado",
      }
  }

  try:
    resultado_update = coleccion.update_one({"_id": id_prueba}, cambios)
    if resultado_update.modified_count > 0:
      print(
          "-> Actualización aplicada con éxito."
          f" Documentos modificados: {resultado_update.modified_count}"
      )
      # Verificación post-update
      doc_actualizado = coleccion.find_one(
          {"_id": id_prueba}, {"contenido": 1, "estado_moderacion": 1}
      )
      print(f"   Nuevo contenido: {doc_actualizado.get('contenido')}")
      print(f"   Nuevo campo:     {doc_actualizado.get('estado_moderacion')}")
    else:
      print("[AVISO] No se realizaron modificaciones en el documento.")
  except PyMongoError as e:
    print(f"[ERROR EN UPDATE] Falló la actualización: {e}")

  # -------------------------------------------------------------
  # 4. DELETE (delete_one)
  # -------------------------------------------------------------
  print("\n[4. DELETE] Eliminando el documento de prueba...")
  try:
    resultado_delete = coleccion.delete_one({"_id": id_prueba})
    if resultado_delete.deleted_count > 0:
      print(
          "-> Documento eliminado con éxito."
          f" Documentos borrados: {resultado_delete.deleted_count}"
      )
    else:
      print("[ALERTA] No se encontró el documento a eliminar.")

    # Confirmación de inexistencia
    doc_post_delete = coleccion.find_one({"_id": id_prueba})
    if doc_post_delete is None:
      print("-> Verificación completada: el registro ya no existe en la base.")
  except PyMongoError as e:
    print(f"[ERROR EN DELETE] Falló la eliminación: {e}")

  print("\n" + "=" * 65)
  print(" CICLO CRUD COMPLETADO EXITOSAMENTE")
  print("=" * 65)


if __name__ == "__main__":
  db = conectar_db()
  if db is not None:
    ejecutar_crud(db)