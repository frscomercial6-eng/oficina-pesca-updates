# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
from typing import Optional, List, Dict, Any
import customtkinter as ctk
import tkinter as tk
import sqlite3
import os
os.environ['TK_SILENCE_DEPRECATION'] = '1'
import json
import re
import concurrent.futures
import time
import base64
import configparser
import traceback
import threading
import subprocess
import webbrowser
import socket
import urllib.request
from urllib.parse import quote, quote_plus, urljoin, urlparse, parse_qs, unquote
from tkinter import ttk, filedialog, messagebox, simpledialog
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from datetime import datetime
# Corrige imports ausentes para web scraping
from urllib.request import Request, urlopen
from core.financeiro.calculos import OSCalculator, formatar_monetario
from status_os import normalizar_status_orcamento, STATUS_ORCAMENTO, STATUS_AGUARDANDO_ORCAMENTO

# Importações centralizadas do arquivo config.py (Versão 1.0.6)
from config import (
    CAMINHO_BANCO, inicializar_banco, DIRETORIO_RECURSOS, get_db_connection, get_logger,
    obter_google_ai_key_mestre, enviar_arquivo_para_drive_usuario, enviar_registro_os_central_silencioso,
    localizar_ou_criar_pasta_drive, localizar_ou_criar_planilha, buscar_linha_por_fabricante_modelo,
    adicionar_linha_planilha, ler_links_alertas_conhecimento, salvar_link_alerta_conhecimento,
        obter_modo_operacao
)

# NOVO: import do sistema de i18n
from core.i18n import t

# Inicialização da variável global logger (Resolve o NameError)
logger = get_logger()

# Espaçamento vertical entre "CONDIÇÕES DA ORDEM DE SERVIÇO" e "TERMO DE GARANTIA".
ESPACO_ENTRE_CONDICOES_E_TERMOS_OS = 52


def _quebrar_linha(c, texto: str, largura_max: float, fonte: str = "Helvetica", tamanho: int = 10):
    """Quebra texto em múltiplas linhas respeitando largura_max no canvas PDF."""
    palavras = (texto or "").split()
    linhas: list = []
    atual = ""
    for palavra in palavras:
        tentativa = f"{atual} {palavra}".strip()
        if c.stringWidth(tentativa, fonte, tamanho) <= largura_max:
            atual = tentativa
        else:
            if atual:
                linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas or [""]


def _sanitizar_nome_arquivo(nome: str) -> str:
    """Sanitiza nome para ser seguro em nomes de arquivo Windows/Linux.
    Remove espaços, acentos e caracteres especiais."""
    import unicodedata
    # Remove acentos
    nome = unicodedata.normalize('NFKD', nome)
    nome = nome.encode('ASCII', 'ignore').decode('ASCII')
    # Remove caracteres especiais e espaços, substituindo por underscore
    nome = re.sub(r'[^a-zA-Z0-9_-]', '_', nome)
    # Remove underscores múltiplos consecutivos
    nome = re.sub(r'_+', '_', nome)
    # Remove underscores nas pontas
    nome = nome.strip('_')
    return nome or "CLIENTE"


def obter_proximo_numero_orcamento_oficial():
    """Fonte única oficial da O.S. para sequência de numeração de orçamento."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'ultimo_orcamento'")
            res = cursor.fetchone()
            ultimo_config = int(res[0] or 0) if res else 0
            cursor.execute("SELECT COALESCE(MAX(id), 0) FROM orcamentos_aguardo")
            ultimo_banco = int((cursor.fetchone() or [0])[0] or 0)
        return max(ultimo_config, ultimo_banco, 500) + 1
    except Exception as e:
        logger.exception("Erro ao carregar próximo número oficial de orçamento: %s", e)
        return 501


def salvar_orcamento_aguardo_oficial(os_id: int, dados: dict, sinal: float = 0.0, saldo: float = 0.0):
    """Persistência oficial de O.S. usada pela tela de O.S. e fluxos rápidos do PDV."""
    if not isinstance(dados, dict):
        raise ValueError("Dados inválidos para salvar O.S.")

    status_final = normalizar_status_orcamento(dados.get("status", "AGUARDANDO"))

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO orcamentos_aguardo
            (id, cliente, telefone_cliente_whatsapp, equipamento, defeito, resumo_equipamento_defeito,
             valor_total, sinal, saldo, status, data, itens_detalhes, dados_adicionais)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(os_id),
                str(dados.get("cliente", "")),
                str(dados.get("telefone_cliente_whatsapp", "")),
                str(dados.get("equipamento", "")),
                str(dados.get("defeito", "")),
                str(dados.get("resumo_equipamento_defeito", "")),
                float(dados.get("total", 0.0) or 0.0),
                float(sinal or 0.0),
                float(saldo or 0.0),
                str(status_final),
                str(dados.get("data", "")),
                str(dados.get("itens_json", "[]")),
                str(dados.get("dados_adicionais", "{}")),
            ),
        )
        cursor.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('ultimo_orcamento', ?)", (int(os_id),))
        conn.commit()


def _subtotal_equipamento_payload(equipamento: dict) -> float:
    itens_ativos = []
    for item in (equipamento.get("itens") or []):
        if not isinstance(item, (list, tuple)) or len(item) < 4:
            continue
        status_item = str(item[4] if len(item) > 4 else "ATIVO").strip().upper()
        if status_item == "REPROVADO":
            continue
        itens_ativos.append(float(item[3] or 0))

    return OSCalculator.calcular_total(
        itens=itens_ativos,
        desconto=equipamento.get("desconto", 0),
        frete=equipamento.get("frete", 0),
        adicional=equipamento.get("opcional", 0),
    )


def salvar_os_completa(
    os_id: int,
    cliente: str,
    telefone: str,
    endereco: str,
    equipamentos: list[dict],
    status: str = STATUS_ORCAMENTO,
    forma_pagamento: str | None = None,
    on_save_callback=None,
):
    cliente_final = str(cliente or "").strip().upper()
    telefone_final = str(telefone or "").strip()
    endereco_final = str(endereco or "").strip()
    equipamentos_validos = [
        eq for eq in (equipamentos or [])
        if isinstance(eq, dict) and (eq.get("equipamento") or eq.get("defeito") or eq.get("itens"))
    ]

    if not cliente_final:
        raise ValueError("Informe o cliente antes de salvar a O.S.")
    if not equipamentos_validos:
        raise ValueError("Adicione ao menos um equipamento na O.S. antes de salvar.")

    itens_flat = []
    total_os = 0.0
    for eq in equipamentos_validos:
        total_os += _subtotal_equipamento_payload(eq)
        for item in eq.get("itens") or []:
            if isinstance(item, (list, tuple)) and len(item) >= 4:
                status_item = str(item[4] if len(item) > 4 else "ATIVO").strip().upper()
                itens_flat.append([str(item[0]), str(item[1]), str(item[2]), str(item[3]), status_item])

    primeiro_item = equipamentos_validos[0]
    resumo_equipamento_defeito = f"{str(primeiro_item.get('equipamento', '') or '').strip().upper()} - {str(primeiro_item.get('defeito', '') or '').strip().upper()}".strip(" -")
    status_final = normalizar_status_orcamento(status)

    sinal = OSCalculator.calcular_sinal_por_forma(total_os, forma_pagamento) if status_final == 'APROVADO' else 0.0
    saldo = float(total_os - sinal)

    dados = {
        "cliente": cliente_final,
        "telefone_cliente_whatsapp": telefone_final,
        "equipamento": primeiro_item.get("equipamento", ""),
        "defeito": primeiro_item.get("defeito", ""),
        "resumo_equipamento_defeito": resumo_equipamento_defeito,
        "total": total_os,
        "status": status_final,
        "data": datetime.now().strftime("%d/%m/%Y"),
        "itens_json": json.dumps(itens_flat),
        "dados_adicionais": json.dumps({
            "modo_os_por_cliente": True,
            "cliente_telefone": telefone_final,
            "cliente_endereco": endereco_final,
            "resumo_equipamento_defeito": resumo_equipamento_defeito,
            "equipamentos": equipamentos_validos,
            "equipamento_ativo_idx": None,
            "historico_itens_reprovados": [],
            "opcional": float(primeiro_item.get("opcional", 0.0)),
            "frete": float(primeiro_item.get("frete", 0.0)),
            "desconto": float(primeiro_item.get("desconto", 0.0)),
            "prazo": str(primeiro_item.get("prazo", "7 dias úteis")),
            "obs": str(primeiro_item.get("obs", "")),
            "forma_de_pagamento": forma_pagamento,
        })
    }

    salvar_orcamento_aguardo_oficial(os_id, dados, sinal=sinal, saldo=saldo)

    try:
        enviar_registro_os_central_silencioso({
            "id": int(os_id),
            "cliente": dados["cliente"],
            "status": dados["status"],
            "total": float(dados["total"]),
        }, operacao="upsert")
    except Exception:
        logger.exception("Falha ao enfileirar sincronização central da O.S. %s.", os_id)

    if callable(on_save_callback):
        on_save_callback()

    return dados


# --- CONFIGURACOES DE CAMINHOS ---
def _garantir_colunas_orcamentos_aguardo():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS status_orcamento (
                    status TEXT PRIMARY KEY,
                    ativo INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            for status in ("ORÇAMENTO", "AGUARDANDO ORÇAMENTO", "EM ANDAMENTO", "APROVADO", "FINALIZADO", "REPROVADO", "ENTREGUE"):
                cursor.execute(
                    "INSERT OR REPLACE INTO status_orcamento (status, ativo) VALUES (?, 1)",
                    (status,),
                )
            cursor.execute("UPDATE orcamentos_aguardo SET status = ? WHERE UPPER(COALESCE(status,'')) = 'AGUARDANDO'", (STATUS_ORCAMENTO,))
            cursor.execute("UPDATE orcamentos_aguardo SET status = ? WHERE UPPER(COALESCE(status,'')) = 'AGUARDANDO ORCAMENTO'", (STATUS_AGUARDANDO_ORCAMENTO,))
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS esquemas_vistas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fabricante TEXT,
                    modelo TEXT,
                    url TEXT UNIQUE,
                    origem TEXT
                )
            """)
            cursor.execute("PRAGMA table_info(orcamentos_aguardo)")
            cols = {row[1] for row in cursor.fetchall()}
            if "telefone_cliente_whatsapp" not in cols:
                cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN telefone_cliente_whatsapp TEXT")
            if "resumo_equipamento_defeito" not in cols:
                cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN resumo_equipamento_defeito TEXT")
            if "status_entrega" not in cols:
                cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN status_entrega TEXT")
            if "data_finalizacao" not in cols:
                cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN data_finalizacao TEXT")
            if "data_entrega" not in cols:
                cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN data_entrega TEXT")
            cursor.execute(
                """
                UPDATE orcamentos_aguardo
                SET resumo_equipamento_defeito = TRIM(
                        COALESCE(NULLIF(equipamento, ''), '') ||
                        CASE
                            WHEN COALESCE(NULLIF(equipamento, ''), '') <> ''
                             AND COALESCE(NULLIF(defeito, ''), '') <> '' THEN ' - '
                            ELSE ''
                        END ||
                        COALESCE(NULLIF(defeito, ''), '')
                    )
                WHERE COALESCE(NULLIF(resumo_equipamento_defeito, ''), '') = ''
                """
            )
            cursor.execute(
                """
                UPDATE orcamentos_aguardo
                SET status_entrega = COALESCE(NULLIF(status_entrega, ''), 'PENDENTE'),
                    data_finalizacao = COALESCE(NULLIF(data_finalizacao, ''), 'Vazio'),
                    data_entrega = COALESCE(NULLIF(data_entrega, ''), 'Vazio')
                WHERE status_entrega IS NULL OR status_entrega = ''
                   OR data_finalizacao IS NULL OR data_finalizacao = ''
                   OR data_entrega IS NULL OR data_entrega = ''
                """
            )
            conn.commit()
    except Exception as exc:
        logger.info("Falha ao garantir colunas extras de orcamentos_aguardo: %s", exc)


