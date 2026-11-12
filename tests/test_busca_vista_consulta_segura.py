from __future__ import annotations

import queue
import unittest
from unittest.mock import patch
from urllib.parse import unquote_plus

import tela_os
import busca_vista_fontes

F = tela_os.FrmOS


class Harness:
    _normalizar_termo_tecnico = F._normalizar_termo_tecnico
    _variantes_modelo = F._variantes_modelo
    _extrair_fabricante_modelo = F._extrair_fabricante_modelo
    _equipamento_seguro_para_consulta = F._equipamento_seguro_para_consulta
    _extrair_pecas_pagina_tecnica = F._extrair_pecas_pagina_tecnica
    _extrair_conhecimento_pagina_tecnica = F._extrair_conhecimento_pagina_tecnica
    _buscar_links_web_diagrama = F._buscar_links_web_diagrama
    _normalizar_link_resultado = F._normalizar_link_resultado
    _link_eh_tecnico_valido = F._link_eh_tecnico_valido
    _pontuar_link_diagrama = F._pontuar_link_diagrama
    _tipo_documentacao_tecnica = F._tipo_documentacao_tecnica
    _rotulo_fonte_tecnica = F._rotulo_fonte_tecnica
    _executar_busca_filtrada_bg = F._executar_busca_filtrada_bg
    _descobrir_catalogo_busca_vista = F._descobrir_catalogo_busca_vista

    def __init__(self):
        self.urls = []
        self._callbacks_busca_vista = queue.Queue()
        self.concluidos = []

    def _buscar_pagina_tecnica(self, url, timeout):
        self.urls.append(url)
        return "<html><body>Catalogo</body></html>", "text/html"

    def _concluir_busca_vista(self, termo, resultados, cancelada=False, erro=False, mensagem="", catalogo=None):
        self.concluidos.append((resultados, cancelada, erro, mensagem))

    def consultas(self):
        return [unquote_plus(u.split("q=", 1)[1]) for u in self.urls if "duckduckgo.com" in u]


