# -*- coding: utf-8 -*-
import os
import json
import threading
import unicodedata
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from xml.dom import minidom
from xml.etree import ElementTree as ET

import customtkinter as ctk

from config import CAMINHO_BANCO, get_db_connection
from configuracao_fiscal import tentar_enviar_venda
from dados_oficina import obter_dados_oficina

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    _REPORTLAB_OK = True
except Exception:
    _REPORTLAB_OK = False


def _patch_ctklabel_destroy_safely():
    """Workaround global para evitar excecao de destroy em CTkLabel sem _font."""
    try:
        if getattr(ctk.CTkLabel, "_ofp_safe_destroy_patched", False):
            return
        original_destroy = ctk.CTkLabel.destroy

        def safe_destroy(widget):
            try:
                if not hasattr(widget, "_font"):
                    widget._font = None
            except Exception:
                pass
            try:
                original_destroy(widget)
            except Exception:
                try:
                    tk.Label.destroy(widget)
                except Exception:
                    pass

        ctk.CTkLabel.destroy = safe_destroy
        ctk.CTkLabel._ofp_safe_destroy_patched = True
    except Exception:
        pass


_patch_ctklabel_destroy_safely()


def _to_float(valor):
    try:
        return float(str(valor).replace(",", "."))
    except Exception:
        return 0.0


def _fmt_moeda(valor):
    return f"R$ {float(valor or 0):.2f}".replace(".", ",")


def _normalizar_texto_pagamento(valor):
    txt = str(valor or "").strip().upper()
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    return " ".join(txt.replace("_", " ").replace("-", " ").split())


def _mapear_tpag_fiscal(metodo_pagamento):
    # Codigos oficiais de tPag usados em NF-e/NFC-e (layout 4.00 e NTs vigentes).
    metodo = _normalizar_texto_pagamento(metodo_pagamento)
    if not metodo:
        return "99"

    if "PIX" in metodo or "INSTANTANEO" in metodo:
        return "17"
    if "DINHEIRO" in metodo or metodo in {"CASH", "ESPECIE"}:
        return "01"
    if "CHEQUE" in metodo:
        return "02"
    if "DEBITO" in metodo:
        return "04"
    if "CREDITO" in metodo:
        return "03"
    if "CARTAO" in metodo:
        # Sem detalhamento credito/debito no PDV: assume credito como padrao de mercado.
        return "03"
    if "CREDIARIO" in metodo or "CREDITO LOJA" in metodo:
        return "05"
    if "VALE ALIMENT" in metodo:
        return "10"
    if "VALE REFEICAO" in metodo:
        return "11"
    if "VALE PRESENTE" in metodo:
        return "12"
    if "VALE COMBUST" in metodo:
        return "13"
    if "DUPLICATA" in metodo:
        return "14"
    if "BOLETO" in metodo:
        return "15"
    if "DEPOSITO" in metodo:
        return "16"
    if "TRANSFERENCIA" in metodo or "TED" in metodo or "DOC" in metodo:
        return "18"
    if "CARTEIRA DIGITAL" in metodo:
        return "18"
    if "FIDELIDADE" in metodo or "CASHBACK" in metodo or "CREDITO VIRTUAL" in metodo:
        return "19"
    if "SEM PAGAMENTO" in metodo:
        return "90"
    return "99"


