import marshal
import zipfile

import pytest

from tools.verificar_pacote_release import (
    _verificar_bytes,
    _verificar_nome,
    verificar_zip,
)


def test_scanner_rejeita_credencial_embutida_em_codigo():
    segredo = "GOCSPX-" + "x" * 24
    codigo = compile(f"def f(): return {segredo!r}", "sintetico.py", "exec")
    with pytest.raises(RuntimeError):
        _verificar_bytes(marshal.dumps(codigo), "executavel")
    with pytest.raises(RuntimeError):
        _verificar_bytes(segredo.encode(), "recurso")
    with pytest.raises(RuntimeError):
        _verificar_nome("assets/client_secret_desktop.json")


def test_zip_deve_corresponder_integralmente_ao_stage(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "arquivo.txt").write_text("seguro", encoding="utf-8")
    pacote = tmp_path / "pacote.zip"
    with zipfile.ZipFile(pacote, "w") as arquivo:
        arquivo.write(stage / "arquivo.txt", "arquivo.txt")
    verificar_zip(pacote, stage)
    (stage / "arquivo.txt").write_text("alterado", encoding="utf-8")
    with pytest.raises(RuntimeError):
        verificar_zip(pacote, stage)