class TestConsultaExterna(unittest.TestCase):
    def setUp(self):
        tela_os._limpar_cache_busca_vista()

    def test_os_text_with_personal_data_never_reaches_external_requests(self):
        original = "Sumax Akita 2 - cliente João Silva tel 11 99999-8888 obs: cabo quebrado"
        copia = str(original)
        h = Harness()
        seguro = h._equipamento_seguro_para_consulta(original)
        self.assertEqual(seguro, ("SUMAX", "AKITA 2"))
        h._buscar_links_web_diagrama(*h._extrair_fabricante_modelo(original))

        enviado = " ".join(h.urls).upper()
        for proibido in ("JOAO", "JOÃO", "SILVA", "99999", "8888", "CLIENTE", "CABO", "QUEBRADO", "OBS", "TEL"):
            self.assertNotIn(proibido, unquote_plus(enviado))
        self.assertTrue(h.consultas())
        self.assertEqual(original, copia)

    def test_personal_data_without_separator_blocks_the_query(self):
        h = Harness()
        for texto in (
            "Sumax Akita 2 11999998888",
            "Sumax Akita 2 11 99999-8888",
            "Sumax Akita 2 serie 123456",
            "Sumax Akita 2 joao@email.com",
            "Sumax Akita 2 Rua das Flores 10",
            "Sumax Akita 2 obs cabo quebrado",
        ):
            self.assertIsNone(h._equipamento_seguro_para_consulta(texto), texto)
            h._buscar_links_web_diagrama(*h._extrair_fabricante_modelo(texto))
        self.assertEqual(h.urls, [])

    def test_allowed_and_blocked_equipment_identifications(self):
        h = Harness()
        seguro = h._equipamento_seguro_para_consulta
        self.assertEqual(seguro("SUMAX AKITA 2"), ("SUMAX", "AKITA 2"))
        self.assertEqual(seguro("SUMAX AKITA II"), ("SUMAX", "AKITA II"))
        self.assertEqual(seguro("MARURI BLACK PIRA BG 400"), ("MARURI", "BLACK PIRA BG 400"))
        self.assertEqual(seguro("MARURI BLACK PIRA BG 400 - CLIENTE JOAO"), ("MARURI", "BLACK PIRA BG 400"))
        self.assertEqual(seguro("Sumax Akita 2, tel 11 99999-8888"), ("SUMAX", "AKITA 2"))
        self.assertIsNone(seguro("SUMAX AKITA JOAO"))
        self.assertIsNone(seguro("SUMAX AKITA 2 JOAO"))
        self.assertIsNone(seguro("MARURI BLACK PIRA BG 400 JOAO SILVA"))
        self.assertIsNone(seguro("SUMAX JOAO"))

    def test_sumax_akita_2_generates_valid_technical_queries(self):
        h = Harness()
        h._buscar_links_web_diagrama("SUMAX", "AKITA 2")
        consultas = h.consultas()
        self.assertTrue(consultas)
        self.assertTrue(all("AKITA" in c.upper() for c in consultas))
        self.assertTrue(any("AKITA II" in c.upper() for c in consultas))
        self.assertTrue(any("AKITA2" in c.upper() for c in consultas))
        self.assertTrue(any("SUMAX" in c.upper() for c in consultas))

    def test_maruri_black_pira_bg_400_generates_valid_technical_queries(self):
        h = Harness()
        self.assertEqual(
            h._equipamento_seguro_para_consulta("Carretilha Maruri Black Pira BG 400"),
            ("MARURI", "BLACK PIRA BG 400"),
        )
        h._buscar_links_web_diagrama("MARURI", "BLACK PIRA BG 400")
        consultas = h.consultas()
        self.assertTrue(consultas)
        self.assertTrue(all("BLACK PIRA BG 400" in c.upper() for c in consultas[:3]))
        self.assertTrue(any("maruri" in u for u in h.urls))

    def test_roman_and_arabic_variants_are_kept(self):
        h = Harness()
        self.assertEqual(h._variantes_modelo("Akita 2"), ["AKITA II", "AKITA2"])
        self.assertEqual(h._variantes_modelo("Akita II"), ["AKITA2"])
        self.assertEqual(
            h._normalizar_termo_tecnico("Akita II", separar_alfanumerico=True),
            h._normalizar_termo_tecnico("Akita 2", separar_alfanumerico=True),
        )
        self.assertEqual(h._equipamento_seguro_para_consulta("shimano stella 4000 xg"), ("SHIMANO", "STELLA 4000 XG"))
        self.assertEqual(h._equipamento_seguro_para_consulta("Sumax Akita II"), ("SUMAX", "AKITA II"))
        self.assertEqual(
            h._equipamento_seguro_para_consulta("Daiwa Tatula SV TW 103"),
            ("DAIWA", "TATULA SV TW 103"),
        )
        self.assertIsNone(h._equipamento_seguro_para_consulta("Daiwa Tatula SV TW 103 Joao"))

    def test_expanded_catalog_allows_known_families_and_blocks_arbitrary_words(self):
        h = Harness()
        seguro = h._equipamento_seguro_para_consulta
        self.assertEqual(seguro("Shimano Ultegra 4000 XG"), ("SHIMANO", "ULTEGRA 4000 XG"))
        self.assertEqual(seguro("Daiwa Caldia 3000"), ("DAIWA", "CALDIA 3000"))
        self.assertEqual(seguro("Okuma Salina"), ("OKUMA", "SALINA"))
        self.assertEqual(seguro("Penn Battle 4000"), ("PENN", "BATTLE 4000"))
        self.assertEqual(seguro("Abu Garcia Revo 5"), ("ABU GARCIA", "REVO 5"))
        self.assertEqual(seguro("Marine Sports BG 400"), ("MARINE SPORTS", "BG 400"))
        for texto in ("Shimano Ultegra Maria", "Daiwa Joao 3000", "Albatroz Carlos", "Pinnacle Silva 4000", "Marine Sports Pedro"):
            self.assertIsNone(seguro(texto), texto)

    def test_site_restricted_queries_use_only_known_domains(self):
        h = Harness()
        h._buscar_links_web_diagrama("KASTKING", "SHARKY 3000")
        consultas = h.consultas()
        self.assertTrue(any(c.startswith("site:kastking.com") for c in consultas))
        self.assertTrue(any(c.startswith("site:reelschematic.com") for c in consultas))
        for c in consultas:
            self.assertNotIn("JOAO", c.upper())

    def test_source_labels_for_known_brands(self):
        h = Harness()
        self.assertEqual(h._rotulo_fonte_tecnica("https://www.daisen.com.br/p/1"), "Daisen")
        self.assertEqual(h._rotulo_fonte_tecnica("https://www.daiwa.com/x"), "Daiwa")

    def test_part_extraction_rejects_phone_and_serial_like_values(self):
        self.assertTrue(tela_os._peca_parece_dado_pessoal("11999998888", "Mola"))
        self.assertTrue(tela_os._peca_parece_dado_pessoal("RD-1", "Contato 11 99999-8888"))
        self.assertFalse(tela_os._peca_parece_dado_pessoal("RD2345", "Engrenagem principal"))
        h = Harness()
        pecas = h._extrair_pecas_pagina_tecnica(
            "<table><tr><td>11999998888</td><td>Mola</td></tr><tr><td>RD2345</td><td>Engrenagem principal</td></tr></table>"
        )
        codigos = [p["codigo"] for p in pecas]
        self.assertIn("RD2345", codigos)
        self.assertNotIn("11999998888", codigos)

    def test_search_engine_anti_bot_page_is_reported_as_limitation_not_empty_result(self):
        class Anomalia(Harness):
            def _buscar_pagina_tecnica(self, url, timeout):
                self.urls.append(url)
                if "duckduckgo.com" in url:
                    return '<html><div class="anomaly-modal__title">Unfortunately, bots use DuckDuckGo too.</div></html>', "text/html"
                return "<html><body>Catalogo</body></html>", "text/html"

        h = Anomalia()
        h._buscar_links_web_diagrama("SHIMANO", "STELLA 4000 XG")
        self.assertTrue(any("verificação anti-robô" in x for x in h._ultima_busca_limitacoes))
        tela_os._limpar_cache_busca_vista()

    def test_home_locale_and_login_pages_are_not_technical_links(self):
        h = Harness()
        for url in ("https://marurifishing.com.py", "https://marurifishing.com.py/locale/es", "https://marurifishing.com.py/login"):
            self.assertFalse(h._link_eh_tecnico_valido(url), url)
        self.assertTrue(h._link_eh_tecnico_valido("https://marurifishing.com.py/produto/pecas-carretilha-black-pira-bg-400"))

    def test_no_query_when_manufacturer_or_model_is_not_safe(self):
        h = Harness()
        for texto in ("", "carretilha", "Sumax", "Fulano Silva 11 99999-8888", "reel quebrado cliente Maria", "Sumax - cliente Maria"):
            self.assertIsNone(h._equipamento_seguro_para_consulta(texto), texto)
            h._buscar_links_web_diagrama(*h._extrair_fabricante_modelo(texto))
        self.assertEqual(h.urls, [])

    def test_unsafe_equipment_reports_message_and_sends_nothing(self):
        h = Harness()
        cancelamento = tela_os.threading.Event()
        h._executar_busca_filtrada_bg("Maria 11 99999-8888", cancelamento)
        h._callbacks_busca_vista.get_nowait()()

        self.assertEqual(h.urls, [])
        resultados, cancelada, erro, mensagem = h.concluidos[0]
        self.assertEqual(resultados, [])
        self.assertIn("identificar fabricante e modelo", mensagem)

    def test_safe_equipment_runs_search_in_background_worker(self):
        h = Harness()
        h._executar_busca_filtrada_bg("Sumax Akita 2 - cliente Joao", tela_os.threading.Event())
        h._callbacks_busca_vista.get_nowait()()

        self.assertTrue(h.urls)
        self.assertEqual(h.concluidos[0][3], "")
        self.assertNotIn("JOAO", unquote_plus(" ".join(h.urls)).upper())

    def test_modelo_nao_cadastrado_e_comparado_localmente_sem_transmitir_os(self):
        class Catalogo(Harness):
            def _buscar_pagina_tecnica(self, url, timeout):
                self.urls.append(url)
                return '<html><a href="/diagrama-kratos-20.pdf">Kratos 20</a></html>', "text/html"

            def _concluir_busca_vista(self, termo, resultados, cancelada=False, erro=False, mensagem="", catalogo=None):
                self.concluidos.append((mensagem, catalogo))

        h = Catalogo()
        busca_vista_fontes.limpar_cache_fontes()
        with patch.dict(busca_vista_fontes.FONTES_INICIAIS, {
            "SAINT": (("Saint", "https://catalogo.test/"),)
        }):
            h._executar_busca_filtrada_bg("Saint Kratos - cliente João", tela_os.threading.Event())
            h._callbacks_busca_vista.get_nowait()()
        mensagem, catalogo = h.concluidos[0]
        self.assertEqual(mensagem, "")
        self.assertEqual(catalogo[0][0]["nome"], "Kratos 20")
        self.assertTrue(catalogo[0][0]["validado_no_catalogo"])
        self.assertEqual(h.urls, ["https://catalogo.test/"])
        busca_vista_fontes.limpar_cache_fontes()


if __name__ == "__main__":
    unittest.main()
