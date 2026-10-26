import integridad as ig
import servicios as s


def test_auditoria_detecta_los_problemas_conocidos_del_dataset(db):
    h = ig.auditar(db)
    assert h["publicaciones_con_usuario_inexistente"]["cantidad"] == 0
    assert h["reacciones_con_usuario_o_publicacion_inexistente"]["cantidad"] == 0
    assert h["reacciones_duplicadas_mismo_usuario_y_publicacion"]["cantidad"] == 1
    assert h["publicaciones_anteriores_al_registro_del_usuario"]["cantidad"] == 48
    assert h["reacciones_anteriores_a_su_publicacion"]["cantidad"] == 245
    assert h["comentarios_anteriores_a_su_publicacion"]["cantidad"] == 251


def test_correccion_elimina_duplicados_y_marca_fechas(db):
    assert ig.corregir_duplicados_reacciones(db) == 1
    assert ig.auditar(db)["reacciones_duplicadas_mismo_usuario_y_publicacion"]["cantidad"] == 0
    marcados = ig.marcar_inconsistencias_temporales(db)
    assert marcados["reacciones"] > 0 and db.reacciones.count_documents({}) == 499
    assert db.comentarios.count_documents({}) == 500  # marcar no borra


def test_borrar_publicacion_con_servicio_no_crea_huerfanos(db):
    s.eliminar_publicacion(db, "pub_1")
    h = ig.auditar(db)
    assert h["reacciones_con_usuario_o_publicacion_inexistente"]["cantidad"] == 0
    assert h["comentarios_con_usuario_o_publicacion_inexistente"]["cantidad"] == 0
    assert h["campañas_con_publicaciones_inexistentes"]["cantidad"] == 0


def test_borrar_directo_si_crea_huerfanos(db):
    """Demuestra el problema que el borrado en cascada evita."""
    pid = db.reacciones.find_one()["publicacion_id"]
    db.publicaciones.delete_one({"_id": pid})
    assert ig.auditar(db)["reacciones_con_usuario_o_publicacion_inexistente"]["cantidad"] >= 1
