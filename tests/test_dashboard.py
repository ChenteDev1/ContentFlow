import json
import re

import generar_dashboard as gd


def test_dashboard_se_genera_con_datos_reales(tmp_path, monkeypatch, db):
    destino = tmp_path / "index.html"
    monkeypatch.setattr(gd, "SALIDA", str(destino))
    assert gd.main(["--local"]) == 0
    html = destino.read_text(encoding="utf-8")
    assert "/*__DATOS__*/null" not in html
    datos = json.loads(re.search(r"const D = (\{.*?\});\nconst nf", html, re.S).group(1).replace("<\\/", "</"))
    assert datos["conteos"]["usuarios"] == 500
    assert len(datos["usuarios_activos"]) == 10 and len(datos["horas"]) == 24
    assert datos["auditoria"]["reacciones_duplicadas_mismo_usuario_y_publicacion"] == 1
    assert sum(a["usuarios"] for a in datos["audiencia"]["dispositivo"]) == 500
