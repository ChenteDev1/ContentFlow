# GUÍA Y GUIÓN DE PRESENTACIÓN · CONTENTFLOW (EP2)
**Evaluación Parcial N°2 · BDY0101 Base de Datos No Relacionales**  
**Integrantes:** Vicente Alarcón · Francisco Aranguiz · Carlos Bittner  
**Tiempo estimado:** 5 a 6 minutos total

---

## 📌 Preparación antes de pasar a exponer (30 segundos)

1. **Terminal 1 en VS Code:** Dejar corriendo la API con:
   ```bash
   uvicorn api:app --port 8000
   ```
2. **Postman:** Abierto con el entorno **`ContentFlow local`** seleccionado (arriba a la derecha) y la carpeta `A. Flujo CRUD completo` desplegada.
3. **Navegador:** 
   * Pestaña 1: Azure Portal en `cosmos-contentflow-mongo-va` > Data Explorer.
   * Pestaña 2: `dashboard/index.html` (el Dashboard interactivo).

---

## 👤 BLOQUE 1: VICENTE (aprox. 1:40 min)
**Rol:** Contexto del caso, Arquitectura en Azure y Carga remota de datos.

### 📋 En pantalla:
* Mostrar Azure Portal > Data Explorer con la base `contentflow_db` y las 5 colecciones desplegadas.
* Mostrar que cada colección tiene 500 documentos.

### 🗣️ Diálogo de Vicente:
> «Buenas tardes profesor y compañeros. Junto a Francisco y Carlos les presentaremos la Evaluación Parcial N°2 correspondiente al caso **ContentFlow (Forma A)**.
> 
> ContentFlow es una red social y plataforma de contenidos que gestiona miles de interacciones diarias distribuidas en 5 entidades: usuarios, publicaciones, comentarios, reacciones y campañas publicitarias. Nuestro encargo consistió en migrar y administrar esta información en una base de datos NoSQL en la nube, resolver requerimientos analíticos, garantizar integridad en las operaciones CRUD y conectar una aplicación externa en tiempo real.
> 
> *[Mostrar Azure Portal > Data Explorer]*
> 
> **¿Por qué seleccionamos Azure Cosmos DB con API for MongoDB?**  
> Porque el modelo documental JSON se adapta naturalmente a una plataforma de contenidos. Nos permite almacenar arrays embebidos (como los hashtags) y subdocumentos (como las métricas de campañas) sin requerir tablas intermedias ni esquemas rígidos. Descartamos *Gremlin* porque el caso no requería grafos de redes complejas, y descartamos *Table API* porque no admite filtros compuestos ni agregaciones.
> 
> La cuenta se configuró en modo **Serverless**, pagando únicamente por las *Request Units* (RU) que consumen nuestras operaciones, ideal para controlar costos. Además, usamos coherencia predeterminada **Session**, lo que asegura que cualquier escritura pueda ser leída inmediatamente por la misma sesión. Las credenciales están protegidas mediante variables de entorno en un archivo `.env` que nunca se expone en Git.
> 
> *[Mostrar las 5 colecciones con 500 documentos cada una]*
> 
> Para poblar la base de datos de manera limpia y remota, construimos el script `carga_inicial.py`. Este script primero valida la estructura y llaves únicas de los 5 archivos JSON locales antes de tocar Azure, y luego inserta los **2.500 documentos** (500 por cada colección), verificando automáticamente que los conteos en la nube coincidan con los archivos.
> 
> Ahora mi compañero Francisco les mostrará la analítica de negocio y el Dashboard que construyó.»

---

## 👤 BLOQUE 2: PANCHO / FRANCISCO (aprox. 1:40 min)
**Rol:** Analítica de Negocio y Dashboard HTML interactivo.

### 📋 En pantalla:
* Pestaña del navegador con `dashboard/index.html`.
* Mostrar tarjetas superiores (KPIs), gráfico de usuarios activos, categorías, franjas horarias y barras de campañas.

