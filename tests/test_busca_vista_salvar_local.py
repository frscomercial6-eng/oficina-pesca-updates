from __future__ import annotations

import queue
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

import config
import tela_os

F = tela_os.FrmOS


class SyncThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target

    def start(self):
        self._target()


class Harness:
    _salvar_diagrama_silencioso = F._salvar_diagrama_silencioso

    def __init__(self):
        self._callbacks_busca_vista = queue.Queue()
        self.status = []

    def _atualizar_status_busca_diagrama(self, texto, cor=None, **kw):
        self.status.append(texto)

    def _post_drive_evento(self, *a, **k):
        raise AssertionError("transmissão não permitida")


class TestSalvarReferenciaLocal(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE esquemas_vistas (id INTEGER PRIMARY KEY, fabricante TEXT, modelo TEXT, url TEXT, origem TEXT)"
        )

    def _salvar(self, harness, *args, **kwargs):
        sync_mock = MagicMock()
        rede = MagicMock(side_effect=AssertionError("rede não permitida"))
        with patch.object(tela_os, "get_db_connection", return_value=self.conn), \
             patch.object(tela_os, "salvar_link_alerta_conhecimento", sync_mock), \
             patch.object(config, "salvar_link_alerta_conhecimento", sync_mock), \
             patch.object(config, "adicionar_linha_planilha", rede), \
             patch.object(tela_os.urllib.request, "urlopen", rede), \
             patch.object(tela_os.threading, "Thread", SyncThread):
            harness._salvar_diagrama_silencioso(*args, **kwargs)
        while not harness._callbacks_busca_vista.empty():
            harness._callbacks_busca_vista.get()()
        return sync_mock, rede

    def test_saves_only_locally_without_any_external_call(self):
        harness = Harness()
        sync_mock, rede = self._salvar(
            harness, "SUMAX", "AKITA 2", "https://exemplo.com/akita2.pdf",
            {"partes": [{"codigo": "1"}]}, "Maruri Fishing",
        )

        sync_mock.assert_not_called()
        rede.assert_not_called()
        self.assertEqual(
            self.conn.execute("SELECT fabricante, modelo, url, origem FROM esquemas_vistas").fetchall(),
            [("SUMAX", "AKITA 2", "https://exemplo.com/akita2.pdf", "Maruri Fishing")],
        )
        self.assertEqual(harness.status, ["Referência técnica salva localmente neste computador."])

    def test_equipment_text_with_customer_data_is_not_transmitted(self):
        harness = Harness()
        termo = "Sumax Akita 2 - cliente João Silva tel 11 99999-8888 cabo quebrado"
        fabricante, modelo = harness_extrair(termo)
        sync_mock, rede = self._salvar(
            harness, fabricante, modelo, "https://exemplo.com/akita2.pdf", {"modelo": termo}, "Maruri Fishing"
        )

        sync_mock.assert_not_called()
        rede.assert_not_called()
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM esquemas_vistas").fetchone()[0], 1)

    def test_local_failure_is_reported_without_sync(self):
        harness = Harness()
        self.conn.execute("DROP TABLE esquemas_vistas")
        sync_mock, _ = self._salvar(harness, "SUMAX", "AKITA 2", "https://exemplo.com/a")

        sync_mock.assert_not_called()
        self.assertEqual(harness.status, ["Não foi possível salvar a referência técnica localmente."])


def harness_extrair(termo):
    class H:
        _normalizar_termo_tecnico = F._normalizar_termo_tecnico
        _extrair_fabricante_modelo = F._extrair_fabricante_modelo

    return H()._extrair_fabricante_modelo(termo)


if __name__ == "__main__":
    unittest.main()
