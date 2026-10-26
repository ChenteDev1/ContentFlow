# Guía del proyecto ContentFlow (léanla primero)

*Un solo documento para entender todo: qué es el proyecto, cómo cumple la pauta, qué hace cada archivo, qué deben saber explicar y qué falta. Si algo de los mensajes anteriores del chat contradice esta guía, vale esta guía.*

---

## 1. El proyecto en 30 segundos

**ContentFlow** es una red de contenidos ficticia. Tenemos 5 archivos JSON con 2.500 datos (500 usuarios, 500 publicaciones, 500 reacciones, 500 comentarios y 500 campañas). El encargo pide:

1. **Subir esos datos a una base NoSQL en la nube** (Azure Cosmos DB con API de MongoDB).
2. **Consultarlos y modificarlos** respondiendo preguntas de negocio.
3. **Hacer un CRUD completo** (Crear, Leer, Actualizar, Eliminar) con validaciones.
4. **Conectar una aplicación externa** que lea y escriba en la base (nosotros hicimos una **API REST**, probada con **Postman**).
5. **Controlar errores y dejar registro** (logs).
6. **Entregar un informe PDF + el link al repositorio.**

Las preguntas de la gerencia (el "caso") son tres: *¿quiénes son los usuarios más activos?, ¿qué contenidos son más populares?, ¿qué impacto tienen las campañas?* El **panel HTML** (`dashboard/index.html`) las responde con gráficos.

> **Qué es lo que ya existía y qué se agregó.** Vicente ya había creado la cuenta en Azure, cargado los datos y hecho 3 consultas y un CRUD simple. Se agregó: consultas reales de lectura y modificación, analítica, mediciones de eficiencia, CRUD multi-colección con validaciones, API REST + Postman, auditoría de datos, logs, pruebas automáticas, el panel HTML y el informe.

---

## 2. Cómo cumple cada requisito de la pauta

| La pauta pide (apartado del informe) | Dónde está en el proyecto | Indicadores |
|---|---|---|
| **1. Objetivos** | Informe §1 | todos |
| **2. Configuración NoSQL**: API elegida y por qué, contenedor, claves de partición, throughput, consistencia, problemas resueltos | Informe §2. Cuenta `cosmos-contentflow-mongo-va`, modo *Serverless*, consistencia *Session*. Particiones y throughput explicados con honestidad | IE1, IE2, IE3 |
| **3. Datos de prueba**: carga y verificación | `carga_inicial.py` (valida → carga → cuenta). Verificado en 4 herramientas: consola, Data Explorer, Mongo Shell y `GET /salud` | IE1, IE3, IE7 |
| **4. Consultas** de lectura y modificación, con filtros, proyecciones, búsquedas compuestas, orden y ejemplos de negocio | `consultas_negocio.py` (5 de lectura), `consultas_modificacion.py` (4 de modificación), `analitica_negocio.py` y el panel HTML; eficiencia en `optimizacion_indices.py` | IE4, IE5, IE6, IE7 |
| **5. CRUD completo** con evidencias | `operaciones_crud.py`: un caso de negocio con las 5 colecciones, 12 casos inválidos y borrado en cascada | IE7, IE8, IE9 |
| **6. Integración con aplicación externa**: flujo, herramienta, string de conexión, librerías, evidencia de lectura/escritura | `api.py` (FastAPI) + `postman/` (colección con 19 pruebas) | IE9, IE10 |
| **7. Control de errores y validaciones** | `validaciones.py`, `servicios.py`, `config.py` (logs), `integridad.py`, `tests/` | IE11 |
| **Entregables**: informe PDF, scripts, capturas, código/screenshots de integración, link al repo | PDF con `generar_informe.py`; `Evidencias/`; este repositorio | — |

**Dos detalles de la pauta que no hay que olvidar:** (a) dice que el encargo es **en parejas** y nosotros somos tres: avisen al profe; (b) la inscripción del grupo y la entrega se hacen por **AVA**, dejando el link del repo.

---

## 3. Qué hace cada archivo (en simple)

