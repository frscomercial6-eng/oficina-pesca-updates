# -*- coding: utf-8 -*-
"""Teste da integracao da Busca de Estoque com o carrinho do PDV.

Valida o nucleo da alteracao em pdv.py/_abrir_busca_estoque -> confirmar_selecao:
ao confirmar um produto (duplo clique/ENTER/botao), o item precisa ser adicionado
ao carrinho com (id, nome, preco_unitario, quantidade) e os totais recalculados.
"""
import os
import sys

# Garante que a raiz do projeto seja o primeiro item do sys.path quando o
# teste e executado diretamente (python tests/test_pdv_busca_estoque.py).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Mock: evita chamar messagebox.showwarning/showinfo em ambiente headless
# (necessita root.tk). Neste teste validamos apenas a logica de carrinho.
import unittest.mock as _mock
if not hasattr(_mock, "_patched"):
    _mock.patch("pdv.messagebox.showwarning").start()
    _mock.patch("pdv.messagebox.showinfo").start()
    _mock._patched = True

import pdv


class _FakePDV:
    """Simula apenas a parte do carrinho usada por _adicionar_item_no_carrinho."""

    def __init__(self):
        self._carrinho = []
        self.total_item = 0.0
        self.total_carrinho = 0.0

    def _renderizar_carrinho(self):
        # No PDV real, _renderizar_carrinho chama _atualizar_resumo -> totais.
        self.total_carrinho = self._total_itens()

    def _total_itens(self):
        return float(sum(i["total_item"] for i in self._carrinho))


def test_to_float_preco_com_virgula():
    # A Tree do popup exibe o preco formatado com virgula ("29,90").
    assert pdv._to_float("29,90") == 29.9
    assert pdv._to_float("1.234,56") == 1234.56


def test_adicionar_item_novo():
    pdv_obj = _FakePDV()
    ret = pdv.FrmPDV._adicionar_item_no_carrinho(
        pdv_obj,
        row=(1, "MANIVELA MOLINETE GRANDE", 29.9, 10),
        qtd=2,
    )
    assert ret is True
    assert len(pdv_obj._carrinho) == 1
    item = pdv_obj._carrinho[0]
    assert item["produto_id"] == 1
    assert item["nome_produto"] == "MANIVELA MOLINETE GRANDE"
    assert item["preco_unitario"] == 29.9
    assert item["quantidade"] == 2
    assert item["total_item"] == 59.8
    # Renderizacao (recalculo de totais) foi executada.
    assert pdv_obj.total_carrinho == 59.8


def test_adicionar_mesmo_produto_acumula_qtd():
    pdv_obj = _FakePDV()
    pdv.FrmPDV._adicionar_item_no_carrinho(pdv_obj, row=(2, "PROD B", 10.0, 5), qtd=1)
    pdv.FrmPDV._adicionar_item_no_carrinho(pdv_obj, row=(2, "PROD B", 10.0, 5), qtd=1)
    assert len(pdv_obj._carrinho) == 1
    assert pdv_obj._carrinho[0]["quantidade"] == 2
    assert pdv_obj.total_carrinho == 20.0


def test_estoque_insuficiente_nao_adiciona():
    pdv_obj = _FakePDV()
    ret = pdv.FrmPDV._adicionar_item_no_carrinho(pdv_obj, row=(3, "PROD C", 5.0, 1), qtd=5)
    assert ret is False
    assert len(pdv_obj._carrinho) == 0


if __name__ == "__main__":
    test_to_float_preco_com_virgula()
    test_adicionar_item_novo()
    test_adicionar_mesmo_produto_acumula_qtd()
    test_estoque_insuficiente_nao_adiciona()
    print("TESTE_PDV_CARRINHO_OK")