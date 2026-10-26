import pytest

import validaciones as v


def pub_valida(**extra):
    d = {"usuario_id": "user_1", "contenido": "Hola", "fecha_publicacion": "2025-07-01T10:00:00",
         "categoria": "Cultura", "tipo": "Texto", "hashtags": ["#cultura"]}
    d.update(extra)
    return d


def test_publicacion_valida():
    assert v.validar_publicacion(pub_valida())["categoria"] == "Cultura"


@pytest.mark.parametrize("campo,valor", [
    ("categoria", "Cocina"), ("tipo", "Audio"), ("contenido", "   "),
    ("usuario_id", "sin-formato"), ("fecha_publicacion", "01/07/2025"),
    ("hashtags", []), ("hashtags", ["sin_numeral"]), ("hashtags", ["#a", "#a"]),
])
def test_publicacion_invalida(campo, valor):
    with pytest.raises(v.ErrorValidacion):
        v.validar_publicacion(pub_valida(**{campo: valor}))


def test_acumula_todos_los_errores():
    with pytest.raises(v.ErrorValidacion) as e:
        v.validar_publicacion({})
    assert len(e.value.errores) >= 6


def test_campos_desconocidos_rechazados():
    with pytest.raises(v.ErrorValidacion):
        v.validar_publicacion(pub_valida(admin=True))


def test_cuerpo_no_objeto():
    with pytest.raises(v.ErrorValidacion):
        v.validar_publicacion(["no", "objeto"])


def test_actualizacion_parcial():
    assert v.validar_publicacion({"contenido": "nuevo"}, parcial=True) == {"contenido": "nuevo"}


def test_usuario_correo_invalido():
    with pytest.raises(v.ErrorValidacion):
        v.validar_usuario({"nombre": "Ana", "correo": "ana-arroba.cl", "pais": "Chile",
                           "genero": "Otro", "dispositivo": "Móvil",
                           "fecha_registro": "2025-01-01T00:00:00"})


def test_reaccion_tipo_invalido():
    with pytest.raises(v.ErrorValidacion):
        v.validar_reaccion({"usuario_id": "user_1", "publicacion_id": "pub_1",
                            "tipo_reaccion": "Me divierte", "fecha": "2025-01-01T00:00:00"})


@pytest.mark.parametrize("likes", [-1, 1.5, "3", True])
def test_comentario_likes_invalidos(likes):
    with pytest.raises(v.ErrorValidacion):
        v.validar_comentario({"usuario_id": "user_1", "publicacion_id": "pub_1",
                              "comentario": "ok", "fecha": "2025-01-01T00:00:00", "likes": likes})


def test_formato_fecha_igual_al_dataset():
    assert len(v.ahora_iso()) == 19 and v.parsear_fecha(v.ahora_iso())
