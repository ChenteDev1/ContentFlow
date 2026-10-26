import pytest
from fastapi.testclient import TestClient

import api


@pytest.fixture()
def cliente(db):
    api._db = None  # fuerza a tomar la base simulada inyectada por la fixture
    return TestClient(api.app)


def test_salud(cliente):
    r = cliente.get("/salud")
    assert r.status_code == 200 and r.json()["estado"] == "ok"
    assert r.json()["documentos"]["usuarios"] == 500
    assert "X-Request-ID" in r.headers and "X-Process-Time-ms" in r.headers


def test_listar_con_filtro_y_paginacion(cliente):
    r = cliente.get("/publicaciones", params={"categoria": "Deportes", "limite": 5, "pagina": 2})
    j = r.json()
    assert r.status_code == 200 and j["total"] == 100 and len(j["datos"]) == 5
    fechas = [p["fecha_publicacion"] for p in j["datos"]]
    assert fechas == sorted(fechas, reverse=True)


def test_ciclo_completo_por_http(cliente):
    cuerpo = {"usuario_id": "user_1", "contenido": "Desde Postman", "categoria": "Tecnología",
              "tipo": "Texto", "hashtags": ["#Azure"], "fecha_publicacion": "2026-06-01T10:00:00"}
    c = cliente.post("/publicaciones", json=cuerpo)
    assert c.status_code == 201
    pid = c.json()["_id"]
    assert cliente.get(f"/publicaciones/{pid}").json()["contenido"] == "Desde Postman"
    u = cliente.put(f"/publicaciones/{pid}", json={"contenido": "Editado"})
    assert u.status_code == 200 and u.json()["contenido"] == "Editado"
    rc = cliente.post("/reacciones", json={"usuario_id": "user_2", "publicacion_id": pid,
                                           "tipo_reaccion": "Me gusta", "fecha": "2026-06-01T11:00:00"})
    assert rc.status_code == 201
    assert cliente.get(f"/publicaciones/{pid}").json()["reacciones"] == 1
    d = cliente.delete(f"/publicaciones/{pid}")
    assert d.status_code == 200 and d.json()["reacciones"] == 1
    assert cliente.get(f"/publicaciones/{pid}").status_code == 404


@pytest.mark.parametrize("metodo,ruta,cuerpo,estado", [
    ("post", "/publicaciones", {"usuario_id": "user_1"}, 422),
    ("post", "/publicaciones", {"usuario_id": "user_x9999", "contenido": "x", "categoria": "Cultura",
                                "tipo": "Texto", "hashtags": ["#a"]}, 409),
    ("put", "/publicaciones/pub_1", {"usuario_id": "user_2"}, 422),
    ("put", "/publicaciones/no_existe_1", {"contenido": "x"}, 404),
    ("delete", "/publicaciones/no_existe_1", None, 404),
    ("post", "/reacciones", {"usuario_id": "user_1", "publicacion_id": "pub_1", "tipo_reaccion": "Wow"}, 422),
    ("get", "/publicaciones?categoria=Cocina", None, 422),
    ("get", "/publicaciones?limite=1000", None, 422),
])
def test_errores_controlados(cliente, metodo, ruta, cuerpo, estado):
    r = getattr(cliente, metodo)(ruta, **({"json": cuerpo} if cuerpo is not None else {}))
    assert r.status_code == estado
    assert r.headers["X-Request-ID"]


def test_analitica(cliente):
    assert len(cliente.get("/analitica/usuarios-activos?top=3").json()) == 3
    assert len(cliente.get("/analitica/horarios").json()) == 4


def test_base_caida_devuelve_503_sin_filtrar_detalles(cliente, monkeypatch):
    from pymongo.errors import ServerSelectionTimeoutError

    def falla():
        raise ServerSelectionTimeoutError("mongodb://user:SECRETA@host timeout")

    monkeypatch.setattr(api, "db", falla)
    r = cliente.get("/publicaciones")
    assert r.status_code == 503
    assert "SECRETA" not in r.text