class FrmOS(ctk.CTkToplevel):
    def _montar_resumo_equipamento_defeito(self, equipamento: str, defeito: str) -> str:
        equipamento_limpo = str(equipamento or "").strip().upper()
        defeito_limpo = str(defeito or "").strip().upper()
        if equipamento_limpo and defeito_limpo:
            return f"{equipamento_limpo} - {defeito_limpo}"
        return equipamento_limpo or defeito_limpo

    def _link_funcional(self, url):
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36)'}, method='HEAD')
            with urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _selecionar_pagamento_simples(self):
        """Abre janela simples de pagamento e retorna {'condicao','metodo'} ou None."""
        dialogo = ctk.CTkToplevel(self)
        dialogo.title("Pagamento da O.S.")
        dialogo.geometry("460x420")
        dialogo.resizable(False, False)
        dialogo.attributes("-topmost", True)
        dialogo.configure(fg_color="#161b22")
        dialogo.grab_set()
        dialogo.focus_force()
        dialogo.lift()

        resultado = {"condicao": None, "metodo": None}

        ctk.CTkLabel(
            dialogo,
            text=t("label_condicao_pagamento"),
            font=("Arial", 14, "bold"),
            text_color="orange",
        ).pack(pady=(14, 8))

        ctk.CTkLabel(dialogo, text=t("ui_condi_o"), font=("Arial", 12, "bold"), text_color="#ecf0f1").pack(anchor="w", padx=20)
        f_cond = ctk.CTkFrame(dialogo, fg_color="#161b22")
        f_cond.pack(fill="x", padx=20, pady=(4, 10))

        lbl_cond = ctk.CTkLabel(dialogo, text=t("ui_condi_o_n_o_selecionada"), text_color="#95a5a6")
        lbl_cond.pack(anchor="w", padx=20, pady=(0, 10))

        def escolher_condicao(valor, texto):
            resultado["condicao"] = valor
            lbl_cond.configure(text=f"Condição: {texto}", text_color="#2ecc71")
            atualizar_estado_confirmar()

        ctk.CTkButton(f_cond, text=t("ui_50_entrada"), width=130, command=lambda: escolher_condicao("50%_sinal", "50% entrada")).pack(side="left", padx=4)
        ctk.CTkButton(f_cond, text=t("ui_100_vista"), width=130, command=lambda: escolher_condicao("100%_total", "100% à vista")).pack(side="left", padx=4)
        ctk.CTkButton(f_cond, text=t("ui_100_na_entrega"), width=130, command=lambda: escolher_condicao("100%_entrega", "100% na entrega")).pack(side="left", padx=4)

        ctk.CTkLabel(dialogo, text=t("ui_forma_de_pagamento"), font=("Arial", 12, "bold"), text_color="#ecf0f1").pack(anchor="w", padx=20) #
        f_met = ctk.CTkFrame(dialogo, fg_color="#161b22") #
        f_met.pack(fill="x", padx=20, pady=(4, 10)) #
        
        lbl_met = ctk.CTkLabel(dialogo, text=t("ui_forma_n_o_selecionada"), text_color="#95a5a6")
        lbl_met.pack(anchor="w", padx=20, pady=(0, 14))

        def escolher_metodo(valor):
            resultado["metodo"] = valor
            lbl_met.configure(text=f"Forma: {valor}", text_color="#2ecc71")
            atualizar_estado_confirmar()

        ctk.CTkButton(f_met, text=t("ui_pix"), width=130, command=lambda: escolher_metodo("PIX")).pack(side="left", padx=4)
        ctk.CTkButton(f_met, text=t("ui_cart_o"), width=130, command=lambda: escolher_metodo("CARTÃO")).pack(side="left", padx=4)
        ctk.CTkButton(f_met, text=t("ui_dinheiro"), width=130, command=lambda: escolher_metodo("DINHEIRO")).pack(side="left", padx=4)

        botoes = ctk.CTkFrame(dialogo, fg_color="#161b22")
        botoes.pack(fill="x", padx=20, pady=(4, 10))

        def confirmar():
            dialogo.destroy()

        btn_confirmar = ctk.CTkButton(botoes, text=t("btn_confirmar"), fg_color="#27ae60", state="disabled", command=confirmar)
        btn_confirmar.pack(side="left", padx=(0, 8), fill="x", expand=True)
        ctk.CTkButton(botoes, text=t("btn_cancelar"), fg_color="#7f8c8d", command=dialogo.destroy).pack(side="left", fill="x", expand=True)

        def atualizar_estado_confirmar():
            if resultado["condicao"] and resultado["metodo"]:
                btn_confirmar.configure(state="normal")

        dialogo.wait_window()
        if resultado["condicao"] and resultado["metodo"]:
            return resultado
        return None

    def _lancar_financeiro_pos_aprovacao(self, total, cliente, forma_pagamento, metodo_pagamento):
        """Lança no financeiro apenas quando há recebimento imediato."""
        if forma_pagamento == "100%_entrega":
            return

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM fluxo_caixa WHERE descricao LIKE ?", (f"%O.S. {self.num_oc}%",))
            if cursor.fetchone() is not None:
                return

            valor = total if forma_pagamento == "100%_total" else OSCalculator.calcular_sinal(total)
            descricao = (
                f"O.S. {self.num_oc} - {cliente} (100% TOTAL)"
                if forma_pagamento == "100%_total"
                else f"SINAL O.S. {self.num_oc} - {cliente} (50% ENTRADA)"
            )
            cursor.execute(
                "INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento) VALUES (?,?,?,?,?,?)",
                (datetime.now().strftime("%d/%m/%Y"), descricao, "ENTRADA", valor, "ORDEM DE SERVIÇO", metodo_pagamento),
            )
            conn.commit()


    def __init__(self, master, id_orc=None, on_save_callback=None, dados_precarregados=None):
        super().__init__(master)
        # MODO SEGURANCA: init minimizado para diagnosticar travamento no carregamento.
        # Todas as inicializacoes de banco, rede, threads, leitura de arquivos e montagem de UI complexa
        # foram removidas temporariamente desta copia de teste.
        self.title("SISTEMA FRS - TESTE MINIMO")
        self.geometry("1000x650")
        self.resizable(True, True)
        self.configure(fg_color="#d9d9d9")
        self.lift()
        self.focus_force()

        self._lbl_teste = ctk.CTkLabel(
            self,
            text=t("ui_tela_os_teste_modo_minimo_sem_banco_threads_assets"),
            font=("Arial", 16, "bold"),
            text_color="#1f2937",
        )
        self._lbl_teste.pack(pady=24)

    def _aplicar_dados_precarregados(self):
        dados = self._dados_precarregados or {}
        if not dados:
            return
        try:
            cliente = str(dados.get("cliente") or "").strip().upper()
            equipamento = str(dados.get("equipamento") or "").strip().upper()
            defeito = str(dados.get("defeito") or "").strip().upper()
            status = normalizar_status_orcamento(dados.get("status") or STATUS_ORCAMENTO)

            if cliente:
                self.txt_cliente.delete(0, 'end')
                self.txt_cliente.insert(0, cliente)
            if equipamento:
                self.txt_equip.delete(0, 'end')
                self.txt_equip.insert(0, equipamento)
            if defeito:
                self.txt_defeito.delete(0, 'end')
                self.txt_defeito.insert(0, defeito)

            self.atualizar_identificacao_documento(status)
        except Exception:
            pass

    def destroy(self):
        """Fecha a janela de forma segura para evitar travamentos em encerramento."""
        try:
            try:
                for after_id in self.tk.call("after", "info"):
                    self.after_cancel(after_id)
            except Exception:
                pass
            self.withdraw()
            super().destroy()
        except Exception:
            pass
            
    def _setup_interface(self):
        # Limpa o frame_conteudo antes de adicionar widgets
        for widget in self.frame_conteudo.winfo_children():
            widget.destroy()

        self.frame_conteudo.grid_columnconfigure(0, weight=1)
        self.frame_conteudo.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self.frame_conteudo, fg_color="#1f2a38", corner_radius=20)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(0, 5))
        self.lbl_oc = ctk.CTkLabel(header, text=f"ORÇAMENTO Nº: {self.num_oc}", font=("Arial", 24, "bold"), text_color="orange")
        self.lbl_oc.pack(side="left", padx=15, pady=15)
        ctk.CTkLabel(header, text=t("ui_registro_r_pido_cliente_equipamentos_or_amento_por_item_quan"), font=("Arial", 10), text_color="#bdc3c7").pack(side="left", padx=15)
        self.atualizar_identificacao_documento(self.status_documento)

        # LAYOUT ÚNICO: CTkScrollableFrame substituindo TabView
        self.main_scroll = ctk.CTkScrollableFrame(self.frame_conteudo, fg_color="#181c24")
        self.main_scroll.grid(row=1, column=0, padx=10, pady=0, sticky="nsew")

        # Bloco 1: Dados do Cliente
        f_dados = ctk.CTkFrame(self.main_scroll, fg_color="#1f2a38", corner_radius=20)
        f_dados.pack(pady=10, padx=10, fill="x")
        f_dados.grid_columnconfigure(0, weight=3)
        f_dados.grid_columnconfigure(1, weight=1)
        f_dados.grid_columnconfigure(2, weight=3)

        ctk.CTkLabel(f_dados, text=t("ui_cliente_1"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=0, padx=(15, 5), pady=(10, 2), sticky="w")
        ctk.CTkLabel(f_dados, text=t("ui_busca"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=1, padx=(0, 15), pady=(10, 2), sticky="e")
        ctk.CTkLabel(f_dados, text=t("ui_telefone_whatsapp"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=2, padx=(0, 15), pady=(10, 2), sticky="w")

        self.txt_cliente = ctk.CTkEntry(f_dados, placeholder_text=t("ui_nome_do_cliente"), width=300)
        self.txt_cliente.grid(row=1, column=0, padx=(15, 5), pady=(0, 12), sticky="ew")
        self.txt_cliente.bind("<Return>", self.buscar_cliente)
        self.txt_cliente.bind("<FocusOut>", self.buscar_cliente)

        self.btn_lupa = ctk.CTkButton(f_dados, text="🔍", width=50, fg_color="#2980b9", command=self.abrir_consulta_clientes)
        self.btn_lupa.grid(row=1, column=1, padx=(0, 15), pady=(0, 12), sticky="e")

        self.txt_fone = ctk.CTkEntry(f_dados, placeholder_text=t("ui_telefone_whatsapp"), width=250)
        self.txt_fone.grid(row=1, column=2, padx=(0, 15), pady=(0, 12), sticky="ew")

        # Mantido apenas para compatibilidade com fluxos legados (campo oculto no novo UX).
        self.txt_end_cliente = ctk.CTkEntry(f_dados, placeholder_text=t("ui_endere_o_completo"), width=400)

        # Bloco 2: Dados do Equipamento
        f_equip = ctk.CTkFrame(self.main_scroll, fg_color="#1f2a38", corner_radius=20)
        f_equip.pack(pady=5, padx=10, fill="x")
        f_equip.grid_columnconfigure(0, weight=2)
        f_equip.grid_columnconfigure(1, weight=1)
        f_equip.grid_columnconfigure(2, weight=3)

        ctk.CTkLabel(f_equip, text=t("ui_modelo_equipamento"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=0, padx=(15, 5), pady=(10, 2), sticky="w")
        ctk.CTkLabel(f_equip, text=t("ui_diagrama"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=1, padx=(0, 5), pady=(10, 2), sticky="w")
        ctk.CTkLabel(f_equip, text=t("ui_defeito_relatado"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=2, padx=(0, 15), pady=(10, 2), sticky="w")

        f_modelo = ctk.CTkFrame(f_equip, fg_color="#1f2a38")
        f_modelo.grid(row=1, column=0, padx=(15, 5), pady=(0, 10), sticky="ew")
        f_modelo.grid_columnconfigure(0, weight=1)

        self.txt_equip = ctk.CTkEntry(f_modelo, placeholder_text=t("ui_modelo_equipamento"), width=300)
        self.txt_equip.grid(row=0, column=0, padx=(0, 4), pady=0, sticky="ew")
        self.txt_equip.bind("<KeyRelease>", self._agendar_vigilancia_preventiva)
        self.txt_equip.bind("<FocusOut>", self._iniciar_vigilancia_preventiva)
        self.txt_equip.bind("<Return>", lambda _e: self._adicionar_equipamento())

        self.lbl_alerta_preventivo = ctk.CTkLabel(f_modelo, text="", width=22, text_color="#f1c40f", font=("Arial", 15, "bold"), cursor="hand2")
        self.lbl_alerta_preventivo.grid(row=0, column=1, padx=(0, 2), pady=0, sticky="e")
        self.lbl_alerta_preventivo.bind("<Enter>", self._mostrar_tooltip_alerta_preventivo)
        self.lbl_alerta_preventivo.bind("<Leave>", self._ocultar_tooltip_alerta_preventivo)
        self.lbl_alerta_preventivo.bind("<Button-1>", self._mostrar_tooltip_alerta_preventivo)
        
        self.btn_buscar_vista = ctk.CTkButton(f_equip, text=t("ui_buscar_diagrama"), width=150, fg_color="#8e44ad", hover_color="#9b59b6", 
                                              command=lambda: self.buscar_vista_equipamento(self.txt_equip.get()))
        self.btn_buscar_vista.grid(row=1, column=1, padx=(0, 5), pady=(0, 10), sticky="ew")
        self.txt_defeito = ctk.CTkEntry(f_equip, placeholder_text=t("ui_defeito_relatado"), width=400)
        self.txt_defeito.grid(row=1, column=2, padx=(0, 15), pady=(0, 10), sticky="ew")
        self.txt_defeito.bind("<Return>", lambda _e: self._adicionar_equipamento())

        f_lista_equip = ctk.CTkFrame(self.main_scroll, fg_color="#1f2a38", corner_radius=20)
        f_lista_equip.pack(fill="x", pady=5, padx=10)
        ctk.CTkLabel(f_lista_equip, text=t("ui_itens_da_o_s_envelope_do_cliente"), font=("Arial", 12, "bold"), text_color="#ecf0f1").pack(anchor="w", padx=15, pady=(10, 6))
        barra_equip = ctk.CTkFrame(f_lista_equip, fg_color="#1f2a38")
        barra_equip.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(barra_equip, text=t("ui_adicionar_item"), fg_color="#27ae60", width=160, command=self._adicionar_equipamento).pack(side="left", padx=(0, 8), pady=4)
        ctk.CTkButton(barra_equip, text=t("ui_remover_item_1"), fg_color="#c0392b", width=150, command=self._remover_equipamento_ativo).pack(side="left", padx=(0, 8), pady=4)

        self.tab_equipamentos = ttk.Treeview(f_lista_equip, columns=("idx", "equip", "def", "subtotal", "status"), show="headings", height=5)
        self.tab_equipamentos.heading("idx", text="#")
        self.tab_equipamentos.heading("equip", text=t("ui_equipamento"))
        self.tab_equipamentos.heading("def", text=t("ui_defeito"))
        self.tab_equipamentos.heading("subtotal", text=t("ui_subtotal"))
        self.tab_equipamentos.heading("status", text=t("ui_status"))
        self.tab_equipamentos.column("idx", width=40, anchor="center")
        self.tab_equipamentos.column("equip", width=280)
        self.tab_equipamentos.column("def", width=340)
        self.tab_equipamentos.column("subtotal", width=120, anchor="e")
        self.tab_equipamentos.column("status", width=100, anchor="center")
        self.tab_equipamentos.pack(fill="x", padx=15, pady=(0, 12))
        self.tab_equipamentos.bind("<<TreeviewSelect>>", self._on_selecionar_equipamento)
        self.tab_equipamentos.tag_configure("reprovado", foreground="#fca5a5")

        # Checklist
        f_check = ctk.CTkFrame(self.main_scroll, fg_color="#1f2a38", corner_radius=20)
        f_check.pack(fill="x", pady=5, padx=10)
        ctk.CTkLabel(f_check, text=t("ui_acompanha"), font=("Arial", 12, "bold"), text_color="#ecf0f1").pack(side="left", padx=15, pady=10)
        self._chk_widgets = []
        for text, var in [("CAPA", self.check_capa), ("LINHA", self.check_linha), ("MANIVELA", self.check_manivela), ("CAIXA", self.check_caixa)]:
            chk = ctk.CTkCheckBox(f_check, text=text, variable=var, onvalue="SIM", offvalue="NÃO", text_color="#ecf0f1")
            chk.pack(side="left", padx=6)
            self._chk_widgets.append(chk)

        # Bloco 3: Tabela de Peças e Serviços (Treeview)
        f_item = ctk.CTkFrame(self.main_scroll, fg_color="#1f2a38", corner_radius=20)
        f_item.pack(fill="x", pady=5, padx=10)
        ctk.CTkLabel(f_item, text=t("ui_descri_o"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=0, padx=(15, 5), pady=(8, 0), sticky="w")
        ctk.CTkLabel(f_item, text=t("ui_qtd"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=1, padx=3, pady=(8, 0), sticky="w")
        ctk.CTkLabel(f_item, text=t("ui_valor_unit"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=2, padx=3, pady=(8, 0), sticky="w")
        ctk.CTkLabel(f_item, text=t("ui_a_es"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=3, columnspan=3, padx=(5, 15), pady=(8, 0), sticky="w")
        self.txt_serv = ctk.CTkEntry(f_item, placeholder_text=t("ui_descri_o_da_pe_a_servi_o"), width=400)
        self.txt_serv.grid(row=1, column=0, padx=(15, 5), pady=(2, 10), sticky="ew")
        self.txt_serv.bind("<KeyRelease>", self.sugerir_preco)
        self.txt_serv.bind("<Return>", lambda _e: self.add_item())
        self.txt_qtd = ctk.CTkEntry(f_item, width=70)
        self.txt_qtd.insert(0, "1")
        self.txt_qtd.grid(row=1, column=1, padx=3, pady=(2, 10))
        self.txt_qtd.bind("<Return>", lambda _e: self.add_item())
        self.txt_val = ctk.CTkEntry(f_item, placeholder_text=t("ui_r_unit"), width=100)
        self.txt_val.grid(row=1, column=2, padx=3, pady=(2, 10))
        self.txt_val.bind("<Return>", lambda _e: self.add_item())
        self.btn_add = ctk.CTkButton(f_item, text=t("ui_add"), fg_color="#27ae60", width=90, command=self.add_item)
        self.btn_add.grid(row=1, column=3, padx=(5, 15), pady=(2, 10))
        f_item.grid_columnconfigure(0, weight=1)

        self.tab = ttk.Treeview(self.main_scroll, columns=("d","q","u","t","s"), show="headings", height=8, displaycolumns=("d","q","u","t"))
        self.tab.heading("d", text=t("ui_descri_o"))
        self.tab.heading("q", text=t("ui_qtd"))
        self.tab.heading("u", text=t("ui_unit"))
        self.tab.heading("t", text=t("ui_total"))
        self.tab.heading("s", text=t("ui_status_1"))
        self.tab.column("d", width=520)
        self.tab.column("q", width=80, anchor="center")
        self.tab.column("u", width=120, anchor="center")
        self.tab.column("t", width=120, anchor="center")
        self.tab.column("s", width=120, anchor="center")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=30, font=("Arial", 11))
        style.configure("Treeview.Heading", font=("Arial", 11, "bold"))
        style.configure("evenrow.Treeview", background="#2c3e50")
        style.configure("oddrow.Treeview", background="#34495e")
        self.tab.pack(pady=(5, 10), padx=10, fill="both", expand=True)
        self.tabela = self.tab
        self.tab.tag_configure('reprovado', foreground="#fca5a5")

        self.botao_remover = tk.Button(
            self.main_scroll,
            text=t("ui_remover"),
            width=12,
            bg="#c0392b",
            fg="#ffffff",
            activebackground="#a93226",
            relief="raised",
            command=self.remover_item_selecionado,
        )
        self.botao_remover.pack(anchor="e", padx=12, pady=(0, 8))
        self.btn_remover = self.botao_remover

        self.lbl_hist_itens = ctk.CTkLabel(
            self.main_scroll,
            text=t("ui_hist_rico_de_itens_reprovados_removidos_0"),
            font=("Arial", 10, "bold"),
            text_color="#f59e0b",
            anchor="w",
        )
        self.lbl_hist_itens.pack(fill="x", padx=14, pady=(0, 6))

        footer_frame = ctk.CTkFrame(self.main_scroll, fg_color="#1f2a38", corner_radius=20)
        footer_frame.pack(fill="x", pady=5, padx=10)
        # Ajusta a configuração das colunas para o novo layout
        footer_frame.grid_columnconfigure(0, weight=1) # Opcional
        footer_frame.grid_columnconfigure(1, weight=1) # Frete
        footer_frame.grid_columnconfigure(2, weight=1) # Desconto
        footer_frame.grid_columnconfigure(3, weight=2) # Total Geral (ocupa mais espaço à direita)

        # Labels dos campos financeiros
        ctk.CTkLabel(footer_frame, text=t("ui_opcional"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=0, padx=5, pady=(8, 0), sticky="w")
        ctk.CTkLabel(footer_frame, text=t("ui_frete"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=1, padx=5, pady=(8, 0), sticky="w")
        ctk.CTkLabel(footer_frame, text=t("ui_desconto"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=2, padx=5, pady=(8, 0), sticky="w")
        ctk.CTkLabel(footer_frame, text=t("ui_total_geral"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(row=0, column=3, padx=10, pady=(8, 0), sticky="e")

        # Campos Opcional, Frete, Desconto na linha de entrada (row=1)
        self.ent_opcional = ctk.CTkEntry(footer_frame, placeholder_text=t("ui_opcional_r"), width=100) # Largura reduzida
        self.ent_opcional.grid(row=1, column=0, padx=5, pady=(2, 10), sticky="ew")
        self.ent_opcional.bind("<KeyRelease>", lambda e: self.atualizar_total())
        self.ent_opcional.configure(state="normal")

        self.ent_frete = ctk.CTkEntry(footer_frame, placeholder_text=t("ui_frete_r"), width=100) # Largura reduzida
        self.ent_frete.grid(row=1, column=1, padx=5, pady=(2, 10), sticky="ew")
        self.ent_frete.bind("<KeyRelease>", lambda e: self.atualizar_total())
        self.ent_frete.configure(state="normal")

        self.ent_desc = ctk.CTkEntry(footer_frame, placeholder_text=t("ui_desconto_r"), width=100) # Largura reduzida
        self.ent_desc.grid(row=1, column=2, padx=5, pady=(2, 10), sticky="ew")
        self.ent_desc.bind("<KeyRelease>", lambda e: self.atualizar_total())
        self.ent_desc.configure(state="normal")

        self.lbl_total = ctk.CTkLabel(footer_frame, text=t("ui_total_o_s_r_0_00"), font=("Arial", 14, "bold"), text_color="#2ecc71")
        self.lbl_total.grid(row=1, column=3, padx=10, pady=(2, 10), sticky="e") # Alinhado à direita

        # Prazo de Entrega com rótulo explícito
        ctk.CTkLabel(footer_frame, text=t("ui_prazo_de_entrega"), font=("Arial", 10, "bold"), text_color="#bdc3c7").grid(
            row=2, column=0, columnspan=4, padx=10, pady=(2, 2), sticky="w"
        )
        self.txt_prazo = ctk.CTkEntry(footer_frame, placeholder_text=t("ui_prazo_de_entrega"))
        self.txt_prazo.grid(row=3, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="ew") # Ocupa todas as colunas
        self.txt_prazo.insert(0, "7 dias úteis")

        # Área de Observação (f_obs) ocupa todo o espaço restante
        self.f_obs = ctk.CTkFrame(footer_frame, fg_color="#181c24")
        self.f_obs.grid(row=4, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="nsew") # Ocupa todas as colunas e expande
        self.f_obs.grid_columnconfigure(0, weight=1)
        self.f_obs.grid_rowconfigure(1, weight=1) # Faz o txt_obs expandir verticalmente

        self.lbl_obs = ctk.CTkLabel(
            self.f_obs,
            text=t("ui_observa_o"),
            font=("Arial", 10),
            text_color="#bdc3c7",
        )
        self.lbl_obs.grid(row=0, column=0, padx=(2, 0), pady=(2, 2), sticky="w")

        self.txt_obs = ctk.CTkTextbox(self.f_obs, height=80, wrap="word") # Aumenta a altura inicial
        self.txt_obs.grid(row=1, column=0, padx=0, pady=0, sticky="nsew") # Expande em todas as direções

        # Status da busca de diagrama em uma nova linha
        self.lbl_status_busca_diagrama = ctk.CTkLabel(
            footer_frame,
            text="",
            font=("Arial", 10),
            text_color="#95a5a6",
            anchor="w",
            justify="left",
        )
        self.lbl_status_busca_diagrama.grid(row=5, column=0, columnspan=4, padx=10, pady=(0, 8), sticky="ew") # Ocupa todas as colunas
        self.main_scroll._parent_canvas.yview_moveto(0) # Inicia no topo

        # Lista de todos os campos editáveis para controle de travamento
        self._campos_bloqueio = [
            self.txt_cliente, self.txt_fone, self.txt_end_cliente,
            self.txt_equip, self.txt_defeito,
            self.txt_serv, self.txt_qtd, self.txt_val,
            self.ent_opcional, self.ent_frete, self.ent_desc,
            self.txt_prazo, self.txt_obs,
        ]

    def atualizar_identificacao_documento(self, status):
        """Atualiza a identidade visual do documento (Orçamento vs O.S.) e o título com base no status."""
        status_up = str(status or "AGUARDANDO").upper()
        self.status_documento = status_up
        
        # Lógica para determinar se o documento é um Orçamento ou uma O.S.
        if status_up in ("APROVADO", "FINALIZADO", "ENTREGUE", "EM ANDAMENTO"):
            self.tipo_documento = "ORDEM DE SERVIÇO"
            cor = "#2ecc71"  # Verde para O.S.
            prefixo = "O.S. Nº"
        elif status_up == "REPROVADO":
            self.tipo_documento = "ORÇAMENTO REPROVADO"
            cor = "#c0392b"  # Vermelho para Reprovado
            prefixo = "ORÇ. Nº"
        else:
            self.tipo_documento = "ORÇAMENTO"
            cor = "orange"   # Laranja padrão para orçamentos novos/aguardando
            prefixo = "ORÇAMENTO Nº"

        # Atualiza o label do número do documento e o botão de geração de PDF
        if hasattr(self, 'lbl_oc'):
            self.lbl_oc.configure(text=f"{prefixo}: {self.num_oc}", text_color=cor)
        
        if hasattr(self, 'btn_pdf'):
            self.btn_pdf.configure(text=f"📄 GERAR {self.tipo_documento}")

    def _aplicar_maximizacao(self):
        try:
            self.state("zoomed") #
        except Exception: #
            pass #
        try: #
            self.attributes("-zoomed", True)
            return
        except Exception:
            pass
        try:
            w = self.winfo_screenwidth()
            h = self.winfo_screenheight()
            self.geometry(f"{w}x{h}+0+0")
        except Exception:
            pass

    def carregar_proximo_numero(self):
        return obter_proximo_numero_orcamento_oficial()

    def _parse_valor(self, valor, default=0.0):
        """Converte valores monetários aceitando vírgula ou ponto."""
        return OSCalculator.parse_monetario(valor, default=default)

    def carregar_dados_oficina(self):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT nome_oficina, endereco_oficina, telefone_oficina, chave_pix, logo_path, logo_patrocinador_path
                    FROM dados_oficina
                    WHERE id = 1
                    """
                )
                res = cursor.fetchone()
            if res:
                self.nome_oficina = res[0] or self.nome_oficina
                self.endereco_oficina = res[1] or self.endereco_oficina
                self.telefone_oficina = res[2] or self.telefone_oficina
                self.chave_pix = res[3] or self.chave_pix
                self.logo_oficina = res[4] or self.logo_oficina
                self.logo_patrocinador = (res[5] or self.logo_patrocinador) if len(res) > 5 else self.logo_patrocinador
        except Exception as e:
            logger.exception("Erro ao carregar dados da oficina: %s", e)

    def abrir_config_oficina(self):
        janela = ctk.CTkToplevel(self)
        janela.title("DADOS DA OFICINA")
        janela.geometry("620x500")
        janela.resizable(False, False)
        janela.grab_set()
        janela.focus_force()

        ctk.CTkLabel(janela, text=t("ui_configurar_layout_da_oficina"), font=("Arial", 20, "bold"), text_color="orange").pack(pady=(20, 12))

        form = ctk.CTkFrame(janela)
        form.pack(fill="both", expand=True, padx=20, pady=10)

        ent_nome = ctk.CTkEntry(form, placeholder_text=t("ui_nome_da_oficina"))
        ent_nome.pack(fill="x", padx=15, pady=(15, 8))
        ent_nome.insert(0, self.nome_oficina)

        ent_endereco = ctk.CTkEntry(form, placeholder_text=t("ui_endere_o"))
        ent_endereco.pack(fill="x", padx=15, pady=8)
        ent_endereco.insert(0, self.endereco_oficina)

        ent_fone = ctk.CTkEntry(form, placeholder_text=t("ui_telefone"))
        ent_fone.pack(fill="x", padx=15, pady=8)
        ent_fone.insert(0, self.telefone_oficina)

        ent_pix = ctk.CTkEntry(form, placeholder_text=t("ui_chave_pix"))
        ent_pix.pack(fill="x", padx=15, pady=8)
        ent_pix.insert(0, self.chave_pix)

        logo_var = ctk.StringVar(value=self.logo_oficina)
        f_logo = ctk.CTkFrame(form, fg_color="#1f2a38")
        f_logo.pack(fill="x", padx=15, pady=(8, 4))
        ent_logo = ctk.CTkEntry(f_logo, textvariable=logo_var)
        ent_logo.pack(side="left", fill="x", expand=True)

        def escolher_logo():
            caminho = filedialog.askopenfilename(
                parent=janela,
                title="Selecionar imagem da oficina",
                filetypes=[("Imagens", "*.png;*.jpg;*.jpeg;*.webp")]
            )
            if caminho:
                logo_var.set(caminho)

        ctk.CTkButton(f_logo, text=t("ui_imagem"), width=90, fg_color="#2980b9", command=escolher_logo).pack(side="left", padx=(8, 0))

        def salvar():
            nome = ent_nome.get().strip()
            endereco = ent_endereco.get().strip()
            telefone = ent_fone.get().strip()
            pix = ent_pix.get().strip()
            logo = logo_var.get().strip()

            if not nome:
                messagebox.showwarning("Atenção", "Informe o nome da oficina.", parent=janela)
                return

            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE dados_oficina
                        SET nome_oficina = ?, endereco_oficina = ?, telefone_oficina = ?, chave_pix = ?, logo_path = ?
                        WHERE id = 1
                        """,
                        (nome, endereco, telefone, pix, logo)
                    )
                    conn.commit()

                self.nome_oficina = nome
                self.endereco_oficina = endereco
                self.telefone_oficina = telefone
                self.chave_pix = pix
                self.logo_oficina = logo

                messagebox.showinfo("Sucesso", "Dados da oficina atualizados no layout.", parent=janela)
                janela.destroy()
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível salvar: {e}", parent=janela)

        def _descobrir_oficina_udp(timeout_total=5.0):
            payload = json.dumps({
                "type": "OFP_DISCOVER_REQUEST",
                "app": "oficina_pesca",
                "source": "desktop_oficina_cfg",
            }).encode("utf-8")
            fim = datetime.now().timestamp() + timeout_total
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.settimeout(0.9)
                sock.bind(("", 0))
                while datetime.now().timestamp() < fim:
                    try:
                        sock.sendto(payload, ("255.255.255.255", 42111))
                    except Exception:
                        pass
                    try:
                        resp, addr = sock.recvfrom(4096)
                        data = json.loads(resp.decode("utf-8", errors="ignore"))
                        tipo = str(data.get("type", "")).strip().upper()
                        if tipo not in ("OFP_DISCOVER_RESPONSE", "OFP_DISCOVERY"):
                            continue
                        host = str(data.get("host", "")).strip() or str(addr[0]).strip()
                        port = int(data.get("port", 8000) or 8000)
                        if host and port > 0:
                            return f"http://{host}:{port}"
                    except socket.timeout:
                        continue
                    except Exception:
                        continue
            return ""

        def _salvar_servidor_url_cfg(url_base: str):
            caminhos = [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.cfg"),
                os.path.join(os.getcwd(), "config.cfg"),
            ]
            cfg_path = ""
            for p in caminhos:
                if os.path.exists(p):
                    cfg_path = p
                    break
            if not cfg_path:
                cfg_path = caminhos[0]

            parser = configparser.ConfigParser()
            if os.path.exists(cfg_path):
                parser.read(cfg_path, encoding="utf-8")
            if not parser.has_section("app"):
                parser.add_section("app")
            parser.set("app", "servidor_url", url_base)
            with open(cfg_path, "w", encoding="utf-8") as f:
                parser.write(f)
            return cfg_path

        def localizar_oficina_rede_cfg():
            btn_localizar.configure(state="disabled", text=t("ui_localizando"))
            lbl_rede.configure(text=t("ui_buscando_servidor_na_rede_local"), text_color="#f1c40f")

            def worker():
                url = ""
                erro = ""
                try:
                    url = _descobrir_oficina_udp(timeout_total=5.0)
                except Exception as e:
                    erro = str(e)

                def finalizar():
                    btn_localizar.configure(state="normal", text=t("ui_localizar_oficina_na_rede"))
                    if not url:
                        lbl_rede.configure(text=t("ui_oficina_n_o_localizada_na_rede"), text_color="#e74c3c")
                        msg = "Não foi possível localizar a oficina automaticamente na rede."
                        if erro:
                            msg += f"\n\nDetalhe: {erro}"
                        messagebox.showwarning("Rede Local", msg, parent=janela)
                        return
                    try:
                        caminho = _salvar_servidor_url_cfg(url)
                        lbl_rede.configure(text=f"Oficina localizada: {url}", text_color="#2ecc71")
                        messagebox.showinfo("Rede Local", f"Oficina localizada com sucesso!\n\nServidor: {url}\nConfig salvo em: {caminho}", parent=janela)
                    except Exception as e:
                        lbl_rede.configure(text=t("ui_servidor_encontrado_mas_falha_ao_salvar"), text_color="#f39c12")
                        messagebox.showwarning("Rede Local", f"Servidor encontrado: {url}\nFalha ao salvar config: {e}", parent=janela)

                self.after(0, finalizar)

            # Modo teste síncrono: execução direta sem thread.
            worker()

        bloco_rede = ctk.CTkFrame(form, fg_color="#1f2937")
        bloco_rede.pack(fill="x", padx=15, pady=(4, 10))
        ctk.CTkLabel(
            bloco_rede,
            text=t("ui_configura_o_t_cnica_de_rede"),
            text_color="orange",
            font=("Arial", 13, "bold"),
        ).pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(
            bloco_rede,
            text="Use 'Localizar' para configurar o IP do servidor central.",
            text_color="#94a3b8",
            font=("Arial", 11),
        ).pack(anchor="w", padx=10, pady=(0, 8))

        f_srv = ctk.CTkFrame(bloco_rede, fg_color="#1f2937")
        f_srv.pack(fill="x", padx=10, pady=5)

        btn_localizar = ctk.CTkButton(f_srv, text=t("ui_localizar_oficina_na_rede"), command=localizar_oficina_rede_cfg)
        btn_localizar.pack(side="left", padx=5)
        lbl_rede = ctk.CTkLabel(f_srv, text="")
        lbl_rede.pack(side="left", padx=5)

        ctk.CTkButton(janela, text=t("ui_salvar_dados"), fg_color="#27ae60", command=salvar).pack(pady=20)

    def _atualizar_alerta_ui(self, modelo, alerta=False):
        """Atualiza a sinalização visual de alertas preventivos (Thread Safe)."""
        def update():
            if not self.winfo_exists(): return
            if alerta:
                self.lbl_alerta_preventivo.configure(text="⚠")
            else:
                self.lbl_alerta_preventivo.configure(text="")
        self.after(0, update)

    def _normalizar_forma_pagamento(self, condicao_pagamento=None):
        """Converte entradas legadas para o padrão canônico de pagamento."""
        bruto = condicao_pagamento if condicao_pagamento is not None else self.var_pagamento.get()
        valor = str(bruto or "").strip().upper()
        if valor in ("VISTA", "100%_TOTAL", "100_TOTAL", "100%"):
            return "100%_total"
        if valor in ("100%_ENTREGA", "ENTREGA", "TOTAL_ENTREGA", "100% NA ENTREGA"):
            return "100%_entrega"
        return "50%_sinal"

    def salvar_documento(self, status='AGUARDANDO', forma_de_pagamento=None):
        """Persiste os dados da O.S. no banco local e sincroniza remotamente."""
        inicio_salvamento = time.perf_counter()
        try:
            forma_pagamento = self._normalizar_forma_pagamento(forma_de_pagamento) if status == 'APROVADO' else None

            # Garante que alterações do item em edição sejam persistidas na estrutura em memória.
            self._salvar_equipamento_ativo()

            # Se ainda não houver item na lista, tenta aproveitar o equipamento digitado.
            if not self.os_equipamentos and self.txt_equip.get().strip() and self.txt_defeito.get().strip():
                self.os_equipamentos.append(
                    {
                        "equipamento": self.txt_equip.get().strip().upper(),
                        "defeito": self.txt_defeito.get().strip().upper(),
                        "itens": self._coletar_itens_tabela(),
                        "opcional": float(self._parse_valor(self.ent_opcional.get())),
                        "frete": float(self._parse_valor(self.ent_frete.get())),
                        "desconto": float(self._parse_valor(self.ent_desc.get())),
                        "prazo": self.txt_prazo.get().strip() or "7 dias úteis",
                        "obs": self.txt_obs.get("1.0", "end-1c").strip(),
                    }
                )

            dados = salvar_os_completa(
                self.num_oc,
                self.txt_cliente.get().strip().upper(),
                self._normalizar_telefone_whatsapp(self.txt_fone.get()),
                self.txt_end_cliente.get().strip(),
                list(self.os_equipamentos),
                status=status,
                forma_pagamento=forma_pagamento,
                on_save_callback=self.on_save_callback,
            )
            
            self.atualizar_identificacao_documento(dados["status"])
            duracao = time.perf_counter() - inicio_salvamento
            if duracao >= 1.5:
                logger.warning("Salvamento da O.S. %s concluiu em %.2fs.", self.num_oc, duracao)
            else:
                logger.info("O.S. %s salva com status %s em %.2fs.", self.num_oc, dados["status"], duracao)
            return dados
        except Exception as e:
            logger.exception("Erro ao salvar O.S. %s.", getattr(self, "num_oc", "?"))
            messagebox.showerror("Erro", f"Erro ao salvar: {e}")
            return None

    def gerar_documento_pdf(self, tipo_documento=None, eh_os=False, forma_de_pagamento=None):
        """Wrapper para o gerador de PDF original. Mantém o layout Reportlab intacto."""
        if eh_os:
            tipo = "ORDEM DE SERVIÇO"
            prefixo = "Ordem_de_Servico_N"
        else:
            tipo = tipo_documento or self.tipo_documento or "ORÇAMENTO"
            prefixo = "Orcamento_N"
            
        # Adiciona nome do cliente sanitizado ao filename
        cliente = self.txt_cliente.get().strip().upper()
        cliente_sanitizado = _sanitizar_nome_arquivo(cliente) if cliente else "CLIENTE"
        nome_arquivo = f"{prefixo}{self.num_oc}_{cliente_sanitizado}.pdf"
        
        self.update_idletasks()
        self.focus_force()
        self.attributes('-topmost', False)
        try:
            caminho = filedialog.asksaveasfilename(
                parent=self,
                defaultextension=".pdf",
                initialfile=nome_arquivo,
            )
        finally:
            self.attributes('-topmost', True)
            self.focus_force()

        if not caminho:
            return None

        self.gerar_pdf_fiel(caminho, tipo_documento=tipo, condicao_pagamento=forma_de_pagamento)
        try:
            enviar_arquivo_para_drive_usuario(caminho, pasta_remota="Oficina de Pesca - PDFs")
        except Exception:
            pass
        # os.startfile(caminho) # REMOVIDO: Para não bloquear a UI
        try:
            webbrowser.open(caminho) # Abre o PDF de forma não bloqueante
        except Exception:
            try:
                # Fallback para Windows se webbrowser falhar
                subprocess.Popen(['start', '', caminho], shell=True)
            except Exception:
                messagebox.showwarning("PDF", "Não foi possível abrir o PDF automaticamente. O arquivo foi salvo.", parent=self)
        return caminho

    def _normalizar_telefone_whatsapp(self, telefone):
        """Normaliza número de cliente: adiciona +55 apenas se parecer brasileiro (10-11 dígitos).
        Números com prefixo internacional diferente são mantidos como estão.
        """
        digitos = re.sub(r"\D", "", str(telefone or ""))
        if not digitos:
            return ""
        # Já tem código de país (começa com 55 e tem 12+ dígitos)
        if digitos.startswith("55") and len(digitos) >= 12:
            return digitos
        # Parece número brasileiro sem DDI (10 = fixo com DDD, 11 = celular com DDD)
        if len(digitos) in (10, 11):
            return f"55{digitos}"
        # Número estrangeiro ou formato desconhecido — usa como está
        return digitos

    def _normalizar_telefone_fornecedor(self, telefone):
        """Normaliza número de fornecedor: sempre força prefixo Brasil (+55).
        Fornecedores são todos nacionais.
        """
        digitos = re.sub(r"\D", "", str(telefone or ""))
        if not digitos:
            return ""
        # Já tem +55
        if digitos.startswith("55") and len(digitos) >= 12:
            return digitos
        # Garante +55 independente do tamanho
        return f"55{digitos}"

    def _oferecer_envio_whatsapp(self, caminho_pdf, tipo_documento=None):
        tipo = tipo_documento or self.tipo_documento or "ORÇAMENTO"
        if tipo != "ORÇAMENTO":
            return

        if not messagebox.askyesno(
            "WhatsApp",
            "PDF gerado com sucesso. Deseja abrir o WhatsApp para enviar ao cliente?",
            parent=self,
        ):
            return

        cliente = self.txt_cliente.get().strip().upper() or "CLIENTE"
        telefone = self._normalizar_telefone_whatsapp(self.txt_fone.get())
        nome_pdf = os.path.basename(caminho_pdf)
        prazo = self.txt_prazo.get().strip() or "A combinar"
        valor_total = self.atualizar_total()

        msg = (
            f"Olá, Pescador {cliente}! Tudo bem?\n\n"
            f"Seu orçamento nº {self.num_oc} já está pronto.\n"
            f"Valor total: {formatar_monetario(valor_total)}\n"
            f"Prazo estimado: {prazo}\n"
            f"Arquivo PDF: {nome_pdf}\n\n"
            f"{self.nome_oficina}\n"
            f"Contato: {self.telefone_oficina}\n\n"
            "Já abri o WhatsApp para envio. Basta anexar o PDF e enviar."
        )
        texto = quote(msg)

        if telefone:
            link = f"https://wa.me/{telefone}?text={texto}"
        else:
            link = f"https://wa.me/?text={texto}"

        try:
            webbrowser.open(link)
        except Exception:
            try:
                self.clipboard_clear()
                self.clipboard_append(link)
            except Exception:
                pass
            messagebox.showinfo(
                "WhatsApp",
                "Não foi possível abrir o WhatsApp automaticamente.\nO link foi copiado para a área de transferência.",
                parent=self,
            )
            return

        copiar_link = messagebox.askyesno(
            "WhatsApp",
            "Deseja copiar o link do WhatsApp também?",
            parent=self,
        )
        if copiar_link:
            try:
                self.clipboard_clear()
                self.clipboard_append(link)
                messagebox.showinfo("WhatsApp", "Link copiado para a área de transferência.", parent=self)
            except Exception:
                pass

    def setup_campos(self):
        # --- MODO ESCUTA SILENCIOSO ---
        self.after(1000, self._modo_escuta_pdf_clipboard)

    def _modo_escuta_pdf_clipboard(self):
        def _verificar():
            try:
                import pyperclip
                link = pyperclip.paste()
                if link and link.lower().endswith('.pdf') and link.startswith('http'):
                    # Modo teste síncrono: execução direta sem thread.
                    self._salvar_pdf_silencioso(link)
            except Exception as e:
                logger.info(f"Modo Escuta: erro ao ler clipboard: {e}")
            self.after(2000, self._modo_escuta_pdf_clipboard)
        _verificar()

    def _salvar_pdf_silencioso(self, link):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO pdfs_salvos (link, data) VALUES (?, ?)", (link, datetime.now().isoformat()))
                conn.commit()
        except Exception as e:
            logger.info(f"Modo Escuta: erro ao salvar no banco: {e}")
        try:
            # Modo teste síncrono: execução direta sem thread.
            self._enviar_drive_silencioso(link)
        except Exception as e:
            logger.info(f"Modo Escuta: erro ao iniciar thread do Drive: {e}")

    def _enviar_drive_silencioso(self, link):
        try:
            enviar_arquivo_para_drive_usuario(link, pasta_remota="Oficina de Pesca - PDFs")
        except Exception as e:
            logger.info(f"Modo Escuta: erro ao enviar para o Drive: {e}")

    # --- BUSCA PROATIVA DE ALERTAS ---
    def _buscar_modelos(self):
        """Fallback seguro quando não há fonte de modelos configurada."""
        return []

    def listar_modelos(self):
        modelos = self._buscar_modelos()
        for modelo in modelos:
            if self._defeito_cronico_conhecido(modelo):
                self._exibir_alerta_cronico(modelo)
            else:
                # Modo teste síncrono: execução direta sem thread.
                self._minerar_defeitos_cronicos_google(modelo)

    def _minerar_defeitos_cronicos_google(self, modelo):
        try:
            # Simulação de busca Google/fóruns (substitua por scraping real ou API)
            import time
            time.sleep(2)  # Simula latência
            # Exemplo: se modelo contém "coroa", retorna defeito crônico
            if "coroa" in modelo.lower():
                defeito = "DESGASTE DE COROA"
            else:
                defeito = None
            # Aqui você pode expandir para buscar "manhas de manutenção" também
            if defeito:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT OR IGNORE INTO defeitos_cronicos (modelo, defeito) VALUES (?, ?)", (modelo, defeito)) #
                    conn.commit()
                if self.winfo_exists():
                    self.after(0, lambda: self._atualizar_alerta_ui(modelo, alerta=True)) # UI Thread Safety
        except Exception as e:
            logger.info(f"Mineração de defeitos Google: erro para modelo {modelo}: {e}")

    def _defeito_cronico_conhecido(self, modelo):
        # Consulta local/banco/cache
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT defeito FROM defeitos_cronicos WHERE modelo = ?", (modelo,))
                return cursor.fetchone() is not None
        except Exception:
            return False

    def _exibir_alerta_cronico(self, modelo):
        # Exibe o triângulo ⚠️ na interface para o modelo
        try:
            # Supondo que há um método para atualizar a UI
            self._atualizar_alerta_ui(modelo, alerta=True)
        except Exception:
            pass

    def _buscar_e_salvar_defeito_cronico_ia(self, modelo):
        # Busca IA (simulação)
        defeito = self._consultar_ia_defeito_cronico(modelo)
        if defeito:
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT OR IGNORE INTO defeitos_cronicos (modelo, defeito) VALUES (?, ?)", (modelo, defeito))
                    conn.commit() #
                if self.winfo_exists():
                    self.after(0, lambda: self._atualizar_alerta_ui(modelo, alerta=True)) # UI Thread Safety
            except Exception:
                pass

    def _consultar_ia_defeito_cronico(self, modelo):
        # Aqui seria chamada à IA real. Exemplo fixo:
        if "coroa" in modelo.lower():
            return "DESGASTE DE COROA"
        return None


    def carregar_dados_orcamento(self, id_orc):
        """Carrega dados do orçamento para a tela O.S. no formato legado e no modo OS por cliente."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT cliente, telefone_cliente_whatsapp, equipamento, defeito, resumo_equipamento_defeito, valor_total, sinal, saldo, status, itens_detalhes, dados_adicionais FROM orcamentos_aguardo WHERE id=?",
                    (id_orc,)
                )
                res = cursor.fetchone()

            if not res:
                return

            self.num_oc = id_orc
            self.atualizar_identificacao_documento(res[8])
            self.txt_cliente.delete(0, 'end')
            self.txt_cliente.insert(0, str(res[0] or ""))

            dados_adicionais = {}
            if res[10]:
                try:
                    dados_adicionais = json.loads(res[10])
                except Exception:
                    dados_adicionais = {}

            self.txt_fone.delete(0, 'end')
            telefone_salvo = str(res[1] or "").strip() or str(dados_adicionais.get("cliente_telefone", ""))
            self.txt_fone.insert(0, telefone_salvo)
            self.txt_end_cliente.delete(0, 'end')
            self.txt_end_cliente.insert(0, str(dados_adicionais.get("cliente_endereco", "")))
            self._historico_itens_reprovados = list(dados_adicionais.get("historico_itens_reprovados") or [])
            self._atualizar_label_historico_itens()

            equipamentos = dados_adicionais.get("equipamentos") if isinstance(dados_adicionais, dict) else None
            equipamentos_normalizados = []

            if isinstance(equipamentos, list) and equipamentos:
                for equipamento in equipamentos:
                    if not isinstance(equipamento, dict):
                        continue
                    equipamentos_normalizados.append(
                        {
                            "equipamento": str(equipamento.get("equipamento", "")).strip().upper(),
                            "defeito": str(equipamento.get("defeito", "")).strip().upper(),
                            "itens": [
                                [
                                    str(item[0]),
                                    str(item[1]),
                                    str(item[2]),
                                    str(item[3]),
                                    self._normalizar_status_item(item[4] if len(item) > 4 else "ATIVO"),
                                ]
                                for item in (equipamento.get("itens") or [])
                                if isinstance(item, (list, tuple)) and len(item) >= 4
                            ],
                            "opcional": float(self._parse_valor(equipamento.get("opcional", 0))),
                            "frete": float(self._parse_valor(equipamento.get("frete", 0))),
                            "desconto": float(self._parse_valor(equipamento.get("desconto", 0))),
                            "prazo": str(equipamento.get("prazo", "7 dias úteis") or "7 dias úteis"),
                            "obs": str(equipamento.get("obs", "") or ""),
                        }
                    )
            else:
                itens_legado = []
                if res[9]:
                    try:
                        bruto = json.loads(str(res[9]).strip())
                        for item in bruto:
                            if isinstance(item, dict):
                                itens_legado.append([
                                    str(item.get('descricao', item.get('item', ''))),
                                    str(item.get('quantidade', item.get('qtd', 1))),
                                    str(item.get('valor_unitario', item.get('unitario', 0))),
                                    str(item.get('valor_total', item.get('total', 0))),
                                    self._normalizar_status_item(item.get('status', 'ATIVO')),
                                ])
                            elif isinstance(item, (list, tuple)) and len(item) >= 4:
                                itens_legado.append([
                                    str(item[0]), str(item[1]), str(item[2]), str(item[3]),
                                    self._normalizar_status_item(item[4] if len(item) > 4 else "ATIVO"),
                                ])
                    except Exception:
                        itens_legado = []

                equipamentos_normalizados.append(
                    {
                        "equipamento": str(res[2] or "").strip().upper(),
                        "defeito": str(res[3] or "").strip().upper(),
                        "itens": itens_legado,
                        "opcional": float(self._parse_valor(dados_adicionais.get('opcional', dados_adicionais.get('adicional', 0)))),
                        "frete": float(self._parse_valor(dados_adicionais.get('frete', 0))),
                        "desconto": float(self._parse_valor(dados_adicionais.get('desconto', 0))),
                        "prazo": str(dados_adicionais.get('prazo', '7 dias úteis') or '7 dias úteis'),
                        "obs": str(dados_adicionais.get('obs', '') or ''),
                    }
                )

            self.os_equipamentos = [eq for eq in equipamentos_normalizados if eq.get("equipamento") or eq.get("defeito") or eq.get("itens")]
            self._orcamento_em_edicao = True
            self.indice_equipamento_ativo = None
            self._atualizar_lista_equipamentos_ui()

            if self.os_equipamentos:
                self._carregar_equipamento_no_form(0)
            else:
                self._limpar_formulario_item_ativo()

            forma_salva = self._normalizar_forma_pagamento(dados_adicionais.get('forma_de_pagamento'))
            self.var_pagamento.set(forma_salva)
            self._atualizar_rotulo_botao_salvar()
            self.atualizar_total()
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao carregar orçamento: {e}")

    def _coletar_itens_tabela(self):
        itens = []
        for item_id in self.tab.get_children():
            valores = self.tab.item(item_id).get("values", [])
            if len(valores) >= 4:
                status_item = self._normalizar_status_item(valores[4] if len(valores) > 4 else "ATIVO")
                qtd = self._parse_valor(valores[1], default=0.0)
                unit = self._parse_valor(valores[2], default=0.0)
                total = float(qtd) * float(unit)
                itens.append([str(valores[0]), str(valores[1]), str(valores[2]), f"{total:.2f}", status_item])
        return itens

    def _normalizar_status_item(self, status_item):
        status = str(status_item or "AGUARDANDO").strip().upper()
        if status in ("REPROVADO", "REPROVADA"):
            return "REPROVADO"
        return "AGUARDANDO"

    def _tags_item(self, idx, status_item):
        zebra = 'evenrow' if idx % 2 == 0 else 'oddrow'
        status = self._normalizar_status_item(status_item)
        if status == "REPROVADO":
            return (zebra, 'reprovado')
        return (zebra,)

    def _status_equipamento(self, equipamento):
        itens = list((equipamento or {}).get("itens") or [])
        for item in itens:
            if len(item) >= 5 and self._normalizar_status_item(item[4]) == "REPROVADO":
                return "REPROVADO"
        return "AGUARDANDO"

    def _aplicar_itens_tabela(self, itens):
        for item_id in self.tab.get_children():
            self.tab.delete(item_id)
        for item in itens or []:
            row_count = len(self.tab.get_children())
            status_item = self._normalizar_status_item(item[4] if len(item) > 4 else "ATIVO")
            qtd = self._parse_valor(item[1], default=0.0)
            unit = self._parse_valor(item[2], default=0.0)
            total = float(qtd) * float(unit)
            self.tab.insert("", "end", values=(item[0], item[1], f"{unit:.2f}", f"{total:.2f}", status_item), tags=self._tags_item(row_count, status_item))

    def _reaplicar_zebra_tabela_itens(self):
        for idx, item_id in enumerate(self.tab.get_children()):
            valores = self.tab.item(item_id).get("values", [])
            status_item = self._normalizar_status_item(valores[4] if len(valores) > 4 else "ATIVO")
            self.tab.item(item_id, tags=self._tags_item(idx, status_item))

    def _limpar_edicao_item(self):
        self._item_em_edicao_id = None
        if hasattr(self, "btn_add"):
            self.btn_add.configure(text=t("ui_add"), fg_color="#27ae60", hover_color="#2ecc71")
        self._atualizar_estado_botao_reativar(None)

    def _atualizar_estado_botao_reativar(self, status_item):
        botao = getattr(self, "btn_reativar_item", None)
        if botao is None:
            return
        status_norm = self._normalizar_status_item(status_item)
        if status_norm == "REPROVADO":
            botao.configure(state="normal")
            botao.grid()
            return
        botao.configure(state="disabled")
        botao.grid_remove()

    def _on_selecionar_item_tabela(self, _event=None):
        selecionado = self.tab.selection()
        if not selecionado:
            self._atualizar_estado_botao_reativar(None)
            return
        item_id = selecionado[0]
        valores = self.tab.item(item_id).get("values", [])
        if len(valores) < 3:
            return

        self._item_em_edicao_id = item_id
        self.txt_serv.delete(0, 'end')
        self.txt_serv.insert(0, str(valores[0] or ""))
        self.txt_qtd.delete(0, 'end')
        self.txt_qtd.insert(0, str(valores[1] or "1"))
        self.txt_val.delete(0, 'end')
        self.txt_val.insert(0, str(valores[2] or ""))
        status_item = self._normalizar_status_item(valores[4] if len(valores) > 4 else "ATIVO")
        self._atualizar_estado_botao_reativar(status_item)
        if status_item == "REPROVADO":
            self.btn_add.configure(text=t("ui_atualizar_reprovado"), fg_color="#7f1d1d", hover_color="#991b1b")
        else:
            self.btn_add.configure(text=t("ui_atualizar"), fg_color="#2563eb", hover_color="#3b82f6")

    def _on_duplo_clique_item_tabela(self, _event=None):
        self._on_selecionar_item_tabela(_event)
        self.txt_serv.focus_set()
        try:
            self.txt_serv.icursor('end')
        except Exception:
            pass

    def _atualizar_label_historico_itens(self):
        if hasattr(self, "lbl_hist_itens") and self.lbl_hist_itens.winfo_exists():
            self.lbl_hist_itens.configure(
                text=f"Histórico de itens reprovados/removidos: {len(self._historico_itens_reprovados or [])}"
            )

    def _registrar_item_reprovado(self, origem, valores_item, motivo):
        try:
            item = list(valores_item or [])
            if len(item) < 4:
                return
            self._historico_itens_reprovados.append(
                {
                    "os_id": int(getattr(self, "num_oc", 0) or 0),
                    "equipamento_idx": int(self.indice_equipamento_ativo or 0),
                    "origem": str(origem or "TABELA"),
                    "descricao": str(item[0]),
                    "qtd": str(item[1]),
                    "valor_unitario": str(item[2]),
                    "valor_total": str(item[3]),
                    "motivo": str(motivo or "REPROVADO"),
                    "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                }
            )
            self._atualizar_label_historico_itens()
        except Exception:
            logger.exception("Falha ao registrar histórico de item reprovado/removido.")

    def _inserir_ou_atualizar_item_tabela(self, descricao: str, qtd: int, valor_unitario: float):
        desc_norm = str(descricao or "").strip().upper()
        if not desc_norm or qtd <= 0 or valor_unitario <= 0:
            return

        assinatura = (
            int(self.indice_equipamento_ativo or 0),
            desc_norm,
            int(qtd),
            round(float(valor_unitario), 2),
        )
        agora = time.monotonic()
        if assinatura == self._ultima_assinatura_item and (agora - float(self._ultimo_item_ts or 0.0)) <= 0.45:
            return
        self._ultima_assinatura_item = assinatura
        self._ultimo_item_ts = agora

        for item_id in self.tab.get_children():
            valores = self.tab.item(item_id).get("values", [])
            if len(valores) < 4:
                continue

            status_exist = self._normalizar_status_item(valores[4] if len(valores) > 4 else "AGUARDANDO")
            if status_exist == "REPROVADO":
                continue

            desc_exist = str(valores[0]).strip().upper()
            if desc_exist != desc_norm:
                continue

            try:
                unit_exist = float(self._parse_valor(valores[2]))
            except Exception:
                unit_exist = 0.0

            if abs(unit_exist - float(valor_unitario)) > 0.0001:
                continue

            try:
                qtd_exist = int(float(str(valores[1]).replace(",", ".")))
            except Exception:
                qtd_exist = 0

            qtd_nova = max(1, qtd_exist + int(qtd))
            total_novo = qtd_nova * float(valor_unitario)
            self.tab.item(item_id, values=(desc_norm, qtd_nova, f"{valor_unitario:.2f}", f"{total_novo:.2f}", "AGUARDANDO"))
            self._reaplicar_zebra_tabela_itens()
            return

        row_count = len(self.tab.get_children())
        subtotal = int(qtd) * float(valor_unitario)
        self.tab.insert(
            "",
            "end",
            values=(desc_norm, int(qtd), f"{valor_unitario:.2f}", f"{subtotal:.2f}", "AGUARDANDO"),
            tags=self._tags_item(row_count, "AGUARDANDO"),
        )
        self._reaplicar_zebra_tabela_itens()

    def _subtotal_equipamento(self, equipamento):
        itens_ativos = []
        for item in (equipamento.get("itens") or []):
            if len(item) < 3:
                continue
            if self._normalizar_status_item(item[4] if len(item) > 4 else "AGUARDANDO") == "REPROVADO":
                continue
            qtd = self._parse_valor(item[1], default=0.0)
            unit = self._parse_valor(item[2], default=0.0)
            itens_ativos.append(float(qtd) * float(unit))
        return OSCalculator.calcular_total(
            itens=itens_ativos,
            desconto=equipamento.get("desconto", 0),
            frete=equipamento.get("frete", 0),
            adicional=equipamento.get("opcional", 0),
        )

    def _atualizar_lista_equipamentos_ui(self):
        if not hasattr(self, "tab_equipamentos"):
            return
        for item_id in self.tab_equipamentos.get_children():
            self.tab_equipamentos.delete(item_id)

        for idx, equipamento in enumerate(self.os_equipamentos, start=1):
            subtotal = self._subtotal_equipamento(equipamento)
            status = self._status_equipamento(equipamento)
            self.tab_equipamentos.insert(
                "",
                "end",
                iid=str(idx - 1),
                values=(idx, equipamento.get("equipamento", ""), equipamento.get("defeito", ""), formatar_monetario(subtotal), status),
                tags=("reprovado",) if status == "REPROVADO" else (),
            )

    def _limpar_formulario_item_ativo(self):
        self._limpar_edicao_item()
        self.txt_equip.delete(0, 'end')
        self.txt_defeito.delete(0, 'end')
        self.txt_serv.delete(0, 'end')
        self.txt_qtd.delete(0, 'end')
        self.txt_qtd.insert(0, "1")
        self.txt_val.delete(0, 'end')
        for campo in [self.ent_opcional, self.ent_frete, self.ent_desc]:
            campo.delete(0, 'end')
        self.txt_prazo.delete(0, 'end')
        self.txt_prazo.insert(0, "7 dias úteis")
        self.txt_obs.delete('1.0', 'end')
        self._aplicar_itens_tabela([])

    def _salvar_equipamento_ativo(self):
        if self.indice_equipamento_ativo is None:
            return
        if self.indice_equipamento_ativo < 0 or self.indice_equipamento_ativo >= len(self.os_equipamentos):
            return

        equipamento = self.os_equipamentos[self.indice_equipamento_ativo]
        equipamento["equipamento"] = self.txt_equip.get().strip().upper()
        equipamento["defeito"] = self.txt_defeito.get().strip().upper()
        equipamento["itens"] = self._coletar_itens_tabela()
        equipamento["opcional"] = float(self._parse_valor(self.ent_opcional.get()))
        equipamento["frete"] = float(self._parse_valor(self.ent_frete.get()))
        equipamento["desconto"] = float(self._parse_valor(self.ent_desc.get()))
        equipamento["prazo"] = self.txt_prazo.get().strip() or "7 dias úteis"
        equipamento["obs"] = self.txt_obs.get("1.0", "end-1c").strip()

    def _carregar_equipamento_no_form(self, indice):
        if indice < 0 or indice >= len(self.os_equipamentos):
            return
        self.indice_equipamento_ativo = indice
        equipamento = self.os_equipamentos[indice]

        self.txt_equip.delete(0, 'end')
        self.txt_equip.insert(0, equipamento.get("equipamento", ""))
        self.txt_defeito.delete(0, 'end')
        self.txt_defeito.insert(0, equipamento.get("defeito", ""))
        self._aplicar_itens_tabela(equipamento.get("itens") or [])

        opcional = float(self._parse_valor(equipamento.get("opcional", 0)))
        frete = float(self._parse_valor(equipamento.get("frete", 0)))
        desconto = float(self._parse_valor(equipamento.get("desconto", 0)))
        self.ent_opcional.delete(0, 'end')
        self.ent_opcional.insert(0, "" if opcional == 0 else f"{opcional:.2f}")
        self.ent_frete.delete(0, 'end')
        self.ent_frete.insert(0, "" if frete == 0 else f"{frete:.2f}")
        self.ent_desc.delete(0, 'end')
        self.ent_desc.insert(0, "" if desconto == 0 else f"{desconto:.2f}")
        self.txt_prazo.delete(0, 'end')
        self.txt_prazo.insert(0, str(equipamento.get("prazo", "7 dias úteis") or "7 dias úteis"))
        self.txt_obs.delete('1.0', 'end')
        self.txt_obs.insert('1.0', str(equipamento.get("obs", "") or ""))

        try:
            self.tab_equipamentos.selection_set(str(indice))
            self.tab_equipamentos.focus(str(indice))
        except Exception:
            pass

    def _adicionar_equipamento(self):
        equipamento = self.txt_equip.get().strip().upper()
        defeito = self.txt_defeito.get().strip().upper()
        if not equipamento or not defeito:
            messagebox.showwarning("Item da O.S.", "Informe modelo/equipamento e defeito para adicionar o item.", parent=self)
            return

        self._salvar_equipamento_ativo()
        self.os_equipamentos.append(
            {
                "equipamento": equipamento,
                "defeito": defeito,
                "itens": [],
                "opcional": 0.0,
                "frete": 0.0,
                "desconto": 0.0,
                "prazo": "7 dias úteis",
                "obs": "",
            }
        )
        self.indice_equipamento_ativo = None
        self._atualizar_lista_equipamentos_ui()
        self._limpar_formulario_item_ativo()
        self.txt_equip.focus_set()
        self.atualizar_total()

    def _remover_equipamento_ativo(self):
        selecao = self.tab_equipamentos.selection()
        if not selecao:
            foco = self.tab_equipamentos.focus()
            if foco:
                selecao = (foco,)
        if not selecao:
            return
        try:
            indice = int(str(selecao[0]))
        except Exception:
            valores = self.tab_equipamentos.item(selecao[0], "values")
            try:
                indice = int(valores[0]) - 1 if valores else -1
            except Exception:
                indice = -1
        if indice < 0 or indice >= len(self.os_equipamentos):
            return
        if not messagebox.askyesno("Remover item", "Deseja remover este equipamento da O.S.?", parent=self):
            return
        self._salvar_equipamento_ativo()
        self.os_equipamentos.pop(indice)
        self.indice_equipamento_ativo = None
        self._atualizar_lista_equipamentos_ui()
        if self.os_equipamentos:
            self._carregar_equipamento_no_form(min(indice, len(self.os_equipamentos) - 1))
        else:
            self._limpar_formulario_item_ativo()
        self._limpar_edicao_item()
        self.atualizar_total()
        if self._orcamento_em_edicao:
            try:
                self.salvar_documento(status="AGUARDANDO")
            except Exception as exc:
                logger.exception("Falha ao persistir remoção de equipamento da O.S. %s.", getattr(self, "num_oc", ""))
                messagebox.showwarning("Remover item", f"Item removido da tela, mas não foi possível atualizar o banco agora: {exc}", parent=self)

    def _on_selecionar_equipamento(self, _event=None):
        selecao = self.tab_equipamentos.selection()
        if not selecao:
            return
        indice = int(selecao[0])
        self._salvar_equipamento_ativo()
        self._carregar_equipamento_no_form(indice)
        self.atualizar_total()

    def _total_os_atual(self):
        total = 0.0
        for equipamento in self.os_equipamentos:
            total += self._subtotal_equipamento(equipamento)
        return total

    # --- FUNÇÃO DE SUGESTÃO DE PREÇO (Corrigida) ---
    def sugerir_preco(self, event):
        texto = self.txt_serv.get().strip()
        if len(texto) < 3: return
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # Busca no banco de dados um produto com nome parecido
                cursor.execute("SELECT preco_venda FROM produtos WHERE nome LIKE ?", (f'%{texto}%',))
                res = cursor.fetchone()
            if res:
                self.txt_val.delete(0, 'end')
                self.txt_val.insert(0, f"{res[0]:.2f}")
        except Exception as e:
            logger.exception("Erro ao sugerir preço: %s", e)

    # --- FUNÇÃO QUE A JANELA DE PRODUTOS CHAMA (Com a janelinha de quantidade) ---
    def adicionar_item_ao_orcamento(self, descricao, valor_unitario):
        if self.indice_equipamento_ativo is None:
            messagebox.showwarning("Item da O.S.", "Selecione um equipamento da lista para lançar peças/serviços.", parent=self)
            return
        # Traz a tela de OS para frente para a janelinha aparecer no lugar certo
        self.lift()
        self.focus_force()
        
        # Abre a janelinha de quantidade que você pediu
        qtd = simpledialog.askinteger("Quantidade", f"Quantos(as) '{descricao}'?", initialvalue=1, parent=self)
        
        if qtd and qtd > 0:
            self._inserir_ou_atualizar_item_tabela(descricao, int(qtd), float(valor_unitario))
            self.atualizar_total()
            
    # --- FUNÇÃO DO BOTÃO "ADD" (Para digitar manual) ---
    def add_item(self):
        try:
            if self.indice_equipamento_ativo is None:
                messagebox.showwarning("Item da O.S.", "Selecione um equipamento da lista antes de adicionar peças/serviços.", parent=self)
                return

            d = self.txt_serv.get().upper()
            q = int(self.txt_qtd.get())
            v = self._parse_valor(self.txt_val.get())
            if not d.strip() or q <= 0 or v <= 0:
                raise ValueError("Dados inválidos para item")

            produto_info = self._consultar_produto_por_nome(d)
            if produto_info:
                _, estoque_atual = produto_info
                if int(estoque_atual or 0) <= 0:
                    self._oferecer_whatsapp_sem_estoque(d)

            if self._item_em_edicao_id:
                item_id = self._item_em_edicao_id
                total_novo = int(q) * float(v)
                valores_atuais = self.tab.item(item_id).get("values", [])
                status_item = self._normalizar_status_item(valores_atuais[4] if len(valores_atuais) > 4 else "ATIVO")
                self.tab.item(item_id, values=(d, int(q), f"{float(v):.2f}", f"{float(total_novo):.2f}", status_item))
                self._reaplicar_zebra_tabela_itens()
                self._limpar_edicao_item()
                self.atualizar_total()
                self.txt_serv.delete(0, 'end')
                self.txt_qtd.delete(0, 'end')
                self.txt_qtd.insert(0, "1")
                self.txt_val.delete(0, 'end')
                self.txt_serv.focus()
                return

            self._inserir_ou_atualizar_item_tabela(d, q, v)
            self.atualizar_total()
            # Limpa os campos e volta o cursor para o nome do serviço
            self.txt_serv.delete(0, 'end')
            self.txt_val.delete(0, 'end')
            self.txt_serv.focus()
        except (ValueError, TypeError):
            messagebox.showwarning("Erro", "Preencha Descrição, Qtd e Valor corretamente!")

    def remover_item_selecionado(self, _event=None):
        # Lógica automática de status e persistência desativada para teste de isolamento.
        item = self.tabela.selection()
        if item:
            self.tabela.delete(item[0])
            print('REMOÇÃO CONCLUÍDA')

    def marcar_item_reprovado(self):
        selecionado = self.tab.selection()
        if not selecionado:
            foco = self.tab.focus()
            if foco:
                selecionado = (foco,)
        if not selecionado:
            messagebox.showwarning("Reprovar item", "Selecione um item para reprovar.", parent=self)
            return

        motivo = simpledialog.askstring(
            "Reprovar item",
            "Motivo da reprovação do item (opcional):",
            parent=self,
        )
        motivo_final = str(motivo or "REPROVADO PELO CLIENTE").strip().upper()

        for item_id in selecionado:
            valores = list(self.tab.item(item_id).get("values", []))
            if len(valores) < 4:
                continue
            status_atual = self._normalizar_status_item(valores[4] if len(valores) > 4 else "ATIVO")
            if status_atual != "REPROVADO":
                self._registrar_item_reprovado("REPROVAR", valores, motivo_final)
            self.tab.item(item_id, values=(valores[0], valores[1], valores[2], valores[3], "REPROVADO"))
            if item_id == self._item_em_edicao_id:
                self._limpar_edicao_item()

        self._reaplicar_zebra_tabela_itens()
        self.atualizar_total()
        try:
            self.salvar_documento(status="AGUARDANDO")
        except Exception:
            pass
        try:
            self._gerar_pdf_orcamento_reprovado_automatico(motivo=motivo_final)
        except Exception:
            logger.exception("Falha ao gerar PDF automático de orçamento reprovado.")
        messagebox.showinfo("Reprovar item", "Item marcado como REPROVADO, mantido no histórico e orçamento atualizado.", parent=self)

    def reativar_item_selecionado(self):
        selecionado = self.tab.selection()
        if not selecionado:
            foco = self.tab.focus()
            if foco:
                selecionado = (foco,)
        if not selecionado:
            messagebox.showwarning("Reativar item", "Selecione um item para reativar.", parent=self)
            return

        alterou = False
        for item_id in selecionado:
            valores = list(self.tab.item(item_id).get("values", []))
            if len(valores) < 4:
                continue
            status_atual = self._normalizar_status_item(valores[4] if len(valores) > 4 else "ATIVO")
            if status_atual == "REPROVADO":
                self.tab.item(item_id, values=(valores[0], valores[1], valores[2], valores[3], "ATIVO"))
                alterou = True

        if not alterou:
            messagebox.showinfo("Reativar item", "Os itens selecionados já estão ativos.", parent=self)
            return

        self._reaplicar_zebra_tabela_itens()
        self.atualizar_total()
        try:
            self.salvar_documento(status="AGUARDANDO")
        except Exception:
            pass
        messagebox.showinfo("Reativar item", "Item reativado com sucesso e orçamento recalculado.", parent=self)

    def _consultar_produto_por_nome(self, nome_produto: str):
        nome = str(nome_produto or "").strip().upper()
        if not nome:
            return None
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, estoque FROM produtos WHERE UPPER(nome)=? LIMIT 1",
                    (nome,),
                )
                return cursor.fetchone()
        except Exception:
            return None

    def _oferecer_whatsapp_sem_estoque(self, nome_produto: str):
        enviar = messagebox.askyesno(
            "Produto sem estoque",
            f"{nome_produto} está sem estoque.\n\nDeseja abrir o WhatsApp para solicitar reposição?",
            parent=self,
        )
        if not enviar:
            return

        arquivo_ref = self._buscar_vista_ja_baixada(nome_produto)
        texto = (
            "Olá! Solicitação de reposição de peça.\n"
            f"Produto: {nome_produto}\n"
            f"O.S.: {self.num_oc}\n"
            "Favor confirmar disponibilidade e prazo."
        )
        # Fornecedores são sempre Brasil → força +55
        numero = self._normalizar_telefone_fornecedor(self.numero_whatsapp_reposicao)
        link = f"https://wa.me/{numero}?text={quote(texto)}"

        try:
            webbrowser.open(link)
        except Exception:
            messagebox.showwarning(
                "WhatsApp",
                "Não foi possível abrir o WhatsApp automaticamente.",
                parent=self,
            )
            return

        if arquivo_ref and os.path.exists(arquivo_ref):
            anexar = messagebox.askyesno(
                "Anexar arquivo",
                "Existe PDF/imagem baixado desta peça. Deseja abrir a pasta para anexar no WhatsApp?",
                parent=self,
            )
            if anexar:
                try:
                    os.startfile(os.path.dirname(arquivo_ref))
                except Exception:
                    pass

    # --- FUNÇÃO DE SOMAR TUDO ---
    def atualizar_total(self):
        try:
            self._salvar_equipamento_ativo()
            self._atualizar_lista_equipamentos_ui()
            total = self._total_os_atual()
            self.lbl_total.configure(text=f"TOTAL O.S.: {formatar_monetario(total)}")
            return total
        except Exception as e:
            logger.exception("Erro ao atualizar total: %s", e)
            return 0

    def _baixar_estoque_aprovacao(self):
        """Baixa estoque dos produtos conforme itens aprovados na O.S."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                for item_id in self.tab.get_children():
                    val = self.tab.item(item_id).get('values', [])
                    if len(val) < 2:
                        continue
                    descricao = str(val[0]).strip().upper()
                    try:
                        qtd = int(float(str(val[1]).replace(",", ".")))
                    except Exception:
                        qtd = 0
                    if not descricao or qtd <= 0:
                        continue

                    cursor.execute(
                        "SELECT id, estoque FROM produtos WHERE UPPER(nome) = ? LIMIT 1",
                        (descricao,)
                    )
                    prod = cursor.fetchone()
                    if not prod:
                        continue

                    id_prod, estoque_atual = prod
                    estoque_atual = int(estoque_atual or 0)
                    novo_estoque = max(0, estoque_atual - qtd)
                    cursor.execute("UPDATE produtos SET estoque = ? WHERE id = ?", (novo_estoque, id_prod))

                conn.commit()
        except Exception:
            logger.exception("Erro ao baixar estoque após aprovação.")

    def _consultar_cliente(self, nome):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT nome, telefone, rua, numero, bairro, cidade, estado FROM clientes WHERE UPPER(nome) = ? LIMIT 1",
                (nome,)
            )
            return cursor.fetchone()

    def _preencher_cliente(self, dados_cliente):
        nome, telefone, rua, numero, bairro, cidade, estado = dados_cliente
        self.txt_cliente.delete(0, 'end')
        self.txt_cliente.insert(0, str(nome or ""))
        self.txt_fone.delete(0, 'end')
        self.txt_fone.insert(0, str(telefone or ""))
        end = f"{rua or ''}, {numero or ''} - {bairro or ''} - {cidade or ''}/{estado or ''}".upper()
        self.txt_end_cliente.delete(0, 'end')
        self.txt_end_cliente.insert(0, end)

    def _reaplicar_placeholders_orcamento(self):
        # Reforça placeholders após limpar campos para evitar perda visual na UI.
        mapeamento = [
            ("ent_desc", "Desconto (R$)"),
            ("ent_frete", "Frete (R$)"),
            ("ent_opcional", "Opcional (R$)"),
            ("txt_serv", "Descrição da Peça/Serviço"),
        ]
        for nome_attr, placeholder in mapeamento:
            campo = getattr(self, nome_attr, None)
            if campo is None:
                continue
            try:
                campo.configure(placeholder_text=placeholder)
            except Exception:
                pass

    def limpar_formulario_orcamento(self):
        self.txt_cliente.delete(0, 'end')
        self.txt_fone.delete(0, 'end')
        self.txt_end_cliente.delete(0, 'end')
        self.os_equipamentos = []
        self.indice_equipamento_ativo = None
        self._limpar_formulario_item_ativo()
        self._atualizar_lista_equipamentos_ui()
        # O triângulo só some ao limpar o formulário ou mudar o modelo
        self._alerta_preventivo_msg = ""
        self._atualizar_alerta_preventivo_ui("")
        self._reaplicar_placeholders_orcamento()
        self.atualizar_total()

    def _restaurar_formulario_pos_salvamento(self):
        self.limpar_formulario_orcamento()
        self.num_oc = self.carregar_proximo_numero()
        self._orcamento_em_edicao = False
        self._atualizar_rotulo_botao_salvar()
        self.atualizar_identificacao_documento("NOVO")

    def _atualizar_rotulo_botao_salvar(self):
        if not hasattr(self, 'btn_salvar_os'):
            return
        if self._orcamento_em_edicao:
            self.btn_salvar_os.configure(text=t("ui_salvar_atualizar"))
        else:
            self.btn_salvar_os.configure(text=t("ui_salvar_entrada"))

    def _alternar_estado_botao_salvar(self, salvando):
        self._salvando_documento = bool(salvando)
        if hasattr(self, 'btn_salvar_os'):
            self.btn_salvar_os.configure(
                state="disabled" if salvando else "normal",
                text=t("ui_salvando_entrada") if salvando else ("💾 SALVAR / ATUALIZAR" if self._orcamento_em_edicao else "💾 SALVAR ENTRADA"),
            )

    def _auditar_salvar_entrada(self, etapa, **dados):
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            logs_dir = os.path.join(base_dir, "logs")
            os.makedirs(logs_dir, exist_ok=True)
            caminho_log = os.path.join(logs_dir, "salvar_entrada_auditoria.log")
            payload = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "etapa": str(etapa or "").strip(),
                "os_id": int(getattr(self, "num_oc", 0) or 0),
                "cliente": self.txt_cliente.get().strip().upper() if hasattr(self, "txt_cliente") else "",
                "telefone": self._normalizar_telefone_whatsapp(self.txt_fone.get()) if hasattr(self, "txt_fone") else "",
            }
            payload.update(dados or {})
            with open(caminho_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("Falha ao registrar auditoria de Salvar Entrada.")

    def _entrada_tem_equipamento(self):
        try:
            self._salvar_equipamento_ativo()
        except Exception:
            pass

        for eq in self.os_equipamentos or []:
            if str(eq.get("equipamento", "")).strip() or str(eq.get("defeito", "")).strip():
                return True

        equipamento_digitado = self.txt_equip.get().strip() if hasattr(self, "txt_equip") else ""
        defeito_digitado = self.txt_defeito.get().strip() if hasattr(self, "txt_defeito") else ""
        return bool(equipamento_digitado or defeito_digitado)

    def _alternar_estado_botao_recibo(self, gerando):
        self._gerando_recibo = bool(gerando)
        if hasattr(self, 'btn_recibo'):
            self.btn_recibo.configure(
                state="disabled" if gerando else "normal",
                text=t("ui_gerando_recibo") if gerando else "🧾 RECIBO ENTRADA",
            )

    def _obter_diretorio_recibos(self, nome_cliente=""):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        recibos_dir = os.path.join(base_dir, "Recibos")
        cliente_limpo = _sanitizar_nome_arquivo(nome_cliente or "CLIENTE")
        recibos_dir = os.path.join(recibos_dir, cliente_limpo)
        os.makedirs(recibos_dir, exist_ok=True)
        return recibos_dir

    def _obter_diretorio_orcamentos_reprovados(self, nome_cliente=""):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        raiz = os.path.join(base_dir, "Orcamentos_Reprovados")
        cliente_limpo = _sanitizar_nome_arquivo(nome_cliente or "CLIENTE")
        pasta = os.path.join(raiz, cliente_limpo)
        os.makedirs(pasta, exist_ok=True)
        return pasta

    def _abrir_whatsapp_envio_pdf(self, caminho_pdf, mensagem_base=""):
        telefone = self._normalizar_telefone_whatsapp(self.txt_fone.get())
        nome_pdf = os.path.basename(caminho_pdf)
        texto_msg = (
            f"{mensagem_base}\n"
            f"Arquivo: {nome_pdf}\n"
            f"Caminho: {caminho_pdf}"
        ).strip()
        link = f"https://wa.me/{telefone}?text={quote(texto_msg)}" if telefone else f"https://wa.me/?text={quote(texto_msg)}"
        webbrowser.open(link)

    def _gerar_pdf_orcamento_reprovado_automatico(self, motivo=""):
        cliente = self.txt_cliente.get().strip().upper() or "CLIENTE"
        pasta = self._obter_diretorio_orcamentos_reprovados(cliente)
        data_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_cliente = _sanitizar_nome_arquivo(cliente)
        caminho_pdf = os.path.join(pasta, f"Orcamento_Reprovado_OS_{int(self.num_oc):05d}_{nome_cliente}_{data_tag}.pdf")

        self.gerar_pdf_fiel(caminho_pdf, tipo_documento="ORÇAMENTO REPROVADO")
        try:
            enviar_arquivo_para_drive_usuario(caminho_pdf, pasta_remota="Oficina de Pesca - PDFs")
        except Exception:
            pass

        msg = (
            f"Olá, {cliente}!\n"
            f"Registramos sua decisão para a O.S. {self.num_oc} como ORÇAMENTO REPROVADO."
        )
        if str(motivo or "").strip():
            msg += f"\nMotivo informado: {str(motivo).strip()}"

        if messagebox.askyesno(
            "Orçamento Reprovado",
            f"PDF gerado com sucesso em:\n{caminho_pdf}\n\nDeseja abrir o WhatsApp para envio rápido?",
            parent=self,
        ):
            try:
                self._abrir_whatsapp_envio_pdf(caminho_pdf, msg)
            except Exception:
                messagebox.showwarning("WhatsApp", "Não foi possível abrir o WhatsApp automaticamente.", parent=self)

        return caminho_pdf

    def _montar_snapshot_recibo_entrada(self, dados_salvos):
        dados_base = dados_salvos or {}
        telefone_formatado = self._normalizar_telefone_whatsapp(
            dados_base.get("telefone_cliente_whatsapp") or self.txt_fone.get()
        )
        equipamento = str(dados_base.get("equipamento", "") or "").strip().upper()
        defeito = str(dados_base.get("defeito", "") or "").strip().upper()
        resumo = str(
            dados_base.get("resumo_equipamento_defeito")
            or self._montar_resumo_equipamento_defeito(equipamento, defeito)
        ).strip().upper()
        return {
            "os_id": int(self.num_oc),
            "cliente": str(dados_base.get("cliente", "") or self.txt_cliente.get().strip().upper()),
            "telefone": telefone_formatado,
            "equipamento": equipamento,
            "defeito": defeito,
            "resumo": resumo,
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }

    def _gerar_pdf_recibo_entrada(self, caminho_pdf, recibo):
        c = canvas.Canvas(caminho_pdf, pagesize=A4)
        largura, altura = A4

        c.setTitle(f"Recibo_Entrada_OS_{recibo['os_id']}")
        c.setFont("Helvetica-Bold", 18)
        c.drawString(50, altura - 70, "RECIBO DE ENTRADA")

        c.setFont("Helvetica", 11)
        y = altura - 110
        linhas = [
            f"Numero da O.S.: {recibo['os_id']}",
            f"Cliente: {recibo['cliente'] or '-'}",
            f"Telefone/WhatsApp: {recibo['telefone'] or '-'}",
            f"Equipamento: {recibo['equipamento'] or '-'}",
            f"Defeito: {recibo['defeito'] or '-'}",
            f"Resumo: {recibo['resumo'] or '-'}",
            f"Gerado em: {recibo['data']}",
        ]
        for linha in linhas:
            partes = _quebrar_linha(c, linha, largura - 100, "Helvetica", 11)
            for parte in partes:
                c.drawString(50, y, parte)
                y -= 20

        y -= 10
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(50, y, "Documento simples para confirmacao de entrada e envio via WhatsApp.")
        c.save()

    def _abrir_whatsapp_recibo_entrada(self, caminho_pdf, recibo):
        mensagem = (
            f"Olá, {recibo['cliente'] or 'cliente'}!\n\n"
            f"Seu recibo de entrada da O.S. {recibo['os_id']} foi gerado.\n"
            f"Resumo: {recibo['resumo'] or '-'}\n"
            f"Arquivo: {os.path.basename(caminho_pdf)}\n"
            f"Caminho: {caminho_pdf}\n\n"
            "O WhatsApp foi aberto para facilitar o envio do recibo."
        )
        telefone = recibo.get("telefone", "")
        texto = quote(mensagem)
        link = f"https://wa.me/{telefone}?text={texto}" if telefone else f"https://wa.me/?text={texto}"
        # Modo teste síncrono: execução direta sem thread.
        webbrowser.open(link)

    def gerar_recibo_entrada(self):
        cliente = self.txt_cliente.get().strip().upper()
        telefone = self.txt_fone.get().strip()
        if not cliente or not telefone:
            messagebox.showwarning("Recibo", "Informe nome e telefone/WhatsApp antes de gerar o recibo.", parent=self)
            return
        if self._gerando_recibo or self._salvando_documento:
            return

        self._alternar_estado_botao_recibo(True)
        try:
            dados_salvos = self.salvar_documento(status="AGUARDANDO")
            if not dados_salvos:
                self._alternar_estado_botao_recibo(False)
                return

            recibo = self._montar_snapshot_recibo_entrada(dados_salvos)
            nome_cliente = _sanitizar_nome_arquivo(recibo["cliente"] or "CLIENTE")
            caminho_pdf = os.path.join(
                self._obter_diretorio_recibos(recibo["cliente"]),
                f"Recibo_Entrada_OS_{recibo['os_id']}_{nome_cliente}.pdf",
            )

            def worker():
                try:
                    self._gerar_pdf_recibo_entrada(caminho_pdf, recibo)
                    logger.info("Recibo de entrada da O.S. %s gerado em %s.", recibo["os_id"], caminho_pdf)
                    if self.winfo_exists():
                        self.after(0, lambda: self._finalizar_recibo_entrada(caminho_pdf, recibo))
                except Exception as exc:
                    logger.exception("Falha ao gerar recibo de entrada da O.S. %s.", recibo["os_id"])
                    if self.winfo_exists():
                        self.after(0, lambda err=exc: self._falhar_recibo_entrada(err))

            # Modo teste síncrono: execução direta sem thread.
            worker()
        except Exception as e:
            self._alternar_estado_botao_recibo(False)
            messagebox.showerror("Recibo", f"Não foi possível iniciar a geração do recibo: {e}", parent=self)

    def _finalizar_recibo_entrada(self, caminho_pdf, recibo):
        self._alternar_estado_botao_recibo(False)
        if messagebox.askyesno(
            "Recibo",
            "Recibo gerado com sucesso. Deseja abrir o WhatsApp agora para enviar ao cliente?",
            parent=self,
        ):
            self._abrir_whatsapp_recibo_entrada(caminho_pdf, recibo)
        messagebox.showinfo(
            "Recibo",
            f"Recibo gerado com sucesso em:\n{caminho_pdf}",
            parent=self,
        )

    def _falhar_recibo_entrada(self, erro):
        self._alternar_estado_botao_recibo(False)
        messagebox.showerror("Recibo", f"Erro ao gerar recibo de entrada: {erro}", parent=self)

    def preencher_cliente_da_consulta(self, cliente):
        if not isinstance(cliente, dict):
            return
        self.txt_cliente.delete(0, 'end')
        self.txt_fone.delete(0, 'end')
        self.txt_end_cliente.delete(0, 'end')
        self._reaplicar_placeholders_orcamento()
        self.txt_cliente.insert(0, str(cliente.get("nome", "")))
        self.txt_fone.insert(0, str(cliente.get("whatsapp", "")))
        self.txt_end_cliente.insert(0, str(cliente.get("endereco", "")).upper())
        self.txt_equip.focus_set()

    def _abrir_cadastro_cliente(self, nome):
        from clientes import FrmClientes

        def apos_salvar(nome_salvo):
            self.txt_cliente.delete(0, 'end')
            self.txt_cliente.insert(0, nome_salvo)
            self.buscar_cliente(abrir_cadastro=False)

        janela = FrmClientes(self, nome_inicial=nome, ao_salvar=apos_salvar)
        janela.focus_force()

    def abrir_consulta_clientes(self):
        try:
            from clientes import JanelaListaClientes
            janela = JanelaListaClientes(self, on_cliente_escolhido=self.preencher_cliente_da_consulta)
            janela.focus_force()
        except Exception as e:
            messagebox.showerror("Clientes", f"Não foi possível abrir consulta de clientes: {e}", parent=self)

    def buscar_cliente(self, event=None, abrir_cadastro=True):
        nome = self.txt_cliente.get().strip().upper()
        if not nome or self._cliente_em_validacao:
            return
        try:
            self._cliente_em_validacao = True
            res = self._consultar_cliente(nome)
            if res:
                self._preencher_cliente(res)
            else:
                self.txt_fone.delete(0, 'end')
                self.txt_end_cliente.delete(0, 'end')
                if abrir_cadastro and messagebox.askyesno("Cliente não cadastrado", f"{nome} não está cadastrado. Deseja abrir o cadastro agora?", parent=self):
                    self._abrir_cadastro_cliente(nome)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro: {e}", parent=self)
        finally:
            self._cliente_em_validacao = False

    def _ocultar_tooltip_alerta_preventivo(self, _event=None):
        if self._alerta_preventivo_tooltip is not None:
            try:
                self._alerta_preventivo_tooltip.destroy()
            except Exception:
                pass
            self._alerta_preventivo_tooltip = None

    def _mostrar_tooltip_alerta_preventivo(self, _event=None):
        if not self._vigilancia_habilitada:
            return
        if not self._alerta_preventivo_msg or str(self.lbl_alerta_preventivo.cget("text") or "").strip() != "⚠":
            return

        self._ocultar_tooltip_alerta_preventivo()
        try:
            tip = ctk.CTkToplevel(self)
            tip.overrideredirect(True)
            tip.configure(fg_color="#111821")

            texto = (
                "Observação: "
                f"{self._alerta_preventivo_msg} "
                "Recomenda-se verificação preventiva."
            )
            lbl = ctk.CTkLabel(
                tip,
                text=texto,
                justify="left",
                wraplength=360,
                text_color="#f8f9fa",
                fg_color="#111821",
                corner_radius=8,
                font=("Arial", 11),
                padx=10,
                pady=8,
            )
            lbl.pack()

            x = self.lbl_alerta_preventivo.winfo_rootx() + 16
            y = self.lbl_alerta_preventivo.winfo_rooty() + 28
            tip.geometry(f"+{x}+{y}")
            self._alerta_preventivo_tooltip = tip
            self.after(5000, self._ocultar_tooltip_alerta_preventivo)
        except Exception:
            self._ocultar_tooltip_alerta_preventivo()

    def _atualizar_alerta_preventivo_ui(self, mensagem: str):
        # Independente de pop-ups, o alerta só some se limpar ou mudar o modelo
        if not self._vigilancia_habilitada:
            self._alerta_preventivo_msg = ""
            self._ocultar_tooltip_alerta_preventivo()
            self.lbl_alerta_preventivo.configure(text="")
            return
        self._alerta_preventivo_msg = str(mensagem or "").strip()
        if self._alerta_preventivo_msg:
            self.lbl_alerta_preventivo.configure(text="⚠")
        else:
            self.lbl_alerta_preventivo.configure(text="")
            self._ocultar_tooltip_alerta_preventivo()

    # --- CORREÇÃO: assinatura correta para evitar TypeError ---

    def _agendar_vigilancia_preventiva(self, _event=None):
        if not self._vigilancia_habilitada:
            return
        try:
            if self._vigilancia_after_id is not None:
                self.after_cancel(self._vigilancia_after_id)
        except Exception:
            pass

        if self.winfo_exists(): #
            self._vigilancia_after_id = self.after(700, self._iniciar_vigilancia_preventiva)

    def _iniciar_vigilancia_preventiva(self, event=None):
        if not self._vigilancia_habilitada:
            return
        equipamento = self.txt_equip.get().strip().upper()
        if len(equipamento) < 4:
            self._atualizar_alerta_preventivo_ui("")
            return

        self._vigilancia_token += 1
        token = self._vigilancia_token

        if equipamento in self._cache_vigilancia_modelo:
            self._atualizar_alerta_preventivo_ui(self._cache_vigilancia_modelo.get(equipamento, ""))
            return

        def worker():
            msg = ""
            try:
                fabricante, modelo = self._extrair_fabricante_modelo(equipamento)
                msg = self._buscar_alerta_preventivo_modelo(fabricante, modelo)
            except Exception as e:
                logger.info("Vigilância técnica: falha na busca preventiva: %s", e)

            def aplicar():
                if token != self._vigilancia_token:
                    return
                if self.winfo_exists():
                    self._cache_vigilancia_modelo[equipamento] = msg #
                    self._atualizar_alerta_preventivo_ui(msg)

            if self.winfo_exists():
                self.after(0, aplicar)

        # Modo teste síncrono: execução direta sem thread.
        worker()

    def _detectar_peca_com_desgaste(self, texto: str) -> str:
        base = str(texto or "").lower()
        mapa = [
            (("anti reverse", "anti-reverse", "one way", "one-way"), "ANTI-REVERSO"),
            (("drag", "drag washer", "friction washer"), "SISTEMA DE DRAG"),
            (("bearing", "bearings", "rolamento", "rolamentos"), "ROLAMENTO"),
            (("worm shaft", "sem-fim", "sem fim"), "EIXO SEM-FIM"),
            (("pinion", "pinhao", "engrenagem"), "PINHÃO/ENGRENAGEM"),
            (("line roller", "bail roller", "rolete"), "ROLETE DE LINHA"),
            (("handle", "manivela"), "MANIVELA"),
            (("spool", "carretel"), "CARRETEL"),
            (("level wind", "pawl"), "GUIA DE LINHA"),
        ]
        for termos, nome_peca in mapa:
            if any(t in base for t in termos):
                return nome_peca
        return "COMPONENTES INTERNOS"

    def _sintetizar_alerta_desgaste_com_ia(self, fabricante: str, modelo: str, texto_fonte: str) -> str:
        prompt = (
            "Você é um assistente técnico de manutenção. "
            f"Analise o texto abaixo sobre {fabricante} {modelo} e identifique apenas UMA peça com indício de desgaste prematuro. "
            "Responda estritamente no formato: PECA=<nome da peça>.\n\n"
            f"TEXTO: {texto_fonte[:4000]}"
        )
        resp = self._chamar_google_ai_texto(prompt, timeout=14)
        m = re.search(r"PECA\s*=\s*([^\n\r]+)", str(resp or ""), flags=re.IGNORECASE)
        if m:
            peca = re.sub(r"\s+", " ", m.group(1)).strip().upper()
            if peca:
                return peca
        return ""

    def _buscar_alerta_preventivo_modelo(self, fabricante: str, modelo: str) -> str:
        if not fabricante or not modelo:
            return ""

        alvo = f"{fabricante} {modelo}".strip()
        consultas = [
            f'"{alvo}" "common issues"',
            f'"{alvo}" "premature wear"',
            f'"{alvo}" "desgaste prematuro"',
            f'site:tackletour.com "{alvo}"',
            f'"{alvo}" recall',
        ]

        palavras_risco = (
            "common issue",
            "common issues",
            "premature wear",
            "known issue",
            "failure",
            "worn out",
            "desgaste prematuro",
            "desgaste",
            "falha recorrente",
            "recall",
        )

        links = []
        vistos = set()

        for consulta in consultas:
            try:
                url = f"https://duckduckgo.com/html/?q={quote_plus(consulta)}"
                req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(req, timeout=8) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                trecho = re.sub(r"<[^>]+>", " ", html)
                trecho = re.sub(r"\s+", " ", trecho).lower()
                if any(p in trecho for p in palavras_risco):
                    peca = self._sintetizar_alerta_desgaste_com_ia(fabricante, modelo, trecho) or self._detectar_peca_com_desgaste(trecho)
                    return f"Este modelo possui histórico de desgaste prematuro em {peca}."

                for l in self._extrair_links_html(html, url):
                    n = self._normalizar_link_resultado(l)
                    if n and n not in vistos:
                        vistos.add(n)
                        links.append(n)
            except Exception:
                continue

        for link in links[:5]:
            try:
                req = Request(link, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(req, timeout=8) as resp:
                    bruto = resp.read().decode("utf-8", errors="ignore")
                texto = re.sub(r"<[^>]+>", " ", bruto)
                texto = re.sub(r"\s+", " ", texto).lower()
                if modelo.lower() not in texto and fabricante.lower() not in texto:
                    continue
                if any(p in texto for p in palavras_risco):
                    peca = self._sintetizar_alerta_desgaste_com_ia(fabricante, modelo, texto) or self._detectar_peca_com_desgaste(texto)
                    return f"Este modelo possui histórico de desgaste prematuro em {peca}."
            except Exception:
                continue

        return ""

    def _extrair_links_html(self, html: str, base_url: str) -> list[str]:
        links = []
        padrao = re.compile(r'(?:href|src)=["\']([^"\']+)["\']', re.IGNORECASE)
        for raw in padrao.findall(html or ""):
            link = (raw or "").strip()
            if not link:
                continue
            if link.startswith("//"):
                link = "https:" + link
            elif link.startswith("/"):
                link = urljoin(base_url, link)
            if not link.lower().startswith(("http://", "https://")):
                continue
            links.append(link)
        return links

    def _normalizar_link_resultado(self, link: str) -> str:
        link = (link or "").strip()
        if not link:
            return ""
        parsed = urlparse(link)
        if "duckduckgo.com" in parsed.netloc.lower() and parsed.path.startswith("/l/"):
            uddg = parse_qs(parsed.query).get("uddg", [""])[0]
            if uddg:
                return unquote(uddg)
        return link

    def _pasta_download_vistas(self) -> str:
        pasta = os.path.join(os.path.dirname(CAMINHO_BANCO), "downloads_vistas")
        os.makedirs(pasta, exist_ok=True)
        return pasta

    def _buscar_vista_ja_baixada(self, equipamento: str) -> str:
        chave = re.sub(r"[^a-z0-9]+", "_", str(equipamento or "").lower()).strip("_")
        if not chave:
            return ""
        pasta = self._pasta_download_vistas()
        candidatos = []
        for nome in os.listdir(pasta):
            nome_low = nome.lower()
            if chave in re.sub(r"[^a-z0-9]+", "_", nome_low):
                caminho = os.path.join(pasta, nome)
                if os.path.isfile(caminho):
                    candidatos.append(caminho)
        if not candidatos:
            return ""
        candidatos.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return candidatos[0]

    def _ler_cfg_diagrama(self) -> configparser.ConfigParser:
        cfg = configparser.ConfigParser()
        try:
            cfg_path = os.path.join(os.path.dirname(CAMINHO_BANCO), "config.cfg")
            if os.path.exists(cfg_path):
                cfg.read(cfg_path, encoding="utf-8")
        except Exception:
            pass
        return cfg

    def _obter_google_ai_key(self) -> str:
        return str(obter_google_ai_key_mestre() or "").strip()

    def _obter_cfg_diagrama(self, chave: str, fallback: str = "") -> str:
        if chave == "gemini_api_key":
            key_env = self._obter_google_ai_key()
            if key_env:
                return key_env
        cfg = self._ler_cfg_diagrama()
        return str(cfg.get("ia_diagramas", chave, fallback=fallback)).strip()

    def _chamar_google_ai_texto(self, prompt: str, timeout: int = 18) -> str:
        api_key = self._obter_google_ai_key()
        if not api_key:
            return ""
        model_name = self._obter_cfg_diagrama("gemini_model", "gemini-1.5-flash")
        try:
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": str(prompt or "").strip()}
                        ]
                    }
                ]
            }
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))

            for cand in data.get("candidates", []):
                parts = cand.get("content", {}).get("parts", [])
                for p in parts:
                    txt = str(p.get("text") or "").strip()
                    if txt:
                        return txt
        except Exception:
            logger.info("Google AI: chamada de texto falhou.")
        return ""

    def _normalizar_modelo_key(self, fabricante: str, modelo: str) -> str:
        base = f"{fabricante} {modelo}".strip().lower()
        base = re.sub(r"\s+", " ", base)
        return re.sub(r"[^a-z0-9 ]+", "", base).strip()

    def _extrair_fabricante_modelo(self, equipamento: str) -> tuple[str, str]:
        txt = str(equipamento or "").strip().upper()
        if not txt:
            return "", ""
        partes = [p for p in re.split(r"\s+", txt) if p]
        if len(partes) == 1:
            return partes[0], partes[0]
        return partes[0], " ".join(partes[1:])

    def _higienizar_termo_busca(self, equipamento: str) -> str:
        termo = str(equipamento or "").strip().upper()
        if not termo:
            return ""

        sinonimos_erro = {
            "TRATOR": "TATULA",
            "TATUADOR": "TATULA",
            "TATULA": "TATULA",
            "CARRETIA": "CARRETILHA",
            "MOLINETEIRO": "MOLINETE",
        }

        marcas = ("DAIWA", "SHIMANO", "MARINE", "MARURI", "ABU", "OKUMA")

        termo_base = termo
        for errado, correto in sinonimos_erro.items():
            termo_base = re.sub(rf"\b{re.escape(errado)}\b", correto, termo_base)

        alterado_por_sinonimo = termo_base != termo
        if alterado_por_sinonimo:
            if "TATULA" in termo_base and not any(m in termo_base for m in marcas):
                termo_base = f"DAIWA {termo_base}".strip()
            return termo_base

        prompt = (
            "Você é um tradutor técnico de oficina de pesca. "
            "Considere contexto de carretilhas e molinetes (DAIWA, SHIMANO, MARINE, MARURI, ABU, OKUMA). "
            "Nunca interprete termos como veículo/profissão. "
            "Responda somente JSON válido com as chaves: termo_corrigido, confianca, justificativa. "
            "confianca deve ser número de 0 a 100. "
            "Exemplo: entrada 'Esquema técnico do trator 300' -> termo_corrigido='DAIWA TATULA 300'.\n\n"
            f"Termo original: {termo}"
        )
        resposta = self._chamar_google_ai_texto(prompt, timeout=12)

        candidato = ""
        confianca = 0.0
        try:
            bloco = str(resposta or "").strip()
            inicio = bloco.find("{")
            fim = bloco.rfind("}")
            if inicio >= 0 and fim > inicio:
                bloco = bloco[inicio:fim + 1]
            data = json.loads(bloco)
            if isinstance(data, dict):
                candidato = str(data.get("termo_corrigido") or "").strip().upper()
                confianca = float(data.get("confianca") or 0.0)
        except Exception:
            candidato = str(resposta or "").strip().upper()
            confianca = 0.0

        if not candidato or confianca < 90.0:
            return termo

        candidato = re.sub(r"\s+", " ", candidato)
        candidato = re.sub(r"[^A-Z0-9 /.-]", "", candidato).strip()
        if len(candidato) < 4:
            return termo

        if "TATULA" in candidato and not any(m in candidato for m in marcas):
            candidato = f"DAIWA {candidato}".strip()

        return candidato

    def _atualizar_status_busca_diagrama(self, texto: str, cor: str = "#95a5a6"):
        if not self.winfo_exists(): return
        lbl = getattr(self, "lbl_status_busca_diagrama", None)
        if lbl is None:
            return
        try:
            lbl.configure(text=str(texto or ""), text_color=cor)
        except Exception:
            pass

    def _carregar_json_colaborativo_drive(self) -> dict:
        url = self._obter_cfg_diagrama("drive_json_url", "")
        if not url:
            return {}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _buscar_link_no_drive(self, fabricante: str, modelo: str) -> str:
        base = self._carregar_json_colaborativo_drive()
        if not base:
            return ""

        chaves = [
            self._normalizar_modelo_key(fabricante, modelo),
            self._normalizar_modelo_key("", modelo),
            self._normalizar_modelo_key(fabricante, ""),
        ]
        for chave in chaves:
            if not chave:
                continue
            item = base.get(chave)
            if isinstance(item, str) and item.lower().startswith(("http://", "https://")):
                return item
            if isinstance(item, dict):
                link = str(item.get("url") or item.get("link") or "").strip()
                if link.lower().startswith(("http://", "https://")):
                    return link
        return ""

    def _post_drive_evento(self, payload: dict, caminho_arquivo: str = ""):
        url = self._obter_cfg_diagrama("drive_webhook_url", "")
        if not url:
            return
        body = dict(payload or {})
        if caminho_arquivo and os.path.exists(caminho_arquivo):
            nome = os.path.basename(caminho_arquivo)
            with open(caminho_arquivo, "rb") as f:
                conteudo = f.read()
            body["arquivo_nome"] = nome
            body["arquivo_base64"] = base64.b64encode(conteudo).decode("ascii")

        data = json.dumps(body, ensure_ascii=True).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "OficinaPesca/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15):
            pass

    def _registrar_sucesso_colaborativo(self, fabricante: str, modelo: str, url_diagrama: str):
        try:
            self._post_drive_evento(
                {
                    "acao": "registrar_sucesso",
                    "fabricante": fabricante,
                    "modelo": modelo,
                    "url": url_diagrama,
                    "origem": "oficina_desktop",
                    "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        except Exception:
            logger.exception("Falha ao registrar sucesso colaborativo do diagrama.")

    def _registrar_falha_colaborativa(self, fabricante: str, modelo: str, motivo: str):
        try:
            self._post_drive_evento(
                {
                    "acao": "registrar_falha",
                    "fabricante": fabricante,
                    "modelo": modelo,
                    "motivo": motivo,
                    "origem": "oficina_desktop",
                    "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        except Exception:
            logger.exception("Falha ao registrar log de falha colaborativa.")

    def _registrar_links_descobertos_colaborativo(self, fabricante: str, modelo: str, opcoes: list[dict]):
        if not opcoes:
            return

        links = []
        for item in opcoes[:12]:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            links.append(
                {
                    "url": url,
                    "score": int(item.get("score") or 0),
                }
            )

        if not links:
            return

        payload = {
            "acao": "registrar_links_descobertos",
            "fabricante": fabricante,
            "modelo": modelo,
            "destino_email": "frs.suporte.oficina@gmail.com",
            "origem": "oficina_desktop",
            "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "links": links,
        }

        def _worker():
            try:
                self._post_drive_evento(payload)
            except Exception:
                logger.exception("Falha ao registrar links descobertos para o Drive colaborativo.")

        try:
            # Modo teste síncrono: execução direta sem thread.
            _worker()
        except Exception:
            pass

    def _link_eh_tecnico_valido(self, link: str) -> bool:
        l = (link or "").lower().split("?")[0]
        if not l.startswith(("http://", "https://")):
            return False

        # Blacklist rigorosa: ignora logos, ícones, redes sociais e termos genéricos
        blacklist = ("logo", "banner", "icon", "cart", "index", "promocao", "social", "favicon", "sprite", "css", "js", "facebook", "instagram", "twitter")
        if any(x in l for x in blacklist):
            return False

        # Ignora páginas HTML genéricas que não são arquivos de documento
        if l.endswith((".html", ".htm", ".php", ".aspx")):
            return False

        if any(l.split("?")[0].endswith(ext) for ext in (".pdf", ".png", ".jpg", ".jpeg", ".webp")):
            return True

        # Palavras-chave técnicas obrigatórias para validar o link
        palavras = ("schematic", "pdf", "parts list", "exploded view", "manual", "parts", "diagram", "vista", "explodida")
        return any(p in l for p in palavras)

    def _salvar_diagrama_silencioso(self, fabricante, modelo, url):
        """Motor de Inteligência: Catalogação automática no DB local e Sincronização imediata no Google Drive."""
        if not url:
            return

        def _thread_save():
            try:
                # 1. Registro no Banco de Dados Local
                fabricante_up = fabricante.upper()
                modelo_up = modelo.upper()
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT OR IGNORE INTO esquemas_vistas (fabricante, modelo, url, origem) VALUES (?, ?, ?, ?)",
                        (fabricante_up, modelo_up, url, "Inteligência Compartilhada")
                    )
                    conn.commit()

                # 2. Upload em tempo real para a PLANILHA_CONHECIMENTO (Google Drive) via config.py
                # Isso garante a alimentação do cérebro compartilhado do sistema
                salvar_link_alerta_conhecimento(fabricante_up, modelo_up, url, origem="ia_auto_feed")
                
                if self.winfo_exists(): #
                    self.after(0, lambda: self._feedback_silencioso("Check: Link sincronizado com a nuvem"))
            except Exception as e:
                logger.info(f"Falha na sincronização inteligente com Drive: {e}")
        
        # Modo teste síncrono: execução direta sem thread.
        _thread_save()

    def _pontuar_link_diagrama(self, link: str, fabricante: str, modelo: str) -> int:
        l = (link or "").lower()
        oficiais = (
            "reelschematic.com",
            "shimano",
            "daiwa",
            "marine",
            "maruri",
            "abu",
            "okuma",
        )
        score = 0
        if any(dom in l for dom in oficiais):
            score += 90
        if l.split("?")[0].endswith(".pdf"):
            score += 200  # Prioridade absoluta para arquivos PDF
        if any(x in l for x in ("exploded", "schematic", "manual", "diagram", "part list", "explodida")):
            score += 70

        for t in re.findall(r"[a-z0-9]+", f"{fabricante} {modelo}".lower()):
            if len(t) >= 3 and t in l:
                score += 3
        return score

    def abrir_janela_ia_diagramas(self, titulo: str = "Selecionar Diagrama Técnico"):
        win = ctk.CTkToplevel(self)
        win.title(titulo)
        win.geometry("700x350")
        win.resizable(False, False)
        win.configure(fg_color="#161b22")
        win.grab_set()
        win.focus_force()
        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - (700 // 2)
        y = (win.winfo_screenheight() // 2) - (350 // 2)
        win.geometry(f"700x350+{x}+{y}")
        return win

    def _buscar_links_web_diagrama(self, fabricante: str, modelo: str) -> list[dict]:
        consulta_base = f"{fabricante} {modelo}".strip()
        # Query de pesquisa refinada conforme solicitado
        query = f"{consulta_base} schematic pdf parts list exploded view"

        consultas = [
            query,
            f"site:reelschematic.com {consulta_base} exploded",
            f"site:shimano.com {consulta_base} schematic",
            f"site:daiwa.com {consulta_base} schematic",
            f"site:daiwa.com {consulta_base} manual",
            f"site:marinefishing.com.br {consulta_base} manual",
            f"site:marurifishing.com.py {consulta_base} manual",
        ]

        encontrados = []
        vistos = set()

        for consulta in consultas:
            try:
                url = f"https://duckduckgo.com/html/?q={quote_plus(consulta)}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                links = [self._normalizar_link_resultado(l) for l in self._extrair_links_html(html, url)]
            except Exception:
                continue

            for link in links:
                link = (link or "").strip()
                if not link or link in vistos:
                    continue
                vistos.add(link)
                if not self._link_eh_tecnico_valido(link):
                    continue
                encontrados.append({
                    "url": link,
                    "score": self._pontuar_link_diagrama(link, fabricante, modelo),
                })

        encontrados.sort(key=lambda x: x.get("score", 0), reverse=True)
        encontrados = encontrados[:12]

        # Refino opcional com IA para priorizar links tecnicamente mais úteis.
        if encontrados:
            try:
                lista_urls = [str(x.get("url") or "").strip() for x in encontrados if str(x.get("url") or "").strip()]
                if lista_urls:
                    prompt = (
                        "Priorize links de diagrama técnico (vista explodida) para manutenção. "
                        f"Modelo: {fabricante} {modelo}. "
                        "Responda apenas com uma lista de URLs, uma por linha, na ordem de relevância.\n\n"
                        + "\n".join(lista_urls)
                    )
                    resposta = self._chamar_google_ai_texto(prompt, timeout=16)
                    ordem = [ln.strip() for ln in str(resposta or "").splitlines() if ln.strip().startswith(("http://", "https://"))]
                    if ordem:
                        rank = {u: i for i, u in enumerate(ordem)}
                        encontrados.sort(key=lambda item: (rank.get(str(item.get("url") or ""), 9999), -int(item.get("score", 0))))
            except Exception:
                pass

            self._registrar_links_descobertos_colaborativo(fabricante, modelo, encontrados)

        return encontrados

    def _popup_opcoes_diagrama(self, fabricante: str, modelo: str, opcoes: list[dict]) -> tuple[bool, bool]:
        resolvido = {"ok": False}
        tentou = {"flag": False}

        win = self.abrir_janela_ia_diagramas("Selecionar Diagrama Técnico")

        ctk.CTkLabel(win, text=t("ui_sele_o_de_diagrama_t_cnico"), text_color="orange", font=("Arial", 17, "bold")).pack(pady=(10, 2))
        ctk.CTkLabel(win, text=f"Modelo: {fabricante} {modelo}".strip(), text_color="#bdc3c7", font=("Arial", 11)).pack(pady=(0, 8))

        frame = ctk.CTkFrame(win, fg_color="#161b22")
        frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        frame.grid_columnconfigure((0, 1, 2), weight=1)

        def abrir_e_validar(url_diagrama: str):
            tentou["flag"] = True
            try:
                webbrowser.open(url_diagrama)
            except Exception:
                messagebox.showwarning("Diagrama", "Não foi possível abrir o link automaticamente.", parent=win)
                return
            
            # Salvamento automático sem perguntar
            self._salvar_diagrama_silencioso(fabricante, modelo, url_diagrama)
            self._registrar_sucesso_colaborativo(fabricante, modelo, url_diagrama)

        melhores = [str(item.get("url", "")).strip() for item in opcoes[:3] if str(item.get("url", "")).strip()]

        bloco_amarelo = ctk.CTkFrame(frame, fg_color="#f1c40f", corner_radius=10)
        bloco_amarelo.grid(row=0, column=0, sticky="nsew", padx=6, pady=2)
        ctk.CTkLabel(bloco_amarelo, text=t("ui_resultados_t_cnicos"), text_color="#2c3e50", font=("Arial", 13, "bold")).pack(pady=(10, 6))
        ctk.CTkLabel(bloco_amarelo, text=f"{len(opcoes)} opção(ões) encontrada(s)", text_color="#2c3e50", font=("Arial", 10)).pack(pady=(0, 6))
        if melhores:
            ctk.CTkButton(
                bloco_amarelo,
                text=t("ui_abrir_diagrama_t_cnico_1"),
                width=170,
                height=32,
                fg_color="#d68910",
                hover_color="#b9770e",
                command=lambda: abrir_e_validar(melhores[0]),
            ).pack(pady=(4, 6))
        ctk.CTkLabel(bloco_amarelo, text=t("ui_valide_ap_s_abrir"), text_color="#5d4037", font=("Arial", 10)).pack(pady=(0, 10))

        bloco_azul = ctk.CTkFrame(frame, fg_color="#2980b9", corner_radius=10)
        bloco_azul.grid(row=0, column=1, sticky="nsew", padx=6, pady=2)
        ctk.CTkLabel(bloco_azul, text=t("ui_links_sugeridos"), text_color="#ecf0f1", font=("Arial", 13, "bold")).pack(pady=(10, 6))
        for i, url in enumerate(melhores[1:], start=2):
            ctk.CTkButton(
                bloco_azul,
                text=f"Abrir Diagrama Técnico {i}",
                width=170,
                height=32,
                fg_color="#1f618d",
                hover_color="#154360",
                command=lambda u=url: abrir_e_validar(u),
            ).pack(pady=4)
        if len(melhores) <= 1:
            ctk.CTkLabel(bloco_azul, text=t("ui_sem_links_dispon_veis"), text_color="#ecf0f1", font=("Arial", 10)).pack(pady=(6, 6))

        bloco_verde = ctk.CTkFrame(frame, fg_color="#27ae60", corner_radius=10)
        bloco_verde.grid(row=0, column=2, sticky="nsew", padx=6, pady=2)
        ctk.CTkLabel(bloco_verde, text=t("ui_a_es"), text_color="#ecf0f1", font=("Arial", 13, "bold")).pack(pady=(10, 6))
        ctk.CTkLabel(bloco_verde, text=t("ui_se_nada_resolver_continue_npara_a_busca_por_foto"), text_color="#ecf0f1", font=("Arial", 10), justify="center").pack(pady=(0, 10))
        ctk.CTkButton(
            bloco_verde,
            text=t("ui_nenhuma_op_o_funcionou"),
            fg_color="#1e8449",
            hover_color="#196f3d",
            width=170,
            height=32,
            command=win.destroy,
        ).pack(pady=(4, 8))

        win.wait_window()
        return resolvido["ok"], tentou["flag"]

    def _gemini_identificar_modelo_por_foto(self, caminho_foto: str, fabricante: str, modelo: str) -> str:
        api_key = self._obter_cfg_diagrama("gemini_api_key", "")
        model_name = self._obter_cfg_diagrama("gemini_model", "gemini-1.5-flash")
        if not api_key:
            return ""
        try:
            with open(caminho_foto, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("ascii")

            prompt = (
                "Você é técnico em manutenção de carretilhas e molinetes. "
                "Analise a foto e retorne somente um texto curto no formato: FABRICANTE MODELO. "
                f"Contexto informado: fabricante={fabricante}, modelo={modelo}."
            )
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
                        ]
                    }
                ]
            }
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))

            txt = ""
            for cand in data.get("candidates", []):
                parts = cand.get("content", {}).get("parts", [])
                for p in parts:
                    if p.get("text"):
                        txt = str(p.get("text")).strip()
                        break
                if txt:
                    break
            txt = re.sub(r"\s+", " ", txt).strip().upper()
            return txt
        except Exception:
            logger.exception("Falha ao analisar foto com Gemini Vision.")
            return ""

    def _fallback_anexar_foto_gemini(self, fabricante: str, modelo: str) -> str:
        # Mantido apenas para compatibilidade; fluxo atual usa _gemini_identificar_modelo_por_foto_com_dialog.
        return ""

    def _is_technical_url(self, text):
        """Verifica se o texto copiado é um link de diagrama técnico válido."""
        if not text.lower().startswith(("http://", "https://")):
            return False
        l_text = text.lower().split('?')[0]
        if l_text.endswith(".pdf"):
            return True
        tech_domains = [
            "reelschematic.com", "shimano.com", "daiwa.com",
            "marinefishing.com.br", "marurifishing.com.py",
            "mikesreelrepair.com", "southwestreel.com"
        ]
        return any(domain in l_text for domain in tech_domains)

    def _feedback_silencioso(self, msg):
        """Exibe feedback temporário e discreto na UI."""
        if not self.winfo_exists(): return
        self._atualizar_status_busca_diagrama(msg, cor="#2ecc71")
        self.after(4000, lambda: self.winfo_exists() and self._atualizar_status_busca_diagrama(""))

    def aprovar_os(self, total, cliente):
        """Sequência de Aprovação Sagrada: Salva -> PDF Original (Reportlab) -> Financeiro."""
        try:
            escolha = self._selecionar_pagamento_simples()
            if not escolha:
                return

            forma_pagamento = self._normalizar_forma_pagamento(escolha.get("condicao"))
            metodo_pagamento = str(escolha.get("metodo") or "PIX")
            self.var_pagamento.set(forma_pagamento)
            self.salvar_documento(status='APROVADO', forma_de_pagamento=forma_pagamento)
            # Gera PDF original com logotipos e termos (Reportlab)
            pdf_gerado = self.gerar_documento_pdf(eh_os=True, forma_de_pagamento=forma_pagamento)
            if pdf_gerado:
                self._lancar_financeiro_pos_aprovacao(total, cliente, forma_pagamento, metodo_pagamento)
        except Exception as e:
            messagebox.showerror("Aprovação", f"Erro ao aprovar O.S.: {e}")

    # Tooltip for alert icon
    _current_alert_tooltip = None

    def _show_alert_tooltip(self, event, message: str):
        """Displays a tooltip with the alert message."""
        self._hide_alert_tooltip() # Hide any existing tooltip

        widget = event.widget
        # Position the tooltip slightly below the widget
        x = widget.winfo_rootx() + widget.winfo_width() // 2 - 150 # Center it roughly
        y = widget.winfo_rooty() + widget.winfo_height() + 5

        tooltip = ctk.CTkToplevel(self)
        tooltip.wm_overrideredirect(True) # Remove window decorations
        tooltip.wm_geometry(f"+{x}+{y}")
        tooltip.configure(fg_color="#333333") # Dark background for tooltip

        label = ctk.CTkLabel(
            tooltip,
            text=f"Nota Técnica: {message}",
            font=("Arial", 10),
            text_color="#f8f8f8",
            wraplength=300,
            justify="left",
            padx=5,
            pady=5
        )
        label.pack(ipadx=1, ipady=1)
        self._current_alert_tooltip = tooltip

    def _hide_alert_tooltip(self, event=None):
        """Hides the currently displayed tooltip."""
        if self._current_alert_tooltip:
            self._current_alert_tooltip.destroy()
            self._current_alert_tooltip = None

    def _abrir_diagrama_direto(self, link_info: dict, termo_busca: str):
        """Etapa 1: Abre um único diagrama diretamente em uma janela preta para visualização imediata."""
        url = link_info["url"]
        display_name = link_info.get("display_name", url)
        fabricante, modelo = self._extrair_fabricante_modelo(termo_busca)

        win = ctk.CTkToplevel(self)
        win.title(f"Diagrama: {display_name}")
        win.geometry("800x600")
        win.configure(fg_color="#000000") # Absolute black background
        win.grab_set()
        win.focus_force()
        win.lift()

        ctk.CTkLabel(win, text=f"Diagrama para: {display_name}", font=("Arial", 16, "bold"), text_color="#f8f8f8", fg_color="#000000").pack(pady=(15, 5))
        ctk.CTkLabel(win, text=t("ui_abrindo_no_navegador"), font=("Arial", 12), text_color="#cccccc", fg_color="#000000").pack(pady=(5, 10))

        # Modo teste síncrono: execução direta sem thread.
        self._run_ai_alert_scan_and_notify(fabricante, modelo, termo_busca)

        def _open_and_save():
            try:
                webbrowser.open(url)
                self._salvar_diagrama_silencioso(fabricante, modelo, url) # Step 5: Total Synchronization
                self._atualizar_status_busca_diagrama(f"Diagrama para '{display_name}' aberto e salvo.", cor="#2ecc71")
            except Exception as e:
                self._atualizar_status_busca_diagrama(f"Erro ao abrir diagrama: {e}", cor="#e74c3c")

        win.after(100, _open_and_save)

    def _run_ai_alert_scan_and_notify(self, fabricante: str, modelo: str, termo_busca: str):
        """Runs the AI alert scan in background and notifies if a new alert is found."""
        try:
            alert_message = self._buscar_alerta_preventivo_modelo(fabricante, modelo)
            if alert_message:
                try:
                    existing_alert = self._check_for_preexisting_alert(fabricante, modelo)
                    if not existing_alert or existing_alert != alert_message:
                        salvar_link_alerta_conhecimento(
                            fabricante, modelo, "", origem="ia_alert_scan", alerta=alert_message
                        )
                        if self.winfo_exists():
                            self.after(0, lambda: self.winfo_exists() and self._feedback_silencioso(f"Novo alerta técnico salvo para {fabricante} {modelo}."))
                except Exception:
                    logger.exception("Falha ao salvar novo alerta técnico via AI scan.")
        except Exception as e: #
            # Log the exception if necessary, but don't re-raise to prevent app crash
            logger.error(f"Erro na thread de Vigilância Técnica: {e}")

    def _exibir_janela_diagramas_multiplas_escolhas(self, termo_busca: str, links: list[dict]):
        """Etapa 2: Exibe uma janela com múltiplos links para o usuário escolher."""
        win = ctk.CTkToplevel(self)
        win.title(f"Diagramas para: {termo_busca}")
        win.geometry("800x520")
        win.configure(fg_color="#000000")  # Absolute black background
        win.grab_set()
        win.focus_force()
        win.lift()

        ctk.CTkLabel(win, text=f"Resultados para: {termo_busca}", font=("Arial", 16, "bold"), text_color="#f8f8f8", fg_color="#000000").pack(pady=(15, 5))
        
        if links:
            ctk.CTkLabel(win, text=t("ui_clique_no_tri_ngulo_para_ver_alertas_t_cnicos"), font=("Arial", 10), text_color="#f1c40f", fg_color="#000000").pack(pady=(0, 10))
        
        scroll_frame = ctk.CTkScrollableFrame(win, fg_color="#000000") # Black background for scrollable frame
        scroll_frame.pack(fill="both", expand=True, padx=15, pady=10)

        if not links:
            ctk.CTkLabel(scroll_frame, text=t("ui_nenhum_diagrama_encontrado_para_este_equipamento"), text_color="#ff6b6b", font=("Arial", 12)).pack(pady=30)
            ctk.CTkButton(scroll_frame, text=t("ui_tentar_identifica_o_por_foto"), fg_color="#e67e22", hover_color="#d35400", width=250, height=40,
                          command=lambda: (win.destroy(), self._executar_busca_por_foto_bg(termo_busca))).pack(pady=10)
            return

        def on_click_link(url_to_open: str, display_name: str):
            # Modo teste síncrono: execução direta sem thread.
            fabricante, modelo = self._extrair_fabricante_modelo(termo_busca)
            self._run_ai_alert_scan_and_notify(fabricante, modelo, termo_busca)

            webbrowser.open(url_to_open)
            self._salvar_diagrama_silencioso(fabricante, modelo, url_to_open) # Step 5: Total Synchronization
            self._atualizar_status_busca_diagrama(f"Diagrama para '{display_name}' aberto e salvo.", cor="#2ecc71")

        for link_info in links:
            url = link_info["url"]
            display_name = link_info.get("display_name", url)
            alert_message = link_info.get("alert_message")

            item_container = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            item_container.pack(anchor="w", padx=20, pady=4)

            model_label = ctk.CTkLabel(
                item_container,
                text=display_name,  # Display model name, not URL
                text_color="#cccccc",  # Light gray text
                fg_color="transparent",
                cursor="hand2",
                font=("Arial", 12, "underline")
            )
            model_label.pack(side="left")
            model_label.bind("<Button-1>", lambda e, u=url, dn=display_name: on_click_link(u, dn))

            if alert_message:
                alert_icon_label = ctk.CTkLabel(
                    item_container,
                    text=t("ui_"), # Space for visual separation
                    text_color="#f1c40f",
                    fg_color="transparent",
                    cursor="hand2",
                    font=("Arial", 12, "bold")
                )
                alert_icon_label.pack(side="left", padx=(5, 0))
                alert_icon_label.bind("<Enter>", lambda e, msg=alert_message: self._show_alert_tooltip(e, msg))
                alert_icon_label.bind("<Leave>", self._hide_alert_tooltip)
                alert_icon_label.bind("<Button-1>", lambda e, msg=alert_message: self._show_alert_tooltip(e, msg))

        ctk.CTkButton(win, text=t("ui_nenhum_funcionou_fechar"), fg_color="#c0392b", command=win.destroy).pack(pady=10)

    def buscar_vista_equipamento(self, equipamento_digitado=None):
        """Inicia motor de inteligência compartilhada: Busca, Filtro e Upload Automático para o Drive."""
        termo = (equipamento_digitado or self.txt_equip.get()).strip()
        if not termo: return

        self._atualizar_status_busca_diagrama("Buscando diagramas técnicos...", cor="#f1c40f")

        # Modo teste síncrono: execução direta sem thread.
        self._executar_busca_filtrada_bg(termo)

    def _executar_busca_filtrada_bg(self, termo):
        """Lógica de raspagem, aplicação de filtros rigorosos por marca e upload para o cérebro compartilhado."""
        fabricante, modelo = self._extrair_fabricante_modelo(termo)
        links_coletados = []
        lock = threading.Lock()
        fab_upper = fabricante.upper()
        
        alvos = [
            "https://reelschematic.com/reelschematics/", "https://www.marinefishing.com.br/manuais",
            "https://marurifishing.com.py/categoria/pecas-carretilha", "https://marurifishing.com.py/categoria/manutencao",
            "https://joga.com.br/manuais/",
        ]

        def scraper(url):
            try:
                req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urlopen(req, timeout=4) as resp:
                    html = resp.read().decode('utf-8', errors='ignore') #
                    urls = re.findall(r'href=["\'](https?://[^"\']+\.(?:pdf|jpg|png|jpeg))["\']', html, re.I) #
                    for link_url in urls:
                        l_low = link_url.lower()
                        # FILTROS RÍGIDOS DE NEGÓCIO
                        if "MARURI" in fab_upper: #
                            # Maruri: Apenas Imagens
                            if not any(ext in l_low for ext in (".jpg", ".jpeg", ".png")): continue #
                        elif any(m in fab_upper for m in ("MARINE", "SHIMANO", "DAIWA")): #
                            # Shimano/Marine/Daiwa: Apenas PDFs
                            if not l_low.endswith(".pdf"): continue #
                        
                        if modelo.lower() in l_low or fabricante.lower() in l_low: #
                            with lock: #
                                if link_url not in [lc["url"] for lc in links_coletados]: # Avoid duplicates
                                    links_coletados.append({"url": link_url, "display_name": self._obter_nome_modelo_do_link(link_url, fabricante, modelo)})
            except: pass

        # Modo teste síncrono: varredura sequencial sem ThreadPoolExecutor.
        for alvo in alvos:
            scraper(alvo)

        # Incluir links do Drive colaborativo (Etapa 5)
        drive_links = self._buscar_links_colaborativos_drive(fabricante, modelo)
        for d_link in drive_links:
            if d_link not in [lc["url"] for lc in links_coletados]:
                links_coletados.append({"url": d_link, "display_name": self._obter_nome_modelo_do_link(d_link, fabricante, modelo)})

        # Add alert messages to links_coletados
        for link_info in links_coletados:
            alert_msg = self._check_for_preexisting_alert(fabricante, modelo)
            link_info["alert_message"] = alert_msg

        # Incluir links da busca geral na web (menos precisa, menor prioridade)
        web_links_raw = self._buscar_links_web_diagrama(fabricante, modelo)
        for w_link_info in web_links_raw:
            if w_link_info["url"] not in [lc["url"] for lc in links_coletados]:
                links_coletados.append({"url": w_link_info["url"], "display_name": self._obter_nome_modelo_do_link(w_link_info["url"], fabricante, modelo)})

        self.after(0, lambda: self._processar_conclusao_busca(termo, links_coletados))

    def _obter_nome_modelo_do_link(self, url: str, fabricante: str, modelo: str) -> str:
        """Tenta extrair um nome de modelo mais limpo do URL ou usa o termo de busca."""
        url_lower = url.lower()
        
        # Priorize o modelo e fabricante da busca original
        if fabricante and modelo:
            return f"{fabricante} {modelo}".strip().upper()

        # Tenta extrair do URL
        match = re.search(r'/(?:schematics|manuais|pecas-carretilha|manutencao)/([^/]+?)(?:\.pdf|\.jpg|\.png|\.jpeg|$)', url_lower)
        if match:
            extracted_name = match.group(1).replace('-', ' ').replace('_', ' ').strip()
            # Capitalize first letter of each word
            extracted_name = ' '.join([word.capitalize() for word in extracted_name.split()])
            return f"{fabricante.capitalize() if fabricante else ''} {extracted_name}".strip()

        # Fallback para o URL completo se nada mais funcionar
        return url

    def _processar_conclusao_busca(self, termo_busca: str, links_encontrados: list[dict]):
        """Finaliza a busca técnica e exibe a interface de resultados, seguindo o fluxo de inteligência."""
        
        try:
            # Etapa 1: Precisão Exata
            if len(links_encontrados) == 1:
                self._abrir_diagrama_direto(links_encontrados[0], termo_busca)
                self._atualizar_status_busca_diagrama("Diagrama localizado e aberto.", cor="#2ecc71")
            else:
                # Etapa 2: Múltiplas Escolhas ou Caso Vazio
            # A janela agora trata o caso de lista vazia exibindo a mensagem 'Nenhum diagrama encontrado' #
                self._exibir_janela_diagramas_multiplas_escolhas(termo_busca, links_encontrados)
                if links_encontrados:
                    self._atualizar_status_busca_diagrama("Resultados localizados.", cor="#2ecc71")
                else:
                    self._atualizar_status_busca_diagrama("Busca concluída: sem resultados.", cor="#e67e22")
                    
        except Exception as e:
            logger.exception(f"Erro ao processar resultados da busca para {termo_busca}: {e}")
            self._atualizar_status_busca_diagrama("Erro técnico ao processar resultados.", cor="#e74c3c")

    def _executar_busca_por_foto_bg(self, termo_busca: str):
        """Etapa 3: Executa a busca por foto em background e processa o resultado."""
        self.after(0, lambda: self.winfo_exists() and self._atualizar_status_busca_diagrama("Aguardando foto para identificação...", cor="#f1c40f"))
        fabricante, modelo = self._extrair_fabricante_modelo(termo_busca)
        
        identified_model_str = self._gemini_identificar_modelo_por_foto_com_dialog(fabricante, modelo)
        
        if identified_model_str:
            if self.winfo_exists(): #
                self.after(0, lambda: self.winfo_exists() and self._atualizar_status_busca_diagrama(f"Modelo identificado: {identified_model_str}. Buscando diagramas...", cor="#2ecc71"))
            fab_ai, mod_ai = self._extrair_fabricante_modelo(identified_model_str)
            
            # Re-executar a busca com o modelo identificado pela IA
            links_ai_search = self._buscar_links_web_diagrama(fab_ai, mod_ai)
            
            # Adicionar links do Drive colaborativo para o modelo identificado pela IA
            drive_links_ai = self._buscar_links_colaborativos_drive(fab_ai, mod_ai)
            for d_link in drive_links_ai:
                if d_link not in [lc["url"] for lc in links_ai_search]:
                    links_ai_search.append({"url": d_link, "display_name": self._obter_nome_modelo_do_link(d_link, fab_ai, mod_ai)})

            if self.winfo_exists(): #
                self.after(0, lambda: self.winfo_exists() and self._processar_conclusao_busca(identified_model_str, links_ai_search))
        else: #
            if self.winfo_exists():
                self.after(0, lambda: self.winfo_exists() and self._atualizar_status_busca_diagrama("Identificação por foto falhou ou cancelada. Iniciando busca manual...", cor="#e74c3c"))
            # Fallback para a Etapa 4 se a identificação por foto falhar
            self.after(0, lambda: self.winfo_exists() and self._abrir_busca_global_navegador(termo_busca))
            self.after(0, lambda: self.winfo_exists() and self._monitorar_clipboard_escuta(termo_busca))

    def _gemini_identificar_modelo_por_foto_com_dialog(self, fabricante: str, modelo: str) -> str:
        """
        Abre o diálogo de arquivo para o usuário selecionar uma foto e usa a IA para identificar o modelo.
        Retorna a string do modelo identificado ou uma string vazia se falhar/cancelar.
        """
        caminho_foto = filedialog.askopenfilename(
            parent=self,
            title="Anexar foto do equipamento",
            filetypes=[("Imagens", "*.jpg;*.jpeg;*.png;*.webp;*.bmp")],
        )
        if not caminho_foto:
            return ""

        if self.winfo_exists(): #
            self.after(0, lambda: self.winfo_exists() and self._atualizar_status_busca_diagrama("Enviando foto para análise da IA...", cor="#f1c40f"))
        sugestao = self._gemini_identificar_modelo_por_foto(caminho_foto, fabricante, modelo)
        
        if sugestao:
            try:
                nome_modelo_sanitizado = self._normalizar_modelo_key(fabricante, modelo).replace(" ", "_") or "modelo_desconhecido"
                # Esta parte é para contribuição, não estritamente para o fluxo de busca, mas é bom manter.
                self._post_drive_evento(
                    {
                        "acao": "upload_contribuicao",
                        "fabricante": fabricante,
                        "modelo": modelo,
                        "pasta": "Contribuicoes",
                        "nome_arquivo": f"{nome_modelo_sanitizado}_contribuicao.jpg",
                        "origem": "oficina_desktop",
                    },
                    caminho_arquivo=caminho_foto,
                )
            except Exception:
                logger.exception("Falha ao enviar contribuição de foto para o Drive.")
            return sugestao
        return ""

    def _buscar_links_colaborativos_drive(self, fabricante: str, modelo: str) -> list[str]:
        """Busca links na planilha colaborativa do Drive."""
        links = []
        try:
            row, msg = ler_links_alertas_conhecimento(fabricante, modelo) #
            if row and len(row) > 2:
                url = str(row[2]).strip()
                if url and self._link_eh_tecnico_valido(url):
                    links.append(url)
        except Exception:
            logger.exception("Falha ao buscar links no Drive colaborativo.")
        return links

    def _check_for_preexisting_alert(self, fabricante: str, modelo: str) -> Optional[str]:
        """Checks the Drive knowledge base for existing alerts for a given model."""
        try:
            row, msg = ler_links_alertas_conhecimento(fabricante, modelo)
            if row and len(row) > 4 and str(row[4]).strip():
                return str(row[4]).strip()
        except Exception:
            logger.exception(f"Falha ao buscar alertas pre-existentes para {fabricante} {modelo}.")
        return None
    def _monitorar_clipboard_escuta(self, termo):
        """Etapa 4: Monitora o clipboard de forma totalmente automática e silenciosa (Modo Escuta)."""
        fab, mod = self._extrair_fabricante_modelo(termo)
        ultimo_clip = ""
        start = time.time()
        while time.time() - start < 180:  # 3 minutos de escuta ativa
            try:
                conteudo = self.clipboard_get().strip()
                if conteudo and conteudo != ultimo_clip:
                    ultimo_clip = conteudo
                    if self._link_eh_tecnico_valido(conteudo):
                        # Etapa 4 e 5: Salvamento automático e Sincronização Total (Local + Drive) #
                        if self.winfo_exists():
                            self.after(0, lambda c=conteudo: self.winfo_exists() and self._salvar_diagrama_silencioso(fab, mod, c))
                        break
            except Exception:
                pass
            time.sleep(1.5)  # Intervalo otimizado para não pesar na CPU
        self.after(2000, lambda: self.winfo_exists() and self._atualizar_status_busca_diagrama(""))

    def _abrir_busca_global_navegador(self, termo):
        """Abre navegador e deixa o Monitor de Link agir em background."""
        query = quote_plus(f"{termo} schematic diagram pdf exploded view")
        webbrowser.open(f"https://www.google.com/search?q={query}")

    # --- FIM: Removido bloco duplicado/solto de aprovação de O.S. fora de métodos ---

    def _perguntar_condicao_pagamento(self):
        escolha = self._selecionar_pagamento_simples()
        if not escolha:
            return None
        return escolha.get("condicao")

    def _perguntar_tipo_pagamento(self):
        escolha = self._selecionar_pagamento_simples()
        if not escolha:
            return None
        return escolha.get("metodo")

    def clicar_reprovado(self):
        if messagebox.askyesno("Reprovar", "Marcar como REPROVADO?", parent=self):
            self.salvar_documento(status="REPROVADO")
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE orcamentos_aguardo SET status='REPROVADO' WHERE id=?", (self.num_oc,))
                conn.commit()
            try:
                enviar_registro_os_central_silencioso(
                    {
                        "id": int(self.num_oc),
                        "cliente": self.txt_cliente.get().strip().upper(),
                        "status": "REPROVADO",
                        "data": datetime.now().strftime("%d/%m/%Y"),
                    },
                    operacao="status",
                )
            except Exception:
                pass
            self.atualizar_identificacao_documento("REPROVADO")
            try:
                self._gerar_pdf_orcamento_reprovado_automatico(motivo="REPROVADO PELO CLIENTE")
            except Exception:
                logger.exception("Falha ao gerar PDF automático de orçamento reprovado da O.S. %s.", self.num_oc)
            messagebox.showinfo("FRS", "Orçamento marcado como REPROVADO e histórico preservado.", parent=self)

    def pesquisar_orcamento(self):
        try:
            from gestao_os import FrmGestaoOrcamentos
            parent = self.master
            self.destroy()
            janela = FrmGestaoOrcamentos(parent, on_os_update_callback=self.on_save_callback)
            try:
                setattr(parent, "_janela_gestao_os", janela)
            except Exception:
                pass
            janela.focus_force()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir a pesquisa de O.S.: {e}", parent=self)

    def salvar_entrada(self):
        cliente = self.txt_cliente.get().strip().upper()
        telefone = self.txt_fone.get().strip()
        telefone_normalizado = self._normalizar_telefone_whatsapp(telefone)
        inicio = time.perf_counter()

        self._auditar_salvar_entrada("inicio")

        if not cliente or not telefone:
            messagebox.showwarning("Atenção", "Informe nome e telefone/WhatsApp do cliente.", parent=self)
            self._auditar_salvar_entrada("validacao_falhou", motivo="cliente_ou_telefone_ausente")
            return
        if not telefone_normalizado:
            messagebox.showwarning("Atenção", "Telefone inválido para salvar entrada.", parent=self)
            self._auditar_salvar_entrada("validacao_falhou", motivo="telefone_invalido")
            return
        if not self._entrada_tem_equipamento():
            messagebox.showwarning("Atenção", "Informe ao menos equipamento/defeito antes de salvar entrada.", parent=self)
            self._auditar_salvar_entrada("validacao_falhou", motivo="equipamento_ausente")
            return
        if self._salvando_documento:
            self._auditar_salvar_entrada("ignorado", motivo="salvamento_em_andamento")
            return

        self.txt_fone.delete(0, 'end')
        self.txt_fone.insert(0, telefone_normalizado)

        self._alternar_estado_botao_salvar(True)
        try:
            numero_salvo = self.num_oc
            dados_salvos = self.salvar_documento(status="AGUARDANDO")
            if not dados_salvos:
                self._auditar_salvar_entrada("falha", motivo="salvar_documento_retornou_vazio")
                return

            duracao = round(time.perf_counter() - inicio, 3)
            self._auditar_salvar_entrada(
                "sucesso",
                duracao_seg=duracao,
                telefone_salvo=str(dados_salvos.get("telefone_cliente_whatsapp", "") or ""),
                equipamento=str(dados_salvos.get("equipamento", "") or ""),
                defeito=str(dados_salvos.get("defeito", "") or ""),
            )
            if self._orcamento_em_edicao:
                self._salvar_equipamento_ativo()
                self._atualizar_lista_equipamentos_ui()
                self.atualizar_total()
                messagebox.showinfo("Atualização", f"Orçamento/O.S. {numero_salvo} atualizado com sucesso.", parent=self)
            else:
                self._orcamento_em_edicao = True
                self._atualizar_rotulo_botao_salvar()
                self._restaurar_formulario_pos_salvamento()
                messagebox.showinfo("Entrada", f"Entrada da O.S. {numero_salvo} salva com sucesso.", parent=self)
        except Exception as e:
            self._auditar_salvar_entrada("erro", erro=str(e))
            messagebox.showerror("Erro", str(e), parent=self)
        finally:
            self._alternar_estado_botao_salvar(False)

    def salvar_os_rapido(self):
        # Alias de compatibilidade para fluxos antigos.
        self.salvar_entrada()

    def abrir_estoque(self):
        try:
            from menu import FrmProdutos
            FrmProdutos(self)
        except Exception as e: messagebox.showerror("Erro", f"Erro: {e}")

    def finalizar_e_abrir_pdf(self):
        cliente = self.txt_cliente.get().strip().upper()
        telefone = self.txt_fone.get().strip()
        if not cliente or not telefone:
            messagebox.showwarning("Atenção", "Informe nome e telefone/WhatsApp antes de gerar o documento.", parent=self)
            return
        if self._gerando_orcamento:
            return
        self._gerando_orcamento = True
        if hasattr(self, 'btn_pdf'):
            self.btn_pdf.configure(state="disabled")
        try:
            self.salvar_documento(status="AGUARDANDO")
            caminho_pdf = self.gerar_documento_pdf(self.tipo_documento)
            if caminho_pdf:
                self._oferecer_envio_whatsapp(caminho_pdf, self.tipo_documento)
        except Exception as e:
            messagebox.showerror("Erro", str(e), parent=self)
        finally:
            self._gerando_orcamento = False
            if hasattr(self, 'btn_pdf'):
                self.btn_pdf.configure(state="normal")

    def gerar_pdf_fiel(self, caminho, tipo_documento=None, condicao_pagamento=None):
        c = canvas.Canvas(caminho, pagesize=A4)
        largura, altura = A4
        data_atual = datetime.now().strftime("%d/%m/%Y")
        tipo = tipo_documento or self.tipo_documento or "ORÇAMENTO"
        eh_os = tipo == "ORDEM DE SERVIÇO"
        cor_banner = (0.15, 0.55, 0.32) if eh_os else (0.90, 0.48, 0.13)
        titulo_secundario = "DOCUMENTO DE ENTRADA E EXECUÇÃO" if eh_os else "PROPOSTA COMERCIAL PARA APROVAÇÃO"

        # --- IMAGENS NO TOPO (configuráveis) ---
        try:
            def _resolver_logo_absoluta(caminho_logo, padroes=None):
                bruto = str(caminho_logo or "").strip().strip('"')
                base_dir = os.path.dirname(os.path.abspath(__file__))
                candidatos = []
                if bruto:
                    if os.path.isabs(bruto):
                        candidatos.append(os.path.abspath(bruto))
                    else:
                        candidatos.extend(
                            [
                                os.path.abspath(bruto),
                                os.path.abspath(os.path.join(DIRETORIO_RECURSOS, bruto)),
                                os.path.abspath(os.path.join(base_dir, bruto)),
                                os.path.abspath(os.path.join(base_dir, "assets", bruto)),
                                os.path.abspath(os.path.join(base_dir, "static", bruto)),
                            ]
                        )

                    nome_arquivo = os.path.basename(bruto)
                    if nome_arquivo:
                        candidatos.extend(
                            [
                                os.path.abspath(os.path.join(base_dir, nome_arquivo)),
                                os.path.abspath(os.path.join(base_dir, "assets", nome_arquivo)),
                                os.path.abspath(os.path.join(base_dir, "static", nome_arquivo)),
                            ]
                        )

                for nome_padrao in (padroes or []):
                    candidatos.extend(
                        [
                            os.path.abspath(os.path.join(base_dir, nome_padrao)),
                            os.path.abspath(os.path.join(base_dir, "assets", nome_padrao)),
                            os.path.abspath(os.path.join(base_dir, "static", nome_padrao)),
                        ]
                    )

                for cand in candidatos:
                    if os.path.exists(cand):
                        return cand
                return ""

            logo_path = _resolver_logo_absoluta(self.logo_oficina, padroes=["LOGO.bmp", "logo.png", "logo.jpg", "logo.jpeg", "logo.webp"])
            patr_path = _resolver_logo_absoluta(self.logo_patrocinador, padroes=["logo.png", "LOGO.bmp"])
            if os.path.exists(logo_path):
                c.drawImage(logo_path, 45, altura - 88, width=145, height=72, preserveAspectRatio=True, mask='auto')
            if not patr_path and os.path.exists(logo_path):
                patr_path = logo_path
            if os.path.exists(patr_path):
                c.drawImage(patr_path, largura - 170, altura - 82, width=120, height=60, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass  # Se a imagem não existir, continua sem ela

        # --- CABEÇALHO ---
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, altura - 102, (self.nome_oficina or "OFICINA").upper())
        c.setFont("Helvetica", 10)
        c.drawString(50, altura - 117, self.telefone_oficina)
        c.drawString(50, altura - 132, self.endereco_oficina.upper())

        c.saveState()
        if eh_os:
            c.setFillColorRGB(0.84, 0.92, 0.87)
        elif str(tipo).upper() == "ORÇAMENTO REPROVADO":
            c.setFillColorRGB(0.98, 0.85, 0.85)
        else:
            c.setFillColorRGB(0.98, 0.91, 0.84)
        c.setFont("Helvetica-Bold", 52)
        c.translate(largura / 2, altura / 2)
        c.rotate(35)
        if eh_os:
            marca = "ORDEM DE SERVIÇO"
        elif str(tipo).upper() == "ORÇAMENTO REPROVADO":
            marca = "REPROVADO"
        else:
            marca = "ORÇAMENTO"
        c.drawCentredString(0, 0, marca)
        c.restoreState()

        # Número do Documento à Direita
        c.setFillColorRGB(*cor_banner)
        c.setFont("Helvetica-Bold", 14)
        c.drawRightString(largura - 50, altura - 128, tipo)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 24)
        c.drawRightString(largura - 50, altura - 148, str(self.num_oc))
        c.setFont("Helvetica-Oblique", 8.8)
        c.drawRightString(largura - 50, altura - 178, titulo_secundario)
        
        c.setLineWidth(1.2)
        c.setStrokeColorRGB(*cor_banner)
        c.line(50, altura - 166, largura - 50, altura - 166)
        c.setStrokeColorRGB(0, 0, 0)

        # --- DADOS DO CLIENTE E EQUIPAMENTOS CONSOLIDADOS ---
        self._salvar_equipamento_ativo()

        equipamentos_pdf = []
        for eq in (self.os_equipamentos or []):
            if not isinstance(eq, dict):
                continue
            itens_eq = []
            for it in (eq.get("itens") or []):
                if not isinstance(it, (list, tuple)) or len(it) < 3:
                    continue
                qtd_item = self._parse_valor(it[1], default=0.0)
                unit_item = self._parse_valor(it[2], default=0.0)
                total_item = float(qtd_item) * float(unit_item)
                status_item = self._normalizar_status_item(it[4] if len(it) > 4 else "ATIVO")
                itens_eq.append([str(it[0]), str(it[1]), f"{unit_item:.2f}", f"{total_item:.2f}", status_item])
            if not (eq.get("equipamento") or eq.get("defeito") or itens_eq):
                continue
            subtotal_itens = sum(
                self._parse_valor(item[3])
                for item in itens_eq
                if self._normalizar_status_item(item[4] if len(item) > 4 else "ATIVO") != "REPROVADO"
            )
            v_opc_eq = self._parse_valor(eq.get("opcional", 0))
            v_fre_eq = self._parse_valor(eq.get("frete", 0))
            v_desc_eq = self._parse_valor(eq.get("desconto", 0))
            equipamentos_pdf.append(
                {
                    "equipamento": str(eq.get("equipamento", "")).upper(),
                    "defeito": str(eq.get("defeito", "")).upper(),
                    "itens": itens_eq,
                    "subtotal_itens": subtotal_itens,
                    "opcional": v_opc_eq,
                    "frete": v_fre_eq,
                    "desconto": v_desc_eq,
                    "total": (subtotal_itens + v_opc_eq + v_fre_eq) - v_desc_eq,
                    "prazo": str(eq.get("prazo", "") or "").strip(),
                    "obs": str(eq.get("obs", "") or "").strip(),
                }
            )

        if not equipamentos_pdf:
            itens_atuais = [self.tab.item(i).get('values', []) for i in self.tab.get_children()]
            itens_legados = [
                [
                    str(v[0]),
                    str(v[1]),
                    f"{self._parse_valor(v[2], default=0.0):.2f}",
                    f"{(self._parse_valor(v[1], default=0.0) * self._parse_valor(v[2], default=0.0)):.2f}",
                    self._normalizar_status_item(v[4] if len(v) > 4 else "ATIVO"),
                ]
                for v in itens_atuais
                if isinstance(v, (list, tuple)) and len(v) >= 4
            ]
            subtotal_itens = sum(
                self._parse_valor(item[3])
                for item in itens_legados
                if self._normalizar_status_item(item[4] if len(item) > 4 else "ATIVO") != "REPROVADO"
            )
            v_opc_eq = self._parse_valor(self.ent_opcional.get())
            v_fre_eq = self._parse_valor(self.ent_frete.get())
            v_desc_eq = self._parse_valor(self.ent_desc.get())
            equipamentos_pdf.append(
                {
                    "equipamento": self.txt_equip.get().upper(),
                    "defeito": self.txt_defeito.get().upper(),
                    "itens": itens_legados,
                    "subtotal_itens": subtotal_itens,
                    "opcional": v_opc_eq,
                    "frete": v_fre_eq,
                    "desconto": v_desc_eq,
                    "total": (subtotal_itens + v_opc_eq + v_fre_eq) - v_desc_eq,
                    "prazo": self.txt_prazo.get().strip(),
                    "obs": self.txt_obs.get("1.0", "end-1c").strip(),
                }
            )

        soma_itens = sum(eq["subtotal_itens"] for eq in equipamentos_pdf)
        v_opc = sum(eq["opcional"] for eq in equipamentos_pdf)
        v_fre = sum(eq["frete"] for eq in equipamentos_pdf)
        v_desc = sum(eq["desconto"] for eq in equipamentos_pdf)
        total_geral = (soma_itens + v_opc + v_fre) - v_desc

        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, altura - 182, f"DATA: {data_atual}")
        c.drawString(50, altura - 197, f"CLIENTE: {self.txt_cliente.get().upper()}")
        c.drawString(50, altura - 212, f"TELEFONE/WHATSAPP: {self.txt_fone.get()}")
        c.drawString(50, altura - 227, f"EQUIPAMENTOS NA O.S.: {len(equipamentos_pdf)}")

        c.line(50, altura - 237, largura - 50, altura - 237)

        # --- CHECKLIST DE ENTRADA ---
        y_header = altura - 252
        txt_acompanha = f"ACOMPANHA:  Capa: {self.check_capa.get()}  |  Linha: {self.check_linha.get()}  |  Manivela: {self.check_manivela.get()}  |  Caixa: {self.check_caixa.get()}"
        c.setFont("Helvetica-Bold", 9)
        c.drawString(50, y_header, txt_acompanha)
        y_header -= 10
        c.setLineWidth(1)
        c.line(50, y_header, largura - 50, y_header)

        # --- TABELA DE ITENS POR EQUIPAMENTO ---
        y = y_header - 20
        item_global = 1

        for idx_eq, eq in enumerate(equipamentos_pdf, start=1):
            if y < 170:
                c.showPage()
                y = altura - 50

            c.setFillColorRGB(0.93, 0.95, 0.98)
            c.rect(50, y - 12, largura - 100, 16, stroke=0, fill=1)
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(55, y - 2, f"EQUIPAMENTO {idx_eq}: {eq['equipamento'] or '-'}")
            y -= 16

            c.setFont("Helvetica-Oblique", 9)
            defeito_linhas = _quebrar_linha(c, f"DEFEITO: {eq['defeito'] or '-'}", largura - 110, "Helvetica-Oblique", 9)
            for ln in defeito_linhas:
                c.drawString(55, y, ln)
                y -= 11

            c.setFont("Helvetica-Bold", 9)
            c.drawString(55, y, "ITEM")
            c.drawString(90, y, "DESCRIÇÃO DOS SERVIÇOS / PEÇAS")
            c.drawString(350, y, "QTD")
            c.drawString(410, y, "V. UNIT")
            c.drawRightString(largura - 55, y, "V. TOTAL")
            y -= 4
            c.line(50, y, largura - 50, y)
            y -= 14
            c.setFont("Helvetica", 9)

            if not eq["itens"]:
                c.drawString(90, y, "Sem peças/serviços lançados para este equipamento.")
                y -= 14
            else:
                for item in eq["itens"]:
                    if y < 150:
                        c.showPage()
                        y = altura - 50
                        c.setFont("Helvetica-Bold", 9)
                        c.drawString(55, y, f"EQUIPAMENTO {idx_eq} (continuação)")
                        y -= 12
                        c.drawString(55, y, "ITEM")
                        c.drawString(90, y, "DESCRIÇÃO DOS SERVIÇOS / PEÇAS")
                        c.drawString(350, y, "QTD")
                        c.drawString(410, y, "V. UNIT")
                        c.drawRightString(largura - 55, y, "V. TOTAL")
                        y -= 4
                        c.line(50, y, largura - 50, y)
                        y -= 14
                        c.setFont("Helvetica", 9)
                    desc_linhas = _quebrar_linha(c, str(item[0]), 255, "Helvetica", 9)
                    status_item = self._normalizar_status_item(item[4] if len(item) > 4 else "ATIVO")
                    c.drawString(55, y, str(item_global))
                    if status_item == "REPROVADO":
                        c.setFillColorRGB(0.74, 0.12, 0.12)
                    c.drawString(90, y, desc_linhas[0])
                    for dl in desc_linhas[1:]:
                        y -= 11
                        c.drawString(90, y, dl)
                    c.drawString(350, y, str(item[1]))
                    c.drawString(410, y, formatar_monetario(item[2]))
                    valor_total_item = self._parse_valor(item[1], default=0.0) * self._parse_valor(item[2], default=0.0)
                    if status_item == "REPROVADO":
                        c.drawRightString(largura - 55, y, "REPROVADO")
                        c.setFillColorRGB(0, 0, 0)
                    else:
                        c.drawRightString(largura - 55, y, formatar_monetario(valor_total_item))
                    c.setDash(1, 2)
                    c.setLineWidth(0.5)
                    c.line(50, y - 4, largura - 50, y - 4)
                    c.setDash([])
                    y -= 16
                    item_global += 1

            c.setFont("Helvetica-Bold", 9)
            c.drawRightString(largura - 150, y, f"SUBTOTAL EQUIP. {idx_eq}:")
            c.drawRightString(largura - 55, y, formatar_monetario(eq["total"]))
            y -= 18

        # --- RESUMO FINANCEIRO ---
        y_fin = y - 8
        if y_fin < 180:
            c.showPage()
            y_fin = altura - 100

        c.setLineWidth(1)
        c.line(largura - 250, y_fin + 15, largura - 50, y_fin + 15)

        c.setFont("Helvetica", 10)
        financeiro = [
            ("SUBTOTAL ITENS:", soma_itens),
            ("OPCIONAL:", v_opc),
            ("FRETE:", v_fre),
            ("DESCONTO:", -v_desc),
            ("TOTAL GERAL:", total_geral),
        ]

        for i, (label, valor) in enumerate(financeiro):
            c.drawRightString(largura - 150, y_fin, label)
            c.drawRightString(largura - 55, y_fin, formatar_monetario(valor))
            if i < len(financeiro) - 1:
                y_fin -= 15

        y_fin -= 20

        forma_pagamento = self._normalizar_forma_pagamento(condicao_pagamento) if eh_os else None
        prazos_unicos = [p for p in dict.fromkeys([str(eq.get("prazo", "")).strip() for eq in equipamentos_pdf]) if p]
        prazo_documento = "Conforme itens" if len(prazos_unicos) > 1 else (prazos_unicos[0] if prazos_unicos else self.txt_prazo.get().strip())

        # --- INFORMAÇÕES DE PAGAMENTO ---
        y_pag = y_fin - 40
        c.setFont("Helvetica-Bold", 10)
        if eh_os:
            c.drawString(50, y_pag, "CONDIÇÕES DA ORDEM DE SERVIÇO:")
            c.setFont("Helvetica", 9)
            
            if forma_pagamento == "100%_total":
                c.drawString(50, y_pag - 15, f"VALOR TOTAL: {formatar_monetario(total_geral)}")
                c.drawString(50, y_pag - 30, "STATUS: PAGO")
                c.drawRightString(largura - 50, y_pag - 15, "PRAZO:")
                c.setFont("Helvetica-Bold", 10)
                c.drawRightString(largura - 50, y_pag - 30, prazo_documento)
            elif forma_pagamento == "100%_entrega":
                c.drawString(50, y_pag - 15, f"VALOR TOTAL: {formatar_monetario(total_geral)}")
                c.drawString(50, y_pag - 30, "PAGAMENTO TOTAL NA ENTREGA")
                c.drawRightString(largura - 50, y_pag - 15, "PRAZO:")
                c.setFont("Helvetica-Bold", 10)
                c.drawRightString(largura - 50, y_pag - 30, prazo_documento)
            else:
                valor_sinal = OSCalculator.calcular_sinal_por_forma(total_geral, forma_pagamento)
                c.drawString(50, y_pag - 15, f"SINAL RECEBIDO: {formatar_monetario(valor_sinal)}")
                c.drawString(50, y_pag - 30, f"SALDO RESTANTE: {formatar_monetario(total_geral - valor_sinal)}")
                c.drawRightString(largura - 50, y_pag - 15, "PRAZO:")
                c.setFont("Helvetica-Bold", 10)
                c.drawRightString(largura - 50, y_pag - 30, prazo_documento)

            # Reserva espaço vertical para evitar sobreposição com o bloco de termos.
            y_pag -= ESPACO_ENTRE_CONDICOES_E_TERMOS_OS
        else:
            blocos_obs = []
            for i, eq in enumerate(equipamentos_pdf, start=1):
                obs_eq = str(eq.get("obs", "")).strip()
                if obs_eq:
                    blocos_obs.append(f"Equip. {i} ({eq.get('equipamento') or '-'}): {obs_eq}")
            obs_texto = " | ".join(blocos_obs) if blocos_obs else self.txt_obs.get("1.0", "end-1c").strip()
            prazo_texto = prazo_documento
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y_pag + 15, "OBSERVAÇÃO:")
            c.setFont("Helvetica", 9)
            obs_linhas = _quebrar_linha(c, obs_texto, largura - 230, "Helvetica", 9)
            y_obs = y_pag
            for ln in obs_linhas:
                c.drawString(50, y_obs, ln)
                y_obs -= 12
            c.drawRightString(largura - 50, y_pag + 15, "PRAZO:")
            c.setFont("Helvetica-Bold", 10)
            c.drawRightString(largura - 50, y_pag, prazo_texto)
            y_pag = min(y_obs, y_pag - 20)

        # --- TERMOS E RODAPÉ ---
        if eh_os:
            termos = [
                "1. GARANTIA: 90 dias conforme Art. 26 do CDC para serviços e peças substituídas.",
                "2. MAU USO: A garantia não cobre danos por quedas, humidade ou abertura por terceiros.",
                "3. ABANDONO: Equipamentos não retirados em 90 dias serão vendidos para custear despesas.",
                "4. PAGAMENTO: Aceitamos Cartões de Crédito/Débito (Taxas da operadora por conta do cliente)."
            ]
        else:
            termos = [
                "1. VALIDADE: Este orçamento pode ser revisto caso haja alteração de peças ou serviços necessários.",
                "2. APROVAÇÃO: A execução do serviço começa após confirmação do cliente.",
                "3. ABANDONO: Equipamentos não retirados em 90 dias serão vendidos para custear despesas.",
                "4. GARANTIA: 90 dias conforme Art. 26 do CDC após aprovação e execução do serviço.",
            ]

        altura_termos = 14 + (len(termos) * 10)
        altura_assinaturas = 56
        altura_rodape = 56
        margem_minima = 24
        espaco_necessario = altura_termos + altura_assinaturas + altura_rodape + margem_minima

        if y_pag < espaco_necessario:
            c.showPage()
            y_pag = altura - 120
            c.setFont("Helvetica-Bold", 9)
            c.drawString(50, y_pag + 14, "CONTINUAÇÃO - TERMOS E ASSINATURAS")

        y_termo = y_pag - 20
        c.setFont("Helvetica-Bold", 9)
        c.drawString(50, y_termo, "TERMO DE GARANTIA E CONDIÇÕES:" if eh_os else "TERMOS GERAIS:")
        c.setFont("Helvetica", 7.5)
        for linha in termos:
            y_termo -= 10
            c.drawString(50, y_termo, linha)

        y_ass = max(92, y_termo - 42)
        c.setLineWidth(1)
        c.line(70, y_ass, 240, y_ass)
        c.line(largura - 240, y_ass, largura - 70, y_ass)
        c.setFont("Helvetica", 8)
        c.drawCentredString(155, y_ass - 12, "ASSINATURA DO CLIENTE")
        c.drawCentredString(largura - 155, y_ass - 12, "ASSINATURA DA OFICINA")

        c.setFont("Helvetica-BoldOblique", 8)
        rodape = "ORDEM DE SERVIÇO GERADA E AUTORIZADA PARA EXECUÇÃO." if eh_os else "ORÇAMENTO SUJEITO À APROVAÇÃO DO CLIENTE."
        c.drawCentredString(largura/2, 42, rodape)
        c.drawCentredString(largura/2, 30, "OBRIGADO PELA PREFERÊNCIA! A SUA CONFIANÇA É A NOSSA MELHOR ISCA.")
        
        c.save()


if __name__ == "__main__":
    try:
        # MODO SEGURANCA: sem inicializacao de banco neste arquivo de teste.
        app = ctk.CTk()
        app.withdraw()
        janela_teste = FrmOS(app)
        janela_teste.update_idletasks()
        try:
            janela_teste.attributes('-toolwindow', True)
        except Exception:
            pass
        print('INICIANDO INTERFACE', flush=True)
        print('ENTROU NO MAINLOOP', flush=True)
        app.mainloop()
        print('SAIU DO MAINLOOP', flush=True)
        print('INTERFACE FECHADA', flush=True)
    except Exception as e:
        print(e, flush=True)