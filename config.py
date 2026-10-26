"""Configuración central de ContentFlow.

Un único lugar para:
  * cargar el archivo .env (antes estaba copiado en cada script),
  * crear loggers con salida a consola y a archivo (logs/contentflow.log),
  * conectarse a Azure Cosmos DB for MongoDB con timeout, ping y errores claros.

La cadena de conexión NUNCA se escribe en el código ni en los logs.
"""
import logging
import os
import re
import warnings
from logging.handlers import RotatingFileHandler

from pymongo import MongoClient
from pymongo.errors import PyMongoError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
DATA_DIR = os.path.join(BASE_DIR, "data")
EXPORT_DIR = os.path.join(BASE_DIR, "exportes")
RESULTADOS_DIR = os.path.join(BASE_DIR, "resultados")

COLECCIONES = ["usuarios", "publicaciones", "reacciones", "comentarios", "campañas"]

# pymongo avisa (UserWarning) que está hablando con Cosmos DB. Es informativo, no un error.
warnings.filterwarnings("ignore", message=".*CosmosDB cluster.*", category=UserWarning)


class ConexionError(RuntimeError):
    """No fue posible conectarse a la base de datos (mensaje apto para el usuario)."""


def cargar_env(ruta=None):
    """Lee KEY=VALUE desde .env (sin pisar variables ya definidas en el sistema)."""
    ruta = ruta or os.path.join(BASE_DIR, ".env")
    if not os.path.exists(ruta):
        return
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            valor = valor.strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                valor = valor[1:-1]
            os.environ.setdefault(clave.strip(), valor)


cargar_env()

DB_NAME = os.getenv("DB_NAME", "contentflow_db")
TIMEOUT_MS = int(os.getenv("DB_TIMEOUT_MS", "5000"))


# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
_FORMATO = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def mascarar(texto):
    """Oculta credenciales (usuario:clave@) de cualquier texto antes de loguearlo."""
    return re.sub(r"(mongodb(?:\+srv)?://)[^@/\s]+@", r"\1***:***@", str(texto))


def get_logger(nombre="contentflow"):
    """Logger con consola (INFO) y archivo rotativo logs/contentflow.log (DEBUG)."""
    logger = logging.getLogger(nombre)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    os.makedirs(LOG_DIR, exist_ok=True)
    archivo = RotatingFileHandler(
        os.path.join(LOG_DIR, "contentflow.log"),
        maxBytes=1_000_000, backupCount=3, encoding="utf-8",
    )
    archivo.setLevel(logging.DEBUG)
    archivo.setFormatter(logging.Formatter(_FORMATO))
    consola = logging.StreamHandler()
    consola.setLevel(logging.WARNING)  # la consola la manejan los print de cada script
    consola.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(archivo)
    logger.addHandler(consola)
    return logger


log = get_logger("contentflow.config")

# ----------------------------------------------------------------------------
# Conexión
# ----------------------------------------------------------------------------
_cliente = None
_db_override = None  # permite a las pruebas inyectar una base simulada (mongomock)


def usar_db(db):
    """Solo para pruebas: reemplaza la conexión real por otra base."""
    global _db_override
    _db_override = db


def _obtener_uri():
    uri = os.getenv("COSMOS_CONNECTION_STRING", "").strip()
    if not uri:
        raise ConexionError(
            "Falta COSMOS_CONNECTION_STRING. Copia .env.example a .env y pega tu "
            "cadena de conexión de Azure (Cosmos DB > Cadenas de conexión)."
        )
    if "<PRIMARY_KEY>" in uri:
        raise ConexionError(
            "La cadena de conexión todavía contiene <PRIMARY_KEY>. Reemplázala por "
            "la clave primaria real en tu archivo .env."
        )
    return uri


def conectar_db(timeout_ms=None):
    """Devuelve la base de datos lista para usar o lanza ConexionError.

    * serverSelectionTimeoutMS: falla rápido (5 s) si Azure no responde.
    * ping: verifica autenticación y disponibilidad antes de operar.
    * El cliente se reutiliza (MongoClient es seguro entre hilos).
    """
    global _cliente
    if _db_override is not None:
        return _db_override
    uri = _obtener_uri()
    try:
        if _cliente is None:
            _cliente = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms or TIMEOUT_MS)
        _cliente.admin.command("ping")
        log.info("Conexión verificada con ping (base=%s)", DB_NAME)
        return _cliente[DB_NAME]
    except PyMongoError as e:
        _cliente = None
        log.error("Conexión fallida: %s", mascarar(e))
        raise ConexionError(
            f"No se pudo conectar a Cosmos DB en {timeout_ms or TIMEOUT_MS} ms. "
            "Revisa internet, el firewall de la cuenta (Redes) y la clave. "
            f"Detalle: {mascarar(e)}"
        ) from e


def cerrar_conexion():
    global _cliente
    if _cliente is not None:
        _cliente.close()
        _cliente = None