```
data/*.json              Los 2.500 datos del caso.
.env                     Su clave de Azure (NO se sube a GitHub).
config.py                Se conecta a Azure (con tiempo límite y ping) y escribe el log.
carga_inicial.py         Sube los JSON a Azure y comprueba que quedaron los 500 de cada colección.
validaciones.py          Reglas de qué datos son válidos (categorías, fechas, correo, hashtags...).
servicios.py             Las operaciones (crear/modificar/borrar) respetando las reglas:
                         que el usuario exista, que no haya duplicados, que no queden "huérfanos".
consultas_negocio.py     5 consultas de lectura con tiempo, tamaño y costo (RU).
consultas_modificacion.py  4 modificaciones que se verifican y se deshacen solas.
analitica_negocio.py     Usuarios activos, contenido popular, horarios, campañas, audiencia.
optimizacion_indices.py  Mide "antes y después" de mejoras (proyección, lotes, índices).
operaciones_crud.py      El CRUD completo de un caso real, con casos de error.
integridad.py            Revisa la calidad de los datos (duplicados, fechas raras, huérfanos).
api.py                   La API REST: así una "aplicación externa" lee y escribe en la base.
postman/                 Colección de Postman para probar la API.
generar_dashboard.py     Crea dashboard/index.html (el panel de gráficos).
generar_informe.py       Crea el PDF del informe con los resultados reales.
tests/                   52 pruebas automáticas (no necesitan Azure).
```

**Idea clave para entender el diseño:** en una base NoSQL **no hay llaves foráneas ni integridad automática** (como en SQL). Entonces *la aplicación* debe cuidar que no se inserten reacciones a publicaciones que no existen, que no se borre una publicación dejando comentarios sueltos, etc. Eso es `servicios.py`. Todo lo que escribe (scripts y API) pasa por ahí.

---

## 4. Conceptos que el equipo debe poder explicar

| Concepto | Explicación corta |
|---|---|
| **¿Por qué NoSQL / documentos?** | Cada publicación guarda sus hashtags dentro del mismo documento y el esquema puede cambiar sin migraciones. A cambio no hay JOINs ni integridad automática. |
| **¿Por qué Cosmos DB con API de MongoDB?** | El caso habla de MongoDB y los datos ya son JSON. La pauta permite Cosmos con API MongoDB. Otras APIs: *NoSQL (Core)* exige reescribir consultas; *Gremlin* es para grafos; *Table* es clave-valor y no sirve para filtros compuestos. |
| **Serverless** | No se reserva capacidad: se paga solo por lo que se usa (en RU). Ideal para pruebas y cargas esporádicas. Máximo 5.000 RU/s. |
| **RU (Request Unit)** | La "moneda" de Cosmos: cada operación cuesta RU. Medimos cuántos cuesta cada consulta. |
| **Throughput** | En Serverless no se configura; se mide el consumo real en RU por consulta. |
| **Consistencia *Session*** | Lo que yo escribo, yo lo leo de inmediato (usado en "crear y luego leer"). Es el nivel por defecto. |
| **Clave de partición** | Campo que decide cómo se reparte la información al crecer. **Hoy las colecciones no están particionadas** (son pequeñas); en el informe hay una propuesta por colección y la opción `--shard-key` para aplicarla. No digan que ya está aplicada. |
| **Índice** | Hace más rápidas las búsquedas. En Cosmos es **obligatorio para ordenar en el servidor**; por eso `optimizacion_indices.py` crea índices y mide la diferencia. |
| **Proyección** | Pedir solo los campos necesarios: viaja menos información. |
| **CRUD en cascada** | Al borrar una publicación se borran sus reacciones y comentarios y se quita de las campañas: evita datos huérfanos. |
| **`$inc`, `$addToSet`, `$set`** | `$inc` suma de forma atómica (no se pierden likes simultáneos); `$addToSet` agrega sin duplicar; `$set` cambia un campo. |
| **API REST** | Programa que recibe peticiones HTTP (GET/POST/PUT/DELETE) y las traduce a operaciones en la base: es la "aplicación externa". |
| **Postman** | Cliente para probar la API; nuestra colección escribe, lee lo escrito, modifica, borra y prueba errores. |
| **Logs y trazabilidad** | `logs/contentflow.log` guarda qué pasó y cuándo; cada petición HTTP tiene un `X-Request-ID`. Las claves nunca se escriben en el log. |

---

## 5. Hallazgos honestos (no los escondan, suman puntos en IE8 e IE6)