### 🗣️ Diálogo de Pancho:
> «Gracias, Vicente. La gerencia de ContentFlow nos planteó tres desafíos estratégicos: identificar a los usuarios más activos, descubrir qué contenidos tienen mayor éxito junto a sus mejores horarios, y medir la efectividad de las campañas publicitarias.
> 
> Para resolverlo desarrollamos el script `analitica_negocio.py` utilizando pipelines de agregación nativos de MongoDB:
> 1. **Usuarios más activos:** Diseñamos un índice de actividad donde cada publicación vale 3 puntos, cada comentario 2 y cada reacción 1. Así obtuvimos el Top 10 de usuarios con mayor fidelidad.
> 2. **Contenidos y Horarios:** Sumamos reacciones y comentarios para medir engagement, y agrupamos las fechas por franjas horarias. Detectamos que la **Tarde (12 a 17 horas)** es la franja con mayor interacción por publicación.
> 3. **Impacto de Campañas:** Comparamos las metas de likes y comentarios que fijó cada campaña frente a las interacciones reales de sus publicaciones, calculando su porcentaje de cumplimiento exacto.
> 
> *[Pancho pasa al navegador y navega por el Dashboard HTML]*
> 
> Como el profesor nos autorizó el uso de HTML para la visualización, desarrollé este **Dashboard interactivo**. 
> 
> Este panel traduce directamente los resultados de nuestras consultas en una interfaz visual moderna: incluye tarjetas KPI con los totales del sistema, gráficos de barras con los usuarios líderes, comparativas de popularidad por categoría y el desglose de cumplimiento de cada campaña. Esto le permite a cualquier tomador de decisiones entender el comportamiento de la plataforma sin tener que mirar código ni bases de datos.
> 
> A continuación, Carlos les demostrará las operaciones CRUD y la API REST en Postman.»

---

## 👤 BLOQUE 3: NACHO / CARLOS (aprox. 2:00 min)
**Rol:** Operaciones CRUD, Reglas de Integridad y Demostración en vivo en Postman.

### 📋 En pantalla:
1. En VS Code, mostrar brevemente la terminal donde corrió `operaciones_crud.py` con el mensaje verde: **`RESULTADO: 34/34 verificaciones correctas`**.
2. Cambiar a la ventana de **Postman** (entorno `ContentFlow local` activo).
3. Ejecutar las 3 peticiones en vivo:
   * Petición **`01 Salud`** ➔ Clic en **Send** (muestra `200 OK`).
   * Petición **`03 ESCRIBIR · Crear publicación`** ➔ Clic en **Send** (muestra `201 Created`).
   * Petición **`04 LEER · Obtener la publicación recién creada`** ➔ Clic en **Send** (muestra `200 OK`).

### 🗣️ Diálogo de Nacho:
> «Gracias, Francisco. En bases de datos NoSQL no existen restricciones automáticas de llaves foráneas. Si borramos una publicación, la base no impide por sí sola que queden comentarios huérfanos. Por eso implementamos una capa de servicios e integridad directamente en Python.
> 
> *[Nacho muestra en la terminal la salida de `operaciones_crud.py`]*
> 
> Con `operaciones_crud.py` simulamos un caso de negocio real: un usuario nuevo se registra, crea un post, recibe comentarios y likes con operadores atómicos como `$inc` y `$addToSet`, y luego se retira.
> Implementamos **borrado en cascada**: al eliminar una publicación se borran automáticamente sus reacciones y comentarios huérfanos. Además, pusimos a prueba el sistema con **12 casos de validación negativa** (como categorías inexistentes, correos duplicados y fechas ilógicas), logrando **34 de 34 verificaciones correctas**, lo que garantiza que la base no acepte datos corruptos.
> 
> *[Nacho se cambia a la ventana de Postman]*
> 
> Por último, para la integración con aplicaciones externas, construimos una **API REST** con FastAPI (`api.py`), la cual genera un identificador de trazabilidad `X-Request-ID` para cada petición y guarda el registro en un archivo de log.
> 
> Vamos a probarla en tiempo real con Postman:
> 
> 1. *[Nacho hace clic en `01 Salud` y presiona Send]*  
> «Ejecutamos el endpoint de salud. Nos responde `200 OK`, confirmando la conexión activa y la latencia contra Azure Cosmos DB.»
> 
> 2. *[Nacho hace clic en `03 ESCRIBIR · Crear publicación` y presiona Send]*  
> «Ahora realizamos una escritura: enviamos un JSON con una nueva publicación y la API nos retorna código verde `201 Created` con el ID generado.»
> 
> 3. *[Nacho hace clic en `04 LEER` y presiona Send]*  
> «Y finalmente consultamos inmediatamente por ese ID. Obtenemos un `200 OK` con los datos recién persistidos en Azure, demostrando lectura y escritura en tiempo real gracias a la consistencia de sesión.»

---

## 🏁 CIERRE: VICENTE (15 segundos)
> **Vicente:**  
> «En síntesis, integramos exitosamente Azure Cosmos DB for MongoDB, garantizamos calidad de datos mediante lógica de integridad, visualizamos los patrones del negocio con nuestro Dashboard y demostramos la integración en tiempo real vía API REST.  
> Muchas gracias por su atención profesor, quedamos atentos a cualquier pregunta.»
