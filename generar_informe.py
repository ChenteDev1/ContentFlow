"""Genera el informe técnico en PDF a partir de informe/INFORME_TECNICO_CONTENTFLOW.md.

    pip install markdown playwright && playwright install chromium
    python generar_informe.py

* Incorpora los resultados REALES guardados por los scripts en resultados/*.json,
  las tablas de exportes/*.csv, el log y las capturas de Evidencias/.
* Lo que aún no exista se muestra como recuadro amarillo "PENDIENTE" y se lista
  al final: así nunca se entrega un informe con cifras inventadas.
* Si no hay Chromium/Playwright, deja un HTML autocontenido en informe/build/informe.html
  que se puede abrir en Chrome y guardar como PDF (Ctrl+P).
"""
import base64
import csv
import html
import json
import mimetypes
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(BASE, "informe", "INFORME_TECNICO_CONTENTFLOW.md")
SALIDA_DIR = os.path.join(BASE, "informe", "build")
PDF = os.path.join(BASE, "INFORME_TECNICO_CONTENTFLOW.pdf")

COMO_GENERAR = {
    "Evidencias/Integridad_Auditoria.png": "python integridad.py",
    "Evidencias/Consultas_Lectura.png": "python consultas_negocio.py",
    "Evidencias/Consultas_Modificacion.png": "python consultas_modificacion.py",
    "Evidencias/Analitica.png": "python analitica_negocio.py --exportar",
    "Evidencias/Optimizacion_Indices.png": "python optimizacion_indices.py",
    "Evidencias/CRUD_Escenario.png": "python operaciones_crud.py",
    "Evidencias/API_Swagger.png": "uvicorn api:app --port 8000  →  http://127.0.0.1:8000/docs",
    "Evidencias/Postman_Run.png": "Postman → Run collection (colección en postman/)",
    "Evidencias/Postman_Request_Crear.png": "Postman → POST /publicaciones (respuesta 201 visible)",
    "Evidencias/Postman_Request_Leer.png": "Postman → GET /publicaciones/{id} (respuesta 200)",
    "Evidencias/DataExplorer_Verificacion.png": "Data Explorer → publicaciones → el documento creado por la API",
    "Evidencias/ConsistenciaPredeterminada.png": "Azure Portal → Cosmos DB → Configuración → Coherencia predeterminada",
    "Evidencias/Log_Extracto.png": "abrir logs/contentflow.log y capturar unas líneas",
}
pendientes = []


def pend(texto):
    pendientes.append(texto)
    return f'<div class="pend"><b>PENDIENTE</b> · {html.escape(texto)}</div>'


def imagen(ruta, pie):
    ruta_abs = os.path.join(BASE, ruta)
    if not os.path.exists(ruta_abs):
        como = COMO_GENERAR.get(ruta, "")
        return pend(f"falta la captura {ruta}" + (f" — se obtiene con: {como}" if como else ""))
    mime = mimetypes.guess_type(ruta_abs)[0] or "image/png"
    with open(ruta_abs, "rb") as f:
        datos = base64.b64encode(f.read()).decode()
    return (f'<figure><img src="data:{mime};base64,{datos}" alt="{html.escape(pie)}">'
            f"<figcaption>{html.escape(pie)}</figcaption></figure>")


def cargar_json(nombre):
    ruta = os.path.join(BASE, "resultados", nombre)
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def tabla_html(encabezados, filas):
    h = "".join(f"<th>{html.escape(str(c))}</th>" for c in encabezados)
    cuerpo = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in fila) + "</tr>" for fila in filas)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{cuerpo}</tbody></table>"


def miles(n):
    return f"{n:,}".replace(",", ".")