* El dataset tiene **fechas incoherentes**: 245 reacciones y 251 comentarios son anteriores a la publicación que reaccionan o comentan, 48 publicaciones son anteriores al registro de su autor y hay 1 reacción duplicada. Los scripts lo detectan, lo **marcan** (no lo borran) y las reglas nuevas impiden crear más.
* La consulta 3 original no filtraba nada (devolvía 500 campañas) y hablaba de un "presupuesto" que no existe en los datos. Está corregida.
* Los datos son sintéticos y pequeños: las diferencias entre categorías, horas y campañas son **pequeñas**. El panel lo dice en pantalla. No inventen "tendencias".
* Los números de tiempo del informe anterior (420/374/621 ms) no coincidían con las capturas; se reemplazaron por mediciones nuevas.

---

## 6. Demostración de 5 minutos (para la defensa)

1. **Azure Portal → Data Explorer:** mostrar las 5 colecciones y sus 500 documentos.
2. `python consultas_negocio.py` → explicar una consulta (filtro, proyección, orden) con su tiempo y RU.
3. `python operaciones_crud.py` → mostrar las verificaciones OK y los casos inválidos rechazados.
4. `uvicorn api:app --port 8000` + **Postman → Run collection** → todo verde; luego mostrar el documento creado en Data Explorer.
5. Abrir `dashboard/index.html` → responder las 3 preguntas de la gerencia con los gráficos.
6. Cerrar con `logs/contentflow.log` y la sección de calidad de datos.

---

## 7. Qué falta por hacer (lista única)

Todo lo que sigue **solo se puede hacer con acceso a su cuenta de Azure** (yo no tengo la clave). Hagan los pasos en este orden; cada uno dice qué captura guardar en `Evidencias/`.

- [ ] `pip install -r requirements.txt` y crear `.env` con la clave (copiando `.env.example`).
- [ ] `python carga_inicial.py` (si la base ya está cargada, igual conviene: deja todo en estado conocido). *Captura ya existente.*
- [ ] `python integridad.py` → `Integridad_Auditoria.png`
- [ ] `python consultas_negocio.py` → `Consultas_Lectura.png`
- [ ] `python consultas_modificacion.py` → `Consultas_Modificacion.png`
- [ ] `python analitica_negocio.py --exportar` → `Analitica.png`
- [ ] `python optimizacion_indices.py` → `Optimizacion_Indices.png`
- [ ] `python operaciones_crud.py` → `CRUD_Escenario.png` (debe decir 34/34)
- [ ] `python generar_dashboard.py` (con Azure) y abrir `dashboard/index.html` → reemplazar `Dashboard_Panel.png`
- [ ] `uvicorn api:app --port 8000` → capturar `http://127.0.0.1:8000/docs` → `API_Swagger.png`
- [ ] Postman: importar `postman/ContentFlow.postman_collection.json`, **Run collection** → `Postman_Run.png`; una escritura (`POST`) → `Postman_Request_Crear.png`; su lectura → `Postman_Request_Leer.png`
- [ ] Data Explorer: el documento creado por la API → `DataExplorer_Verificacion.png`
- [ ] Azure Portal → Cosmos DB → *Coherencia predeterminada* → `ConsistenciaPredeterminada.png`
- [ ] Capturar unas líneas de `logs/contentflow.log` → `Log_Extracto.png`
- [ ] `python generar_informe.py` → debe decir **Versión 2.0 · Final** (0 pendientes) → entregar `INFORME_TECNICO_CONTENTFLOW.pdf`
- [ ] Inscribir el grupo en AVA y entregar **PDF + link del repo**.
- [ ] Preguntar al profe: ¿trío o pareja? ¿se exige dashboard de Power BI (ahora se aceptó HTML)?
- [ ] **Seguridad:** no mostrar la clave en ninguna captura; si alguna vez se pegó en un chat, rotarla en Azure (*Claves de acceso → regenerar*).

---

## 8. Subir los cambios a GitHub (hace el dueño del repo, Vicente)

```bash
# 1. descomprimir ContentFlow_actualizado.zip SOBRE la carpeta local del repo (reemplazar archivos)
cd ContentFlow
git add -A
git status                      # revisar: NO debe aparecer .env
git commit -m "Consultas, CRUD multi-colección, API REST, panel HTML e informe"
git push
```