class FrmPDV(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("PDV - Venda de Balcao")
        self.geometry("1220x760")
        self.configure(fg_color="#0f1720")

        self._carrinho = []
        self._pagamentos = []
        self._ultima_venda = None
        self._orcamento_vinculado = None
        self._metodo_pagamento = "DINHEIRO"
        self._produto_cols = set()
        self._produto_preselecionado = None
        self._auto_impressao = ctk.BooleanVar(value=True)
        self._finalizando_venda = False

        self._garantir_tabelas_pdv()
        self._carregar_colunas_produtos()
        self._configurar_estilo_treeviews()
        self._montar_interface()
        self._configurar_atalhos()
        self.protocol("WM_DELETE_WINDOW", self._safe_destroy_window)

        self.after(80, self._aplicar_maximizacao)
        self.after(120, self._focar_busca)

    def _safe_destroy_window(self):
        try:
            if not bool(self.winfo_exists()):
                return
            try:
                for after_id in self.tk.call("after", "info"):
                    self.after_cancel(after_id)
            except Exception:
                pass
            self.withdraw()
            super().destroy()
        except Exception:
            pass

    def destroy(self):
        self._safe_destroy_window()

    def _configurar_estilo_treeviews(self):
        estilo = ttk.Style()
        try:
            estilo.theme_use("default")
        except Exception:
            pass

        estilo.configure(
            "PDV.Treeview",
            background="#111827",
            fieldbackground="#111827",
            foreground="#e5edf5",
            rowheight=30,
            borderwidth=0,
        )
        estilo.map(
            "PDV.Treeview",
            background=[("selected", "#f59e0b")],
            foreground=[("selected", "#0f1720")],
        )
        estilo.configure(
            "PDV.Treeview.Heading",
            background="#1f2937",
            foreground="#f8fafc",
            relief="flat",
            font=("Arial", 10, "bold"),
        )

    def _configurar_atalhos(self):
        self.bind("<F1>", self._atalho_finalizar)
        self.bind("<F2>", self._atalho_limpar)
        self.bind("<F3>", self._atalho_busca_estoque)
        self.bind("<Delete>", lambda _e: self._remover_item())

    def _atalho_finalizar(self, _event=None):
        self._finalizar_venda()
        return "break"

    def _atalho_limpar(self, _event=None):
        self._limpar_venda()
        return "break"

    def _atalho_busca_estoque(self, _event=None):
        self._abrir_busca_estoque()
        return "break"

    def _aplicar_maximizacao(self):
        try:
            self.state("zoomed")
            return
        except Exception:
            pass
        try:
            self.attributes("-zoomed", True)
        except Exception:
            pass

    def _garantir_tabelas_pdv(self):
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pdv_vendas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT,
                    total REAL,
                    forma_pagamento TEXT,
                    status TEXT DEFAULT 'aberto'
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pdv_itens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    venda_id INTEGER,
                    produto_id INTEGER,
                    nome_produto TEXT,
                    quantidade INTEGER,
                    preco_unitario REAL,
                    total_item REAL
                )
                """
            )

            # Migração segura para bancos já existentes.
            cur.execute("PRAGMA table_info(pdv_vendas)")
            cols_pdv_vendas = {str(row[1]).lower() for row in cur.fetchall()}
            if "data" not in cols_pdv_vendas:
                cur.execute("ALTER TABLE pdv_vendas ADD COLUMN data TEXT")
            if "forma_pagamento" not in cols_pdv_vendas:
                cur.execute("ALTER TABLE pdv_vendas ADD COLUMN forma_pagamento TEXT")
            if "status" not in cols_pdv_vendas:
                cur.execute("ALTER TABLE pdv_vendas ADD COLUMN status TEXT DEFAULT 'aberto'")

            # Compatibilidade com versão antiga: aproveita colunas existentes.
            if "data_hora" in cols_pdv_vendas:
                cur.execute(
                    """
                    UPDATE pdv_vendas
                    SET data = substr(COALESCE(data_hora, ''), 1, 10)
                    WHERE COALESCE(data, '') = ''
                    """
                )
            if "metodo_pagamento" in cols_pdv_vendas:
                cur.execute(
                    """
                    UPDATE pdv_vendas
                    SET forma_pagamento = metodo_pagamento
                    WHERE COALESCE(forma_pagamento, '') = ''
                    """
                )
            cur.execute("UPDATE pdv_vendas SET status = 'aberto' WHERE COALESCE(status, '') = ''")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS financeiro_geral (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_hora TEXT,
                    data_referencia TEXT,
                    descricao TEXT,
                    tipo TEXT,
                    total_dinheiro REAL,
                    total_pix REAL,
                    total_cartao REAL,
                    total_geral REAL,
                    detalhe_json TEXT
                )
                """
            )

            cur.execute("PRAGMA table_info(financeiro_geral)")
            cols_financeiro = {str(row[1]).lower() for row in cur.fetchall()}
            if "descricao" not in cols_financeiro:
                cur.execute("ALTER TABLE financeiro_geral ADD COLUMN descricao TEXT")
            conn.commit()

    def _carregar_colunas_produtos(self):
        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("PRAGMA table_info(produtos)")
                self._produto_cols = {str(row[1]).lower() for row in cur.fetchall()}
        except Exception:
            self._produto_cols = set()

    def _montar_interface(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        topo = ctk.CTkFrame(self, fg_color="#0d1b2a", corner_radius=8)
        topo.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        topo.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(topo, text="Qtd", font=("Arial", 11, "bold"), text_color="#dbe4ee").grid(
            row=0, column=0, padx=(10, 6), pady=8, sticky="w"
        )
        self.ent_qtd = ctk.CTkEntry(
            topo,
            width=64,
            height=30,
            justify="center",
            fg_color="#111827",
            border_color="#93c5fd",
            border_width=2,
        )
        self.ent_qtd.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="w")
        self.ent_qtd.insert(0, "1")
        self.ent_qtd.bind("<Return>", self._enter_na_qtd)

        self.ent_busca = ctk.CTkEntry(
            topo,
            placeholder_text="Produto / codigo de barras... (Enter adiciona | Tab vazio abre busca)",
            height=30,
            fg_color="#111827",
            border_color="#93c5fd",
            border_width=2,
        )
        self.ent_busca.grid(row=0, column=2, padx=(0, 8), pady=8, sticky="ew")
        self.ent_busca.bind("<Return>", self._enter_na_busca)
        self.ent_busca.bind("<Tab>", self._tab_na_busca)

        acoes_topo = ctk.CTkFrame(topo, fg_color="transparent")
        acoes_topo.grid(row=0, column=3, padx=(8, 12), pady=6, sticky="e")
        acoes_topo.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            acoes_topo,
            text="Adicionar item da Oficina",
            width=220,
            height=30,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._abrir_seletor_item_oficina,
        ).grid(row=0, column=0, sticky="e", padx=(0, 6))
        ctk.CTkButton(
            acoes_topo,
            text="Buscar Produto",
            width=170,
            height=30,
            fg_color="#0ea5e9",
            hover_color="#0284c7",
            command=self._abrir_busca_estoque,
        ).grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(
            acoes_topo,
            text="F1 Finaliza | F2 Limpa | F3 Busca | Delete Remove",
            font=("Arial", 10, "bold"),
            text_color="#cbd5e1",
        ).grid(row=1, column=0, columnspan=2, sticky="e", pady=(4, 0))

        frame_item = ctk.CTkFrame(topo, fg_color="transparent")
        frame_item.grid(row=1, column=0, columnspan=4, sticky="ew", padx=(10, 12), pady=(0, 8))
        frame_item.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(frame_item, text="ID", text_color="#cbd5e1").grid(row=0, column=0, padx=(0, 6), sticky="w")
        self.ent_item_id = ctk.CTkEntry(frame_item, width=90, height=28, state="readonly")
        self.ent_item_id.grid(row=0, column=1, padx=(0, 10), sticky="w")

        ctk.CTkLabel(frame_item, text="Produto", text_color="#cbd5e1").grid(row=0, column=2, padx=(0, 6), sticky="w")
        self.ent_item_nome = ctk.CTkEntry(frame_item, height=28, state="readonly")
        self.ent_item_nome.grid(row=0, column=3, padx=(0, 10), sticky="ew")

        ctk.CTkLabel(frame_item, text="Valor", text_color="#cbd5e1").grid(row=0, column=4, padx=(0, 6), sticky="w")
        self.ent_item_valor = ctk.CTkEntry(frame_item, width=130, height=28, justify="right", state="readonly")
        self.ent_item_valor.grid(row=0, column=5, sticky="w")

        centro = ctk.CTkFrame(self, fg_color="#111827", corner_radius=8)
        centro.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        centro.grid_rowconfigure(0, weight=1)
        centro.grid_columnconfigure(0, weight=1)

        self.tree_carrinho = ttk.Treeview(
            centro,
            columns=("id", "nome", "qtd", "unit", "total"),
            show="headings",
            height=14,
            style="PDV.Treeview",
        )
        self.tree_carrinho.heading("id", text="ID")
        self.tree_carrinho.heading("nome", text="Item")
        self.tree_carrinho.heading("qtd", text="Qtd")
        self.tree_carrinho.heading("unit", text="Unit.")
        self.tree_carrinho.heading("total", text="Total")
        self.tree_carrinho.column("id", width=60, anchor="center")
        self.tree_carrinho.column("nome", width=620)
        self.tree_carrinho.column("qtd", width=90, anchor="center")
        self.tree_carrinho.column("unit", width=110, anchor="e")
        self.tree_carrinho.column("total", width=130, anchor="e")
        self.tree_carrinho.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)

        self.scroll_carrinho = ttk.Scrollbar(centro, orient="vertical", command=self.tree_carrinho.yview)
        self.scroll_carrinho.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.tree_carrinho.configure(yscrollcommand=self.scroll_carrinho.set)

        rodape = ctk.CTkFrame(self, fg_color="#0d1b2a", corner_radius=8)
        rodape.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        rodape.grid_columnconfigure(0, weight=1)
        rodape.grid_columnconfigure(1, weight=0)

        painel_pagamento = ctk.CTkFrame(rodape, fg_color="transparent")
        painel_pagamento.grid(row=0, column=0, sticky="nsew", padx=(10, 8), pady=10)
        painel_pagamento.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            painel_pagamento,
            text="Pagamentos",
            font=("Arial", 12, "bold"),
            text_color="#e2e8f0",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.seg_pagamento = ctk.CTkSegmentedButton(
            painel_pagamento,
            values=["DINHEIRO", "CHEQUE", "CARTAO"],
            command=self._sync_metodo_pagamento,
            fg_color="#1f2937",
            selected_color="#f59e0b",
            selected_hover_color="#fbbf24",
            unselected_color="#334155",
            unselected_hover_color="#475569",
            text_color="#0f1720",
        )
        self.seg_pagamento.grid(row=1, column=0, sticky="w")
        self.seg_pagamento.set(self._metodo_pagamento)

        linha_pagto = ctk.CTkFrame(painel_pagamento, fg_color="transparent")
        linha_pagto.grid(row=2, column=0, sticky="ew", pady=(8, 6))
        linha_pagto.grid_columnconfigure(4, weight=1)
        ctk.CTkLabel(linha_pagto, text="Valor", text_color="#cbd5e1").grid(row=0, column=0, padx=(0, 6))
        self.ent_valor_pagamento = ctk.CTkEntry(
            linha_pagto,
            width=120,
            height=32,
            justify="right",
            fg_color="#111827",
            border_color="#93c5fd",
            border_width=2,
        )
        self.ent_valor_pagamento.grid(row=0, column=1, padx=(0, 8))
        self.ent_valor_pagamento.bind("<Return>", lambda _e: self._adicionar_pagamento_atual())
        ctk.CTkButton(
            linha_pagto,
            text="Adicionar Pagamento",
            width=170,
            fg_color="#16a34a",
            command=self._adicionar_pagamento_atual,
        ).grid(row=0, column=2, padx=(0, 8))
        ctk.CTkButton(
            linha_pagto,
            text="Limpar (F2)",
            width=120,
            fg_color="#64748b",
            command=self._limpar_venda,
        ).grid(row=0, column=3)

        acoes_venda = ctk.CTkFrame(linha_pagto, fg_color="transparent")
        acoes_venda.grid(row=0, column=4, padx=(12, 0), sticky="e")

        ctk.CTkButton(
            acoes_venda,
            text="IMPRIMIR CUPOM",
            width=128,
            height=34,
            fg_color="#0ea5e9",
            command=self._imprimir_nao_fiscal_da_tela,
        ).grid(row=0, column=0, padx=(0, 6))

        ctk.CTkButton(
            acoes_venda,
            text="GERAR XML",
            width=108,
            height=34,
            fg_color="#f59e0b",
            command=self._gerar_xml_fiscal_da_tela,
        ).grid(row=0, column=1, padx=6)

        ctk.CTkButton(
            acoes_venda,
            text="GERAR PDF",
            width=108,
            height=34,
            fg_color="#64748b",
            command=self._gerar_pdf_da_tela,
        ).grid(row=0, column=2, padx=6)

        ctk.CTkButton(
            acoes_venda,
            text="FECHAMENTO DE CAIXA",
            width=168,
            height=34,
            fg_color="#16a34a",
            command=self._fechamento_de_caixa,
        ).grid(row=0, column=3, padx=(6, 0))

        self.tree_pagamentos = ttk.Treeview(
            painel_pagamento,
            columns=("metodo", "valor"),
            show="headings",
            height=3,
            style="PDV.Treeview",
        )
        self.tree_pagamentos.heading("metodo", text="Metodo")
        self.tree_pagamentos.heading("valor", text="Valor")
        self.tree_pagamentos.column("metodo", width=170, anchor="w")
        self.tree_pagamentos.column("valor", width=130, anchor="e")
        self.tree_pagamentos.grid(row=3, column=0, sticky="ew")

        painel_resumo = ctk.CTkFrame(rodape, fg_color="#111827", corner_radius=8)
        painel_resumo.grid(row=0, column=1, sticky="nsew", padx=(8, 10), pady=10)
        painel_resumo.grid_columnconfigure(0, weight=1)
        painel_resumo.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(painel_resumo, text="Resumo", font=("Arial", 12, "bold"), text_color="#f8fafc").grid(
            row=0, column=0, columnspan=2, sticky="e", padx=12, pady=(10, 8)
        )
        ctk.CTkLabel(painel_resumo, text="Total", text_color="#cbd5e1").grid(row=1, column=0, sticky="e", padx=(12, 8), pady=3)
        self.lbl_subtotal = ctk.CTkLabel(painel_resumo, text="R$ 0,00", font=("Arial", 12, "bold"), text_color="#e2e8f0")
        self.lbl_subtotal.grid(row=1, column=1, sticky="e", padx=(8, 12), pady=3)

        ctk.CTkLabel(painel_resumo, text="Desconto", text_color="#cbd5e1").grid(row=2, column=0, sticky="e", padx=(12, 8), pady=3)
        self.ent_desconto = ctk.CTkEntry(
            painel_resumo,
            width=126,
            height=30,
            justify="right",
            fg_color="#111827",
            border_color="#93c5fd",
            border_width=2,
        )
        self.ent_desconto.grid(row=2, column=1, sticky="e", padx=(8, 12), pady=3)
        self.ent_desconto.insert(0, "0")
        self.ent_desconto.bind("<KeyRelease>", self._ao_alterar_desconto)

        ctk.CTkLabel(painel_resumo, text="Valor Pago", text_color="#cbd5e1").grid(row=3, column=0, sticky="e", padx=(12, 8), pady=3)
        self.lbl_pago = ctk.CTkLabel(painel_resumo, text="R$ 0,00", font=("Arial", 12, "bold"), text_color="#22c55e")
        self.lbl_pago.grid(row=3, column=1, sticky="e", padx=(8, 12), pady=3)

        ctk.CTkLabel(painel_resumo, text="Saldo", text_color="#cbd5e1").grid(row=4, column=0, sticky="e", padx=(12, 8), pady=3)
        self.lbl_restante = ctk.CTkLabel(painel_resumo, text="R$ 0,00", font=("Arial", 12, "bold"), text_color="#f87171")
        self.lbl_restante.grid(row=4, column=1, sticky="e", padx=(8, 12), pady=3)

        ctk.CTkLabel(painel_resumo, text="Troco", text_color="#cbd5e1").grid(row=5, column=0, sticky="e", padx=(12, 8), pady=3)
        self.lbl_troco = ctk.CTkLabel(painel_resumo, text="R$ 0,00", font=("Arial", 12, "bold"), text_color="#f59e0b")
        self.lbl_troco.grid(row=5, column=1, sticky="e", padx=(8, 12), pady=3)

        ctk.CTkLabel(painel_resumo, text="Total Liquido", text_color="#cbd5e1").grid(row=6, column=0, sticky="e", padx=(12, 8), pady=(3, 12))
        self.lbl_total = ctk.CTkLabel(painel_resumo, text="R$ 0,00", font=("Arial", 18, "bold"), text_color="#22c55e")
        self.lbl_total.grid(row=6, column=1, sticky="e", padx=(8, 12), pady=(3, 12))

        self.btn_finalizar = ctk.CTkButton(
            painel_resumo,
            text="Finalizar (F1)",
            width=190,
            fg_color="#16a34a",
            command=self._finalizar_venda,
        )
        self.btn_finalizar.grid(row=7, column=0, columnspan=2, sticky="e", padx=(8, 12), pady=(0, 10))

        ctk.CTkCheckBox(
            painel_resumo,
            text="Impressao Automatica",
            variable=self._auto_impressao,
            onvalue=True,
            offvalue=False,
            text_color="#cbd5e1",
        ).grid(row=8, column=0, columnspan=2, sticky="e", padx=(8, 12), pady=(0, 8))

        self._atualizar_resumo()

    def _sync_metodo_pagamento(self, valor):
        self._metodo_pagamento = valor or "DINHEIRO"

    def _alternar_estado_finalizacao(self, finalizando: bool):
        self._finalizando_venda = bool(finalizando)
        if hasattr(self, "btn_finalizar"):
            self.btn_finalizar.configure(
                state="disabled" if finalizando else "normal",
                text="Finalizando..." if finalizando else "Finalizar (F1)",
            )

    def _focar_qtd(self):
        try:
            self.ent_qtd.focus_force()
            self.ent_qtd.select_range(0, "end")
        except Exception:
            pass

    def _focar_busca(self):
        try:
            self.ent_busca.focus_force()
            self.ent_busca.select_range(0, "end")
        except Exception:
            pass

    def _set_entry_value(self, entry, valor):
        try:
            entry.configure(state="normal")
            entry.delete(0, "end")
            entry.insert(0, str(valor or ""))
            entry.configure(state="readonly")
        except Exception:
            pass

    def _limpar_item_preselecionado(self):
        self._produto_preselecionado = None
        self._set_entry_value(getattr(self, "ent_item_id", None), "")
        self._set_entry_value(getattr(self, "ent_item_nome", None), "")
        self._set_entry_value(getattr(self, "ent_item_valor", None), "")

    def _preencher_item_preselecionado(self, row):
        try:
            produto_id = int(row[0])
            nome = str(row[1])
            preco = float(row[2] or 0)
            estoque = int(float(row[3] or 0))
        except Exception:
            return

        self._produto_preselecionado = (produto_id, nome, preco, estoque)
        self._set_entry_value(self.ent_item_id, produto_id)
        self._set_entry_value(self.ent_item_nome, nome)
        self._set_entry_value(self.ent_item_valor, f"{preco:.2f}")
        self.ent_busca.delete(0, "end")
        self._focar_qtd()

    def _buscar_produto_por_id(self, produto_id):
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, COALESCE(nome,''), COALESCE(preco_venda,0), COALESCE(estoque,0)
                FROM produtos
                WHERE id = ?
                LIMIT 1
                """,
                (int(produto_id),),
            )
            return cur.fetchone()

    def receber_item_estoque(self, produto_id, nome, preco):
        row = None
        try:
            row = self._buscar_produto_por_id(produto_id)
        except Exception:
            row = None

        if not row:
            row = (int(produto_id or 0), str(nome or ""), float(preco or 0), 0)

        self._preencher_item_preselecionado(row)

    def _enter_na_qtd(self, _event=None):
        if self._produto_preselecionado:
            qtd = int(_to_float(self.ent_qtd.get() or 1) or 1)
            if qtd <= 0:
                qtd = 1
            if self._adicionar_item_no_carrinho(row=self._produto_preselecionado, qtd=qtd):
                self._preparar_proximo_item()
            return "break"
        self._focar_busca()
        return "break"

    def _preparar_proximo_item(self):
        try:
            self.ent_busca.delete(0, "end")
            self.ent_qtd.delete(0, "end")
            self.ent_qtd.insert(0, "1")
        except Exception:
            pass
        self._limpar_item_preselecionado()
        self._focar_busca()

    def _ao_alterar_desconto(self, _event=None):
        self._atualizar_resumo()

    def _total_desconto(self):
        try:
            desconto = max(_to_float(self.ent_desconto.get() or 0), 0.0)
        except Exception:
            desconto = 0.0
        return min(desconto, self._total_itens())

    def _total_liquido(self):
        return max(self._total_itens() - self._total_desconto(), 0.0)

    def _tab_na_busca(self, _event=None):
        termo = (self.ent_busca.get() or "").strip()
        if not termo:
            self._abrir_busca_estoque()
            return "break"
        return None

    def _enter_na_busca(self, _event=None):
        termo = (self.ent_busca.get() or "").strip()
        if not termo:
            return "break"
        qtd = int(_to_float(self.ent_qtd.get() or 1) or 1)
        if qtd <= 0:
            qtd = 1
        if self._adicionar_produto_por_termo(termo=termo, qtd=qtd):
            self._preparar_proximo_item()
        return "break"

    def _buscar_produto_por_termo(self, termo):
        termo = (termo or "").strip()
        if not termo:
            return None

        campo_barra = "codigo_barras" if "codigo_barras" in self._produto_cols else None
        with get_db_connection() as conn:
            cur = conn.cursor()

            if termo.isdigit():
                cur.execute(
                    """
                    SELECT id, COALESCE(nome,''), COALESCE(preco_venda,0), COALESCE(estoque,0)
                    FROM produtos
                    WHERE id = ?
                    LIMIT 1
                    """,
                    (int(termo),),
                )
                row = cur.fetchone()
                if row:
                    return row

            if campo_barra:
                cur.execute(
                    f"""
                    SELECT id, COALESCE(nome,''), COALESCE(preco_venda,0), COALESCE(estoque,0)
                    FROM produtos
                    WHERE COALESCE({campo_barra}, '') = ?
                    LIMIT 1
                    """,
                    (termo,),
                )
                row = cur.fetchone()
                if row:
                    return row

            cur.execute(
                """
                SELECT id, COALESCE(nome,''), COALESCE(preco_venda,0), COALESCE(estoque,0)
                FROM produtos
                WHERE UPPER(COALESCE(nome,'')) = UPPER(?)
                LIMIT 1
                """,
                (termo,),
            )
            row = cur.fetchone()
            if row:
                return row

            cur.execute(
                """
                SELECT id, COALESCE(nome,''), COALESCE(preco_venda,0), COALESCE(estoque,0)
                FROM produtos
                WHERE UPPER(COALESCE(nome,'')) LIKE UPPER(?)
                ORDER BY nome ASC
                LIMIT 1
                """,
                (f"{termo}%",),
            )
            row = cur.fetchone()
            if row:
                return row

            cur.execute(
                """
                SELECT id, COALESCE(nome,''), COALESCE(preco_venda,0), COALESCE(estoque,0)
                FROM produtos
                WHERE UPPER(COALESCE(nome,'')) LIKE UPPER(?)
                ORDER BY nome ASC
                LIMIT 1
                """,
                (f"%{termo}%",),
            )
            return cur.fetchone()

    def _adicionar_item_no_carrinho(self, row, qtd):
        produto_id = int(row[0])
        nome = str(row[1])
        preco = _to_float(row[2])
        estoque = int(float(row[3] or 0))
        qtd = int(qtd or 1)
        if qtd <= 0:
            qtd = 1

        item_existente = next((i for i in self._carrinho if i["produto_id"] == produto_id), None)
        qtd_total = qtd + (item_existente["quantidade"] if item_existente else 0)
        if estoque > 0 and qtd_total > estoque:
            messagebox.showwarning("PDV", f"Estoque insuficiente para {nome}. Disponivel: {estoque}", parent=self)
            return False

        if item_existente:
            item_existente["quantidade"] += qtd
            item_existente["total_item"] = item_existente["quantidade"] * item_existente["preco_unitario"]
        else:
            self._carrinho.append(
                {
                    "produto_id": produto_id,
                    "nome_produto": nome,
                    "quantidade": qtd,
                    "preco_unitario": preco,
                    "total_item": qtd * preco,
                }
            )
        self._renderizar_carrinho()
        return True

    def _adicionar_produto_por_termo(self, termo, qtd):
        row = self._buscar_produto_por_termo(termo)
        if not row:
            messagebox.showwarning("PDV", f"Produto nao encontrado: {termo}", parent=self)
            return False
        return self._adicionar_item_no_carrinho(row=row, qtd=qtd)

    def _abrir_busca_estoque(self):
        win = ctk.CTkToplevel(self)
        win.title("Busca de Estoque")
        win.geometry("760x520")
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="Buscar produto", font=("Arial", 12, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        ent_filtro = ctk.CTkEntry(
            win,
            placeholder_text="Digite para filtrar...",
            height=32,
            fg_color="#1e293b",
            border_color="#f8fafc",
            border_width=1,
        )
        ent_filtro.pack(fill="x", padx=12, pady=(0, 8))

        tree = ttk.Treeview(win, columns=("id", "nome", "preco", "estoque"), show="headings", style="PDV.Treeview")
        tree.heading("id", text="ID")
        tree.heading("nome", text="Produto")
        tree.heading("preco", text="Preco")
        tree.heading("estoque", text="Estoque")
        tree.column("id", width=60, anchor="center")
        tree.column("nome", width=430)
        tree.column("preco", width=110, anchor="e")
        tree.column("estoque", width=100, anchor="center")
        tree.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        def carregar_lista():
            termo = (ent_filtro.get() or "").strip()
            for iid in tree.get_children():
                tree.delete(iid)

            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, COALESCE(nome,''), COALESCE(preco_venda,0), COALESCE(estoque,0)
                    FROM produtos
                    WHERE UPPER(COALESCE(nome,'')) LIKE UPPER(?)
                    ORDER BY nome ASC
                    LIMIT 400
                    """,
                    (f"%{termo}%",),
                )
                for row in cur.fetchall():
                    tree.insert("", "end", values=(row[0], row[1], f"{float(row[2]):.2f}", int(row[3] or 0)))

            itens = tree.get_children()
            if itens:
                tree.selection_set(itens[0])
                tree.focus(itens[0])

        def confirmar_selecao(_event=None):
            sel = tree.selection()
            if not sel:
                return "break"
            valores = tree.item(sel[0], "values")
            if not valores:
                return "break"
            row = (int(valores[0]), str(valores[1]), _to_float(valores[2]), int(float(valores[3] or 0)))
            self._preencher_item_preselecionado(row)
            win.destroy()
            return "break"

        ent_filtro.bind("<KeyRelease>", lambda _e: carregar_lista())
        ent_filtro.bind("<Return>", confirmar_selecao)
        tree.bind("<Double-1>", confirmar_selecao)
        tree.bind("<Return>", confirmar_selecao)

        carregar_lista()
        ent_filtro.focus_force()

    def _coletar_orcamentos_para_pdv(self, termo=""):
        termo_like = f"%{str(termo or '').strip()}%"
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COALESCE(id, 0),
                    COALESCE(cliente, ''),
                    COALESCE(equipamento, ''),
                    COALESCE(valor_total, 0),
                    UPPER(COALESCE(status, '')),
                    COALESCE(data, ''),
                    COALESCE(itens_detalhes, ''),
                    COALESCE(dados_adicionais, '')
                FROM orcamentos_aguardo
                WHERE (
                    UPPER(COALESCE(cliente, '')) LIKE UPPER(?)
                    OR UPPER(COALESCE(equipamento, '')) LIKE UPPER(?)
                    OR CAST(COALESCE(id, 0) AS TEXT) LIKE ?
                )
                AND UPPER(COALESCE(status, '')) <> 'REPROVADO'
                ORDER BY id DESC
                LIMIT 300
                """,
                (termo_like, termo_like, termo_like),
            )
            return cur.fetchall() or []

    def _extrair_itens_orcamento_para_pdv(self, itens_detalhes_raw, dados_adicionais_raw):
        itens = []
        desconto_total = 0.0
        valor_total_orc = 0.0
        try:
            dados_adicionais = json.loads(str(dados_adicionais_raw or "").strip() or "{}")
        except Exception:
            dados_adicionais = {}

        equipamentos = dados_adicionais.get("equipamentos") if isinstance(dados_adicionais, dict) else None
        if isinstance(equipamentos, list) and equipamentos:
            for idx_eq, equipamento in enumerate(equipamentos):
                if not isinstance(equipamento, dict):
                    continue
                nome_eq = str(equipamento.get("equipamento") or "Equipamento").strip()
                desconto_total += _to_float(equipamento.get("desconto", 0))
                for idx_item, item in enumerate(equipamento.get("itens") or []):
                    if not isinstance(item, (list, tuple)) or len(item) < 4:
                        continue
                    descricao = str(item[0] or "Item").strip()
                    qtd = max(int(_to_float(item[1] or 1) or 1), 1)
                    unit = _to_float(item[2] or 0)
                    total_item = _to_float(item[3] or (qtd * unit))
                    valor_total_orc += total_item
                    itens.append(
                        {
                            "produto_id": -200000 - (idx_eq * 1000) - idx_item,
                            "nome_produto": f"{nome_eq} | {descricao}" if nome_eq else descricao,
                            "quantidade": qtd,
                            "preco_unitario": unit if unit > 0 else (total_item / qtd if qtd else 0),
                            "total_item": total_item,
                        }
                    )
        else:
            try:
                bruto = json.loads(str(itens_detalhes_raw or "").strip() or "[]")
            except Exception:
                bruto = []
            for idx_item, item in enumerate(bruto):
                if isinstance(item, dict):
                    descricao = str(item.get("descricao") or item.get("item") or "Item").strip()
                    qtd = max(int(_to_float(item.get("quantidade", item.get("qtd", 1))) or 1), 1)
                    unit = _to_float(item.get("valor_unitario", item.get("unitario", 0)))
                    total_item = _to_float(item.get("valor_total", item.get("total", qtd * unit)))
                elif isinstance(item, (list, tuple)) and len(item) >= 4:
                    descricao = str(item[0] or "Item").strip()
                    qtd = max(int(_to_float(item[1] or 1) or 1), 1)
                    unit = _to_float(item[2] or 0)
                    total_item = _to_float(item[3] or (qtd * unit))
                else:
                    continue
                valor_total_orc += total_item
                itens.append(
                    {
                        "produto_id": -250000 - idx_item,
                        "nome_produto": descricao,
                        "quantidade": qtd,
                        "preco_unitario": unit if unit > 0 else (total_item / qtd if qtd else 0),
                        "total_item": total_item,
                    }
                )

        if desconto_total <= 0:
            desconto_total = _to_float((dados_adicionais or {}).get("desconto", 0))

        return itens, max(desconto_total, 0.0), max(valor_total_orc, 0.0)

    def _carregar_orcamento_no_pdv(self, row_orc):
        if not row_orc:
            return False
        orc_id, cliente, equipamento, valor_total, status, data_orc, itens_detalhes, dados_adicionais = row_orc
        itens, desconto_orc, _total_itens_orc = self._extrair_itens_orcamento_para_pdv(itens_detalhes, dados_adicionais)
        if not itens:
            messagebox.showwarning("PDV", f"Orçamento #{orc_id} sem itens válidos para lançamento no PDV.", parent=self)
            return False

        if self._carrinho:
            if not messagebox.askyesno(
                "PDV",
                "Existe uma venda em andamento. Deseja substituir pelos itens do orçamento selecionado?",
                parent=self,
            ):
                return False

        self._orcamento_vinculado = {
            "id": int(orc_id or 0),
            "cliente": str(cliente or ""),
            "equipamento": str(equipamento or ""),
            "status": str(status or ""),
            "data": str(data_orc or ""),
            "valor_total_orcamento": _to_float(valor_total or 0),
        }
        self._carrinho = itens
        self._pagamentos = []
        self.ent_valor_pagamento.delete(0, "end")
        self.ent_desconto.delete(0, "end")
        self.ent_desconto.insert(0, f"{max(desconto_orc, 0.0):.2f}")
        self._renderizar_carrinho()
        self._renderizar_pagamentos()
        self._atualizar_resumo()
        self._preparar_proximo_item()
        return True

    def _abrir_seletor_item_oficina(self):
        win = ctk.CTkToplevel(self)
        win.title("Selecionar orçamento para fechamento no PDV")
        win.geometry("1040x620")
        win.configure(fg_color="#0f1720")
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(
            win,
            text="Selecione um orçamento para carregar itens e valores automaticamente no PDV",
            font=("Arial", 12, "bold"),
            text_color="#e2e8f0",
        ).pack(anchor="w", padx=12, pady=(12, 6))

        ent_filtro = ctk.CTkEntry(
            win,
            placeholder_text="Filtrar por nº orçamento, cliente ou equipamento...",
            height=34,
            fg_color="#1e293b",
            border_color="#f8fafc",
            border_width=1,
        )
        ent_filtro.pack(fill="x", padx=12, pady=(0, 8))

        tree = ttk.Treeview(
            win,
            columns=("id", "cliente", "equipamento", "valor_total", "status", "data"),
            show="headings",
            style="PDV.Treeview",
        )
        tree.heading("id", text="Orçamento")
        tree.heading("cliente", text="Cliente")
        tree.heading("equipamento", text="Equipamento")
        tree.heading("valor_total", text="Valor")
        tree.heading("status", text="Status")
        tree.heading("data", text="Data")
        tree.column("id", width=100, anchor="center")
        tree.column("cliente", width=250)
        tree.column("equipamento", width=310)
        tree.column("valor_total", width=120, anchor="e")
        tree.column("status", width=120, anchor="center")
        tree.column("data", width=110, anchor="center")
        tree.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        rows_index = {}

        def carregar_itens():
            termo = (ent_filtro.get() or "").strip()
            for iid in tree.get_children():
                tree.delete(iid)
            rows_index.clear()
            for row_orc in self._coletar_orcamentos_para_pdv(termo):
                oid, cliente, equipamento, valor_total, status, data_orc, _itens, _dados = row_orc
                iid = str(int(oid or 0))
                rows_index[iid] = row_orc
                tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(
                        int(oid or 0),
                        str(cliente or ""),
                        str(equipamento or ""),
                        f"{float(valor_total or 0):.2f}",
                        str(status or ""),
                        str(data_orc or ""),
                    ),
                )
            filhos = tree.get_children()
            if filhos:
                tree.selection_set(filhos[0])
                tree.focus(filhos[0])

        def confirmar_item(_event=None):
            sel = tree.selection()
            if not sel:
                return "break"
            row_orc = rows_index.get(str(sel[0]))
            if not row_orc:
                return "break"
            if self._carregar_orcamento_no_pdv(row_orc):
                win.destroy()
            return "break"

        ent_filtro.bind("<KeyRelease>", lambda _e: carregar_itens())
        ent_filtro.bind("<Return>", confirmar_item)
        tree.bind("<Double-1>", confirmar_item)
        tree.bind("<Return>", confirmar_item)

        carregar_itens()
        ent_filtro.focus_force()

    def _renderizar_carrinho(self):
        for item in self.tree_carrinho.get_children():
            self.tree_carrinho.delete(item)

        for i, item in enumerate(self._carrinho, start=1):
            self.tree_carrinho.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    item["produto_id"],
                    item["nome_produto"],
                    item["quantidade"],
                    f"{item['preco_unitario']:.2f}",
                    f"{item['total_item']:.2f}",
                ),
            )

        self._atualizar_resumo()

    def _renderizar_pagamentos(self):
        for item in self.tree_pagamentos.get_children():
            self.tree_pagamentos.delete(item)
        for i, pag in enumerate(self._pagamentos, start=1):
            self.tree_pagamentos.insert("", "end", iid=str(i), values=(pag["metodo"], f"{pag['valor']:.2f}"))

    def _total_itens(self):
        return float(sum(i["total_item"] for i in self._carrinho))

    def _total_pago(self):
        return float(sum(p["valor"] for p in self._pagamentos))

    def _atualizar_resumo(self):
        subtotal = self._total_itens()
        desconto = self._total_desconto()
        total_liquido = max(subtotal - desconto, 0.0)
        pago = self._total_pago()
        restante = max(total_liquido - pago, 0.0)
        troco = max(pago - total_liquido, 0.0)

        self.lbl_subtotal.configure(text=_fmt_moeda(subtotal))
        self.lbl_total.configure(text=_fmt_moeda(total_liquido))
        self.lbl_pago.configure(text=_fmt_moeda(pago))
        self.lbl_restante.configure(text=_fmt_moeda(restante))
        self.lbl_troco.configure(text=_fmt_moeda(troco))

    def _adicionar_pagamento_atual(self):
        total = self._total_liquido()
        if total <= 0:
            messagebox.showwarning("PDV", "Adicione itens antes de lancar pagamentos.", parent=self)
            self._focar_busca()
            return

        restante = max(total - self._total_pago(), 0.0)
        valor_txt = (self.ent_valor_pagamento.get() or "").strip()
        valor = _to_float(valor_txt) if valor_txt else restante
        if valor <= 0:
            messagebox.showwarning("PDV", "Informe um valor de pagamento valido.", parent=self)
            return

        self._pagamentos.append({"metodo": self._metodo_pagamento, "valor": float(valor)})
        self.ent_valor_pagamento.delete(0, "end")
        self._renderizar_pagamentos()
        self._atualizar_resumo()
        self._focar_busca()

    def _remover_item(self):
        sel = self.tree_carrinho.selection()
        if not sel:
            return
        idx = int(sel[0]) - 1
        if 0 <= idx < len(self._carrinho):
            self._carrinho.pop(idx)
            self._renderizar_carrinho()

    def _limpar_venda(self):
        self._carrinho = []
        self._pagamentos = []
        self._metodo_pagamento = "DINHEIRO"
        self._limpar_item_preselecionado()
        self.seg_pagamento.set("DINHEIRO")
        self.ent_qtd.delete(0, "end")
        self.ent_qtd.insert(0, "1")
        self.ent_busca.delete(0, "end")
        self.ent_valor_pagamento.delete(0, "end")
        self.ent_desconto.delete(0, "end")
        self.ent_desconto.insert(0, "0")
        self._renderizar_carrinho()
        self._renderizar_pagamentos()
        self._atualizar_resumo()
        self._focar_busca()

    def _proximo_numero_venda(self):
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM pdv_vendas")
            return int(cur.fetchone()[0] or 1)

    def _proximo_numero_venda_diario(self):
        data_base = datetime.now().strftime("%d/%m/%Y")
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*)
                FROM pdv_vendas
                WHERE substr(COALESCE(data_hora, ''), 1, 10) = ?
                """,
                (data_base,),
            )
            return int(cur.fetchone()[0] or 0) + 1

    def _pagamentos_descricao(self):
        if not self._pagamentos:
            return self._metodo_pagamento
        partes = [f"{p['metodo']} {_fmt_moeda(p['valor'])}" for p in self._pagamentos]
        return "MISTO: " + " | ".join(partes)

    def _snapshot_venda(self):
        subtotal = self._total_itens()
        desconto = self._total_desconto()
        total_liquido = self._total_liquido()
        venda_id = self._proximo_numero_venda()
        seq_dia = self._proximo_numero_venda_diario()
        formas = sorted({_normalizar_texto_pagamento(p.get("metodo") or "") for p in self._pagamentos if p.get("metodo")})
        forma_pagamento = "MISTO" if len(formas) > 1 else (formas[0] if formas else _normalizar_texto_pagamento(self._metodo_pagamento))
        return {
            "sale_id": venda_id,
            "daily_seq": seq_dia,
            "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "date_only": datetime.now().strftime("%d/%m/%Y"),
            "forma_pagamento": forma_pagamento or "DINHEIRO",
            "payment_method": self._pagamentos_descricao(),
            "total_bruto": subtotal,
            "desconto": desconto,
            "total": total_liquido,
            "total_pago": self._total_pago(),
            "troco": max(self._total_pago() - total_liquido, 0.0),
            "items": [dict(i) for i in self._carrinho],
            "payments": [dict(p) for p in self._pagamentos],
        }

    def _base_venda_para_saida(self):
        if self._ultima_venda:
            return dict(self._ultima_venda)
        if self._carrinho:
            return self._snapshot_venda()
        return None

    def _montar_ticket_nao_fiscal(self, venda):
        dados = obter_dados_oficina()
        linhas = [
            (dados.get("nome_oficina") or "OFICINA DE PESCA").upper(),
            "COMPROVANTE NAO FISCAL",
            f"Venda: {venda['sale_id']}  Dia: {int(venda.get('daily_seq') or 0):03d}",
            f"Data: {venda['date']}",
            "-" * 42,
        ]

        for item in venda["items"]:
            qtd = int(item.get("quantidade") or 1)
            nome = str(item.get("nome_produto") or "Item")
            un = float(item.get("preco_unitario") or 0)
            total = float(item.get("total_item") or 0)
            linhas.append(f"{qtd}x {nome[:32]}")
            linhas.append(f"  UN {un:.2f}  TOTAL {total:.2f}")

        linhas.append("-" * 42)
        for pag in venda.get("payments", []):
            linhas.append(f"{pag.get('metodo')}: R$ {float(pag.get('valor') or 0):.2f}")

        linhas.extend(
            [
                "-" * 42,
                f"TOTAL: R$ {float(venda['total']):.2f}",
                f"PAGO: R$ {float(venda.get('total_pago') or 0):.2f}",
                f"TROCO: R$ {float(venda.get('troco') or 0):.2f}",
                "NAO E DOCUMENTO FISCAL",
            ]
        )
        return "\n".join(linhas)

    def _build_escpos_payload(self, texto_ticket):
        return b"\x1b@" + texto_ticket.encode("cp850", errors="replace") + b"\n\n\x1dV\x00"

    def _print_thermal_escpos(self, payload):
        pasta = Path(os.path.dirname(CAMINHO_BANCO)) / "pdv_comprovantes"
        pasta.mkdir(parents=True, exist_ok=True)
        fallback_file = pasta / f"escpos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bin"

        target_override = os.environ.get("PDV_IMPRESSORA_PORTA", "").strip()
        if target_override:
            try:
                if target_override.upper().startswith("COM"):
                    import serial  # type: ignore

                    with serial.Serial(target_override, 9600, timeout=2) as ser:
                        ser.write(payload)
                    return {"ok": True, "target": target_override, "job": None, "fallback": None}
                with open(target_override, "wb") as f:
                    f.write(payload)
                return {"ok": True, "target": target_override, "job": None, "fallback": None}
            except Exception:
                pass

        try:
            import win32print  # type: ignore

            target = win32print.GetDefaultPrinter()
            hprinter = win32print.OpenPrinter(target)
            try:
                job = win32print.StartDocPrinter(hprinter, 1, ("Comprovante Oficina de Pesca", "", "RAW"))
                win32print.StartPagePrinter(hprinter)
                win32print.WritePrinter(hprinter, payload)
                win32print.EndPagePrinter(hprinter)
                win32print.EndDocPrinter(hprinter)
                return {"ok": True, "target": target, "job": job, "fallback": None}
            finally:
                win32print.ClosePrinter(hprinter)
        except Exception:
            with open(fallback_file, "wb") as f:
                f.write(payload)
            return {"ok": False, "target": None, "job": None, "fallback": str(fallback_file)}

    def _imprimir_cupom_background(self, venda):
        ticket = self._montar_ticket_nao_fiscal(venda)
        payload = self._build_escpos_payload(ticket)

        def worker():
            result = self._print_thermal_escpos(payload)
            if not result.get("ok"):
                try:
                    self.after(
                        0,
                        lambda: messagebox.showwarning(
                            "PDV",
                            "Cupom nao enviado para impressora.\n"
                            f"Arquivo RAW salvo em:\n{result.get('fallback')}",
                            parent=self,
                        ),
                    )
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _obter_mapa_fiscal_produtos(self, venda):
        produto_ids = [int(i.get("produto_id") or 0) for i in venda.get("items", []) if int(i.get("produto_id") or 0) > 0]
        if not produto_ids:
            return {}

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(produtos)")
            cols = {str(r[1]).lower() for r in cur.fetchall()}

            col_ncm = "ncm" if "ncm" in cols else None
            col_cfop = "cfop" if "cfop" in cols else None
            col_aliq = "aliquota_icms" if "aliquota_icms" in cols else None

            campos = ["id"]
            if col_ncm:
                campos.append(col_ncm)
            if col_cfop:
                campos.append(col_cfop)
            if col_aliq:
                campos.append(col_aliq)

            placeholders = ",".join("?" for _ in produto_ids)
            cur.execute(
                f"SELECT {', '.join(campos)} FROM produtos WHERE id IN ({placeholders})",
                tuple(produto_ids),
            )

            mapa = {}
            for row in cur.fetchall():
                idx = 1
                pid = int(row[0])
                ncm = str(row[idx]) if col_ncm else "00000000"
                if col_ncm:
                    idx += 1
                cfop = str(row[idx]) if col_cfop else "5102"
                if col_cfop:
                    idx += 1
                aliq = float(row[idx] or 0) if col_aliq else 0.0
                mapa[pid] = {
                    "ncm": (ncm or "00000000").strip(),
                    "cfop": (cfop or "5102").strip(),
                    "aliquota_icms": aliq,
                }
            return mapa

    def _gerar_xml_fiscal(self, venda):
        pasta = Path("C:/PDV/XML_SAIDA")
        pasta.mkdir(parents=True, exist_ok=True)

        dados = obter_dados_oficina()
        fiscal_prod = self._obter_mapa_fiscal_produtos(venda)

        root = ET.Element("FiscalSale")
        ET.SubElement(root, "SaleId").text = str(venda.get("sale_id") or "0")
        ET.SubElement(root, "DateTime").text = str(venda.get("date") or datetime.now().strftime("%d/%m/%Y %H:%M"))
        ET.SubElement(root, "CompanyName").text = str(dados.get("nome_oficina") or "OFICINA DE PESCA")
        ET.SubElement(root, "PaymentMethod").text = str(venda.get("payment_method") or "DINHEIRO")
        ET.SubElement(root, "TotalValue").text = f"{float(venda.get('total') or 0):.2f}"

        pagamentos_node = ET.SubElement(root, "Payments")
        pagamentos = venda.get("payments") or []
        if not pagamentos:
            pagamentos = [{
                "metodo": str(venda.get("payment_method") or "DINHEIRO"),
                "valor": float(venda.get("total") or 0),
            }]

        # Espelhamento da estrutura oficial de mercado para NF-e/NFC-e: pag/detPag.
        nfe_mirror = ET.SubElement(root, "NFe")
        inf_nfe_mirror = ET.SubElement(nfe_mirror, "infNFe")
        pag_mirror = ET.SubElement(inf_nfe_mirror, "pag")

        for pag in pagamentos:
            metodo_original = str(pag.get("metodo") or "")
            tpag = _mapear_tpag_fiscal(metodo_original)
            vpag = float(pag.get('valor') or 0)

            no_pag = ET.SubElement(pagamentos_node, "Payment")
            ET.SubElement(no_pag, "tPag").text = tpag
            ET.SubElement(no_pag, "vPag").text = f"{vpag:.2f}"
            if tpag == "99":
                ET.SubElement(no_pag, "xPag").text = metodo_original or "OUTROS"

            det_pag = ET.SubElement(pag_mirror, "detPag")
            ET.SubElement(det_pag, "tPag").text = tpag
            ET.SubElement(det_pag, "vPag").text = f"{vpag:.2f}"
            if tpag == "99":
                ET.SubElement(det_pag, "xPag").text = metodo_original or "OUTROS"

        troco = float(venda.get("troco") or 0)
        if troco > 0:
            ET.SubElement(pag_mirror, "vTroco").text = f"{troco:.2f}"

        itens_node = ET.SubElement(root, "Items")
        for item in venda.get("items", []):
            pid = int(item.get("produto_id") or 0)
            fiscal = fiscal_prod.get(pid, {"ncm": "00000000", "cfop": "5102", "aliquota_icms": 0.0})

            item_node = ET.SubElement(itens_node, "Item")
            ET.SubElement(item_node, "ProductId").text = str(pid)
            ET.SubElement(item_node, "Description").text = str(item.get("nome_produto") or "Item")
            ET.SubElement(item_node, "NCM").text = str(fiscal.get("ncm") or "00000000")
            ET.SubElement(item_node, "CFOP").text = str(fiscal.get("cfop") or "5102")
            ET.SubElement(item_node, "Quantity").text = str(int(item.get("quantidade") or 1))
            ET.SubElement(item_node, "UnitValue").text = f"{float(item.get('preco_unitario') or 0):.2f}"
            ET.SubElement(item_node, "TotalValue").text = f"{float(item.get('total_item') or 0):.2f}"

            impostos = ET.SubElement(item_node, "Taxes")
            aliq = float(fiscal.get("aliquota_icms") or 0.0)
            base = float(item.get("total_item") or 0)
            valor_icms = base * (aliq / 100.0)
            ET.SubElement(impostos, "ICMSAliquota").text = f"{aliq:.2f}"
            ET.SubElement(impostos, "ICMSValue").text = f"{valor_icms:.2f}"

        xml_bytes = ET.tostring(root, encoding="utf-8")
        pretty = minidom.parseString(xml_bytes).toprettyxml(indent="  ", encoding="utf-8")

        arquivo = pasta / f"venda_{int(venda.get('sale_id') or 0):05d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
        with open(arquivo, "wb") as f:
            f.write(pretty)
        return str(arquivo)

    def _gerar_pdf_venda(self, venda):
        if not _REPORTLAB_OK:
            raise RuntimeError("Biblioteca reportlab nao disponivel no ambiente.")

        dados = obter_dados_oficina()
        pasta = Path(os.path.dirname(CAMINHO_BANCO)) / "pdv_comprovantes"
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo = pasta / f"venda_{int(venda['sale_id']):05d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        c = canvas.Canvas(str(arquivo), pagesize=A4)
        y = 800

        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, y, "Venda (Nao Fiscal)")
        y -= 20

        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, f"Venda #{venda['sale_id']} - Seq Dia {int(venda.get('daily_seq') or 0):03d}")
        y -= 18

        c.setFont("Helvetica", 10)
        c.drawString(40, y, f"Loja: {dados.get('nome_oficina') or 'OFICINA DE PESCA'}")
        y -= 15
        c.drawString(40, y, f"Data: {venda['date']}")
        y -= 15
        c.drawString(40, y, f"Pagamento: {venda['payment_method']}")
        y -= 16

        c.line(40, y, 550, y)
        y -= 18

        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, "Item")
        c.drawString(360, y, "Qtd")
        c.drawString(410, y, "Unit")
        c.drawString(500, y, "Total")
        y -= 14

        c.setFont("Helvetica", 10)
        for item in venda["items"]:
            c.drawString(40, y, str(item.get("nome_produto") or "Item")[:48])
            c.drawRightString(390, y, str(int(item.get("quantidade") or 1)))
            c.drawRightString(470, y, f"{float(item.get('preco_unitario') or 0):.2f}")
            c.drawRightString(550, y, f"{float(item.get('total_item') or 0):.2f}")
            y -= 15
            if y < 85:
                c.showPage()
                y = 800
                c.setFont("Helvetica", 10)

        y -= 5
        c.line(40, y, 550, y)
        y -= 20
        c.setFont("Helvetica-Bold", 12)
        c.drawRightString(550, y, f"TOTAL: R$ {float(venda['total']):.2f}")
        y -= 18
        c.drawRightString(550, y, f"PAGO: R$ {float(venda.get('total_pago') or 0):.2f}")
        y -= 18
        c.drawRightString(550, y, f"TROCO: R$ {float(venda.get('troco') or 0):.2f}")

        c.save()
        return str(arquivo)

    def _gerar_pdf_da_tela(self):
        venda = self._base_venda_para_saida()
        if not venda:
            messagebox.showwarning("PDV", "Nenhuma venda disponivel para gerar PDF.", parent=self)
            return
        try:
            caminho = self._gerar_pdf_venda(venda)
            messagebox.showinfo("PDV", f"PDF gerado com sucesso:\n{caminho}", parent=self)
            if hasattr(os, "startfile"):
                os.startfile(caminho)  # type: ignore[attr-defined]
        except Exception as e:
            messagebox.showerror("PDV", f"Erro ao gerar PDF: {e}", parent=self)

    def _gerar_xml_fiscal_da_tela(self):
        venda = self._base_venda_para_saida()
        if not venda:
            messagebox.showwarning("PDV", "Nenhuma venda disponivel para gerar XML.", parent=self)
            return
        try:
            caminho = self._gerar_xml_fiscal(venda)
            messagebox.showinfo("PDV", f"XML fiscal gerado com sucesso:\n{caminho}", parent=self)
        except Exception as e:
            messagebox.showerror("PDV", f"Erro ao gerar XML fiscal: {e}", parent=self)

    def _imprimir_nao_fiscal_da_tela(self):
        venda = self._base_venda_para_saida()
        if not venda:
            messagebox.showwarning("PDV", "Nenhuma venda para impressao.", parent=self)
            return

        self._imprimir_cupom_background(venda)
        messagebox.showinfo("PDV", "Impressao enviada em background.", parent=self)

    def _imprimir_cupom_automatico(self, venda):
        self._imprimir_cupom_background(venda)

    def _resumo_fechamento_dia(self, data_base):
        total_vendas = 0.0
        total_dinheiro = 0.0
        total_pix = 0.0
        total_cartao = 0.0
        ids_vendas = []

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, COALESCE(total, 0), UPPER(COALESCE(forma_pagamento, ''))
                FROM pdv_vendas
                WHERE COALESCE(data, '') = ?
                  AND UPPER(COALESCE(status, 'ABERTO')) = 'ABERTO'
                """,
                (data_base,),
            )
            for venda_id, total, forma in cur.fetchall():
                v = float(total or 0)
                total_vendas += v
                ids_vendas.append(int(venda_id))

                m = _normalizar_texto_pagamento(forma)
                if "PIX" in m:
                    total_pix += v
                elif "CARTAO" in m or "CREDITO" in m or "DEBITO" in m:
                    total_cartao += v
                elif "DINHEIRO" in m:
                    total_dinheiro += v
                else:
                    # fallback de mercado: formas não mapeadas entram em dinheiro.
                    total_dinheiro += v

        return {
            "data": data_base,
            "total_vendas": total_vendas,
            "dinheiro": total_dinheiro,
            "pix": total_pix,
            "cartao": total_cartao,
            "ids_vendas": ids_vendas,
        }

    def _fechamento_de_caixa(self):
        data_base = datetime.now().strftime("%d/%m/%Y")
        resumo = self._resumo_fechamento_dia(data_base)

        if resumo["total_vendas"] <= 0:
            messagebox.showwarning("PDV", "Nao ha vendas do dia para fechamento.", parent=self)
            return

        msg = (
            f"Data: {resumo['data']}\n\n"
            f"Total Dinheiro: {_fmt_moeda(resumo['dinheiro'])}\n"
            f"Total PIX: {_fmt_moeda(resumo['pix'])}\n"
            f"Total Cartao: {_fmt_moeda(resumo['cartao'])}\n"
            f"Total Geral: {_fmt_moeda(resumo['total_vendas'])}\n\n"
            "Confirmar fechamento e encerrar vendas abertas do dia?"
        )
        if not messagebox.askyesno("Fechamento de Caixa", msg, parent=self):
            return

        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                descricao = (
                    "FECHAMENTO PDV | "
                    f"Dinheiro: {_fmt_moeda(resumo['dinheiro'])} | "
                    f"PIX: {_fmt_moeda(resumo['pix'])} | "
                    f"Cartao: {_fmt_moeda(resumo['cartao'])}"
                )
                cur.execute(
                    """
                    INSERT INTO financeiro_geral (
                        data_hora, data_referencia, descricao, tipo,
                        total_dinheiro, total_pix, total_cartao, total_geral, detalhe_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                        resumo["data"],
                        descricao,
                        "FECHAMENTO_PDV",
                        resumo["dinheiro"],
                        resumo["pix"],
                        resumo["cartao"],
                        resumo["total_vendas"],
                        json.dumps(resumo, ensure_ascii=False),
                    ),
                )

                cur.execute(
                    """
                    UPDATE pdv_vendas
                    SET status = 'fechado'
                    WHERE COALESCE(data, '') = ?
                      AND UPPER(COALESCE(status, 'ABERTO')) = 'ABERTO'
                    """,
                    (resumo["data"],),
                )
                conn.commit()

            self._limpar_venda()
            messagebox.showinfo(
                "Fechamento de Caixa",
                f"Fechamento realizado com sucesso. Total: {_fmt_moeda(resumo['total_vendas'])}",
                parent=self,
            )
        except Exception as e:
            messagebox.showerror("PDV", f"Erro no fechamento de caixa: {e}", parent=self)

    def _finalizar_venda(self):
        if self._finalizando_venda:
            return
        if not self._carrinho:
            messagebox.showwarning("PDV", "Adicione ao menos um item para finalizar a venda.", parent=self)
            return

        total = self._total_liquido()
        if total <= 0:
            messagebox.showwarning("PDV", "Total invalido para finalizacao.", parent=self)
            return

        if not self._pagamentos:
            self._pagamentos.append({"metodo": self._metodo_pagamento, "valor": total})

        total_pago = self._total_pago()
        if total_pago + 1e-6 < total:
            messagebox.showwarning("PDV", f"Pagamento insuficiente. Falta {_fmt_moeda(total - total_pago)}.", parent=self)
            return

        self._alternar_estado_finalizacao(True)
        venda = self._snapshot_venda()

        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO pdv_vendas (data, total, forma_pagamento, status)
                    VALUES (?, ?, ?, 'aberto')
                    """,
                    (venda["date_only"], venda["total"], venda.get("forma_pagamento") or "DINHEIRO"),
                )
                venda_id = int(cur.lastrowid or 0)
                if venda_id <= 0:
                    raise RuntimeError("Falha ao gerar identificador da venda.")

                for item in self._carrinho:
                    cur.execute(
                        """
                        INSERT INTO pdv_itens (venda_id, produto_id, nome_produto, quantidade, preco_unitario, total_item)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            venda_id,
                            item["produto_id"],
                            item["nome_produto"],
                            item["quantidade"],
                            item["preco_unitario"],
                            item["total_item"],
                        ),
                    )

                    cur.execute(
                        """
                        UPDATE produtos
                        SET estoque = CASE
                            WHEN COALESCE(estoque, 0) - ? < 0 THEN 0
                            ELSE COALESCE(estoque, 0) - ?
                        END
                        WHERE id = ?
                        """,
                        (item["quantidade"], item["quantidade"], item["produto_id"]),
                    )

                for pag in self._pagamentos:
                    descricao_fluxo = f"VENDA BALCAO #{venda_id}"
                    cur.execute(
                        """
                        INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento)
                        VALUES (?, ?, 'ENTRADA', ?, ?, ?)
                        """,
                        (
                            datetime.now().strftime("%d/%m/%Y"),
                            descricao_fluxo,
                            float(pag.get("valor") or 0),
                            "PDV",
                            str(pag.get("metodo") or "DINHEIRO"),
                        ),
                    )

                conn.commit()

            venda["sale_id"] = venda_id
            self._ultima_venda = venda

            # Preparacao fiscal CBS/IBS: chamada opcional sem bloquear operacao do PDV.
            # Em modo stand-alone (sem configuracao/adaptador), a venda segue normalmente.
            try:
                tentar_enviar_venda(venda)
            except Exception:
                pass

            if bool(self._auto_impressao.get()):
                self._imprimir_cupom_automatico(venda)
            self._limpar_venda()

            messagebox.showinfo(
                "PDV",
                f"Venda #{venda_id} finalizada com sucesso.\n"
                f"Sequencia do dia: {int(venda.get('daily_seq') or 0):03d}\n"
                f"Total: {_fmt_moeda(venda['total'])}\n"
                f"Pago: {_fmt_moeda(venda.get('total_pago') or 0)}\n"
                f"Troco: {_fmt_moeda(venda.get('troco') or 0)}",
                parent=self,
            )
            self._focar_qtd()
        except Exception as e:
            messagebox.showerror("PDV", f"Erro ao finalizar venda: {e}", parent=self)
        finally:
            self._alternar_estado_finalizacao(False)