def csv_tabla(archivo, columnas, encabezados, maximo):
    ruta = os.path.join(BASE, "exportes", f"{archivo}.csv")
    if not os.path.exists(ruta):
        return pend(f"falta exportes/{archivo}.csv — ejecuta: python analitica_negocio.py --exportar")
    with open(ruta, encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f))[: int(maximo)]
    cols = columnas.split(",")
    return tabla_html(encabezados.split(","), [[html.escape(r.get(c, "")) for c in cols] for r in filas])


def tabla_consultas():
    datos = cargar_json("consultas_lectura.json")
    if not datos:
        return pend("faltan los resultados de las consultas — ejecuta: python consultas_negocio.py")
    filas = []
    for r in datos:
        ru = r.get("ru")
        filas.append([r["consulta"], html.escape(r["titulo"]), r["documentos"], html.escape(r["orden_en"]),
                      f"{r.get('ms_mediana', '–')} ({r.get('ms_min', '–')}–{r.get('ms_max', '–')})",
                      miles(r["bytes"]) if "bytes" in r else "–", ru if ru is not None else "n/d"])
    return tabla_html(["N°", "Consulta", "Docs", "Orden resuelto en", "Mediana ms (mín–máx)", "Bytes", "RU"], filas)


def tabla_optimizacion():
    datos = cargar_json("optimizacion_indices.json")
    if not datos:
        return pend("faltan los resultados de optimización — ejecuta: python optimizacion_indices.py")

    def celda(m):
        if "error" in m:
            return "rechazada: " + html.escape(m["error"][:80])
        ru = f" · {m['ru']} RU" if m.get("ru") is not None else ""
        return f"{m['ms_mediana']} ms · {miles(m['bytes'])} B{ru}"

    filas = []
    for r in datos:
        a, d = r["antes"], r["despues"]
        mejora = r.get("mejora_tiempo_pct")
        filas.append([html.escape(r["titulo"]), f"<small>{html.escape(a['descripcion'])}</small><br>{celda(a)}",
                      f"<small>{html.escape(d['descripcion'])}</small><br>{celda(d)}",
                      f"{mejora:+}%" if mejora is not None else "–"])
    return tabla_html(["Experimento", "Antes", "Después", "Variación de tiempo"], filas)


def extracto_log():
    ruta = os.path.join(BASE, "logs", "contentflow.log")
    if not os.path.exists(ruta):
        return pend("falta logs/contentflow.log — se crea al ejecutar cualquier script o la API")
    with open(ruta, encoding="utf-8") as f:
        lineas = [l.rstrip() for l in f if any(k in l for k in ("contentflow.api", "contentflow.crud",
                                                                 "contentflow.servicios", "contentflow.config"))]
    if not lineas:
        return pend("el log no tiene aún líneas de la API/CRUD; ejecuta la API y el CRUD")
    return "<pre><code>" + html.escape("\n".join(l[:190] for l in lineas[-14:])) + "</code></pre>"


CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 10.2pt; line-height: 1.45; color: #1d2733; }
h1 { font-size: 17pt; color: #0b3d63; border-bottom: 2px solid #0b3d63; padding-bottom: 3px; margin-top: 26px; page-break-after: avoid; }
h1:first-of-type { margin-top: 0; }
h2 { font-size: 13pt; color: #0b3d63; margin-top: 18px; page-break-after: avoid; }
h3 { font-size: 11pt; color: #234; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 9pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th { background: #0b3d63; color: #fff; text-align: left; padding: 4px 6px; }
td { border: 1px solid #c9d3dc; padding: 3px 6px; vertical-align: top; }
tbody tr:nth-child(even) td { background: #f4f7fa; }
code { font-family: Consolas, 'Courier New', monospace; font-size: 8.8pt; background: #eef2f6; padding: 0 2px; border-radius: 2px; }
pre { background: #f1f4f8; border: 1px solid #d6dde5; border-radius: 4px; padding: 7px 9px; overflow-x: auto; white-space: pre-wrap; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
figure { margin: 10px 0 14px; text-align: center; page-break-inside: avoid; }
figure img { max-width: 100%; max-height: 135mm; border: 1px solid #d0d7de; }
figcaption { font-size: 8.8pt; color: #4a5a6a; margin-top: 3px; }
.pend { background: #fff3bf; border: 1.5px dashed #c58b00; color: #5c4400; padding: 6px 9px; margin: 8px 0; font-size: 9pt; border-radius: 4px; }
hr { border: none; border-top: 1px solid #c9d3dc; margin: 14px 0; }
small { color: #556; }
"""


def main():
    os.makedirs(SALIDA_DIR, exist_ok=True)
    with open(MD, encoding="utf-8") as f:
        texto = f.read()

    # los marcadores se reemplazan por un token de una sola línea y luego por HTML crudo
    bloques = {}

    def guardar(h):
        clave = f"@@BLOQUE{len(bloques)}@@"
        bloques[clave] = h
        return f"\n\n{clave}\n\n"

    texto = re.sub(r"\{\{IMG:([^|}]+)\|([^}]+)\}\}", lambda m: guardar(imagen(m[1].strip(), m[2].strip())), texto)
    texto = re.sub(r"\{\{CSV:([^|}]+)\|([^|}]+)\|([^|}]+)\|(\d+)\}\}",
                   lambda m: guardar(csv_tabla(*[g.strip() for g in m.groups()])), texto)
    texto = texto.replace("{{CONSULTAS}}", guardar(tabla_consultas()))
    texto = texto.replace("{{OPTIMIZACION}}", guardar(tabla_optimizacion()))
    texto = texto.replace("{{LOGEXTRACTO}}", guardar(extracto_log()))
    texto = re.sub(r"\{\{PENDIENTE:([^}]+)\}\}", lambda m: guardar(pend(m[1].strip())), texto)
    version = ("2.0 · Final" if not pendientes else f"2.0 · BORRADOR ({len(pendientes)} pendientes por completar)")
    texto = texto.replace("{{VERSION}}", version)

    try:
        import markdown
    except ImportError:
        print("Falta el paquete 'markdown': pip install markdown playwright")
        return 1
    sobrantes = re.findall(r"\{\{[^}]*\}?\}?", texto)
    if sobrantes:
        print(f"[AVISO] marcadores sin procesar en la plantilla: {sobrantes[:5]}")
    cuerpo = markdown.markdown(texto, extensions=["tables", "fenced_code", "sane_lists"])
    for clave, h in bloques.items():
        cuerpo = cuerpo.replace(f"<p>{clave}</p>", h).replace(clave, h)
    documento = (f"<!doctype html><html lang='es'><head><meta charset='utf-8'>"
                 f"<title>Informe técnico ContentFlow</title><style>{CSS}</style></head><body>{cuerpo}</body></html>")
    ruta_html = os.path.join(SALIDA_DIR, "informe.html")
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(documento)
    print(f"HTML: {ruta_html}")

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            nav = p.chromium.launch()
            pagina = nav.new_page()
            pagina.goto("file://" + ruta_html)
            pagina.pdf(path=PDF, format="A4", print_background=True,
                       margin={"top": "18mm", "bottom": "20mm", "left": "16mm", "right": "16mm"},
                       display_header_footer=True, header_template="<span></span>",
                       footer_template="<div style='font-size:8px;width:100%;text-align:center;color:#667'>"
                                       "ContentFlow · BDY0101 · Duoc UC Puerto Montt · página "
                                       "<span class='pageNumber'></span> de <span class='totalPages'></span></div>")
            nav.close()
        print(f"PDF:  {PDF}")
    except Exception as e:  # noqa: BLE001
        print(f"[AVISO] No se pudo generar el PDF automáticamente ({e}).\n"
              f"        Abre {ruta_html} en Chrome y usa Imprimir > Guardar como PDF.")

    print(f"\nVersión: {version}")
    for i, t in enumerate(pendientes, 1):
        print(f"  {i}. PENDIENTE: {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
