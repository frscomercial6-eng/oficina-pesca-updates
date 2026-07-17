# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import re
APK_DOWNLOAD_URL = "https://github.com/frs-oficinadepesca/oficinadepesca/releases/latest/download/OficinaPesca.apk"

# O botão deve ser criado dentro de um método de classe, por exemplo, no __init__ de um Frame/Janela:
# Exemplo:
# class FrmMenu(ctk.CTkFrame):
#     def __init__(self, ...):
#         ...
#         ctk.CTkButton(self, text="📱 Baixar App Celular (APK)", fg_color="#27ae60", font=("Arial", 13, "bold"), command=lambda: webbrowser.open(APK_DOWNLOAD_URL)).pack(pady=(0, 10))
import requests
# Função para checar status do Firebase
def checar_status_firebase():
    try:
        resp = requests.get("https://oficinapescasystem-default-rtdb.firebaseio.com/.json", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False
import tela_os
import firebase_admin
from firebase_admin import credentials
import customtkinter as ctk
import sqlite3
import os
import sys
import shutil
import zipfile
import webbrowser
import socket
import json
import threading
import configparser
import traceback

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from util_recibo import gerar_recibo_entrega
from version_info import VERSION
from config import (
    CAMINHO_BANCO,
    APP_VERSION,
)

# Importação do PIL para garantir que Image e ImageTk estejam definidos
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

# --- Funções auxiliares para resolver caminhos de recursos em ambiente PyInstaller ---
def _base_runtime_dir() -> str:
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

def _resource_base_dir() -> str:
    return getattr(sys, "_MEIPASS", _base_runtime_dir())

def _resolver_recurso(*partes: str) -> str:
    return os.path.join(_resource_base_dir(), *partes)


def _resolver_recurso_existente(*partes: str) -> str:
    if len(partes) == 1 and os.path.isabs(str(partes[0])):
        return str(partes[0])

    candidatos = [
        os.path.join(_base_runtime_dir(), *partes),
        os.path.join(_resource_base_dir(), *partes),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), *partes),
        os.path.join(DIRETORIO_RECURSOS, *partes),
        os.path.join(os.getcwd(), *partes),
    ]
    for caminho in candidatos:
        try:
            if os.path.exists(caminho):
                return caminho
        except Exception:
            continue
    return candidatos[0]
# --- Fim das funções auxiliares ---

from config import (
    inicializar_banco,
    get_db_connection,
    hash_password,
    validate_password,
    DIRETORIO_RECURSOS,
    get_logger,
    SERVIDOR_URL,
    obter_email_backup_nuvem,
    salvar_email_backup_nuvem,
    enviar_backup_nuvem,
    iniciar_sincronizacao_automatica_nuvem,
    dados_oficina_sao_padrao,
    obter_status_licenca,
    obter_status_trial,
    obter_status_acesso_centralizado,
    obter_tipo_licenca,
    obter_chave_instalacao,
    ativar_licenca,
    diagnosticar_chave_licenca,
    publicar_licenca_drive,
    obter_modo_operacao,
    URL_APP_CELULAR_PUBLICA,
    WHATSAPP_ADMIN_DESTINO,
    obter_info_nova_versao,
    sincronizar_dados_da_nuvem,
    conectar_google_drive_usuario,
    google_drive_usuario_conectado,
    garantir_banco_no_drive_usuario,
    enviar_backup_banco_para_drive_usuario,
    listar_backups_banco_drive_usuario,
    restaurar_backup_banco_drive_usuario,
    iniciar_sincronizacao_hibrida_nuvem,
    renovar_token_acesso_drive_se_necessario,
    eh_versao_mais_nova,
    executar_atualizacao,
    listar_os_rejeitados_abandono_dashboard,
    obter_firebase_web_config,
)
from reforma_tributaria import garantir_estrutura_reforma_tributaria
from core.modulos import obter_modulos_habilitados
from shutdown_utils import fechar_sistema
from status_os import STATUS_AGUARDANDO_ORCAMENTO, STATUS_ORCAMENTO
from configuracao_fiscal import ConfiguracaoFiscal, carregar_configuracao_fiscal, salvar_configuracao_fiscal, inicializar_motor_fiscal, verificar_status_motor_fiscal

logger = get_logger(__name__)
STATUS_ORCAMENTO_SQL = f"('{STATUS_ORCAMENTO}')"
STATUS_AGUARDANDO_ORCAMENTO_SQL = f"('{STATUS_AGUARDANDO_ORCAMENTO}')"


def _patch_ctklabel_destroy_safely():
    """Workaround global para bug de _font ausente no destroy de CTkLabel."""
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
                # Evita cascata de erro durante fechamento de janela parcialmente inicializada.
                try:
                    tk.Label.destroy(widget)
                except Exception:
                    pass

        ctk.CTkLabel.destroy = safe_destroy
        ctk.CTkLabel._ofp_safe_destroy_patched = True
    except Exception:
        pass


_patch_ctklabel_destroy_safely()

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

# 2º: CRIA A FUNÇÃO
def verificar_e_criar_tabelas():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS produtos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    preco_custo REAL DEFAULT 0,
                    preco_venda REAL DEFAULT 0,
                    estoque INTEGER DEFAULT 0,
                    ncm VARCHAR(8),
                    compatibilidade TEXT,
                    quantidade_minima INTEGER DEFAULT 3
                )
            """)
            garantir_estrutura_reforma_tributaria(cursor)
            # Não altera schema existente do cliente em runtime.
            # Apenas garante criação inicial quando não há tabela.
            conn.commit()
        logger.info("Tabelas verificadas e prontas.")
    except Exception as e:
        logger.exception("Erro ao criar tabelas de produtos: %s", e)

# 3º: CHAMA A FUNÇÃO
verificar_e_criar_tabelas()


def _obter_info_licenca_visual(role: str = "") -> tuple[str, str]:
    """Retorna texto e cor padronizados para exibição de licença na UI."""
    try:
        status = obter_status_acesso_centralizado() or {}
        licenca_ativa = bool(status.get("licenca_ativa"))
        trial_ativo = bool(status.get("trial_ativo"))
        validade = str(status.get("validade") or "").strip().upper()

        if trial_ativo:
            tipo_exibicao = "Trial"
            cor = "#f1c40f"
        elif licenca_ativa:
            tipo_exibicao = "Permanente" if validade == "PERMANENTE" else "Mensal"
            cor = "#2ecc71"
        else:
            tipo = str(obter_tipo_licenca() or "").strip().upper()
            if tipo == "TRIAL":
                tipo_exibicao = "Trial"
                cor = "#f1c40f"
            elif tipo == "PERMANENTE":
                tipo_exibicao = "Permanente"
                cor = "#2ecc71"
            elif tipo in {"MENSAL", "ATIVA", "TOKEN"}:
                tipo_exibicao = "Mensal"
                cor = "#2ecc71"
            else:
                tipo_exibicao = "Inativa"
                cor = "#e74c3c"

        return f"Licença: {tipo_exibicao}", cor
    except Exception:
        return "Licença: indisponível", "#6b7280"

# 4º: SEGUE O RESTO DO CÓDIGO (CLASSES, ETC)
# class FrmProdutos(ctk.CTkToplevel):
# ...
class FrmProdutos(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Estoque e Margem de Lucro")
        self.geometry("1100x700") 
        self._aplicar_maximizacao()
        self.after(120, self._aplicar_maximizacao)
        
        self.update()
        self.attributes('-topmost', True)
        self.focus_force()
        self.after(300, lambda: self.attributes('-topmost', False))
        self.grab_set()

        ctk.CTkLabel(self, text="🛠️ GESTÃO DE ESTOQUE E MARGEM", font=("Arial", 22, "bold")).pack(pady=15)

        f_busca = ctk.CTkFrame(self)
        f_busca.pack(pady=(0, 8), padx=20, fill="x")
        self.ent_busca_estoque = ctk.CTkEntry(
            f_busca,
            placeholder_text="Buscar por Nome, NCM ou Compatibilidade",
            width=420,
        )
        self.ent_busca_estoque.pack(side="left", padx=(8, 8), pady=8, fill="x", expand=True)
        self.ent_busca_estoque.bind("<Return>", lambda _e: self.carregar_dados())
        ctk.CTkButton(
            f_busca,
            text="Buscar",
            fg_color="#2980b9",
            width=120,
            command=self.carregar_dados,
        ).pack(side="left", padx=(0, 8), pady=8)
        
        # --- CAMPOS DE ENTRADA ---
        f_inputs = ctk.CTkFrame(self)
        f_inputs.pack(pady=10, padx=20, fill="x")

        self.ent_nome = ctk.CTkEntry(f_inputs, placeholder_text="Nome do Produto", width=250)
        self.ent_nome.grid(row=0, column=0, padx=5, pady=5)

        self.ent_compat = ctk.CTkEntry(f_inputs, placeholder_text="Compatibilidade", width=170)
        self.ent_compat.grid(row=0, column=1, padx=5, pady=5)

        self.ent_ncm = ctk.CTkEntry(f_inputs, placeholder_text="NCM (8 dígitos)", width=130)
        self.ent_ncm.grid(row=0, column=2, padx=5, pady=5)

        self.ent_custo = ctk.CTkEntry(f_inputs, placeholder_text="R$ Custo", width=90)
        self.ent_custo.grid(row=0, column=3, padx=5, pady=5)

        # NOVO CAMPO: % Margem
        self.ent_margem = ctk.CTkEntry(f_inputs, placeholder_text="% Margem", width=90)
        self.ent_margem.grid(row=0, column=4, padx=5, pady=5)
        # Ao digitar na margem, ele pode calcular a venda automaticamente
        self.ent_margem.bind("<KeyRelease>", self.calcular_venda_por_margem)

        self.ent_venda = ctk.CTkEntry(f_inputs, placeholder_text="R$ Venda", width=90)
        self.ent_venda.grid(row=0, column=5, padx=5, pady=5)

        self.ent_qtd = ctk.CTkEntry(f_inputs, placeholder_text="Qtd", width=60)
        self.ent_qtd.grid(row=0, column=6, padx=5, pady=5)

        self.ent_qtd_min = ctk.CTkEntry(f_inputs, placeholder_text="Qtd Min (3)", width=90)
        self.ent_qtd_min.grid(row=0, column=7, padx=5, pady=5)
        self.ent_qtd_min.insert(0, "3")

        self.btn_reforma = ctk.CTkButton(
            f_inputs,
            text="IBS/CBS",
            fg_color="#566573",
            width=100,
            command=self._alternar_painel_reforma_tributaria,
        )
        self.btn_reforma.grid(row=0, column=8, padx=5)

        # BOTÕES
        ctk.CTkButton(f_inputs, text="Salvar", fg_color="green", width=100, command=self.salvar_produto).grid(row=0, column=9, padx=5)
        ctk.CTkButton(f_inputs, text="Excluir", fg_color="red", width=100, command=self.excluir_produto).grid(row=0, column=10, padx=5)

        self.frame_reforma = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=16)
        self.frame_reforma.pack(fill="x", padx=20, pady=(0, 8))
        self._reforma_visivel = False
        self.frame_reforma.pack_forget()

        ctk.CTkLabel(
            self.frame_reforma,
            text="Reforma Tributária latente - campos opcionais para IBS/CBS",
            font=("Arial", 12, "bold"),
            text_color="#f1c40f",
        ).grid(row=0, column=0, columnspan=6, sticky="w", padx=12, pady=(12, 4))

        self.ent_aliquota_ibs = ctk.CTkEntry(self.frame_reforma, placeholder_text="Aliquota IBS %", width=130)
        self.ent_aliquota_ibs.grid(row=1, column=0, padx=8, pady=8)
        self.ent_aliquota_cbs = ctk.CTkEntry(self.frame_reforma, placeholder_text="Aliquota CBS %", width=130)
        self.ent_aliquota_cbs.grid(row=1, column=1, padx=8, pady=8)
        self.ent_valor_ibs = ctk.CTkEntry(self.frame_reforma, placeholder_text="Valor IBS", width=130)
        self.ent_valor_ibs.grid(row=1, column=2, padx=8, pady=8)
        self.ent_valor_cbs = ctk.CTkEntry(self.frame_reforma, placeholder_text="Valor CBS", width=130)
        self.ent_valor_cbs.grid(row=1, column=3, padx=8, pady=8)
        self.ent_reforma_json = ctk.CTkEntry(self.frame_reforma, placeholder_text="JSON futuro opcional", width=360)
        self.ent_reforma_json.grid(row=1, column=4, padx=8, pady=8, columnspan=2, sticky="ew")

        # --- TABELA ---
        self.tabela = ttk.Treeview(
            self,
            columns=("id", "nome", "custo", "venda", "margem", "qtd", "ncm", "compat", "qtd_min"),
            show="headings",
        )
        self.tabela.heading("id", text="ID")
        self.tabela.heading("nome", text="PRODUTO")
        self.tabela.heading("custo", text="R$ CUSTO")
        self.tabela.heading("venda", text="R$ VENDA")
        self.tabela.heading("margem", text="LUCRO %")
        self.tabela.heading("qtd", text="QTD")
        self.tabela.heading("ncm", text="NCM")
        self.tabela.heading("compat", text="COMPATIBILIDADE")
        self.tabela.heading("qtd_min", text="QTD MIN")
        
        self.tabela.column("id", width=40)
        self.tabela.column("nome", width=250)
        self.tabela.column("margem", width=100, anchor="center")
        self.tabela.column("ncm", width=110, anchor="center")
        self.tabela.column("compat", width=220)
        self.tabela.column("qtd_min", width=90, anchor="center")
        self.tabela.pack(pady=20, padx=20, fill="both", expand=True)

        self.tabela.bind("<Double-1>", self.selecionar_produto)
        self.carregar_dados()

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def destroy(self):
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

    def _aplicar_maximizacao(self):
        try:
            self.state("zoomed")
            return
        except Exception:
            pass
        try:
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

    def calcular_venda_por_margem(self, event):
        """Calcula o preço de venda automaticamente se digitar a margem"""
        try:
            custo = float(self.ent_custo.get().replace(",", "."))
            margem = float(self.ent_margem.get().replace(",", "."))
            if custo > 0:
                venda = custo + (custo * (margem / 100))
                self.ent_venda.delete(0, 'end')
                self.ent_venda.insert(0, f"{venda:.2f}")
        except (ValueError, TypeError):
            # Durante digitação parcial, apenas ignora valores inválidos temporários.
            return

    def _colunas_produtos(self, cursor):
        cursor.execute("PRAGMA table_info(produtos)")
        return {str(row[1] or "").lower() for row in cursor.fetchall()}

    def _alternar_painel_reforma_tributaria(self):
        self._reforma_visivel = not getattr(self, "_reforma_visivel", False)
        if self._reforma_visivel:
            self.frame_reforma.pack(fill="x", padx=20, pady=(0, 8))
        else:
            self.frame_reforma.pack_forget()

    def salvar_produto(self):
        # 1. Pega o nome e remove espaços extras
        nome = self.ent_nome.get().upper().strip()
        
        if not nome:
            messagebox.showwarning("Atenção", "O nome do produto é obrigatório!")
            return

        try:
            # 2. Limpa os valores (troca vírgula por ponto e ignora espaços)
            custo_txt = self.ent_custo.get().replace(",", ".").strip()
            margem_txt = self.ent_margem.get().replace(",", ".").strip()
            venda_txt = self.ent_venda.get().replace(",", ".").strip()
            qtd_txt = self.ent_qtd.get().strip()
            ncm = "".join(ch for ch in self.ent_ncm.get().strip() if ch.isdigit())[:8]
            compat = self.ent_compat.get().strip().upper()
            qtd_min_txt = self.ent_qtd_min.get().strip()
            aliquota_ibs_txt = self.ent_aliquota_ibs.get().strip().replace(",", ".") if hasattr(self, "ent_aliquota_ibs") else ""
            aliquota_cbs_txt = self.ent_aliquota_cbs.get().strip().replace(",", ".") if hasattr(self, "ent_aliquota_cbs") else ""
            valor_ibs_txt = self.ent_valor_ibs.get().strip().replace(",", ".") if hasattr(self, "ent_valor_ibs") else ""
            valor_cbs_txt = self.ent_valor_cbs.get().strip().replace(",", ".") if hasattr(self, "ent_valor_cbs") else ""
            reforma_json = self.ent_reforma_json.get().strip() if hasattr(self, "ent_reforma_json") else ""

            # 3. Se o campo estiver vazio, vira 0.0 (evita o erro de valor inválido)
            c = float(custo_txt) if custo_txt else 0.0
            m = float(margem_txt) if margem_txt else 0.0
            v = float(venda_txt) if venda_txt else 0.0
            q = int(qtd_txt) if qtd_txt else 0
            q_min = int(qtd_min_txt) if qtd_min_txt else 3
            aliq_ibs = float(aliquota_ibs_txt) if aliquota_ibs_txt else 0.0
            aliq_cbs = float(aliquota_cbs_txt) if aliquota_cbs_txt else 0.0
            val_ibs = float(valor_ibs_txt) if valor_ibs_txt else 0.0
            val_cbs = float(valor_cbs_txt) if valor_cbs_txt else 0.0

            # 4. Lógica: Se você digitou a Margem mas não a Venda, ele calcula agora
            if v == 0 and m > 0 and c > 0:
                v = c + (c * (m / 100))

            # 5. Salva no Banco de Dados
            with get_db_connection() as conn:
                cursor = conn.cursor()
                garantir_estrutura_reforma_tributaria(cursor)
                colunas = self._colunas_produtos(cursor)
                campos = ["nome", "preco_custo", "preco_venda", "estoque"]
                valores = [nome, c, v, q]

                if "ncm" in colunas:
                    campos.append("ncm")
                    valores.append(ncm)
                if "compatibilidade" in colunas:
                    campos.append("compatibilidade")
                    valores.append(compat)
                if "quantidade_minima" in colunas:
                    campos.append("quantidade_minima")
                    valores.append(q_min)
                if "aliquota_ibs" in colunas:
                    campos.append("aliquota_ibs")
                    valores.append(aliq_ibs)
                if "aliquota_cbs" in colunas:
                    campos.append("aliquota_cbs")
                    valores.append(aliq_cbs)
                if "valor_ibs" in colunas:
                    campos.append("valor_ibs")
                    valores.append(val_ibs)
                if "valor_cbs" in colunas:
                    campos.append("valor_cbs")
                    valores.append(val_cbs)
                if "reforma_tributaria_json" in colunas:
                    campos.append("reforma_tributaria_json")
                    valores.append(reforma_json or "{}")

                placeholders = ", ".join(["?"] * len(campos))
                cursor.execute(
                    f"INSERT INTO produtos ({', '.join(campos)}) VALUES ({placeholders})",
                    valores,
                )
                conn.commit()
            
            # 6. Atualiza a lista e limpa os campos
            self.carregar_dados()
            for e in [self.ent_nome, self.ent_compat, self.ent_ncm, self.ent_custo, self.ent_margem, self.ent_venda, self.ent_qtd, self.ent_qtd_min, self.ent_aliquota_ibs, self.ent_aliquota_cbs, self.ent_valor_ibs, self.ent_valor_cbs, self.ent_reforma_json]:
                e.delete(0, 'end')
            self.ent_qtd_min.insert(0, "3")
            if getattr(self, "_reforma_visivel", False):
                self._alternar_painel_reforma_tributaria()
            
            messagebox.showinfo("Sucesso", "Produto guardado com sucesso!")

        except ValueError:
            messagebox.showerror("Erro", "Nos campos de Custo, Margem, Venda e Qtd, use apenas números!")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

    def carregar_dados(self):
        for i in self.tabela.get_children(): self.tabela.delete(i)
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                colunas = self._colunas_produtos(cursor)
                tem_ncm = "ncm" in colunas
                tem_compat = "compatibilidade" in colunas
                tem_qmin = "quantidade_minima" in colunas

                select_ncm = "COALESCE(ncm,'')" if tem_ncm else "''"
                select_compat = "COALESCE(compatibilidade,'')" if tem_compat else "''"
                select_qmin = "COALESCE(quantidade_minima, 3)" if tem_qmin else "3"

                termo = ""
                if hasattr(self, "ent_busca_estoque"):
                    termo = str(self.ent_busca_estoque.get() or "").strip().upper()
                if termo:
                    like = f"%{termo}%"
                    filtros = ["UPPER(COALESCE(nome, '')) LIKE ?"]
                    params = [like]
                    if tem_ncm:
                        filtros.append("UPPER(COALESCE(ncm, '')) LIKE ?")
                        params.append(like)
                    if tem_compat:
                        filtros.append("UPPER(COALESCE(compatibilidade, '')) LIKE ?")
                        params.append(like)

                    cursor.execute(
                        f"""
                        SELECT id, nome, preco_custo, preco_venda, estoque,
                               {select_ncm},
                               {select_compat}, {select_qmin}
                        FROM produtos
                        WHERE {' OR '.join(filtros)}
                        ORDER BY nome
                        """,
                        tuple(params),
                    )
                else:
                    cursor.execute(
                        f"""
                        SELECT id, nome, preco_custo, preco_venda, estoque,
                               {select_ncm},
                               {select_compat}, {select_qmin}
                        FROM produtos
                        ORDER BY nome
                        """
                    )
                for linha in cursor.fetchall():
                    id_p, nome, custo, venda, qtd, ncm, compat, qtd_min = linha
                    margem = ((venda - custo) / custo * 100) if custo > 0 else 0
                    self.tabela.insert(
                        "",
                        "end",
                        values=(id_p, nome, f"{custo:.2f}", f"{venda:.2f}", f"{margem:.1f}%", qtd, ncm, compat, qtd_min),
                    )
        except Exception as e:
            logger.exception("Erro ao carregar produtos: %s", e)

    def excluir_produto(self):
        sel = self.tabela.selection()
        if not sel: return
        if messagebox.askyesno("Confirmar", "Excluir produto?"):
            id_p = self.tabela.item(sel[0], "values")[0]
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM produtos WHERE id = ?", (id_p,))
                conn.commit()
            self.carregar_dados()

    def selecionar_produto(self, event):
        selecao = self.tabela.selection()
        if not selecao: return
        item = self.tabela.item(selecao[0], "values")
        if hasattr(self.master, "adicionar_item_ao_orcamento"):
            # Fechamento seguro antes de interagir com a master
            self.update_idletasks()
            self.after(200, lambda: self.destroy())
            # item[1] é o nome, item[3] é o preço de venda
            self.master.adicionar_item_ao_orcamento(item[1], float(item[3]))


class FrmCadastroUsuarios(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Cadastro de Usuários")
        self.geometry("430x500")
        self.resizable(False, False)

        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (430 // 2)
        y = (self.winfo_screenheight() // 2) - (500 // 2)
        self.geometry(f"+{x}+{y}")

        self.lift()
        self.focus_force()
        self.grab_set()

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        form = ctk.CTkFrame(self)
        form.pack(fill="both", expand=True, padx=20, pady=10)

        self.ent_usuario = ctk.CTkEntry(form, placeholder_text="Usuário", width=320, height=40)
        self.ent_usuario.pack(pady=(20, 10))

        self.ent_senha = ctk.CTkEntry(form, placeholder_text="Senha", show="*", width=320, height=40)
        self.ent_senha.pack(pady=10)

        self.ent_confirma = ctk.CTkEntry(form, placeholder_text="Confirmar senha", show="*", width=320, height=40)
        self.ent_confirma.pack(pady=10)

        self.role_var = ctk.StringVar(value="VENDEDOR")
        self.opt_role = ctk.CTkOptionMenu(form, values=["VENDEDOR", "OFICINA", "ADMIN"], variable=self.role_var, width=320)
        self.opt_role.pack(pady=10)

        ctk.CTkLabel(
            form,
            text="Somente usuários ADMIN podem acessar esta tela.",
            text_color="#95a5a6"
        ).pack(pady=(0, 10))

        self.lbl_status = ctk.CTkLabel(form, text="", text_color="red")
        self.lbl_status.pack(pady=(0, 10))

        ctk.CTkButton(form, text="SALVAR USUÁRIO", fg_color="#27ae60", command=self.salvar_usuario, width=320, height=42).pack(pady=(5, 20))

    def destroy(self):
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

    def salvar_usuario(self):
        usuario = self.ent_usuario.get().strip()
        senha = self.ent_senha.get().strip()
        confirma = self.ent_confirma.get().strip()
        role = self.role_var.get().strip().upper() or "VENDEDOR"

        if not usuario or not senha or not confirma:
            self.lbl_status.configure(text="Preencha todos os campos.", text_color="red")
            return

        if senha != confirma:
            self.lbl_status.configure(text="As senhas não coincidem.", text_color="red")
            return

        senha_ok, msg = validate_password(senha)
        if not senha_ok:
            self.lbl_status.configure(text=msg, text_color="red")
            return

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO usuarios (usuario, senha, role) VALUES (?, ?, ?)",
                    (usuario, hash_password(senha), role)
                )
                conn.commit()

            messagebox.showinfo("Sucesso", f"Usuário '{usuario}' criado com perfil {role}.", parent=self)
            
            # Fechamento seguro para evitar erro 'can't delete Tcl command'
            self.destroy()
        except sqlite3.IntegrityError:
            self.lbl_status.configure(text="Usuário já existe.", text_color="red")
        except Exception as e:
            self.lbl_status.configure(text=f"Erro ao salvar: {e}", text_color="red")

# =================================================================
# RELATÓRIO DE DESEMPENHO (ADMIN)
# =================================================================
class FrmRelatorioDesempenho(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("RELATÓRIO DE DESEMPENHO")
        self.geometry("560x720")
        self.resizable(False, True)
        self.configure(fg_color="#0d1117")
        
        self.update()
        self.attributes('-topmost', True)
        self.focus_force()
        self.after(300, lambda: self.attributes('-topmost', False))
        self.update()
        self.grab_set()
        self._aplicar_maximizacao()
        self.after(120, self._aplicar_maximizacao)

        hoje = datetime.now()
        inicio_mes = hoje.replace(day=1)

        # --- Header ---
        header = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=15)
        header.pack(fill="x", padx=20, pady=(20, 5))
        ctk.CTkLabel(
            header, text="📊 RELATÓRIO DE DESEMPENHO",
            font=("Arial", 20, "bold"), text_color="orange"
        ).pack(pady=(15, 8))

        f_periodo = ctk.CTkFrame(header, fg_color="#1f2a38")
        f_periodo.pack(pady=(0, 14))
        ctk.CTkLabel(f_periodo, text="De:", font=("Arial", 12), text_color="#bdc3c7").pack(side="left", padx=(10, 4))
        self.ent_inicio = ctk.CTkEntry(f_periodo, width=105, placeholder_text="01/04/2026")
        self.ent_inicio.insert(0, inicio_mes.strftime("%d/%m/%Y"))
        self.ent_inicio.pack(side="left", padx=4)
        ctk.CTkLabel(f_periodo, text="à", font=("Arial", 12), text_color="#bdc3c7").pack(side="left", padx=4)
        self.ent_fim = ctk.CTkEntry(f_periodo, width=105, placeholder_text="30/04/2026")
        self.ent_fim.insert(0, hoje.strftime("%d/%m/%Y"))
        self.ent_fim.pack(side="left", padx=4)
        ctk.CTkButton(
            f_periodo, text="🔄 ATUALIZAR", fg_color="#2980b9", hover_color="#3498db",
            width=120, command=self.carregar_dados
        ).pack(side="left", padx=(10, 5))

        # --- Área de conteúdo ---
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="#0d1117", corner_radius=0)
        self.scroll.pack(fill="both", expand=True, padx=12, pady=8)

        self.carregar_dados()

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def destroy(self):
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

    def _aplicar_maximizacao(self):
        try:
            self.state("zoomed")
            return
        except Exception:
            pass
        try:
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

    def _parse_data(self, texto):
        try:
            return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
        except Exception:
            return None

    def _secao_titulo(self, texto):
        f = ctk.CTkFrame(self.scroll, fg_color="#1f2a38", corner_radius=10)
        f.pack(fill="x", padx=5, pady=(12, 2))
        ctk.CTkLabel(
            f, text=texto, font=("Arial", 13, "bold"), text_color="orange"
        ).pack(pady=8, padx=15, anchor="w")

    def _card_linha(self, label, valor, cor_valor="#ecf0f1", negrito=False):
        f = ctk.CTkFrame(self.scroll, fg_color="#161f2c", corner_radius=8)
        f.pack(fill="x", padx=5, pady=2)
        ctk.CTkLabel(
            f, text=label, font=("Arial", 12), text_color="#bdc3c7", anchor="w"
        ).pack(side="left", padx=15, pady=9)
        fnt = ("Arial", 12, "bold") if negrito else ("Arial", 12)
        ctk.CTkLabel(
            f, text=valor, font=fnt, text_color=cor_valor, anchor="e"
        ).pack(side="right", padx=15, pady=9)

    def _separador(self):
        f = ctk.CTkFrame(self.scroll, fg_color="#2c3e50", height=2, corner_radius=0)
        f.pack(fill="x", padx=20, pady=4)

    def carregar_dados(self):
        for w in self.scroll.winfo_children():
            w.destroy()

        dt_inicio = self._parse_data(self.ent_inicio.get())
        dt_fim = self._parse_data(self.ent_fim.get())

        if not dt_inicio or not dt_fim:
            ctk.CTkLabel(
                self.scroll, text="⚠  Datas inválidas. Use dd/mm/aaaa.",
                text_color="#ff6b6b", font=("Arial", 12)
            ).pack(pady=20)
            return

        d_ini = dt_inicio.strftime("%Y-%m-%d")
        d_fim = dt_fim.strftime("%Y-%m-%d")

        # Helper para converter data dd/mm/yyyy → yyyy-mm-dd no SQLite
        fmt_data = "date(substr({col},7,4)||'-'||substr({col},4,2)||'-'||substr({col},1,2))"
        data_orc = fmt_data.format(col="data")
        data_cx  = fmt_data.format(col="data")

        try:
            with get_db_connection() as conn:
                cur = conn.cursor()

                # --- OPERACIONAL ---
                cur.execute(
                    f"SELECT COUNT(*) FROM orcamentos_aguardo WHERE {data_orc} BETWEEN ? AND ?",
                    (d_ini, d_fim)
                )
                total_criados = cur.fetchone()[0]

                cur.execute(
                    "SELECT COUNT(*) FROM orcamentos_aguardo WHERE UPPER(status) = 'APROVADO'"
                )
                bancada = cur.fetchone()[0]

                cur.execute(
                    f"SELECT COUNT(*) FROM orcamentos_aguardo WHERE UPPER(COALESCE(status,'')) IN {STATUS_ORCAMENTO_SQL}"
                )
                aguardando = cur.fetchone()[0]

                cur.execute(
                    f"""SELECT COUNT(*) FROM orcamentos_aguardo
                        WHERE UPPER(status) = 'FINALIZADO'
                        AND {data_orc} BETWEEN ? AND ?""",
                    (d_ini, d_fim)
                )
                finalizados = cur.fetchone()[0]

                cur.execute(
                    f"""SELECT COUNT(*) FROM orcamentos_aguardo
                        WHERE UPPER(status) = 'REPROVADO'
                        AND {data_orc} BETWEEN ? AND ?""",
                    (d_ini, d_fim)
                )
                reprovados = cur.fetchone()[0]

                # --- FINANCEIRO ---
                cur.execute(
                    f"""SELECT COALESCE(SUM(valor), 0) FROM fluxo_caixa
                        WHERE UPPER(tipo) = 'ENTRADA'
                        AND {data_cx} BETWEEN ? AND ?""",
                    (d_ini, d_fim)
                )
                total_entradas = float(cur.fetchone()[0] or 0)

                cur.execute(
                    f"""SELECT COALESCE(SUM(valor), 0) FROM fluxo_caixa
                        WHERE UPPER(tipo) IN ('SAÍDA','SAIDA')
                        AND {data_cx} BETWEEN ? AND ?""",
                    (d_ini, d_fim)
                )
                total_saidas = float(cur.fetchone()[0] or 0)

                lucro = total_entradas - total_saidas

                # --- SALDO A RECEBER ---
                cur.execute(
                    "SELECT COALESCE(SUM(saldo), 0) FROM orcamentos_aguardo WHERE UPPER(status) = 'APROVADO'"
                )
                saldo_receber = float(cur.fetchone()[0] or 0)

        except Exception as e:
            ctk.CTkLabel(
                self.scroll, text=f"Erro ao carregar dados:\n{e}",
                text_color="#ff6b6b", wraplength=500
            ).pack(pady=20, padx=20)
            return

        # --- Título do período ---
        ctk.CTkLabel(
            self.scroll,
            text=f"📅  {dt_inicio.strftime('%d/%m/%Y')}  à  {dt_fim.strftime('%d/%m/%Y')}",
            font=("Arial", 13, "bold"), text_color="#64b5f6"
        ).pack(pady=(6, 2), anchor="w", padx=12)

        # --- OPERACIONAL ---
        self._secao_titulo("--- OPERACIONAL ---")
        self._card_linha(
            "Total de Serviços Criados:", str(total_criados),
            "#64b5f6" if total_criados > 0 else "#ecf0f1"
        )
        self._card_linha(
            "Serviços Pendentes (Bancada):", str(bancada),
            "#FFD700" if bancada > 0 else "#ecf0f1"
        )
        self._card_linha(
            "Orçamentos aguardando Aprovação:", str(aguardando),
            "#FFD700" if aguardando > 0 else "#ecf0f1"
        )
        self._card_linha(
            "Finalizados no Período:", str(finalizados),
            "#00e676" if finalizados > 0 else "#ecf0f1"
        )
        self._card_linha(
            "Reprovados no Período:", str(reprovados),
            "#ff6b6b" if reprovados > 0 else "#ecf0f1"
        )

        # --- FINANCEIRO ---
        self._secao_titulo("--- FINANCEIRO (CAIXA) ---")
        self._card_linha(
            "TOTAL DE ENTRADAS:", f"R$ {total_entradas:.2f}",
            "#00e676" if total_entradas > 0 else "#ecf0f1", negrito=True
        )
        self._card_linha(
            "TOTAL DE SAÍDAS (DESPESAS):", f"R$ {total_saidas:.2f}",
            "#ff6b6b" if total_saidas > 0 else "#ecf0f1", negrito=True
        )
        self._separador()
        cor_lucro = "#00e676" if lucro > 0 else ("#ff6b6b" if lucro < 0 else "#ecf0f1")
        self._card_linha("LUCRO REAL (CAIXA):", f"R$ {lucro:.2f}", cor_lucro, negrito=True)

        # --- PREVISÃO ---
        self._secao_titulo("--- PREVISÃO DE RECEBIMENTO ---")
        self._card_linha(
            "SALDO A RECEBER (OS ABERTAS):", f"R$ {saldo_receber:.2f}",
            "#FFD700" if saldo_receber > 0 else "#ecf0f1", negrito=True
        )


class FrmDadosOficina(ctk.CTkToplevel):
    def _revert_withdraw_after_windows_set_titlebar_color(self):
        """Workaround para callback interno do CustomTkinter em alguns ambientes Windows/Python 3.14."""
        try:
            if self.winfo_exists():
                self.deiconify()
        except Exception:
            pass

    def inicializar_firebase(self):
        """
        Inicializa o Firebase Admin SDK com as credenciais e URL do Realtime Database.
        """
        import os
        try:
            cred_path = _resolver_recurso('google-services.json') # Padronizado para google-services.json
            db_url = str((obter_firebase_web_config() or {}).get('databaseURL') or '').strip()
            if not db_url:
                return
            if not firebase_admin._apps:
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': db_url
                })
        except Exception as e:
            print(f"Erro ao inicializar Firebase: {e}")
            # Não interrompe o fluxo caso falhe

    def __init__(self, master):
        super().__init__(master)
        self._encerrando_aplicacao = False
        self._status_motor_fiscal_ativo = None
        self.title("Dados da Oficina")
        self.geometry("980x760")
        self.resizable(True, True)
        self.grab_set()
        self.update()
        self.attributes('-topmost', True) #
        self.focus_force()
        self.after(300, lambda: self.attributes('-topmost', False))
        self.janela_dados_oficina_aberta = True # Flag para controle de duplicidade
        ctk.CTkLabel(self, text="🏪 DADOS DA OFICINA", font=("Arial", 22, "bold"), text_color="orange").pack(pady=(16, 6))

        container = ctk.CTkScrollableFrame(self, fg_color="#1f2a38", corner_radius=12)
        self.update_idletasks()
        container.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        form = container
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

        linha = 0

        def _lbl(txt):
            nonlocal linha
            ctk.CTkLabel(form, text=txt, anchor="w", text_color="orange", font=("Arial", 12, "bold")).grid(
                row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(6, 2)
            )
            linha += 1

        def _entry(attr, placeholder):
            nonlocal linha
            ent = ctk.CTkEntry(
                form,
                placeholder_text=placeholder,
                height=34,
                fg_color="#f8fafc",
                border_width=2,
                border_color="#1d4ed8",
                text_color="#0f1720",
                placeholder_text_color="#64748b",
            )
            ent.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))
            setattr(self, attr, ent)
            linha += 1

        _lbl("Nome da oficina")
        _entry("ent_nome", "Nome da oficina")
        _lbl("CNPJ da oficina")
        _entry("ent_cnpj", "00.000.000/0000-00")
        _lbl("Endereço da oficina")
        _entry("ent_endereco", "Endereço da oficina")
        _lbl("Telefone")
        _entry("ent_telefone", "Telefone")
        _lbl("Chave PIX")
        _entry("ent_pix", "Chave PIX")

        _lbl("Logo da oficina (usado no PDF)")
        f_logo = ctk.CTkFrame(form, fg_color="transparent")
        f_logo.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))
        f_logo.grid_columnconfigure(0, weight=1)
        self.ent_logo = ctk.CTkEntry(
            f_logo,
            placeholder_text="Caminho do logo da oficina",
            height=34,
            fg_color="#f8fafc",
            border_width=2,
            border_color="#1d4ed8",
            text_color="#0f1720",
            placeholder_text_color="#64748b",
        )
        self.ent_logo.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(f_logo, text="Escolher", width=90, fg_color="#2980b9", command=self.escolher_logo).grid(row=0, column=1, padx=(8, 0))
        linha += 1

        _lbl("Imagem do patrocinador (direita)")
        f_logo_dir = ctk.CTkFrame(form, fg_color="transparent")
        f_logo_dir.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))
        f_logo_dir.grid_columnconfigure(0, weight=1)
        self.ent_logo_dir = ctk.CTkEntry(
            f_logo_dir,
            placeholder_text="Caminho da imagem do patrocinador (direita)",
            height=34,
            fg_color="#f8fafc",
            border_width=2,
            border_color="#1d4ed8",
            text_color="#0f1720",
            placeholder_text_color="#64748b",
        )
        self.ent_logo_dir.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(f_logo_dir, text="Escolher", width=90, fg_color="#8e44ad", command=self.escolher_logo_direita).grid(row=0, column=1, padx=(8, 0))
        linha += 1

        ctk.CTkFrame(form, height=2, fg_color="#2e4a6a").grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 6))
        linha += 1
        ctk.CTkLabel(form, text="☁️  BACKUP NA NUVEM", anchor="w", text_color="#3498db", font=("Arial", 13, "bold")).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 2)
        )
        linha += 1
        ctk.CTkLabel(form, text="E-mail para backup na nuvem", anchor="w", text_color="#aab4be", font=("Arial", 11)).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 2)
        )
        linha += 1
        self.ent_email = ctk.CTkEntry(
            form,
            placeholder_text="exemplo@gmail.com",
            height=34,
            fg_color="#f8fafc",
            border_width=2,
            border_color="#1d4ed8",
            text_color="#0f1720",
            placeholder_text_color="#64748b",
        )
        self.ent_email.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))
        linha += 1

        self.btn_google = ctk.CTkButton(
            form,
            text="Entrar no Google Drive",
            width=200,
            fg_color="#1a73e8",
            hover_color="#1558b0",
            command=self.conectar_google_drive_oficial,
        )
        self.btn_google.grid(row=linha, column=0, sticky="w", padx=10, pady=(0, 8))
        linha += 1

        f_drive_actions = ctk.CTkFrame(form, fg_color="transparent")
        f_drive_actions.grid(row=linha, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 8))
        ctk.CTkButton(
            f_drive_actions,
            text="Backup para o Drive",
            width=200,
            fg_color="#27ae60",
            hover_color="#1f8d4d",
            command=self.backup_para_drive_manual,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            f_drive_actions,
            text="Restaurar do Drive",
            width=200,
            fg_color="#d68910",
            hover_color="#b9770e",
            command=self.restaurar_do_drive_manual,
        ).grid(row=0, column=1)
        linha += 1

        ctk.CTkFrame(form, height=2, fg_color="#2e4a6a").grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 6))
        linha += 1
        ctk.CTkLabel(form, text="🧾 CONFIGURAÇÃO FISCAL (ACBr)", anchor="w", text_color="#64b5f6", font=("Arial", 13, "bold")).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 2)
        )
        linha += 1

        ctk.CTkButton(
            form,
            text="CONFIGURAR ACBr",
            width=220,
            fg_color="#1f6aa5",
            hover_color="#1a5a8b",
            font=("Arial", 12, "bold"),
            command=self.abrir_configuracao_instalacao_acbr,
        ).grid(row=linha, column=0, sticky="w", padx=10, pady=(0, 8))
        linha += 1

        ctk.CTkLabel(form, text="Modalidade Fiscal", anchor="w", text_color="#aab4be", font=("Arial", 11)).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 2)
        )
        linha += 1
        self.var_modalidade_fiscal = ctk.StringVar(value="NF-e (Venda)")
        self.opt_modalidade_fiscal = ctk.CTkOptionMenu(
            form,
            values=["NF-e (Venda)", "NFS-e (Serviço)"],
            variable=self.var_modalidade_fiscal,
            height=34,
            fg_color="#1f6aa5",
            button_color="#1a5a8b",
            button_hover_color="#174a71",
            dropdown_fg_color="#1f2a38",
        )
        self.opt_modalidade_fiscal.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))
        linha += 1

        ctk.CTkLabel(form, text="CNPJ Emitente (NF-e)", anchor="w", text_color="#aab4be", font=("Arial", 11)).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 2)
        )
        linha += 1
        self.ent_fiscal_cnpj = ctk.CTkEntry(
            form,
            placeholder_text="00.000.000/0000-00",
            height=34,
            fg_color="#f8fafc",
            border_width=2,
            border_color="#1d4ed8",
            text_color="#0f1720",
            placeholder_text_color="#64748b",
        )
        self.ent_fiscal_cnpj.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))
        linha += 1

        ctk.CTkLabel(form, text="IE (Inscrição Estadual)", anchor="w", text_color="#aab4be", font=("Arial", 11)).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 2)
        )
        linha += 1
        self.ent_fiscal_ie = ctk.CTkEntry(
            form,
            placeholder_text="Inscrição Estadual",
            height=34,
            fg_color="#f8fafc",
            border_width=2,
            border_color="#1d4ed8",
            text_color="#0f1720",
            placeholder_text_color="#64748b",
        )
        self.ent_fiscal_ie.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))
        linha += 1

        ctk.CTkLabel(form, text="Token Fiscal", anchor="w", text_color="#aab4be", font=("Arial", 11)).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 2)
        )
        linha += 1
        self.ent_fiscal_token = ctk.CTkEntry(
            form,
            placeholder_text="Token/CSC do emissor",
            height=34,
            fg_color="#f8fafc",
            border_width=2,
            border_color="#1d4ed8",
            text_color="#0f1720",
            placeholder_text_color="#64748b",
        )
        self.ent_fiscal_token.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))
        linha += 1

        ctk.CTkLabel(form, text="Caminho do Certificado A1", anchor="w", text_color="#aab4be", font=("Arial", 11)).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 2)
        )
        linha += 1
        f_cert_a1 = ctk.CTkFrame(form, fg_color="transparent")
        f_cert_a1.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))
        f_cert_a1.grid_columnconfigure(0, weight=1)
        self.ent_fiscal_cert_a1 = ctk.CTkEntry(
            f_cert_a1,
            placeholder_text="Caminho do certificado A1 (.pfx/.p12)",
            height=34,
            fg_color="#f8fafc",
            border_width=2,
            border_color="#1d4ed8",
            text_color="#0f1720",
            placeholder_text_color="#64748b",
        )
        self.ent_fiscal_cert_a1.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            f_cert_a1,
            text="Escolher",
            width=90,
            fg_color="#2980b9",
            command=self.escolher_certificado_a1,
        ).grid(row=0, column=1, padx=(8, 0))
        linha += 1

        ctk.CTkLabel(form, text="Configuração de rede da oficina", anchor="w", text_color="#aab4be", font=("Arial", 11)).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 2)
        )
        linha += 1
        f_rede = ctk.CTkFrame(form, fg_color="transparent")
        f_rede.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        f_rede.grid_columnconfigure(1, weight=1)
        self.btn_localizar_rede = ctk.CTkButton(
            f_rede,
            text="LOCALIZAR OFICINA NA REDE",
            width=280,
            height=34,
            fg_color="#1f6aa5",
            hover_color="#1a5a8b",
            command=self.localizar_oficina_rede_cfg,
        )
        self.btn_localizar_rede.grid(row=0, column=0, padx=(0, 8), pady=0)
        self.lbl_rede = ctk.CTkLabel(f_rede, text="", anchor="w", text_color="#94a3b8", font=("Arial", 10))
        self.lbl_rede.grid(row=0, column=1, sticky="ew")
        linha += 1

        ctk.CTkFrame(form, height=2, fg_color="#2e4a6a").grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(4, 6))
        linha += 1
        ctk.CTkLabel(form, text="ℹ️  INFORMAÇÕES DO SISTEMA", anchor="w", text_color="#95a5a6", font=("Arial", 13, "bold")).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 2)
        )
        linha += 1
        self.lbl_versao = ctk.CTkLabel(form, text="Versão: carregando...", anchor="w", text_color="#7f8c8d", font=("Arial", 11))
        self.lbl_versao.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 2))
        linha += 1

        self.ent_tipo_licenca_info = ctk.CTkEntry(
            form,
            height=34,
            fg_color="#d1d5db",
            border_width=1,
            border_color="#9ca3af",
            text_color="#374151",
        )
        self.ent_tipo_licenca_info.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))
        self.ent_tipo_licenca_info.insert(0, "Tipo de licença: carregando...")
        self.ent_tipo_licenca_info.configure(state="readonly")
        linha += 1

        ctk.CTkButton(
            form,
            text="ATIVAR LICENÇA",
            fg_color="#34495e",
            hover_color="#3c5a71",
            width=220,
            font=("Arial", 12, "bold"),
            command=self.abrir_tela_ativacao_licenca,
        ).grid(row=linha, column=0, sticky="w", padx=10, pady=(0, 8))
        linha += 1

        ctk.CTkButton(form, text="SALVAR DADOS", fg_color="#27ae60", width=220, font=("Arial", 13, "bold"), command=self.salvar).grid(
            row=linha, column=0, sticky="w", padx=10, pady=(0, 10)
        )
        linha += 1

        ctk.CTkFrame(form, height=2, fg_color="#2e4a6a").grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(2, 6))
        linha += 1
        ctk.CTkLabel(form, text="RECUPERACAO DE BACKUP", anchor="w", text_color="#f1c40f", font=("Arial", 13, "bold")).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 2)
        )
        linha += 1
        ctk.CTkLabel(form, text="Use esta opcao apos reinstalacao para restaurar um arquivo .db antigo.", anchor="w", text_color="#aab4be", font=("Arial", 11)).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6)
        )
        linha += 1
        ctk.CTkButton(form, text="RESTAURAR BACKUP AGORA", fg_color="#d68910", hover_color="#b9770e", width=260, font=("Arial", 12, "bold"), command=self.restaurar_backup_manual).grid(
            row=linha, column=0, sticky="w", padx=10, pady=(0, 10)
        )
        linha += 1

        ctk.CTkFrame(form, height=2, fg_color="#2e4a6a").grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(2, 6))
        linha += 1
        ctk.CTkLabel(form, text="SERVIDOR PARA CLIENTE", anchor="w", text_color="#64b5f6", font=("Arial", 13, "bold")).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 2)
        )
        linha += 1
        ctk.CTkLabel(form, text="Gera um pacote para o cliente clicar e instalar o servidor local.", anchor="w", text_color="#aab4be", font=("Arial", 11)).grid(
            row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6)
        )
        linha += 1

        f_servidor = ctk.CTkFrame(form, fg_color="transparent")
        f_servidor.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 8))
        f_servidor.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            f_servidor,
            text="GERAR INSTALADOR DO SERVIDOR",
            fg_color="#2980b9",
            hover_color="#3498db",
            width=320,
            height=36,
            font=("Arial", 12, "bold"),
            command=self.gerar_instalador_servidor,
        ).grid(row=0, column=0, padx=(0, 8), pady=0)
        ctk.CTkLabel(
            f_servidor,
            text="Gera um pacote para o cliente instalar o servidor local com poucos cliques.",
            anchor="w",
            justify="left",
            text_color="#aab4be",
            font=("Arial", 10),
        ).grid(row=0, column=1, sticky="ew")

        self._inicializar_status_fiscal_em_background()

        # Adia a carga de dados para garantir estabilidade da renderização
        self.after(250, self.carregar)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _inicializar_status_fiscal_em_background(self):
        def _worker_fiscal():
            ativo = False
            try:
                inicializar_motor_fiscal(carregar_configuracao_fiscal())
                status_motor = verificar_status_motor_fiscal()
                ativo = bool(status_motor.get("ok"))
            except Exception as exc:
                logger.info("ACBrMonitor indisponível na tela Dados da Oficina: %s", exc)
                ativo = False

            def _aplicar_status():
                if not self.winfo_exists():
                    return
                self._status_motor_fiscal_ativo = ativo

            try:
                self.after(0, _aplicar_status)
            except Exception:
                pass

        threading.Thread(target=_worker_fiscal, daemon=True, name="ofp-dados-oficina-fiscal").start()

    def destroy(self):
        self._encerrando_aplicacao = True
        try:
            for after_id in self.tk.call("after", "info"):
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            self.grab_release()
        except Exception:
            pass

        try:
            # Workaround: normaliza _font ausente em labels do CustomTkinter antes do destroy.
            def _patch_font_attr(widget):
                try:
                    if widget.__class__.__name__ == "CTkLabel" and not hasattr(widget, "_font"):
                        setattr(widget, "_font", None)
                except Exception:
                    pass
                try:
                    for ch in widget.winfo_children():
                        _patch_font_attr(ch)
                except Exception:
                    pass

            _patch_font_attr(self)

            if self.winfo_exists():
                super().destroy()
        except Exception as exc:
            logger.warning("Falha ao fechar Dados da Oficina: %s", exc)

    def _aplicar_maximizacao(self):
        try:
            self.state("zoomed")
            return
        except Exception:
            pass
        try:
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

    def carregar(self):
        """Carrega os dados da oficina com tratamento de erros robusto e logs de terminal."""
        def _thread_db():
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT nome_oficina, endereco_oficina, telefone_oficina, chave_pix, logo_path, logo_patrocinador_path, cnpj_oficina FROM dados_oficina WHERE id = 1"
                    )
                    row = cursor.fetchone()
                
                email_atual = obter_email_backup_nuvem()
                cfg_fiscal = carregar_configuracao_fiscal()
                
                # Retorna para a Main Thread para atualizar a UI
                self.after(0, lambda: self.winfo_exists() and _atualizar_ui(row, email_atual, cfg_fiscal))
            except Exception as e:
                logger.exception("Erro na busca de dados em background: %s", e)

        def _atualizar_ui(row, email_atual, cfg_fiscal):
            if getattr(self, "_encerrando_aplicacao", False) or not self.winfo_exists():
                return
            try:
                if not hasattr(self, 'ent_nome') or self.ent_nome is None:
                    return

                if row:
                    self.ent_nome.delete(0, 'end'); self.ent_nome.insert(0, str(row[0] or ""))
                    self.ent_endereco.delete(0, 'end'); self.ent_endereco.insert(0, str(row[1] or ""))
                    self.ent_telefone.delete(0, 'end'); self.ent_telefone.insert(0, str(row[2] or ""))
                    self.ent_pix.delete(0, 'end'); self.ent_pix.insert(0, str(row[3] or ""))
                    self.ent_logo.delete(0, 'end'); self.ent_logo.insert(0, str(row[4] or ""))
                    self.ent_logo_dir.delete(0, 'end'); self.ent_logo_dir.insert(0, str(row[5] or ""))
                    if len(row) > 6:
                        self.ent_cnpj.delete(0, 'end'); self.ent_cnpj.insert(0, str(row[6] or ""))

                params_fiscal = cfg_fiscal.parametros_gerais if isinstance(cfg_fiscal.parametros_gerais, dict) else {}
                modalidade_fiscal = str(params_fiscal.get("modalidade_fiscal") or "nfe").strip().lower()
                cnpj_fiscal = str(params_fiscal.get("emitente_cnpj") or (row[6] if row and len(row) > 6 else "")).strip()
                ie_fiscal = str(params_fiscal.get("emitente_ie") or "").strip()
                token_fiscal = str(params_fiscal.get("acbr_token") or "").strip()
                cert_a1 = str(params_fiscal.get("acbr_certificado_a1_path") or params_fiscal.get("certificado_a1_path") or "").strip()
                self.var_modalidade_fiscal.set("NFS-e (Serviço)" if modalidade_fiscal == "nfse" else "NF-e (Venda)")
                self.ent_fiscal_cnpj.delete(0, 'end'); self.ent_fiscal_cnpj.insert(0, cnpj_fiscal)
                self.ent_fiscal_ie.delete(0, 'end'); self.ent_fiscal_ie.insert(0, ie_fiscal)
                self.ent_fiscal_token.delete(0, 'end'); self.ent_fiscal_token.insert(0, token_fiscal)
                self.ent_fiscal_cert_a1.delete(0, 'end'); self.ent_fiscal_cert_a1.insert(0, cert_a1)

                if email_atual:
                    self.ent_email.delete(0, 'end'); self.ent_email.insert(0, str(email_atual))
                
                if self.winfo_exists():
                    self._configurar_labels_info()
            except Exception as e:
                logger.exception("Erro ao popular UI da tela Dados da Oficina: %s", e)

        threading.Thread(target=_thread_db, daemon=True).start()

    def _configurar_labels_info(self):
        """Configura labels de versão e licença de forma segura."""
        try:
            if not hasattr(self, 'lbl_versao'):
                return
            self.lbl_versao.configure(text=f"Versão do sistema: {APP_VERSION}")

            if hasattr(self, 'ent_tipo_licenca_info'):
                tipo = str(obter_tipo_licenca() or "INATIVA").strip().upper()
                if tipo == "PERMANENTE":
                    tipo_txt = "Permanente"
                elif tipo == "TRIAL":
                    tipo_txt = "Trial"
                elif tipo in {"MENSAL", "ATIVA", "TOKEN"}:
                    tipo_txt = "Mensal"
                else:
                    tipo_txt = "Inativa"

                self.ent_tipo_licenca_info.configure(state="normal")
                self.ent_tipo_licenca_info.delete(0, "end")
                self.ent_tipo_licenca_info.insert(0, f"Tipo de licença: {tipo_txt}")
                self.ent_tipo_licenca_info.configure(state="readonly")
        except Exception as lic_err:
            logger.warning("Erro ao configurar labels de licença: %s", lic_err)

    def abrir_tela_ativacao_licenca(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Ativar Licença")
        dialog.geometry("500x285")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus_force()

        chave_inst = str(obter_chave_instalacao() or "").strip()
        ctk.CTkLabel(dialog, text="Chave de instalação deste PC:", text_color="#bdc3c7").pack(pady=(16, 4))

        frame_chave = ctk.CTkFrame(dialog, fg_color="#1f2a38")
        frame_chave.pack(pady=(0, 12), padx=12, fill="x")
        ctk.CTkLabel(frame_chave, text=chave_inst, text_color="#f1c40f", font=("Courier", 13, "bold")).pack(side="left", padx=(10, 8), pady=8)

        def _copiar_chave():
            dialog.clipboard_clear()
            dialog.clipboard_append(chave_inst)
            btn_copiar.configure(text="Copiado")
            dialog.after(1500, lambda: btn_copiar.configure(text="Copiar Chave"))

        btn_copiar = ctk.CTkButton(
            frame_chave,
            text="Copiar Chave",
            command=_copiar_chave,
            width=130,
            height=30,
            fg_color="#2980b9",
            hover_color="#3498db",
        )
        btn_copiar.pack(side="right", padx=(0, 8), pady=8)

        ctk.CTkLabel(dialog, text="Contra-senha de ativação:", text_color="#bdc3c7").pack(pady=(2, 4))
        entry_chave = ctk.CTkEntry(dialog, width=420, height=40, placeholder_text="Cole aqui a chave enviada pelo suporte")
        entry_chave.pack(pady=(0, 10))

        def _confirmar():
            chave = entry_chave.get().strip()
            if not chave:
                messagebox.showwarning("Ativação", "Informe a contra-senha de ativação.", parent=dialog)
                return

            btn_confirmar.configure(state="disabled", text="ATIVANDO...")
            ok, msg = ativar_licenca(chave)
            if ok:
                def _publicar_drive_bg():
                    try:
                        publicar_licenca_drive(chave)
                    except Exception as exc:
                        logger.warning("Falha silenciosa ao publicar licença no Drive: %s", exc)

                threading.Thread(target=_publicar_drive_bg, daemon=True, name="ofp-licenca-drive-menu").start()
                self._configurar_labels_info()
                messagebox.showinfo("Ativação", "Licença ativada com sucesso.", parent=dialog)
                dialog.destroy()
                return

            try:
                diag = diagnosticar_chave_licenca(chave)
                detalhe = str(diag.get("motivo") or "").strip()
                if detalhe:
                    msg = f"{msg}\n\nDiagnóstico: {detalhe}"
            except Exception:
                pass

            btn_confirmar.configure(state="normal", text="ATIVAR AGORA")
            messagebox.showerror("Ativação", msg, parent=dialog)

        btn_confirmar = ctk.CTkButton(
            dialog,
            text="ATIVAR AGORA",
            command=_confirmar,
            width=320,
            height=36,
            fg_color="#27ae60",
            hover_color="#2ecc71",
        )
        btn_confirmar.pack(pady=(4, 8))
        entry_chave.bind("<Return>", lambda _e: _confirmar())

    def escolher_logo(self):
        caminho = filedialog.askopenfilename(
            parent=self,
            title="Selecionar logo da oficina",
            filetypes=[("Imagens", "*.png;*.jpg;*.jpeg;*.webp;*.bmp")],
        )
        if caminho:
            self.ent_logo.delete(0, "end")
            self.ent_logo.insert(0, caminho)

    def escolher_logo_direita(self):
        caminho = filedialog.askopenfilename(
            parent=self,
            title="Selecionar imagem do patrocinador",
            filetypes=[("Imagens", "*.png;*.jpg;*.jpeg;*.webp")]
        )
        if caminho:
            self.ent_logo_dir.delete(0, "end")
            self.ent_logo_dir.insert(0, caminho)

    def escolher_certificado_a1(self):
        caminho = filedialog.askopenfilename(
            parent=self,
            title="Selecionar certificado A1",
            filetypes=[("Certificado A1", "*.pfx;*.p12"), ("Todos os arquivos", "*.*")],
        )
        if caminho:
            self.ent_fiscal_cert_a1.delete(0, "end")
            self.ent_fiscal_cert_a1.insert(0, caminho)

    def abrir_configuracao_instalacao_acbr(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidatos_setup = [
            os.path.join(base_dir, "instala", "ACBrMonitorPLUS-DEMO-1.4.0.467-x86-I.exe"),
            os.path.join(base_dir, "config_fiscal", "acbr_monitor", "ACBrMonitorPLUS-DEMO-1.4.0.467-x86-I.exe"),
        ]

        for instalador in candidatos_setup:
            if not os.path.exists(instalador):
                continue
            try:
                if hasattr(os, "startfile"):
                    os.startfile(instalador)  # type: ignore[attr-defined]
                else:
                    webbrowser.open(instalador)
                return
            except Exception as exc:
                messagebox.showerror("ACBr", f"Não foi possível abrir o instalador do ACBr: {exc}", parent=self)
                return

        pasta_config = os.path.join(base_dir, "config_fiscal")
        if os.path.isdir(pasta_config):
            try:
                if hasattr(os, "startfile"):
                    os.startfile(pasta_config)  # type: ignore[attr-defined]
                else:
                    webbrowser.open(pasta_config)
                return
            except Exception as exc:
                messagebox.showerror("ACBr", f"Não foi possível abrir a pasta de configuração fiscal: {exc}", parent=self)
                return

        messagebox.showwarning(
            "ACBr",
            "Não foi localizado instalador ou pasta de configuração do ACBr nesta instalação.",
            parent=self,
        )

    def _descobrir_oficina_udp_cfg(self, timeout_total=5.0):
        payload = json.dumps({
            "type": "OFP_DISCOVER_REQUEST",
            "app": "oficina_pesca",
            "source": "menu_dados_oficina",
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
                    resposta, addr = sock.recvfrom(4096)
                    data = json.loads(resposta.decode("utf-8", errors="ignore"))
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

    def _salvar_servidor_url_cfg_menu(self, url_base: str):
        caminhos = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.cfg"),
            os.path.join(os.getcwd(), "config.cfg"),
        ]
        caminho_cfg = ""
        for caminho in caminhos:
            if os.path.exists(caminho):
                caminho_cfg = caminho
                break
        if not caminho_cfg:
            caminho_cfg = caminhos[0]

        parser = configparser.ConfigParser()
        if os.path.exists(caminho_cfg):
            parser.read(caminho_cfg, encoding="utf-8")
        if not parser.has_section("app"):
            parser.add_section("app")
        parser.set("app", "servidor_url", url_base)
        with open(caminho_cfg, "w", encoding="utf-8") as arquivo_cfg:
            parser.write(arquivo_cfg)
        return caminho_cfg

    def localizar_oficina_rede_cfg(self):
        self.btn_localizar_rede.configure(state="disabled", text="LOCALIZANDO...")
        self.lbl_rede.configure(text="Buscando servidor na rede local...", text_color="#f1c40f")

        def worker():
            url = ""
            erro = ""
            try:
                url = self._descobrir_oficina_udp_cfg(timeout_total=5.0)
            except Exception as exc:
                erro = str(exc)

            def finalizar():
                self.btn_localizar_rede.configure(state="normal", text="LOCALIZAR OFICINA NA REDE")
                if not url:
                    self.lbl_rede.configure(text="Oficina não localizada na rede.", text_color="#e74c3c")
                    msg = "Não foi possível localizar a oficina automaticamente na rede."
                    if erro:
                        msg += f"\n\nDetalhe: {erro}"
                    messagebox.showwarning("Rede Local", msg, parent=self)
                    return
                try:
                    caminho = self._salvar_servidor_url_cfg_menu(url)
                    self.lbl_rede.configure(text=f"Oficina localizada: {url}", text_color="#2ecc71")
                    messagebox.showinfo("Rede Local", f"Oficina localizada com sucesso!\n\nServidor: {url}\nConfig salvo em: {caminho}", parent=self)
                except Exception as exc:
                    self.lbl_rede.configure(text="Servidor encontrado, mas falha ao salvar.", text_color="#f39c12")
                    messagebox.showwarning("Rede Local", f"Servidor encontrado: {url}\nFalha ao salvar config: {exc}", parent=self)

            self.after(0, finalizar)

        threading.Thread(target=worker, daemon=True).start()

    def _abrir_url_externa(self, url: str, titulo: str):
        try:
            abriu = bool(webbrowser.open(url, new=2))
            if abriu:
                messagebox.showinfo(
                    "Nuvem",
                    f"Abrindo {titulo} no navegador.\n\nFaça login e finalize a configuracao na nuvem.",
                    parent=self,
                )
                return
        except Exception:
            pass

        try:
            self.clipboard_clear()
            self.clipboard_append(url)
        except Exception:
            pass
        messagebox.showwarning(
            "Nuvem",
            "Nao foi possivel abrir o navegador automaticamente.\n\n"
            "O link foi copiado para a area de transferencia.",
            parent=self,
        )


    def conectar_google_drive_oficial(self):
        """Dispara autenticação OAuth2 e upload para o Google Drive e Firebase."""
        email_digitado = self.ent_email.get().strip().lower()

        messagebox.showinfo(
            "Google Drive",
            "Você será redirecionado para o Google para autorizar a sincronização",
            parent=self,
        )

        ok_auth, msg_auth, email_autenticado = conectar_google_drive_usuario(
            login_hint=email_digitado
        )
        if not ok_auth:
            logger.warning("Falha na autenticacao Google Drive: %s", msg_auth)
            messagebox.showwarning(
                "Google Drive",
                msg_auth or "Nao foi possivel autenticar com o Google Drive.",
                parent=self,
            )
            return

        logger.info("Autenticacao Google Drive concluida: %s", email_autenticado)

        # Primeiro upload do banco de dados apos autenticacao
        ok_sync, msg_sync = garantir_banco_no_drive_usuario()
        if ok_sync:
            logger.info("Banco de dados sincronizado: %s", msg_sync)
            messagebox.showinfo(
                "Google Drive",
                "Sincronização configurada com sucesso!",
                parent=self,
            )
            # Inicia o background sync apenas apos autenticacao manual
            iniciar_sincronizacao_hibrida_nuvem()

            # --- Sincronização com Firebase ---
            def atualizar_firebase_rtdb():
                import firebase_admin
                from firebase_admin import db
                import logging
                try:
                    # Sanitização do e-mail
                    email_sanitizado = email_digitado.replace('.', '_at_').replace('@', '_at_')
                    self.inicializar_firebase()
                    # Buscar dados da oficina
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT nome_oficina, endereco_oficina, telefone_oficina, chave_pix, logo_path, logo_patrocinador_path FROM dados_oficina WHERE id = 1")
                        dados_oficina = cursor.fetchone()
                        oficina_dict = {}
                        if dados_oficina:
                            oficina_dict = {
                                "nome_oficina": dados_oficina[0],
                                "endereco_oficina": dados_oficina[1],
                                "telefone_oficina": dados_oficina[2],
                                "chave_pix": dados_oficina[3],
                                "logo_path": dados_oficina[4],
                                "logo_patrocinador_path": dados_oficina[5],
                            }
                        # Buscar últimas ordens de serviço
                        cursor.execute("SELECT id_os, cliente_nome, equipamento, data_abertura, status FROM ordens_servico ORDER BY id_os DESC LIMIT 10")
                        ordens = cursor.fetchall()
                        ordens_list = []
                        for row in ordens:
                            ordens_list.append({
                                "id": row[0], # id_os
                                "cliente": row[1],
                                "equipamento": row[2],
                                "data": row[3], # data_abertura
                                "status": row[4],
                            })
                    # Enviar para o Firebase
                    ref = db.reference(f"usuarios/{email_sanitizado}/")
                    ref.update({
                        "dados_oficina": oficina_dict,
                        "os": ordens_list # Nome da chave alterado para 'os' para coincidir com login.py
                    })
                    logger.info("Dados enviados ao Firebase Realtime Database com sucesso!")
                except Exception as e:
                    logger.warning(f"Falha ao sincronizar com Firebase: {e}")

            atualizar_firebase_rtdb()
            return

        logger.warning("Falha no primeiro sync: %s", msg_sync)
        messagebox.showwarning(
            "Google Drive",
            f"Autenticacao bem-sucedida, mas falha no sync: {msg_sync}",
            parent=self,
        )

    def _garantir_drive_autenticado(self) -> bool:
        if google_drive_usuario_conectado():
            return True

        autenticar = messagebox.askyesno(
            "Google Drive",
            "Você ainda não está autenticado no Google Drive.\n\nDeseja autenticar agora?",
            parent=self,
        )
        if not autenticar:
            return False

        self.conectar_google_drive_oficial()
        return google_drive_usuario_conectado()

    def backup_para_drive_manual(self):
        if not self._garantir_drive_autenticado():
            return

        ok, msg = enviar_backup_banco_para_drive_usuario()
        if ok:
            messagebox.showinfo(
                "Backup no Drive",
                f"Backup concluído com sucesso.\n\n{msg}",
                parent=self,
            )
            return

        messagebox.showwarning("Backup no Drive", msg or "Falha ao enviar backup para o Drive.", parent=self)

    def _selecionar_backup_drive(self, backups: list[dict]) -> dict | None:
        if not backups:
            return None

        dialog = ctk.CTkToplevel(self)
        dialog.title("Selecionar backup do Drive")
        dialog.geometry("760x420")
        dialog.resizable(True, True)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="Selecione um arquivo .db da nuvem",
            font=("Arial", 14, "bold"),
            text_color="orange",
        ).pack(anchor="w", padx=16, pady=(12, 8))

        opcoes: list[str] = []
        mapa: dict[str, dict] = {}
        for item in backups:
            nome = str(item.get("name") or "backup.db")
            mod = str(item.get("modified") or "-")
            tam = str(item.get("size") or "0")
            rotulo = f"{nome}  |  {mod}  |  {tam} bytes"
            opcoes.append(rotulo)
            mapa[rotulo] = item

        selecionado = {"item": backups[0]}
        var = tk.StringVar(value=opcoes[0])

        lbl_info = ctk.CTkLabel(dialog, text="", anchor="w", justify="left", text_color="#aab4be", font=("Arial", 11))
        lbl_info.pack(fill="x", padx=16, pady=(0, 8))

        def _atualizar_info(chave: str):
            item = mapa.get(chave, backups[0])
            selecionado["item"] = item
            lbl_info.configure(
                text=(
                    f"Arquivo: {item.get('name', '-') }\n"
                    f"Alterado: {item.get('modified', '-') }\n"
                    f"Tamanho: {item.get('size', '0')} bytes"
                )
            )

        combo = ctk.CTkOptionMenu(dialog, values=opcoes, variable=var, command=_atualizar_info)
        combo.pack(fill="x", padx=16, pady=(0, 10))
        _atualizar_info(opcoes[0])

        retorno = {"value": None}

        def _confirmar():
            retorno["value"] = selecionado.get("item")
            dialog.destroy()

        def _cancelar():
            retorno["value"] = None
            dialog.destroy()

        botoes = ctk.CTkFrame(dialog, fg_color="transparent")
        botoes.pack(anchor="e", padx=16, pady=(8, 12))
        ctk.CTkButton(botoes, text="Cancelar", fg_color="#7f8c8d", width=120, command=_cancelar).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(botoes, text="Restaurar", fg_color="#d68910", hover_color="#b9770e", width=120, command=_confirmar).grid(row=0, column=1)

        self.wait_window(dialog)
        return retorno["value"]

    def restaurar_do_drive_manual(self):
        if not self._garantir_drive_autenticado():
            return

        ok_list, backups, msg_list = listar_backups_banco_drive_usuario(limit=80)
        if not ok_list:
            messagebox.showwarning("Restaurar do Drive", msg_list or "Falha ao listar backups no Drive.", parent=self)
            return

        if not backups:
            messagebox.showinfo("Restaurar do Drive", "Nenhum arquivo .db encontrado na pasta Oficina_Backup.", parent=self)
            return

        escolhido = self._selecionar_backup_drive(backups)
        if not escolhido:
            return

        confirmar = messagebox.askyesno(
            "Confirmar restauracao",
            "Isso vai substituir o banco atual pelos dados do backup selecionado no Drive.\n\nDeseja continuar?",
            parent=self,
        )
        if not confirmar:
            return

        ok_restore, msg_restore = restaurar_backup_banco_drive_usuario(
            str(escolhido.get("id") or ""),
            str(escolhido.get("name") or ""),
        )
        if not ok_restore:
            messagebox.showerror("Restaurar do Drive", msg_restore or "Falha ao restaurar backup do Drive.", parent=self)
            return

        reiniciar = messagebox.askyesno(
            "Backup restaurado",
            f"{msg_restore}\n\nDeseja fechar o sistema agora para reabrir com os dados restaurados?",
            parent=self,
        )
        if reiniciar:
            encerrar = getattr(self.master, "_encerrar_aplicacao", None)
            if callable(encerrar):
                encerrar()
                return
            messagebox.showwarning("Encerramento", "Não foi possível acionar o encerramento centralizado.", parent=self)

    def salvar(self):
        nome = self.ent_nome.get().strip()
        endereco = self.ent_endereco.get().strip()
        telefone = self.ent_telefone.get().strip()
        pix = self.ent_pix.get().strip()
        logo = self.ent_logo.get().strip()
        logo_dir = self.ent_logo_dir.get().strip()
        cnpj = self.ent_cnpj.get().strip()
        email_nuvem = self.ent_email.get().strip().lower()
        cnpj_fiscal = self.ent_fiscal_cnpj.get().strip() or cnpj
        ie_fiscal = self.ent_fiscal_ie.get().strip()
        token_fiscal = self.ent_fiscal_token.get().strip()
        cert_a1_fiscal = self.ent_fiscal_cert_a1.get().strip()
        modalidade_fiscal = "nfse" if "NFS-e" in str(self.var_modalidade_fiscal.get()) else "nfe"

        if not nome:
            messagebox.showwarning("Atenção", "Informe o nome da oficina.", parent=self)
            return

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO dados_oficina
                        (id, nome_oficina, endereco_oficina, telefone_oficina, chave_pix, logo_path, logo_patrocinador_path, cnpj_oficina)
                    VALUES
                        (1, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (nome, endereco, telefone, pix, logo, logo_dir, cnpj)
                )
                conn.commit()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível salvar dados da oficina: {e}", parent=self)
            return

        try:
            cfg_atual = carregar_configuracao_fiscal()
            parametros = dict(cfg_atual.parametros_gerais or {}) if isinstance(cfg_atual.parametros_gerais, dict) else {}
            parametros.update(
                {
                    "provedor": "acbr",
                    "acbr_modo": str(parametros.get("acbr_modo") or "monitor").strip().lower() or "monitor",
                    "emitente_cnpj": cnpj_fiscal,
                    "emitente_ie": ie_fiscal,
                    "acbr_token": token_fiscal,
                    "modalidade_fiscal": modalidade_fiscal,
                    "acbr_certificado_a1_path": cert_a1_fiscal,
                    "certificado_a1_path": cert_a1_fiscal,
                }
            )
            salvar_configuracao_fiscal(
                ConfiguracaoFiscal(
                    api_key_plugnotas=str(cfg_atual.api_key_plugnotas or "").strip(),
                    api_key_focusnfe=str(cfg_atual.api_key_focusnfe or "").strip(),
                    ambiente=str(cfg_atual.ambiente or "homologacao").strip().lower() or "homologacao",
                    parametros_gerais=parametros,
                )
            )
        except Exception as e:
            messagebox.showwarning(
                "Configuração Fiscal",
                f"Dados da oficina salvos, mas houve falha ao salvar configuração fiscal: {e}",
                parent=self,
            )

        # Inicializa o Firebase após salvar localmente
        self.inicializar_firebase()

        # salvar email backup se informado
        if email_nuvem:
            ok, msg = salvar_email_backup_nuvem(email_nuvem)
            if not ok:
                messagebox.showwarning("E-mail Nuvem", f"Dados salvos, mas não foi possível salvar e-mail: {msg}", parent=self)

        messagebox.showinfo("Sucesso", "Dados da oficina atualizados com sucesso.", parent=self)
        
        # Fechamento seguro para evitar erro 'can't delete Tcl command'
        self.destroy()
    def restaurar_backup_manual(self):
        caminho_backup = filedialog.askopenfilename(
            parent=self,
            title="Selecionar backup para restaurar",
            filetypes=[("Banco SQLite", "*.db;*.sqlite;*.sqlite3"), ("Todos os arquivos", "*.*")],
        )
        if not caminho_backup:
            return

        if not os.path.exists(caminho_backup):
            messagebox.showwarning("Backup", "Arquivo de backup nao encontrado.", parent=self)
            return

        confirmar = messagebox.askyesno(
            "Confirmar restauracao",
            "Isso vai substituir o banco atual pelos dados do backup selecionado.\n\nDeseja continuar?",
            parent=self,
        )
        if not confirmar:
            return

        try:
            # Valida se o arquivo selecionado parece um banco SQLite utilizavel.
            with sqlite3.connect(caminho_backup, timeout=5) as conn_teste:
                cur = conn_teste.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tabelas = {str(r[0] or "").strip().lower() for r in cur.fetchall()}

            obrigatorias = {"usuarios", "clientes", "orcamentos_aguardo", "fluxo_caixa", "dados_oficina"}
            if not (tabelas & obrigatorias):
                messagebox.showerror(
                    "Backup",
                    "O arquivo selecionado nao parece ser um banco valido da Oficina de Pesca.",
                    parent=self,
                )
                return

            pasta_backup_local = os.path.join(os.path.dirname(CAMINHO_BANCO), "backup_db")
            os.makedirs(pasta_backup_local, exist_ok=True)

            if os.path.exists(CAMINHO_BANCO):
                carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
                copia_seguranca = os.path.join(pasta_backup_local, f"pre_restore_{carimbo}.db")
                shutil.copy2(CAMINHO_BANCO, copia_seguranca)

            shutil.copy2(caminho_backup, CAMINHO_BANCO)
            inicializar_banco()

            reiniciar = messagebox.askyesno(
                "Backup restaurado",
                "Backup restaurado com sucesso.\n\nDeseja fechar o sistema agora para reabrir com os dados restaurados?",
                parent=self,
            )
            if reiniciar:
                encerrar = getattr(self.master, "_encerrar_aplicacao", None)
                if callable(encerrar):
                    encerrar()
                    return
                messagebox.showwarning("Encerramento", "Não foi possível acionar o encerramento centralizado.", parent=self)
        except Exception as e:
            messagebox.showerror("Backup", f"Nao foi possivel restaurar o backup: {e}", parent=self)

    def gerar_instalador_servidor(self):
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            pasta_saida = os.path.join(base_dir, "PACOTE_SERVIDOR_CLIENTE")
            zip_saida = os.path.join(base_dir, "PACOTE_SERVIDOR_CLIENTE.zip")

            if os.path.exists(pasta_saida):
                shutil.rmtree(pasta_saida, ignore_errors=True)
            os.makedirs(pasta_saida, exist_ok=True)

            arquivos_base = ["servidor.py", "config.py", "config.cfg", "iniciar_servidor.bat"]
            for nome in arquivos_base:
                origem = os.path.join(base_dir, nome)
                if os.path.exists(origem):
                    shutil.copy2(origem, os.path.join(pasta_saida, nome))

            for nome_pasta in ["templates", "static"]:
                origem = os.path.join(base_dir, nome_pasta)
                destino = os.path.join(pasta_saida, nome_pasta)
                if os.path.isdir(origem):
                    shutil.copytree(origem, destino, dirs_exist_ok=True)

            instalador_bat = os.path.join(pasta_saida, "INSTALAR_SERVIDOR_CLIENTE.bat")
            with open(instalador_bat, "w", encoding="utf-8") as f:
                f.write(
                    "@echo off\n"
                    "title Instalador Servidor Oficina de Pesca\n"
                    "cd /d %~dp0\n"
                    "echo =============================================\n"
                    "echo  INSTALADOR SERVIDOR - OFICINA DE PESCA\n"
                    "echo =============================================\n"
                    "echo.\n"
                    "where py >nul 2>nul\n"
                    "if %errorlevel% neq 0 (\n"
                    "  where python >nul 2>nul\n"
                    ")\n"
                    "if %errorlevel% neq 0 (\n"
                    "  echo Python nao encontrado. Instale Python 3.10+ e tente novamente.\n"
                    "  pause\n"
                    "  exit /b 1\n"
                    ")\n"
                    "if not exist venv (\n"
                    "  py -3 -m venv venv >nul 2>nul || python -m venv venv\n"
                    ")\n"
                    "call venv\\Scripts\\activate.bat\n"
                    "python -m pip install --upgrade pip\n"
                    "pip install fastapi uvicorn jinja2 python-multipart\n"
                    "echo.\n"
                    "echo Servidor instalado com sucesso.\n"
                    "echo Para iniciar, use INICIAR_SERVIDOR_CLIENTE.bat\n"
                    "pause\n"
                )

            iniciar_bat = os.path.join(pasta_saida, "INICIAR_SERVIDOR_CLIENTE.bat")
            with open(iniciar_bat, "w", encoding="utf-8") as f:
                f.write(
                    "@echo off\n"
                    "title Servidor Oficina de Pesca\n"
                    "cd /d %~dp0\n"
                    "if not exist venv\\Scripts\\activate.bat (\n"
                    "  echo Execute primeiro: INSTALAR_SERVIDOR_CLIENTE.bat\n"
                    "  pause\n"
                    "  exit /b 1\n"
                    ")\n"
                    "call venv\\Scripts\\activate.bat\n"
                    "python servidor.py\n"
                    "pause\n"
                )

            readme = os.path.join(pasta_saida, "LEIA_ME_SERVIDOR.txt")
            with open(readme, "w", encoding="utf-8") as f:
                f.write(
                    "SERVIDOR OFICINA DE PESCA - CLIENTE\n"
                    "\n"
                    "1) Execute INSTALAR_SERVIDOR_CLIENTE.bat\n"
                    "2) Depois execute INICIAR_SERVIDOR_CLIENTE.bat\n"
                    "3) No celular, use o endereco IP mostrado na tela\n"
                )

            if os.path.exists(zip_saida):
                os.remove(zip_saida)

            with zipfile.ZipFile(zip_saida, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for raiz, _dirs, arquivos in os.walk(pasta_saida):
                    for arquivo in arquivos:
                        caminho = os.path.join(raiz, arquivo)
                        rel = os.path.relpath(caminho, pasta_saida)
                        zf.write(caminho, rel)

            # Abre a pasta automaticamente no Explorer
            try:
                os.startfile(pasta_saida)
            except Exception:
                pass

            # Janela de instruções de entrega ao cliente
            self._janela_instrucoes_servidor(pasta_saida, zip_saida)

        except Exception as e:
            messagebox.showerror("Erro", f"Nao foi possivel gerar pacote do servidor: {e}", parent=self)

    def _janela_instrucoes_servidor(self, pasta_saida, zip_saida):
        win = ctk.CTkToplevel(self)
        win.title("Como entregar o Servidor ao Cliente")
        win.geometry("620x560")
        win.resizable(False, False)
        win.grab_set()
        win.focus_force()
        win.configure(fg_color="#0d1117")

        ctk.CTkLabel(win, text="✅  PACOTE DO SERVIDOR GERADO!",
                     font=("Arial", 17, "bold"), text_color="#2ecc71").pack(pady=(20, 4))
        ctk.CTkLabel(win, text="Escolha a opção de entrega mais adequada para o cliente:",
                     font=("Arial", 12), text_color="#bdc3c7").pack(pady=(0, 12))

        # ── Opção 1: Instalador (recomendado) ───────────────────────────
        card1 = ctk.CTkFrame(win, fg_color="#1a2a1a", corner_radius=12, border_width=2, border_color="#2ecc71")
        card1.pack(fill="x", padx=20, pady=(0, 10))
        f1h = ctk.CTkFrame(card1, fg_color="#1a2a1a")
        f1h.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(f1h, text="📦  OPÇÃO 1 — ZIP (RECOMENDADO)",
                     font=("Arial", 13, "bold"), text_color="#2ecc71").pack(side="left")
        ctk.CTkLabel(f1h, text="  ✔ mais fácil para o cliente",
                     font=("Arial", 11), text_color="#7fba00").pack(side="left", padx=6)
        ctk.CTkLabel(card1,
                     text=(
                         "1. Envie o arquivo  PACOTE_SERVIDOR_CLIENTE.zip  por WhatsApp ou e-mail.\n"
                         "2. O cliente descompacta o ZIP em qualquer pasta.\n"
                         "3. Clica duas vezes em  INSTALAR_SERVIDOR_CLIENTE.bat  (só uma vez).\n"
                         "4. Depois clica em  INICIAR_SERVIDOR_CLIENTE.bat  para ligar o servidor.\n"
                         "5. No celular, acessa pelo endereço IP que aparecer na tela."
                     ),
                     font=("Arial", 11), text_color="#b2d9b2", justify="left", wraplength=560).pack(
            padx=14, pady=(4, 12), anchor="w")
        ctk.CTkButton(card1, text="📋  Copiar caminho do ZIP",
                      fg_color="#1a6b30", hover_color="#27ae60", width=230,
                      command=lambda: (win.clipboard_clear(), win.clipboard_append(zip_saida),
                                       messagebox.showinfo("Copiado", "Caminho do ZIP copiado!", parent=win))
                      ).pack(pady=(0, 12))

        # ── Opção 2: Terminal (avançado) ─────────────────────────────────
        card2 = ctk.CTkFrame(win, fg_color="#1a1a2a", corner_radius=12, border_width=2, border_color="#3498db")
        card2.pack(fill="x", padx=20, pady=(0, 10))
        f2h = ctk.CTkFrame(card2, fg_color="#1a1a2a")
        f2h.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(f2h, text="💻  OPÇÃO 2 — TERMINAL (para técnicos)",
                     font=("Arial", 13, "bold"), text_color="#3498db").pack(side="left")
        ctk.CTkLabel(f2h, text="  ⚠ requer Python",
                     font=("Arial", 11), text_color="#f39c12").pack(side="left", padx=6)
        ctk.CTkLabel(card2,
                     text=(
                         "1. O cliente precisa ter Python 3.10+ instalado.\n"
                         "2. Abra o terminal (Prompt de Comando / PowerShell).\n"
                         "3. Navegue até a pasta do servidor:\n"
                         f"   cd \"{pasta_saida}\"\n"
                         "4. Instale as dependências:\n"
                         "   pip install fastapi uvicorn jinja2 python-multipart\n"
                         "5. Inicie o servidor:\n"
                         "   python servidor.py"
                     ),
                     font=("Consolas", 10), text_color="#a0c4ff", justify="left", wraplength=560).pack(
            padx=14, pady=(4, 8), anchor="w")
        ctk.CTkButton(card2, text="📋  Copiar comando pip install",
                      fg_color="#1a3a6b", hover_color="#2980b9", width=260,
                      command=lambda: (win.clipboard_clear(),
                                       win.clipboard_append("pip install fastapi uvicorn jinja2 python-multipart"),
                                       messagebox.showinfo("Copiado", "Comando copiado!", parent=win))
                      ).pack(pady=(0, 12))

        ctk.CTkButton(win, text="Fechar", fg_color="#7f8c8d", hover_color="#95a5a6",
                      width=140, command=win.destroy).pack(pady=(6, 16))


class FrmBaixaRecibo(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Baixa de O.S. Finalizadas")
        self.geometry("1100x680")
        self.minsize(920, 560)
        self.configure(fg_color="#161b22")
        self.update()
        self.attributes('-topmost', True)
        self.focus_force()
        self.after(300, lambda: self.attributes('-topmost', False))
        self.grab_set()
        self._dados_por_item = {}
        self._aplicar_maximizacao()
        self.after(120, self._aplicar_maximizacao)

        header = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=18)
        header.pack(fill="x", padx=18, pady=(18, 10))
        ctk.CTkLabel(
            header,
            text="🧾 BAIXA DE O.S. FINALIZADAS",
            font=("Arial", 22, "bold"),
            text_color="orange",
        ).pack(side="left", padx=18, pady=18)
        ctk.CTkButton(
            header,
            text="DAR BAIXA / GERAR RECIBO",
            fg_color="#8e6b3b",
            hover_color="#a87c45",
            width=220,
            command=self.gerar_recibo_selecionado,
        ).pack(side="right", padx=(0, 10), pady=18)
        ctk.CTkButton(
            header,
            text="Fechar",
            fg_color="#7f8c8d",
            width=120,
            command=self.destroy,
        ).pack(side="right", padx=(0, 10), pady=18)
        ctk.CTkButton(
            header,
            text="Atualizar",
            fg_color="#2980b9",
            width=130,
            command=self.carregar_os_finalizadas,
        ).pack(side="right", padx=(0, 18), pady=18)

        info = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=18)
        info.pack(fill="x", padx=18, pady=(0, 10))
        ctk.CTkLabel(
            info,
            text="Selecione uma O.S. FINALIZADA para dar baixa, gerar o recibo e marcar como ENTREGUE.",
            font=("Arial", 12),
            text_color="#d5d8dc",
        ).pack(anchor="w", padx=16, pady=(12, 8))
        self.lbl_info_recibo = ctk.CTkLabel(info, text="", font=("Arial", 11), text_color="#95a5a6")
        self.lbl_info_recibo.pack(anchor="w", padx=16, pady=(0, 12))

        tabela_frame = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=18)
        tabela_frame.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        style = ttk.Style()
        style.configure("Treeview", rowheight=28, font=("Arial", 10))
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"))

        self.tab_recibos = ttk.Treeview(
            tabela_frame,
            columns=("id", "cliente", "equipamento", "data", "valor_total", "saldo", "status"),
            show="headings",
            height=14,
        )
        self.tab_recibos.heading("id", text="Nº O.S.")
        self.tab_recibos.heading("cliente", text="CLIENTE")
        self.tab_recibos.heading("equipamento", text="EQUIPAMENTO")
        self.tab_recibos.heading("data", text="DATA")
        self.tab_recibos.heading("valor_total", text="VALOR TOTAL")
        self.tab_recibos.heading("saldo", text="SALDO")
        self.tab_recibos.heading("status", text="STATUS")
        self.tab_recibos.column("id", width=80, anchor="center")
        self.tab_recibos.column("cliente", width=240)
        self.tab_recibos.column("equipamento", width=210)
        self.tab_recibos.column("data", width=110, anchor="center")
        self.tab_recibos.column("valor_total", width=120, anchor="e")
        self.tab_recibos.column("saldo", width=120, anchor="e")
        self.tab_recibos.column("status", width=110, anchor="center")
        self.tab_recibos.pack(fill="both", expand=True, padx=16, pady=16)
        self.tab_recibos.bind("<<TreeviewSelect>>", self._selecionar_os)
        self.tab_recibos.bind("<Double-1>", self.gerar_recibo_selecionado)

        self.carregar_os_finalizadas() #
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def destroy(self):
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

    def _aplicar_maximizacao(self):
        try:
            self.state("zoomed")
            return
        except Exception:
            pass
        try:
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

    def carregar_os_finalizadas(self):
        self._dados_por_item.clear()
        for item in self.tab_recibos.get_children():
            self.tab_recibos.delete(item)

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, cliente, equipamento, defeito, valor_total, sinal, saldo, status, data
                    FROM orcamentos_aguardo
                    WHERE UPPER(COALESCE(status, '')) = 'FINALIZADO'
                      AND UPPER(COALESCE(status_entrega, '')) <> 'ENTREGUE'
                    ORDER BY id DESC
                    """
                )
                rows = cursor.fetchall()

            for row in rows:
                os_id, cliente, equipamento, _defeito, valor_total, _sinal, saldo, status, data = row
                item_id = self.tab_recibos.insert(
                    "",
                    "end",
                    values=(
                        os_id,
                        cliente or "",
                        equipamento or "",
                        data or "-",
                        f"R$ {float(valor_total or 0):.2f}",
                        f"R$ {float(saldo or 0):.2f}",
                        status or "",
                    ),
                )
                self._dados_por_item[item_id] = row

            if rows:
                self.lbl_info_recibo.configure(text=f"{len(rows)} O.S. finalizada(s) pronta(s) para baixa.")
            else:
                self.lbl_info_recibo.configure(text="Nenhuma O.S. finalizada pendente de baixa.")
        except Exception as exc:
            self.lbl_info_recibo.configure(text=f"Erro ao carregar O.S. finalizadas: {exc}")

    def _selecionar_os(self, _event=None):
        selecao = self.tab_recibos.selection()
        if not selecao:
            return None
        dados = self._dados_por_item.get(selecao[0])
        if dados:
            self.lbl_info_recibo.configure(
                text=f"O.S. {dados[0]} | {dados[1] or ''} | {dados[2] or ''} | R$ {float(dados[4] or 0):.2f}"
            )
        return dados

    def gerar_recibo_selecionado(self, _event=None):
        dados_os = self._selecionar_os()
        if not dados_os:
            messagebox.showwarning("Recibo", "Selecione uma O.S. finalizada para dar baixa.", parent=self)
            return

        num_os = int(dados_os[0])
        confirmar = messagebox.askyesno(
            "Dar baixa",
            f"Gerar recibo e dar baixa na O.S. {num_os}?\n\n"
            "O status sera alterado para ENTREGUE e o financeiro sera atualizado automaticamente.",
            parent=self,
        )
        if not confirmar:
            return

        try:
            caminho_pdf = gerar_recibo_entrega(dados_os)
            if hasattr(self.master, "_janela_viva") and self.master._janela_viva(getattr(self.master, "_janela_gestao_os", None)):
                self.master._janela_gestao_os.buscar_os()
            if hasattr(self.master, "_ultima_os_contexto"):
                self.master._ultima_os_contexto = None
            messagebox.showinfo("Recibo", f"Baixa concluida com sucesso.\n\nArquivo: {caminho_pdf}", parent=self)
            self.carregar_os_finalizadas()
        except Exception as exc:
            messagebox.showerror("Recibo", f"Nao foi possivel dar baixa na O.S.: {exc}", parent=self)


# =================================================================
# MENU PRINCIPAL
# =================================================================
class FrmMenu(ctk.CTk):
    def __init__(self, usuario="", role="VENDEDOR", senha_login=""):
        super().__init__()
        try:
            tk._default_root = self
        except Exception:
            pass
        print(f"Log: Menu Principal carregado para usuário: {usuario}")
        self.withdraw()
        self.usuario = usuario or "USUÁRIO"
        self.role = (role or "VENDEDOR").upper()
        self._senha_login = senha_login or ""
        self._backup_nuvem_executado = False
        self._primeira_instalacao_checada = False
        self._janela_gestao_os = None
        self._janela_os_atual = None
        self._ultima_os_contexto = None
        self._encerrando_aplicacao = False
        self._aviso_motor_fiscal_inicio_exibido = False
        self.title(f"Sistema Oficina de Pesca v{VERSION}")
        self.geometry("1100x750") #
        self.configure(fg_color="#0f1720")
        self._encerrando_aplicacao = False

        self.update_idletasks()
        self.geometry(f"+{(self.winfo_screenwidth() // 2) - (1100 // 2)}+{(self.winfo_screenheight() // 2) - (750 // 2)}")

        self.protocol("WM_DELETE_WINDOW", self.confirmar_saida)
        
        self._dash_mode = "COMPLETO"
        self._dashboard_auto_after_id = None
        self._dados_pendencias_dashboard = ([], [], [], []) #
        self._bg_pil_original = None
        self._bg_tk_image = None
        self._bg_canvas = None
        self._bg_cache_size = None
        self._dashboard_bg_after_id = None
        self._dashboard_bg_bound = False
        self.dashboard_content = None
        self._debug_fundo_dashboard_emitido = False
        self._menu_pronto_exibido = False
        self._status_fiscal_dashboard = {
            "texto": "Status Fiscal: verificando...",
            "cor": "#f1c40f",
            "ativo": None,
        }
        self._abandono_alerta_after_id = None

        # Adia a criação da UI para garantir root estável
        self.after(250, self.setup_ui)

        # Agendamentos de serviços em background (Isolados e seguros)
        self.after(2000, self._executar_check_versao_seguro) # Atrasado para estabilizar

    def _executar_check_versao_seguro(self):
        """Busca atualizações no GitHub de forma isolada após a carga inicial."""
        if self._encerrando_aplicacao: return
        if self.winfo_exists(): #
            def worker():
                try:
                    # Usa a nova função de verificação de atualização
                    info = self.verificar_atualizacao()
                    if info and self._eh_versao_mais_nova(info.get("versao", ""), APP_VERSION):
                        logger.info("Nova versao detectada via check automatico.")
                except Exception as e:
                    logger.warning(f"Falha silenciosa na checagem de versao: {e}")
            threading.Thread(target=worker, daemon=True).start()

    def destroy(self):
        try:
            try:
                for after_id in self.tk.call("after", "info"):
                    self.after_cancel(after_id)
            except Exception:
                pass

            self.withdraw()
            super().destroy()
            print("Encerrando threads e saindo...")
            sys.exit(0)
        except SystemExit:
            raise
        except Exception:
            fechar_sistema(self)

    def setup_ui(self):
        """Inicializa componentes que dependem da janela root estar totalmente pronta (fontes, botões)."""
        if self._encerrando_aplicacao: return
        
        # 1. Estrutura de Layout (Sidebar e Área de Conteúdo)
        self.frame_layout = ctk.CTkFrame(self, fg_color="#0f1720")
        self.frame_layout.pack(fill="both", expand=True)

        self.sidebar = ctk.CTkFrame(self.frame_layout, width=210, fg_color="#0d1b2a", corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Elementos de Identidade Visual
        ctk.CTkLabel(self.sidebar, text="🎣", font=("Arial", 34), text_color="orange", fg_color="#0d1b2a").pack(pady=(10, 2))
        ctk.CTkLabel(self.sidebar, text="OFICINA DE PESCA", font=("Arial", 12, "bold"), text_color="orange", fg_color="#0d1b2a", wraplength=190, justify="center").pack(padx=8, pady=(0, 2))
        ctk.CTkLabel(self.sidebar, text=f"👤 {self.usuario.upper()}", font=("Arial", 10), text_color="#7f8c8d", fg_color="#0d1b2a").pack(padx=8, pady=(0, 2))
        ctk.CTkLabel(self.sidebar, text=f"({self.role})", font=("Arial", 9), text_color="#555f6a", fg_color="#0d1b2a").pack(padx=8, pady=(0, 5))

        self.lbl_contador_licenca = ctk.CTkLabel(
            self.sidebar,
            text="Licença: carregando...",
            font=("Arial", 9, "bold"),
            text_color="#607d8b",
            fg_color="#0d1b2a",
            wraplength=190,
            justify="center",
        )
        self.lbl_contador_licenca.pack(padx=8, pady=(0, 5))
        self._atualizar_contador_licenca()

        self.after(2000, self._adicionar_status_nuvem) # Atrasado para estabilizar

        ctk.CTkFrame(self.sidebar, height=1, fg_color="#1e3a5f").pack(fill="x", padx=12, pady=(0, 5))

        self.sidebar_buttons = ctk.CTkFrame(self.sidebar, fg_color="#0d1b2a")
        self.sidebar_buttons.pack(fill="x", padx=6, pady=(0, 0), anchor="n")

        self.area_conteudo = ctk.CTkFrame(self.frame_layout, fg_color="#0f1720")
        self.area_conteudo.pack(side="left", fill="both", expand=True)

        self.dashboard_frame = ctk.CTkFrame(self.area_conteudo, fg_color="#0f1720")
        self.dashboard_frame.pack(fill="both", expand=True, padx=18, pady=(10, 14))
        self.dashboard_content = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.dashboard_content.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.dashboard_content.lift()
        self._configurar_fundo_dashboard()
        if not self._dashboard_bg_bound:
            self.dashboard_frame.bind("<Configure>", self._atualizar_fundo)
            self._dashboard_bg_bound = True

        # 2. Configurações Visuais
        self._aplicar_maximizacao()
        self.after(150, self._aplicar_maximizacao)
        self.after(900, self._aplicar_maximizacao)
        
        # Carrega dados após UI estar montada
        if self.winfo_exists():
            if self.role == "ADMIN":
                self.after(400, self._verificar_primeira_instalacao)
            self.after(1500, self.verificacao_ia_mensal_automatica)

        # HIERARQUIA DE BOTÕES POR PERFIL
        botoes_menu = []
        if self.role in ("ADMIN", "OFICINA"):
            botoes_menu.append(("🧑‍🤝‍🧑  PESCADORES", self.abrir_clientes, "#34495e"))
            botoes_menu.append(("📋  NOVA O.S.", self.abrir_os, "#27ae60"))
            botoes_menu.append(("🔍  CONSULTA", self.abrir_gestao_os, "#d35400"))
            botoes_menu.append(("🧾  GERAR RECIBO", self.gerar_recibo_menu_lateral, "#8e6b3b"))
        
        if self.role in ("ADMIN", "VENDEDOR"):
            botoes_menu.append(("🧾  PDV", self.abrir_pdv, "#1abc9c"))
            botoes_menu.append(("📦  ESTOQUE", self.abrir_produtos, "#e67e22"))
        
        if self.role == "ADMIN":
            botoes_menu.append(("💰  FINANCEIRO", self.abrir_caixa, "#16a085"))

        botoes_menu.append(("📱  APP CELULAR", self.abrir_app_celular_sidebar, "#25D366"))

        if self.role == "ADMIN":
            botoes_menu.extend([
                ("👤  NOVO USUÁRIO", self.abrir_cadastro_usuario, "#2980b9"),
                ("📊  RELATÓRIO", self.abrir_relatorio, "#6c3483"),
                ("🏪  DADOS OFICINA", self.abrir_dados_oficina, "#7f8c8d"),
                ("⬇️  BUSCAR ATUALIZAÇÕES", self.buscar_atualizacoes, "#2c3e50"),
            ])

        for texto, comando, cor in botoes_menu:
            self.add_btn(self.sidebar_buttons, texto, comando, cor)

        # Botão Sair fixo no rodapé
        self.add_btn(self.sidebar, "🚪  SAIR", self.confirmar_saida, "#c0392b", side="bottom")

        # Inicializa Dashboard Modular
        self.modulos_usuario = self._obter_modulos_usuario()
        self._criar_dashboard_modular()
        self._iniciar_auto_refresh_dashboard()
        self.after_idle(self._mostrar_menu_pronto)

    def _iniciar_auto_refresh_dashboard(self):
        try:
            if self._dashboard_auto_after_id is not None:
                self.after_cancel(self._dashboard_auto_after_id)
        except Exception:
            pass
        self._dashboard_auto_after_id = self.after(15000, self._auto_refresh_dashboard_tick)

    def _auto_refresh_dashboard_tick(self):
        self._dashboard_auto_after_id = None
        if self._encerrando_aplicacao or not self.winfo_exists():
            return
        self._atualizar_dashboard_modular()
        self._dashboard_auto_after_id = self.after(15000, self._auto_refresh_dashboard_tick)

    def _adicionar_status_nuvem(self):
        self.lbl_status_nuvem = ctk.CTkLabel(self.sidebar, text="Verificando nuvem...", text_color="#f1c40f", font=("Arial", 10, "bold"), fg_color="#0d1b2a")
        self.lbl_status_nuvem.pack(padx=8, pady=(0, 5))
        self._atualizar_status_nuvem()

    def _atualizar_status_nuvem(self):
        def _worker_nuvem():
            try:
                online = checar_status_firebase()
                status = "Drive: online" if online else "Drive: offline"
                cor = "#2ecc71" if online else "#e74c3c"
                try:
                    ok_token, msg_token = renovar_token_acesso_drive_se_necessario(force=False)
                    if ok_token:
                        logger.info("Token de acesso validado/renovado: %s", msg_token)
                    else:
                        logger.warning("Token de acesso não renovado: %s", msg_token)
                except Exception as exc_token:
                    logger.warning("Falha ao atualizar token de acesso: %s", exc_token)
            except Exception:
                status = "Drive: offline"
                cor = "#e74c3c"

            def _aplicar():
                if self.winfo_exists() and hasattr(self, "lbl_status_nuvem"):
                    self.lbl_status_nuvem.configure(text=status, text_color=cor)

            try:
                self.after(0, _aplicar)
            except Exception:
                pass

        threading.Thread(target=_worker_nuvem, daemon=True, name="ofp-status-nuvem").start()
        # Polling automático de rede removido.
    def _verificar_e_exibir_painel_pendencias(self):
        try:
            orcamentos, bancada, status_finalizados, aguardando_orcamento = self._consultar_pendencias_login()
        except Exception as exc:
            logger.info("Falha ao consultar pendencias do login: %s", exc)
            return
        # Painel integrado ao dashboard principal (sem popup).
        self._dados_pendencias_dashboard = (orcamentos, bancada, status_finalizados, aguardando_orcamento)
        if hasattr(self, "dashboard_frame") and self.dashboard_frame.winfo_exists():
            self._criar_dashboard_modular()


    def _obter_logo_oficina(self):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COALESCE(logo_path, '') FROM dados_oficina WHERE id = 1")
                row = cursor.fetchone()
            caminho = (row[0] if row else "") or ""
            caminho = caminho.strip()
            if caminho and os.path.exists(caminho):
                return caminho
        except Exception:
            pass
        return ""

    def _mostrar_menu_pronto(self):
        if self._menu_pronto_exibido or not self.winfo_exists() or self._encerrando_aplicacao:
            return
        self._menu_pronto_exibido = True
        try:
            # Exibe a janela apenas após concluir montagem e dados iniciais do dashboard.
            self.update_idletasks()
            self._atualizar_fundo()
            self.deiconify()
            self.lift()
            self.focus_force()
            self.update_idletasks()
        except Exception:
            pass
        self.after(450, self._checar_motor_fiscal_na_abertura)
        self._agendar_verificacao_abandono_90d()

    def _agendar_verificacao_abandono_90d(self):
        try:
            if self._abandono_alerta_after_id is not None:
                self.after_cancel(self._abandono_alerta_after_id)
        except Exception:
            pass
        # Executa após estabilizar a UI para não conflitar com popup de primeira instalação.
        self._abandono_alerta_after_id = self.after(1800, self._verificar_abandono_90_dias_na_inicializacao)

    def _parse_data_br_flex(self, valor_data: str) -> datetime | None:
        txt = str(valor_data or "").strip()
        if not txt or txt.upper() == "VAZIO":
            return None
        formatos = [
            "%d/%m/%Y",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formatos:
            try:
                return datetime.strptime(txt, fmt)
            except Exception:
                continue
        return None

    def _consultar_os_alertas_abandono(self):
        try:
            dados = listar_os_rejeitados_abandono_dashboard(
                dias_abandono_min=20,
                dias_aviso1=15,
                dias_aviso2=85,
                limite_card=20,
            )
            return dados if isinstance(dados, dict) else {}
        except Exception as exc:
            logger.info("Falha ao consultar alertas de abandono: %s", exc)
            return {}

    def _normalizar_telefone_whatsapp_alerta(self, telefone: str) -> str:
        digitos = re.sub(r"\D", "", str(telefone or ""))
        if not digitos:
            return ""
        if digitos.startswith("55") and len(digitos) >= 12:
            return digitos
        if len(digitos) in (10, 11):
            return f"55{digitos}"
        return digitos

    def _abrir_whatsapp_alerta_abandono(self, item: dict):
        cliente = str(item.get("cliente") or "Cliente").strip() or "Cliente"
        os_id = int(item.get("os_id") or 0)
        status_tipo = str(item.get("status_tipo") or "reprovado").strip().lower()
        telefone = self._normalizar_telefone_whatsapp_alerta(str(item.get("telefone") or ""))

        mensagem = (
            f"Olá {cliente}, seu equipamento referente à O.S. {os_id} está {status_tipo} sem retirada há mais de 85 dias. "
            "Conforme termo assinado, após este prazo o item está sujeito à desmontagem/venda para sucata. "
            "Favor retirar com urgência."
        )
        texto = quote_plus(mensagem)
        link = f"https://wa.me/{telefone}?text={texto}" if telefone else f"https://wa.me/?text={texto}"
        webbrowser.open(link)

    def _verificar_abandono_90_dias_na_inicializacao(self):
        self._abandono_alerta_after_id = None
        if self._encerrando_aplicacao or not self.winfo_exists():
            return

        dados = self._consultar_os_alertas_abandono()
        itens_criticos = list(dados.get("itens_aviso2") or [])
        itens_aviso = list(dados.get("itens_aviso1") or [])

        if not itens_criticos and not itens_aviso:
            return

        if itens_criticos:
            item = itens_criticos[0]
            os_id = int(item.get("os_id") or 0)
            valor = self._formatar_moeda(item.get("valor") or 0)
            dias = int(item.get("dias") or 0)

            mensagem = (
                f"Alerta Crítico: O.S. {os_id}, Valor {valor}, está há {dias} dias sem retirada. "
                "Deseja enviar mensagem de notificação via WhatsApp?"
            )
            confirmar = messagebox.askyesno("Alerta Crítico de Abandono", mensagem, parent=self)
            if confirmar:
                self._abrir_whatsapp_alerta_abandono(item)
            return

        item = itens_aviso[0]
        os_id = int(item.get("os_id") or 0)
        dias = int(item.get("dias") or 0)
        messagebox.showinfo(
            "Aviso Preventivo de Retirada",
            f"A O.S. {os_id} está há {dias} dias sem retirada. Acompanhe para evitar abandono.",
            parent=self,
        )

    def _checar_motor_fiscal_na_abertura(self):
        if self._encerrando_aplicacao or not self.winfo_exists():
            return
        self._atualizar_status_fiscal_dashboard(forcar_dashboard=True)

    def _acbr_configurado_para_uso(self) -> tuple[bool, str]:
        """Valida campos mínimos do ACBr no banco antes de considerar status ativo."""
        try:
            cfg = carregar_configuracao_fiscal()
            params = cfg.parametros_gerais if isinstance(cfg.parametros_gerais, dict) else {}

            provedor = str(params.get("provedor") or "acbr").strip().lower()
            if provedor != "acbr":
                return False, "Provedor fiscal diferente de ACBr"

            monitor_path = str(params.get("acbr_monitor_path") or "").strip()
            if not monitor_path or not os.path.isdir(monitor_path):
                return False, "ACBrMonitor não configurado"

            cert_path = str(params.get("acbr_certificado_a1_path") or params.get("certificado_a1_path") or "").strip()
            if not cert_path or not os.path.exists(cert_path):
                return False, "Certificado A1 não configurado"

            cnpj_emitente = str(params.get("emitente_cnpj") or "").strip()
            if not cnpj_emitente:
                return False, "CNPJ fiscal não configurado"

            modalidade = str(params.get("modalidade_fiscal") or "").strip().lower()
            if modalidade not in {"nfe", "nfse"}:
                return False, "Modalidade fiscal inválida"

            return True, "ACBr configurado"
        except Exception:
            return False, "Falha ao validar configuração fiscal"

    def _obter_status_fiscal_dashboard(self) -> dict:
        try:
            acbr_ok, motivo_cfg = self._acbr_configurado_para_uso()
            if not acbr_ok:
                return {"texto": "Status Fiscal: Inativo", "cor": "#e74c3c", "ativo": False}

            status_motor = verificar_status_motor_fiscal()
            ativo = bool(status_motor.get("ok"))
            if ativo:
                return {"texto": "Status Fiscal: Ativo", "cor": "#2ecc71", "ativo": True}
            return {"texto": "Status Fiscal: Inativo", "cor": "#e74c3c", "ativo": False}
        except Exception:
            return {"texto": "Status Fiscal: Inativo", "cor": "#e74c3c", "ativo": False}

    def _abrir_configuracao_acbr_dashboard(self):
        if self.role != "ADMIN":
            messagebox.showwarning(
                "Acesso restrito",
                "Somente ADMIN pode configurar o ACBr em Dados da Oficina.",
                parent=self,
            )
            return
        self.abrir_dados_oficina()

    def _atualizar_status_fiscal_dashboard(self, forcar_dashboard: bool = False):
        def _worker_fiscal_dashboard():
            status = self._obter_status_fiscal_dashboard()

            def _aplicar():
                if self._encerrando_aplicacao or not self.winfo_exists():
                    return
                anterior = bool(self._status_fiscal_dashboard.get("ativo")) if isinstance(self._status_fiscal_dashboard, dict) else None
                self._status_fiscal_dashboard = status

                if not status.get("ativo") and not self._aviso_motor_fiscal_inicio_exibido:
                    self._aviso_motor_fiscal_inicio_exibido = True
                    logger.info("Motor fiscal inativo na abertura. Isso não bloqueia o uso básico do sistema.")

                mudou = anterior is None or anterior != bool(status.get("ativo"))
                if (forcar_dashboard or mudou) and hasattr(self, "dashboard_frame") and self.dashboard_frame.winfo_exists():
                    self._criar_dashboard_modular()

            try:
                self.after(0, _aplicar)
            except Exception:
                pass

        threading.Thread(target=_worker_fiscal_dashboard, daemon=True, name="ofp-dashboard-fiscal").start()

    def _obter_modulos_usuario(self):
        try:
            flags = obter_modulos_habilitados()
            return {
                "oficina": bool(flags.get("oficina", True)),
                "pdv": bool(flags.get("pdv", False)),
            }
        except Exception as exc:
            logger.info("Falha ao ler módulos habilitados, usando fallback: %s", exc)
            return {"oficina": True, "pdv": False}

    def _formatar_moeda(self, valor):
        return f"R$ {float(valor or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _obter_indicadores_oficina(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM orcamentos_aguardo
                WHERE UPPER(COALESCE(status,'')) IN ('EM ANDAMENTO', 'APROVADO')
                """
            )
            total_bancada = int((cursor.fetchone() or [0])[0] or 0)

            cursor.execute(
                """
                SELECT COALESCE(SUM(saldo), 0)
                FROM orcamentos_aguardo
                WHERE UPPER(COALESCE(status,'')) NOT IN ('ENTREGUE', 'REPROVADO', 'CANCELADO')
                """
            )
            total_receber_abertas = float((cursor.fetchone() or [0])[0] or 0)

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM orcamentos_aguardo
                WHERE UPPER(COALESCE(status,'')) = 'AGUARDANDO ORÇAMENTO'
                """
            )
            os_pendentes = int((cursor.fetchone() or [0])[0] or 0)

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM orcamentos_aguardo
                WHERE UPPER(COALESCE(status,'')) = 'FINALIZADO'
                """
            )
            os_finalizados = int((cursor.fetchone() or [0])[0] or 0)

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM orcamentos_aguardo
                WHERE UPPER(COALESCE(status,'')) = 'FINALIZADO'
                  AND UPPER(COALESCE(status_entrega,'')) <> 'ENTREGUE'
                """
            )
            os_aguardando_retirada = int((cursor.fetchone() or [0])[0] or 0)

        dados_card = listar_os_rejeitados_abandono_dashboard(
            dias_abandono_min=20,
            dias_aviso1=15,
            dias_aviso2=85,
            limite_card=8,
        )
        rejeitados_abandono_itens = list(dados_card.get("itens_card") or [])
        rejeitados_abandono_tem_aviso1 = bool(dados_card.get("tem_aviso1"))
        rejeitados_abandono_tem_aviso2 = bool(dados_card.get("tem_aviso2"))

        return {
            "bancada": total_bancada,
            "receber": total_receber_abertas,
            "pendentes": os_pendentes,
            "finalizados": os_finalizados,
            "aguardando_retirada": os_aguardando_retirada,
            "rejeitados_abandono_itens": rejeitados_abandono_itens,
            "rejeitados_abandono_tem_aviso1": rejeitados_abandono_tem_aviso1,
            "rejeitados_abandono_tem_aviso2": rejeitados_abandono_tem_aviso2,
        }

    def _obter_indicadores_pdv(self):
        hoje = datetime.now().strftime("%d/%m/%Y")
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT COALESCE(SUM(valor), 0)
                FROM fluxo_caixa
                WHERE UPPER(COALESCE(tipo,'')) = 'ENTRADA'
                  AND UPPER(COALESCE(categoria,'')) NOT LIKE '%ORDEM DE SERV%'
                  AND UPPER(COALESCE(descricao,'')) NOT LIKE '%O.S.%'
                """
            )
            volume_vendas = float((cursor.fetchone() or [0])[0] or 0)

            cursor.execute(
                """
                SELECT COALESCE(SUM(valor), 0)
                FROM fluxo_caixa
                WHERE UPPER(COALESCE(tipo,'')) = 'ENTRADA'
                  AND data = ?
                  AND UPPER(COALESCE(categoria,'')) NOT LIKE '%ORDEM DE SERV%'
                  AND UPPER(COALESCE(descricao,'')) NOT LIKE '%O.S.%'
                """,
                (hoje,),
            )
            vendas_dia = float((cursor.fetchone() or [0])[0] or 0)

            entradas_estoque, saidas_estoque = self._obter_movimentacao_estoque_pdv(cursor)

        return {
            "volume_vendas": volume_vendas,
            "vendas_dia": vendas_dia,
            "estoque_es": f"{entradas_estoque}/{saidas_estoque}",
        }

    def _obter_movimentacao_estoque_pdv(self, cursor):
        """Lê movimentação de estoque da tabela do PDV; fallback para fluxo_caixa."""
        candidatos = [
            "movimentacao_estoque_pdv",
            "pdv_movimentacao_estoque",
            "movimentacoes_estoque_pdv",
        ]

        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tabelas = {str(r[0]).lower() for r in (cursor.fetchall() or [])}
        except Exception:
            tabelas = set()

        for tabela in candidatos:
            if tabela.lower() not in tabelas:
                continue
            try:
                cursor.execute(f"PRAGMA table_info({tabela})")
                colunas = {str(row[1]).lower() for row in (cursor.fetchall() or [])}

                # Suporta variações comuns de schema do PDV.
                if "tipo" in colunas:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {tabela} WHERE UPPER(COALESCE(tipo,''))='ENTRADA'"
                    )
                    entradas = int((cursor.fetchone() or [0])[0] or 0)
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {tabela} WHERE UPPER(COALESCE(tipo,'')) IN ('SAIDA','SAÍDA')"
                    )
                    saidas = int((cursor.fetchone() or [0])[0] or 0)
                    return entradas, saidas

                if "movimento" in colunas:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {tabela} WHERE UPPER(COALESCE(movimento,''))='ENTRADA'"
                    )
                    entradas = int((cursor.fetchone() or [0])[0] or 0)
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {tabela} WHERE UPPER(COALESCE(movimento,'')) IN ('SAIDA','SAÍDA')"
                    )
                    saidas = int((cursor.fetchone() or [0])[0] or 0)
                    return entradas, saidas
            except Exception as exc:
                logger.info("Falha ao ler movimentação no PDV (%s): %s", tabela, exc)

        # Fallback seguro: usa fluxo_caixa apenas com categorias explícitas de PDV/estoque.
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM fluxo_caixa
            WHERE UPPER(COALESCE(tipo,''))='ENTRADA'
              AND (
                    UPPER(COALESCE(categoria,'')) LIKE '%ESTOQUE PDV%'
                 OR UPPER(COALESCE(categoria,'')) LIKE '%ESTOQUE BALCAO%'
                 OR UPPER(COALESCE(categoria,'')) LIKE '%ESTOQUE BALCÃO%'
              )
            """
        )
        entradas = int((cursor.fetchone() or [0])[0] or 0)

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM fluxo_caixa
            WHERE UPPER(COALESCE(tipo,'')) IN ('SAIDA','SAÍDA')
              AND (
                    UPPER(COALESCE(categoria,'')) LIKE '%ESTOQUE PDV%'
                 OR UPPER(COALESCE(categoria,'')) LIKE '%ESTOQUE BALCAO%'
                 OR UPPER(COALESCE(categoria,'')) LIKE '%ESTOQUE BALCÃO%'
              )
            """
        )
        saidas = int((cursor.fetchone() or [0])[0] or 0)
        return entradas, saidas

    def _criar_card_dashboard(self, parent, titulo, valor):
        box = ctk.CTkFrame(parent, fg_color="#1b2635", border_width=1, border_color="#2b3646", corner_radius=10)
        box.pack(side="left", fill="both", expand=True, padx=5, pady=3)
        ctk.CTkLabel(box, text=str(valor), font=("Arial", 17, "bold"), text_color="#ecf0f1").pack(pady=(6, 2))
        ctk.CTkLabel(box, text=titulo, font=("Arial", 10, "bold"), text_color="#bdc3c7", wraplength=180, justify="center").pack(pady=(0, 6), padx=6)
        box.bind("<Button-1>", lambda _e: self.focus_force())

    def _criar_card_rejeitados_abandono(self, parent, itens_card, tem_aviso1=False, tem_aviso2=False):
        if tem_aviso2:
            fg = "#2a1a1a"
            bd = "#7f1d1d"
            titulo_cor = "#fca5a5"
            texto_cor = "#ef4444"
            vazio_cor = "#f87171"
        elif tem_aviso1:
            fg = "#2e2a16"
            bd = "#9a6b00"
            titulo_cor = "#fde68a"
            texto_cor = "#facc15"
            vazio_cor = "#fcd34d"
        else:
            fg = "#1f2530"
            bd = "#3b4b63"
            titulo_cor = "#93c5fd"
            texto_cor = "#bfdbfe"
            vazio_cor = "#93c5fd"

        box = ctk.CTkFrame(parent, fg_color=fg, border_width=1, border_color=bd, corner_radius=10)
        box.pack(side="left", fill="both", expand=True, padx=5, pady=3)

        ctk.CTkLabel(
            box,
            text="Rejeitados/Abandono",
            font=("Arial", 10, "bold"),
            text_color=titulo_cor,
            wraplength=180,
            justify="center",
        ).pack(pady=(6, 2), padx=6)

        linhas = []
        for item in (itens_card or []):
            try:
                os_id = int(item.get("os_id") or 0)
                dias = int(item.get("dias") or 0)
            except Exception:
                continue
            if os_id <= 0:
                continue
            linhas.append(f"OS {os_id} - {dias} dias")

        if not linhas:
            ctk.CTkLabel(box, text="Sem O.S.", font=("Arial", 9), text_color=vazio_cor).pack(pady=(2, 6))
            return

        ctk.CTkLabel(
            box,
            text=" | ".join(linhas),
            font=("Arial", 9),
            text_color=texto_cor,
            wraplength=190,
            justify="center",
        ).pack(pady=(2, 6), padx=6)

    def _criar_linha_cards(self, parent, cards):
        linha = ctk.CTkFrame(parent, fg_color="transparent")
        linha.pack(fill="x", pady=(0, 2))
        for titulo, valor in cards:
            self._criar_card_dashboard(linha, titulo, valor)

    def _criar_painel_pendencias_fixo(self, parent, orcamentos, bancada, status_finalizados, aguardando_orcamento):
        bloco = ctk.CTkFrame(parent, fg_color="#121a24", corner_radius=12)
        bloco.pack(fill="both", expand=True, pady=(2, 2))

        ctk.CTkLabel(
            bloco,
            text="PAINEL DE PENDÊNCIAS (ÚLTIMOS 15 DIAS)",
            font=("Arial", 12, "bold"),
            text_color="#f5f6fa",
        ).pack(anchor="w", padx=10, pady=(6, 4))

        corpo = ctk.CTkFrame(bloco, fg_color="#121a24")
        corpo.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        corpo.grid_columnconfigure((0, 1, 2, 3), weight=1)

        def _linha_item(item):
            if len(item) < 3:
                return ""
            os_id = item[0]
            data = item[1]
            cliente = item[2]
            extra = f" | {item[3]}" if len(item) > 3 and item[3] else ""
            return f"OS {os_id} | {data} | {cliente}{extra}"

        cards = [
            ("ORÇAMENTOS", "#f1c40f", orcamentos),
            ("NA BANCADA", "#3498db", bancada),
            ("FINALIZADOS", "#27ae60", status_finalizados),
            ("AGUARDANDO ORÇAMENTO", "#f39c12", aguardando_orcamento),
        ]

        for col, (titulo, cor, dados) in enumerate(cards):
            card = ctk.CTkFrame(corpo, fg_color="#1a2230", border_width=2, border_color=cor, corner_radius=12)
            card.grid(row=0, column=col, sticky="nsew", padx=4, pady=2)
            ctk.CTkLabel(card, text=f"{titulo} ({len(dados)})", font=("Arial", 11, "bold"), text_color=cor).pack(anchor="w", padx=8, pady=(6, 3))
            lista = ctk.CTkScrollableFrame(card, height=96, fg_color="#0f1720")
            lista.pack(fill="both", expand=True, padx=6, pady=(0, 6))

            if not dados:
                ctk.CTkLabel(
                    lista,
                    text="Sem pendências",
                    text_color="#9ca3af",
                    font=("Arial", 9),
                    anchor="w",
                ).pack(fill="x", padx=6, pady=6)
                continue

            for item in dados:
                try:
                    os_id = int(item[0])
                except Exception:
                    continue

                texto = _linha_item(item)
                if not texto:
                    continue

                ctk.CTkButton(
                    lista,
                    text=texto,
                    anchor="w",
                    height=24,
                    fg_color="#1f2937",
                    hover_color="#334155",
                    text_color="#e5e7eb",
                    font=("Arial", 9),
                    command=lambda oid=os_id: self._abrir_os_por_id_dashboard(oid),
                ).pack(fill="x", padx=4, pady=3)

    def _criar_dashboard_modular(self):
        if self.dashboard_content is None or not self.dashboard_content.winfo_exists():
            self.dashboard_content = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
            self.dashboard_content.place(relx=0, rely=0, relwidth=1, relheight=1)

        for w in self.dashboard_content.winfo_children():
            w.destroy()

        parent_dash = self.dashboard_content
        parent_dash.lift()

        self.modulos_usuario = self._obter_modulos_usuario()
        tem_oficina = self.modulos_usuario.get("oficina", True)
        tem_pdv = self.modulos_usuario.get("pdv", False)
        
        # Lógica de Perfil Restrito (Dashboard)
        if self.role == "VENDEDOR":
            tem_oficina = False
            tem_pdv = True
        elif self.role == "OFICINA":
            tem_oficina = True
            tem_pdv = False

        ctk.CTkLabel(
            parent_dash,
            text="Dashboard",
            font=("Arial", 28, "bold"),
            text_color="orange",
        ).pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(
            parent_dash,
            text=str(self._status_fiscal_dashboard.get("texto", "Status Fiscal: Inativo")),
            font=("Arial", 12, "bold"),
            text_color=str(self._status_fiscal_dashboard.get("cor", "#e74c3c")),
        ).pack(anchor="w", pady=(0, 10))

        # Sem seletor/manual: o dashboard abre pronto pelo perfil do usuário.
        if self.role == "OFICINA":
            mode = "OFICINA"
        elif self.role == "VENDEDOR":
            mode = "PDV"
        else:
            mode = "COMPLETO"

        oficina = self._obter_indicadores_oficina() if tem_oficina else {
            "bancada": 0,
            "receber": 0.0,
            "pendentes": 0,
            "finalizados": 0,
            "aguardando_retirada": 0,
            "rejeitados_abandono_itens": [],
            "rejeitados_abandono_tem_aviso1": False,
            "rejeitados_abandono_tem_aviso2": False,
        }
        pdv = self._obter_indicadores_pdv() if tem_pdv else {"volume_vendas": 0.0, "vendas_dia": 0.0, "estoque_es": "0/0"}

        if mode == "OFICINA":
            self._criar_linha_cards(
                parent_dash,
                [
                    ("OS na Bancada", oficina["bancada"]),
                    ("Total a Receber Oficina", self._formatar_moeda(oficina["receber"])),
                    ("Pendentes", oficina["pendentes"]),
                ],
            )
            linha_oficina_2 = ctk.CTkFrame(parent_dash, fg_color="transparent")
            linha_oficina_2.pack(fill="x", pady=(0, 2))
            self._criar_card_dashboard(linha_oficina_2, "Finalizados", oficina["finalizados"])
            self._criar_card_dashboard(linha_oficina_2, "Aguardando Retirada", oficina["aguardando_retirada"])
            self._criar_card_rejeitados_abandono(
                linha_oficina_2,
                oficina["rejeitados_abandono_itens"],
                oficina["rejeitados_abandono_tem_aviso1"],
                oficina["rejeitados_abandono_tem_aviso2"],
            )
        elif mode == "PDV":
            self._criar_linha_cards(
                parent_dash,
                [
                    ("Volume de Vendas", self._formatar_moeda(pdv["volume_vendas"])),
                    ("Entradas/Saídas de Estoque", pdv["estoque_es"]),
                    ("Vendas do Dia", self._formatar_moeda(pdv["vendas_dia"])),
                ],
            )
        else: # COMPLETO (ADMIN)
            topo = ctk.CTkFrame(parent_dash, fg_color="transparent")
            topo.pack(fill="x", pady=(0, 8))
            self._criar_card_dashboard(
                topo,
                "Consolidado - Total a Receber + Vendas",
                self._formatar_moeda(oficina["receber"] + pdv["vendas_dia"]),
            )

            split = ctk.CTkFrame(parent_dash, fg_color="transparent")
            split.pack(fill="both", expand=True)

            col_oficina = ctk.CTkFrame(split, fg_color="transparent")
            col_oficina.pack(side="left", fill="both", expand=True, padx=(0, 6))
            ctk.CTkLabel(col_oficina, text="Oficina", font=("Arial", 16, "bold"), text_color="#ecf0f1").pack(anchor="w", pady=(0, 6))
            self._criar_linha_cards(
                col_oficina,
                [
                    ("OS na Bancada", oficina["bancada"]),
                    ("Total a Receber Oficina", self._formatar_moeda(oficina["receber"])),
                    ("Pendentes", oficina["pendentes"]),
                ],
            )
            linha_admin_oficina_2 = ctk.CTkFrame(col_oficina, fg_color="transparent")
            linha_admin_oficina_2.pack(fill="x", pady=(0, 2))
            self._criar_card_dashboard(linha_admin_oficina_2, "Finalizados", oficina["finalizados"])
            self._criar_card_dashboard(linha_admin_oficina_2, "Aguardando Retirada", oficina["aguardando_retirada"])
            self._criar_card_rejeitados_abandono(
                linha_admin_oficina_2,
                oficina["rejeitados_abandono_itens"],
                oficina["rejeitados_abandono_tem_aviso1"],
                oficina["rejeitados_abandono_tem_aviso2"],
            )

            col_pdv = ctk.CTkFrame(split, fg_color="transparent")
            col_pdv.pack(side="left", fill="both", expand=True, padx=(6, 0))
            ctk.CTkLabel(col_pdv, text="PDV", font=("Arial", 16, "bold"), text_color="#ecf0f1").pack(anchor="w", pady=(0, 6))
            self._criar_linha_cards(
                col_pdv,
                [
                    ("Volume de Vendas", self._formatar_moeda(pdv["volume_vendas"])),
                    ("Entradas/Saídas de Estoque", pdv["estoque_es"]),
                    ("Vendas do Dia", self._formatar_moeda(pdv["vendas_dia"])),
                ],
            )

        if self.role in ("ADMIN", "OFICINA", "VENDEDOR"):
            try:
                orcamentos, bancada, status_finalizados, aguardando_orcamento = self._consultar_pendencias_login()
                self._dados_pendencias_dashboard = (orcamentos, bancada, status_finalizados, aguardando_orcamento)
            except Exception as exc:
                logger.info("Falha ao montar painel fixo de pendencias: %s", exc)
                orcamentos, bancada, status_finalizados, aguardando_orcamento = ([], [], [], [])

            self._criar_painel_pendencias_fixo(parent_dash, orcamentos, bancada, status_finalizados, aguardando_orcamento)

        self._atualizar_fundo()

    def _atualizar_dashboard_modular(self):
        try:
            if self.winfo_exists():
                self._criar_dashboard_modular()
        except Exception as exc:
            logger.info("Falha ao atualizar dashboard modular: %s", exc)

    def _aplicar_maximizacao(self):
        try:
            self.state("zoomed")
            return
        except Exception:
            pass

    def _janela_viva(self, janela):
        try:
            return janela is not None and bool(janela.winfo_exists())
        except Exception:
            return False

    def _carregar_os_por_id(self, os_id):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, cliente, equipamento, defeito, valor_total, sinal, saldo, status, data
                    FROM orcamentos_aguardo
                    WHERE id = ?
                    """,
                    (int(os_id),),
                )
                return cursor.fetchone()
        except Exception:
            return None

    def _abrir_os_por_id_dashboard(self, os_id):
        try:
            os_id_int = int(os_id)
        except Exception:
            messagebox.showwarning("Dashboard", f"O.S. inválida: {os_id}", parent=self)
            return

        try:
            janela = tela_os.FrmOS(self, id_orc=os_id_int, on_save_callback=self._atualizar_dashboard_modular)
            janela.update()
            janela.attributes('-topmost', True)
            janela.focus_force()
            janela.after(250, lambda: janela.attributes('-topmost', False))
            self._janela_os_atual = janela
        except Exception as exc:
            messagebox.showerror("Dashboard", f"Não foi possível abrir a O.S. {os_id_int}: {exc}", parent=self)

    def _obter_os_contexto_atual(self):
        janelas = []

        try:
            foco = self.focus_get()
            if foco is not None:
                topo = foco.winfo_toplevel()
                if topo is not None and topo is not self:
                    janelas.append(topo)
        except Exception:
            pass

        for janela in (self._janela_gestao_os, self._janela_os_atual):
            if self._janela_viva(janela) and janela not in janelas:
                janelas.append(janela)

        for janela in janelas:
            dados_os = getattr(janela, "dados_os", None)
            if dados_os:
                return dados_os

            num_oc = getattr(janela, "num_oc", None)
            if num_oc:
                dados_carregados = self._carregar_os_por_id(num_oc)
                if dados_carregados:
                    return dados_carregados

        if self._ultima_os_contexto:
            return self._ultima_os_contexto

        return None
        try:
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

    def add_btn(self, parent, texto, cmd, cor=None, side="top"):
        btn = ctk.CTkButton(
            parent,
            text=texto,
            command=cmd,
            height=32,
            font=("Arial", 11, "bold"),
            corner_radius=8,
            fg_color=(cor or "#34495e"),
            hover_color=cor or "#34495e",
            anchor="w",
            text_color="#f5f6fa",
        )
        btn.pack(fill="x", padx=10, pady=2, side=side)

    def _consultar_pendencias_login(self):
        limite = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
        fmt_data = "date(substr(data,7,4)||'-'||substr(data,4,2)||'-'||substr(data,1,2))"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT id, COALESCE(data,''), COALESCE(cliente,''), COALESCE(equipamento,'')
                FROM orcamentos_aguardo
                                WHERE UPPER(COALESCE(status,'')) = 'ORÇAMENTO'
                  AND {fmt_data} >= ?
                ORDER BY id DESC
                """,
                (limite,),
            )
            orcamentos = cursor.fetchall()

            cursor.execute(
                f"""
                SELECT id, COALESCE(data,''), COALESCE(cliente,''), COALESCE(equipamento,'')
                FROM orcamentos_aguardo
                                WHERE UPPER(COALESCE(status,'')) = 'AGUARDANDO ORÇAMENTO'
                  AND {fmt_data} >= ?
                ORDER BY id DESC
                """,
                (limite,),
            )
            aguardando_orcamento = cursor.fetchall()

            cursor.execute(
                f"""
                SELECT id, COALESCE(data,''), COALESCE(cliente,''), COALESCE(equipamento,'')
                FROM orcamentos_aguardo
                WHERE UPPER(COALESCE(status,'')) IN ('EM ANDAMENTO', 'APROVADO')
                  AND {fmt_data} >= ?
                ORDER BY id DESC
                """,
                (limite,),
            )
            bancada = cursor.fetchall()

            cursor.execute(
                f"""
                SELECT id, COALESCE(data,''), COALESCE(cliente,''), COALESCE(equipamento,'')
                FROM orcamentos_aguardo
                                WHERE UPPER(COALESCE(status,'')) = 'FINALIZADO'
                  AND {fmt_data} >= ?
                ORDER BY id DESC
                """,
                (limite,),
            )
            status_finalizados = cursor.fetchall()
        return orcamentos, bancada, status_finalizados, aguardando_orcamento

    def _exibir_popup_pendencias_login(self, orcamentos, bancada, status_finalizados):
        pop = ctk.CTkToplevel(self)
        pop.title("Painel de Pendências")
        largura = 1000
        altura = 380
        x = (pop.winfo_screenwidth() // 2) - (largura // 2)
        y = (pop.winfo_screenheight() // 2) - (altura // 2)
        pop.geometry(f"{largura}x{altura}+{x}+{y}")
        pop.resizable(False, False)
        pop.grab_set()
        pop.focus_force()
        pop.configure(fg_color="#0f1720")

        ctk.CTkLabel(
            pop,
            text="PAINEL DE PENDÊNCIAS (ÚLTIMOS 15 DIAS)",
            font=("Arial", 16, "bold"),
            text_color="#f5f6fa",
        ).pack(pady=(14, 10))

        container = ctk.CTkFrame(pop, fg_color="#0f1720")
        container.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        corpo = ctk.CTkFrame(container, fg_color="#0f1720")
        corpo.pack(fill="both", expand=True)
        corpo.grid_columnconfigure((0, 1, 2), weight=1)

        def _texto_linhas(bloco):
            linhas = []
            for item in bloco:
                if len(item) >= 3:
                    os_id = item[0]
                    data = item[1]
                    cliente = item[2]
                    extra = f" | {item[3]}" if len(item) > 3 and item[3] else ""
                    linhas.append(f"OS {os_id} | {data} | {cliente}{extra}")
            return "\n".join(linhas) if linhas else "Sem pendências"

        cards = [
            ("ORÇAMENTOS", "#f1c40f", orcamentos),
            ("NA BANCADA", "#3498db", bancada),
            ("STATUS / FINALIZADOS", "#27ae60", status_finalizados),
        ]

        for col, (titulo, cor, bloco) in enumerate(cards):
            card = ctk.CTkFrame(corpo, fg_color="#1a2230", border_width=2, border_color=cor, corner_radius=12)
            card.grid(row=0, column=col, sticky="nsew", padx=6, pady=2)
            ctk.CTkLabel(card, text=f"{titulo} ({len(bloco)})", font=("Arial", 14, "bold"), text_color=cor).pack(anchor="w", padx=12, pady=(10, 4))
            txt = ctk.CTkTextbox(card, height=230, fg_color="#0f1720", text_color="#e5e7eb", font=("Arial", 11), wrap="word")
            txt.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            txt.insert("1.0", _texto_linhas(bloco))
            txt.configure(state="disabled")

        ctk.CTkButton(pop, text="Fechar", width=140, fg_color="#7f8c8d", command=pop.destroy).pack(pady=(0, 12))

    def _atualizar_contador_licenca(self):
        try:
            texto, cor = _obter_info_licenca_visual(role=self.role)
            self.lbl_contador_licenca.configure(text=texto, text_color=cor)
        except Exception as e:
            logger.exception("Erro ao atualizar contador de licença/trial: %s", e)
            self.lbl_contador_licenca.configure(text="Licença: indisponível", text_color="#6b7280")
        finally: #
            if self.winfo_exists():
                self.after(60000, self._atualizar_contador_licenca)

    def _verificar_primeira_instalacao(self):
        """Abre tela de dados da oficina na primeira instalação (ADMIN)."""
        try:
            if self._primeira_instalacao_checada:
                return
            self._primeira_instalacao_checada = True
            if dados_oficina_sao_padrao():
                messagebox.showinfo(
                    "Primeira Instalação",
                    "Bem-vindo! Por favor, preencha os dados da sua oficina antes de começar.",
                    parent=self,
                )
                self.abrir_dados_oficina()
        except Exception as e:
            logger.exception("Erro ao verificar primeira instalação: %s", e)

    def _configurar_fundo_dashboard(self):
        if Image is None:
            logger.info("Dashboard fundo: PIL indisponível, carregamento ignorado.")
            return

        runtime_base = os.path.abspath(_base_runtime_dir())
        bundle_base = os.path.abspath(_resource_base_dir())
        modulo_base = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
        fundo_primario = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets", "fundo_menu.jpeg"))

        caminhos = [
            fundo_primario,
            os.path.join(runtime_base, "assets", "fundo_menu.jpeg"),
            os.path.join(runtime_base, "assets", "fundo_menu.jpg"),
            os.path.join(runtime_base, "assets", "fundo_menu.png"),
            os.path.join(runtime_base, "assets", "fundomenu.png"),
            os.path.join(runtime_base, "fundo_menu.jpeg"),
            os.path.join(runtime_base, "fundo_menu.jpg"),
            os.path.join(runtime_base, "fundo_menu.png"),
            os.path.join(runtime_base, "fundomenu.png"),
            os.path.join(bundle_base, "assets", "fundo_menu.jpeg"),
            os.path.join(bundle_base, "assets", "fundo_menu.jpg"),
            os.path.join(bundle_base, "assets", "fundo_menu.png"),
            os.path.join(bundle_base, "assets", "fundomenu.png"),
            os.path.join(bundle_base, "fundo_menu.jpeg"),
            os.path.join(bundle_base, "fundo_menu.jpg"),
            os.path.join(bundle_base, "fundo_menu.png"),
            os.path.join(bundle_base, "fundomenu.png"),
            os.path.join(modulo_base, "assets", "fundo_menu.jpeg"),
            os.path.join(modulo_base, "assets", "fundo_menu.jpg"),
            os.path.join(modulo_base, "assets", "fundo_menu.png"),
            os.path.join(modulo_base, "assets", "fundomenu.png"),
            _resolver_recurso_existente("assets", "fundo_menu.jpeg"),
            _resolver_recurso_existente("assets", "fundo_menu.jpg"),
            _resolver_recurso_existente("assets", "fundo_menu.png"),
            _resolver_recurso_existente("assets", "fundomenu.png"),
            _resolver_recurso_existente("fundo_menu.jpeg"),
            _resolver_recurso_existente("fundo_menu.jpg"),
            _resolver_recurso_existente("fundo_menu.png"),
            _resolver_recurso_existente("fundomenu.png"),
        ]

        img = None
        caminho_fundo_abs = ""
        ultimo_erro = ""
        for caminho in caminhos:
            try:
                caminho_abs = os.path.abspath(caminho)
                if not os.path.exists(caminho_abs):
                    continue
                img = Image.open(caminho_abs).convert("RGB")
                caminho_fundo_abs = caminho_abs
                break
            except Exception as exc:
                ultimo_erro = str(exc)

        if img is None:
            detalhe = f" Último erro: {ultimo_erro}" if ultimo_erro else ""
            logger.error("Dashboard fundo_menu não pôde ser carregado.%s", detalhe)
            self._debug_fundo_dashboard_emitido = True
            return

        try:
            escurecedor = Image.new("RGB", img.size, (0, 0, 0))
            # Overlay forte para manter contraste elevado com cards e textos claros.
            self._bg_pil_original = Image.blend(img, escurecedor, 0.66)
            logger.info("Dashboard fundo carregado com sucesso: %s", caminho_fundo_abs)
        except Exception as exc:
            logger.info("Falha ao carregar fundo do dashboard: %s", exc)
            self._bg_pil_original = None
            self._debug_fundo_dashboard_emitido = True
            return

        if self._bg_canvas is None or not self._bg_canvas.winfo_exists():
            self._bg_canvas = tk.Canvas(
                self.dashboard_frame,
                highlightthickness=0,
                bd=0,
                bg="#0f1720",
            )
            self._bg_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._bg_canvas.lower("all")
        if self.dashboard_content is not None and self.dashboard_content.winfo_exists():
            self.dashboard_content.lift()
        self._bg_cache_size = None
        self._diagnosticar_camadas_dashboard(caminho_fundo_abs)
        self._debug_fundo_dashboard_emitido = True
        self.after(80, self._atualizar_fundo)

    def _diagnosticar_camadas_dashboard(self, caminho_fundo: str):
        try:
            area_fg = self.area_conteudo.cget("fg_color") if hasattr(self, "area_conteudo") else "N/A"
            dash_fg = self.dashboard_frame.cget("fg_color") if hasattr(self, "dashboard_frame") else "N/A"
            logger.info(
                "Dashboard camada base: fundo=%s | area_conteudo.fg=%s | dashboard_frame.fg=%s",
                caminho_fundo,
                area_fg,
                dash_fg,
            )
            filhos = list(self.dashboard_frame.winfo_children()) if hasattr(self, "dashboard_frame") else []
            for idx, filho in enumerate(filhos[:12], start=1):
                try:
                    fg = filho.cget("fg_color")
                except Exception:
                    fg = "N/A"
                logger.info(
                    "Dashboard camada #%s: tipo=%s fg_color=%s",
                    idx,
                    filho.winfo_class(),
                    fg,
                )
            if filhos:
                logger.info(
                    "Dashboard possui %s componentes sobre o fundo. Componentes opacos podem ocultar parcialmente a imagem.",
                    len(filhos),
                )
        except Exception as exc:
            logger.info("Falha no diagnóstico de camadas do dashboard: %s", exc)

    def _atualizar_fundo(self, _event=None):
        if self._bg_pil_original is None or Image is None or ImageTk is None:
            return

        if self._dashboard_bg_after_id is not None:
            try:
                self.after_cancel(self._dashboard_bg_after_id)
            except Exception:
                pass
            self._dashboard_bg_after_id = None

        largura = max(self.dashboard_frame.winfo_width(), 1)
        altura = max(self.dashboard_frame.winfo_height(), 1)

        if largura < 30 or altura < 30:
            return
        
        # Cache: se já processou com esse tamanho, não processa novamente
        if hasattr(self, "_bg_cache_size") and self._bg_cache_size == (largura, altura):
            return
        self._bg_cache_size = (largura, altura)
        
        orig_largura, orig_altura = self._bg_pil_original.size

        escala = max(largura / orig_largura, altura / orig_altura)
        nova_largura = max(int(orig_largura * escala), 1)
        nova_altura = max(int(orig_altura * escala), 1)

        # Usar BILINEAR (muito mais rápido que LANCZOS, ainda com boa qualidade)
        try:
            if hasattr(Image, "Resampling"):
                resample_mode = Image.Resampling.BILINEAR
            elif hasattr(Image, "ANTIALIAS"):
                resample_mode = Image.ANTIALIAS
            else:
                resample_mode = 1  # fallback para ANTIALIAS/LANCZOS
            redimensionada = self._bg_pil_original.resize((nova_largura, nova_altura), resample_mode)
        except Exception:
            # fallback: tenta importar novamente se necessário
            from PIL import Image as PILImage
            if hasattr(PILImage, "Resampling"):
                resample_mode = PILImage.Resampling.BILINEAR
            elif hasattr(PILImage, "ANTIALIAS"):
                resample_mode = PILImage.ANTIALIAS
            else:
                resample_mode = 1
            redimensionada = self._bg_pil_original.resize((nova_largura, nova_altura), resample_mode)

        left = max((nova_largura - largura) // 2, 0)
        top = max((nova_altura - altura) // 2, 0)
        recorte = redimensionada.crop((left, top, left + largura, top + altura))

        self._bg_tk_image = ImageTk.PhotoImage(recorte)
        if hasattr(self, "_bg_canvas") and self._bg_canvas is not None:
            self._bg_canvas.delete("all")
            self._bg_canvas.create_image(0, 0, anchor="nw", image=self._bg_tk_image)
            self._bg_canvas.lower("all")
        if self.dashboard_content is not None and self.dashboard_content.winfo_exists():
            self.dashboard_content.lift()
        if hasattr(self, "sidebar") and self.sidebar is not None:
            self.sidebar.lift()

    def abrir_gestao_os(self):
        try:
            from gestao_os import FrmGestaoOrcamentos
            janela = FrmGestaoOrcamentos(self, on_os_update_callback=self._atualizar_dashboard_modular)
            self._janela_gestao_os = janela
            janela.focus_force()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir a gestão: {e}", parent=self)

    def abrir_clientes(self):
        try:
            from clientes import FrmClientes
            FrmClientes(self)
        except Exception as e: messagebox.showerror("Erro", f"Erro: {e}", parent=self)

    def abrir_os(self):
        try:
            janela = tela_os.FrmOS(self, on_save_callback=self._atualizar_dashboard_modular)
            janela.update()
            janela.attributes('-topmost', True)
            janela.focus_force()
            janela.after(300, lambda: janela.attributes('-topmost', False))
            self._janela_os_atual = janela
        except Exception as e:
            messagebox.showerror("Erro", f"Erro: {e}", parent=self)

    def abrir_pdv(self):
        try:
            from pdv import FrmPDV
            janela = FrmPDV(self, on_os_update_callback=self._atualizar_dashboard_modular)
            janela.focus_force()
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao abrir PDV: {e}", parent=self)

    def abrir_pdv_v2(self):
        """Inicia o fluxo limpo do PDV v2 (Refatorado).
        Esta função prepara o terreno para a futura substituição do PDV atual."""
        try:
            messagebox.showinfo("PDV v2", "O fluxo do novo PDV v2 está sendo preparado. O ambiente de vendas será modernizado em breve.")
            # TODO: Instanciar a nova classe do PDV v2 aqui após a refatoração completa.
        except Exception as e:
            logger.exception("Falha ao abrir ambiente do PDV v2: %s", e)

    def buscar_atualizacoes(self):
        try:
            info_versao = obter_info_nova_versao() or {}
            versao_remota = str(info_versao.get("versao", "")).strip()
            url_download = str(
                info_versao.get("url_download")
                or info_versao.get("download")
                or info_versao.get("download_url")
                or ""
            ).strip()

            if versao_remota and self._eh_versao_mais_nova(versao_remota, APP_VERSION):
                if not url_download:
                    messagebox.showwarning(
                        "Atualizações",
                        f"Nova versão disponível: {versao_remota}, mas sem URL de download configurada.",
                        parent=self,
                    )
                    return

                confirmar = messagebox.askyesno(
                    "Atualizações",
                    f"Nova versão disponível: {versao_remota}\n"
                    f"Versão atual: {APP_VERSION}\n\n"
                    "Deseja baixar e instalar agora?\n"
                    "O sistema pode ser fechado para concluir a atualização.",
                    parent=self,
                )
                if not confirmar:
                    return

                messagebox.showinfo(
                    "Atualizações",
                    "Iniciando download da atualização...",
                    parent=self,
                )
                # Chamada explícita do fluxo de atualização após o aviso informativo.
                self.after(10, lambda: self._iniciar_download_atualizacao(url_download))
                return

            if versao_remota:
                messagebox.showinfo(
                    "Atualizações",
                    f"Seu sistema já está atualizado.\nVersão atual: {APP_VERSION}",
                    parent=self,
                )
                return

            messagebox.showwarning(
                "Atualizações",
                "Não foi possível obter informações de versão agora. Tente novamente em instantes.",
                parent=self,
            )
        except Exception as e:
            messagebox.showerror("Atualizações", f"Erro ao buscar atualizações: {e}", parent=self)

    def _iniciar_download_atualizacao(self, url_download: str):
        def _worker_update():
            ok, msg = executar_atualizacao(
                url_download,
                app_executavel=sys.executable,
                processo_pid=os.getpid(),
                silenciosa=True,
            )

            def _finalizar():
                if ok:
                    messagebox.showinfo(
                        "Atualizações",
                        "Download concluído e instalador iniciado com sucesso.",
                        parent=self,
                    )
                else:
                    messagebox.showerror(
                        "Atualizações",
                        f"Falha ao atualizar: {msg}",
                        parent=self,
                    )

            try:
                self.after(0, _finalizar)
            except Exception:
                _finalizar()

        threading.Thread(target=_worker_update, daemon=True, name="ofp-update-manual").start()

    def abrir_produtos(self):
        FrmProdutos(self)

    def abrir_caixa(self):
        try:
            from tela_financeiro import FrmFinanceiro
            FrmFinanceiro(self)
        except Exception as e: messagebox.showerror("Erro", f"Erro: {e}", parent=self)

    def gerar_recibo_menu_lateral(self):
        FrmBaixaRecibo(self)

    def _candidatos_pasta_apk(self) -> list[str]:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return [
            os.path.join(base_dir, "PACOTE_ENVIO", "apk_celular"),
            os.path.join(base_dir, "dist", "apk_celular"),
            os.path.join(base_dir, "apk_celular_distribuicao"),
            os.path.join(base_dir, "android_apk", "app", "build", "outputs", "apk", "debug"),
        ]

    def _resolver_pasta_apk_distribuicao(self) -> str:
        for pasta in self._candidatos_pasta_apk():
            if os.path.isdir(pasta):
                return pasta
        return ""

    def _resolver_arquivo_apk(self) -> str:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidatos = [
            os.path.join(base_dir, "PACOTE_ENVIO", "apk_celular", "Oficina_Pesca_WebView.apk"),
            os.path.join(base_dir, "apk_celular_distribuicao", "oficina_app_signed.apk"),
            os.path.join(base_dir, "android_apk", "app", "build", "outputs", "apk", "debug", "app-debug.apk"),
        ]

        for dist_apk_dir in [os.path.join(base_dir, "dist", "apk_celular")]:
            if os.path.isdir(dist_apk_dir):
                for nome in sorted(os.listdir(dist_apk_dir), reverse=True):
                    if nome.lower().endswith(".apk"):
                        candidatos.append(os.path.join(dist_apk_dir, nome))

        for caminho in candidatos:
            if os.path.exists(caminho):
                return caminho
        return ""

    def abrir_app_celular_sidebar(self):
        tipo_licenca = str(obter_tipo_licenca() or "").strip().upper()
        if tipo_licenca == "TRIAL":
            messagebox.showwarning(
                "APP CELULAR",
                "Atenção: A integração com o App Celular é exclusiva para licenças Ativas. Por favor, ative sua licença para utilizar este recurso.",
                parent=self,
            )
            return

        pasta_apk = self._resolver_pasta_apk_distribuicao()
        if not pasta_apk:
            messagebox.showwarning(
                "APP CELULAR",
                "Nenhuma pasta de distribuição do APK foi encontrada ainda. Gere o build da versão atual para disponibilizar o app.",
                parent=self,
            )
            return
        self.abrir_pasta_apk_distribuicao()

    def abrir_pasta_apk_distribuicao(self):
        pasta = self._resolver_pasta_apk_distribuicao()
        if not pasta:
            messagebox.showwarning("APK", "Pasta de distribuição do APK não encontrada.", parent=self)
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(pasta)  # type: ignore[attr-defined]
            else:
                webbrowser.open(pasta)
        except Exception as exc:
            messagebox.showerror("APK", f"Não foi possível abrir a pasta do APK: {exc}", parent=self)

    def abrir_relatorio(self):
        if self.role != "ADMIN":
            messagebox.showwarning("Acesso negado", "Somente ADMIN pode acessar o relatório.", parent=self)
            return
        FrmRelatorioDesempenho(self)

    def abrir_dados_oficina(self):
        if self.role != "ADMIN":
            messagebox.showwarning("Acesso negado", "Somente ADMIN pode alterar os dados da oficina.", parent=self)
            return

        # Evita duplicidade e elimina loop de reabertura.
        for widget in self.winfo_children():
            if isinstance(widget, FrmDadosOficina) and widget.winfo_exists():
                widget.lift()
                widget.focus_force()
                return

        try:
            self.update_idletasks()
            self.after_idle(lambda: FrmDadosOficina(self))
        except Exception as e:
            logger.exception("Erro ao abrir tela de Dados da Oficina: %s", e)
            messagebox.showerror("Erro", f"Não foi possível abrir a tela de Dados da Oficina: {e}", parent=self)

    def abrir_cadastro_usuario(self):
        if self.role != "ADMIN":
            messagebox.showwarning("Acesso negado", "Somente ADMIN pode cadastrar usuários.", parent=self)
            return
        FrmCadastroUsuarios(self)

    def _parse_manifesto(self, conteudo: str) -> dict:
        """
        Analisa o conteúdo de um manifesto de versão (JSON ou TXT) e retorna um dicionário.
        Copiado de config.py para uso local.
        """
        bruto = str(conteudo or "").strip()
        if not bruto:
            return {}

        # Tenta JSON primeiro
        try:
            data_json = json.loads(bruto)
            if isinstance(data_json, dict):
                return data_json
        except Exception:
            pass

        # Formato TXT: chave=valor / chave: valor
        data_txt = {}
        for linha in bruto.splitlines():
            item = linha.strip()
            if not item or item.startswith("#"):
                continue
            if "=" in item:
                k, v = item.split("=", 1)
            elif ":" in item:
                k, v = item.split(":", 1)
            else:
                # Permite arquivo com apenas "1.2.3"
                if re.match(r"^\d+(\.\d+)+$", item):
                    data_txt.setdefault("versao", item)
                continue

            chave = str(k or "").strip().lower()
            valor = str(v or "").strip()
            if not chave:
                continue
            data_txt[chave] = valor

        if not data_txt:
            return {}

        # Normaliza aliases comuns
        versao = data_txt.get("versao") or data_txt.get("version") or data_txt.get("tag") or ""
        novidades = data_txt.get("novidades") or data_txt.get("changelog") or data_txt.get("notes") or ""
        url_download = (
            data_txt.get("url_download")
            or data_txt.get("download")
            or data_txt.get("url")
            or data_txt.get("download_url")
            or ""
        )

        saida = {
            "versao": str(versao).strip(),
            "novidades": str(novidades).strip(),
            "url_download": str(url_download).strip(),
        }
        return {k: v for k, v in saida.items() if v}

    def verificar_atualizacao(self) -> dict:
        """Retorna dados de atualização de forma resiliente, sem interromper a UI."""
        try:
            info_versao = obter_info_nova_versao() or {}
            if not isinstance(info_versao, dict):
                return {}

            versao = str(info_versao.get("versao", "")).strip()
            novidades = str(info_versao.get("novidades", "")).strip()
            url_download = str(
                info_versao.get("url_download")
                or info_versao.get("download")
                or info_versao.get("url")
                or ""
            ).strip()

            resultado = {
                "versao": versao,
                "novidades": novidades,
                "url_download": url_download,
            }
            return {k: v for k, v in resultado.items() if v}
        except Exception as e:
            logger.warning("Falha ao verificar atualizacao: %s", e)
            return {}

    def _eh_versao_mais_nova(self, versao_remota: str, versao_local: str) -> bool:
        try:
            return bool(eh_versao_mais_nova(versao_remota, versao_local))
        except Exception:
            return False

    def _detectar_ip_local(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = str(s.getsockname()[0] or "").strip()
            finally:
                s.close()
            if ip and ip != "127.0.0.1":
                return ip
        except Exception:
            pass
        return "127.0.0.1"

    def _url_web_mobile(self) -> str:
        base_publica = str(URL_APP_CELULAR_PUBLICA or "").strip()
        if base_publica:
            if "://" not in base_publica:
                base_publica = f"https://{base_publica}"
            return base_publica.rstrip("/")

        base = str(SERVIDOR_URL or "http://localhost:8000").strip()
        if not base:
            base = "http://localhost:8000"
        if "://" not in base:
            # Adiciona um aviso se o modo é rede mas o servidor_url ainda é localhost
            if obter_modo_operacao() == "rede" and ("localhost" in base or "127.0.0.1" in base):
                messagebox.showwarning(
                    "Configuração de Rede",
                    "O sistema está em modo 'rede', mas 'servidor_url' em config.cfg ainda aponta para 'localhost'. "
                    "Dispositivos externos não conseguirão se conectar. Altere para o IP da máquina servidora.",
                    parent=self)
            base = f"http://{base}"

        parts = urlsplit(base)
        scheme = parts.scheme or "http"
        host = str(parts.hostname or "").lower()
        porta = parts.port
        caminho = parts.path.rstrip("/")

        if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1", ""}:
            ip_local = self._detectar_ip_local()
            host_port = f"{ip_local}:{porta}" if porta else ip_local
        else:
            host_port = parts.netloc

        return urlunsplit((scheme, host_port, caminho, "", "")).rstrip("/")

    def _servidor_mobile_online(self, url_base: str) -> bool:
        alvo = f"{url_base.rstrip('/')}/web/login"
        try:
            req = Request(alvo, method="GET", headers={"User-Agent": "OficinaPesca/1.0"})
            with urlopen(req, timeout=2) as resp:
                codigo = int(getattr(resp, "status", 0) or 0)
                return 200 <= codigo < 500
        except Exception:
            return False

    def _iniciar_servidor_mobile(self) -> bool:
        candidatos = [
            os.path.join(DIRETORIO_RECURSOS, "iniciar_servidor.bat"),
            os.path.join(os.getcwd(), "iniciar_servidor.bat"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "iniciar_servidor.bat"),
        ]
        for arq in candidatos:
            if not os.path.exists(arq):
                continue
            try:
                if hasattr(os, "startfile"):
                    os.startfile(arq)  # type: ignore[attr-defined]
                else:
                    webbrowser.open(arq, new=1)
                logger.info("Servidor mobile iniciado por: %s", arq)
                return True
            except Exception:
                continue
        return False

    def enviar_app_whatsapp_admin(self):
        if self.role != "ADMIN":
            messagebox.showwarning("Acesso negado", "Somente ADMIN pode compartilhar o app mobile.", parent=self)
            return

        url_app = self._url_web_mobile()
        link_login_mobile = url_app if str(url_app).lower().endswith("/app") else f"{url_app}/app"
        usa_url_publica = bool(str(URL_APP_CELULAR_PUBLICA or "").strip())

        if not usa_url_publica and obter_modo_operacao() != "rede":
            messagebox.showwarning(
                "APP Celular",
                "Para compartilhar o APP Celular fora da rede local, preencha 'url_app_celular_publica' no config.cfg.\n"
                "Atualmente, o sistema está em modo 'local' ou sem URL pública configurada.",
                parent=self)
            return

        if not usa_url_publica and not self._servidor_mobile_online(url_app):
            iniciou = self._iniciar_servidor_mobile()
            if iniciou:
                messagebox.showwarning(
                    "APP Celular",
                    "Servidor mobile estava desligado e foi iniciado agora.\n"
                    "Aguarde alguns segundos e clique novamente em APP CELULAR.",
                    parent=self,
                )
            else:
                messagebox.showwarning(
                    "APP Celular",
                    "Servidor mobile nao esta ativo.\n"
                    "Abra o atalho 'Iniciar Servidor Oficina' e tente novamente.",
                    parent=self,
                )
            return

        texto = (
            "Olá!\n\n"
            "Segue o link para acessar o sistema Oficina de Pesca pelo celular:\n"
            f"{link_login_mobile}\n\n"
            "Para instalar o aplicativo, anexe o arquivo APK que está junto nesta mensagem.\n"
            "Se precisar de ajuda para instalar, me avise!\n"
        )

        if not usa_url_publica and ("127.0.0.1" in url_app or "localhost" in url_app):
            messagebox.showwarning(
                "APP Celular",
                "Nao foi possivel detectar um IP de rede para o servidor.\n"
                "Verifique se o computador esta conectado na rede local.",
                parent=self,
            )

        caminho_apk = self._resolver_arquivo_apk()

        # Caminho da Área de Trabalho do usuário
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        nome_destino = os.path.basename(caminho_apk) if caminho_apk else "app-oficina-pesca.apk"
        apk_destino = os.path.join(desktop, nome_destino)

        if caminho_apk and os.path.exists(caminho_apk):
            try:
                shutil.copy2(caminho_apk, apk_destino)
                self.clipboard_clear()
                self.clipboard_append(apk_destino)
                try:
                    os.startfile(desktop)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Erro ao copiar APK para a Área de Trabalho: {e}")
            texto += (f"\nO arquivo APK foi copiado para sua Área de Trabalho como '{nome_destino}'.\n"
                      f"O caminho já está copiado para sua área de transferência.\n"
                      f"No WhatsApp, clique no clipe de anexar e selecione o arquivo na Área de Trabalho.\n")
        else:
            texto += ("\nO arquivo APK não foi encontrado.\n")

        texto_codificado = quote_plus(texto)
        link_whatsapp = f"https://api.whatsapp.com/send?text={texto_codificado}"
        link_whatsapp_reserva = f"https://wa.me/?text={texto_codificado}"
        link_whatsapp_reserva_2 = f"https://web.whatsapp.com/send?text={texto_codificado}"

        abriu = False
        try:
            abriu = bool(webbrowser.open(link_whatsapp, new=2))
        except Exception:
            abriu = False

        if not abriu:
            try:
                abriu = bool(webbrowser.open(link_whatsapp_reserva, new=2))
            except Exception:
                abriu = False

        if not abriu:
            try:
                abriu = bool(webbrowser.open(link_whatsapp_reserva_2, new=2))
            except Exception:
                abriu = False

        if not abriu and hasattr(os, "startfile"):
            try:
                os.startfile(link_whatsapp)  # type: ignore[attr-defined]
                abriu = True
            except Exception:
                abriu = False

        if abriu:
            messagebox.showinfo(
                "WhatsApp",
                "Mensagem aberta no WhatsApp com o link do app mobile.",
                parent=self,
            )
        else:
            try:
                self.clipboard_clear()
                self.clipboard_append(link_whatsapp)
            except Exception:
                pass
            messagebox.showwarning(
                "WhatsApp",
                "Não foi possível abrir automaticamente.\n\n"
                "O link foi copiado para a área de transferência.",
                parent=self,
            )

    def _montar_relatorio_ia(self) -> str:
        pontos_alerta = []
        pontos_ok = []
        sugestoes = []

        try:
            modo = obter_modo_operacao()
            pontos_ok.append(f"Modo de operacao: {modo.upper()}")

            if modo == "rede" and ("localhost" in str(SERVIDOR_URL).lower() or "127.0.0.1" in str(SERVIDOR_URL)):
                pontos_alerta.append(
                    "Modo REDE com servidor_url local. Celulares na rede nao conseguem acessar usando localhost."
                )
                sugestoes.append("Definir app.servidor_url com IP da maquina servidora (ex.: http://192.168.1.10:8000).")

            email_nuvem = (obter_email_backup_nuvem() or "").strip()
            if not email_nuvem:
                pontos_alerta.append("E-mail de backup em nuvem nao configurado.")
                sugestoes.append("Preencher o e-mail em DADOS OFICINA para habilitar backup automatico.")
            else:
                pontos_ok.append(f"E-mail de nuvem configurado: {email_nuvem}")

            if dados_oficina_sao_padrao():
                pontos_alerta.append("Dados da oficina ainda estao no padrao.")
                sugestoes.append("Preencher nome, endereco e contatos em DADOS OFICINA.")
            else:
                pontos_ok.append("Dados da oficina configurados.")

            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM usuarios WHERE UPPER(role)='ADMIN'")
                admins = int(cur.fetchone()[0] or 0)
                cur.execute("SELECT COUNT(*) FROM clientes")
                total_clientes = int(cur.fetchone()[0] or 0)
                cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo")
                total_os = int(cur.fetchone()[0] or 0)

            if admins <= 1:
                pontos_alerta.append("Apenas 1 usuario ADMIN cadastrado.")
                sugestoes.append("Cadastrar um segundo ADMIN para contingencia.")
            else:
                pontos_ok.append(f"Quantidade de ADMINs: {admins}")

            pontos_ok.append(f"Clientes cadastrados: {total_clientes}")
            pontos_ok.append(f"Ordens/Orcamentos registrados: {total_os}")

            info_versao = obter_info_nova_versao() or {}
            versao_remota = str(info_versao.get("versao", "")).strip()
            if versao_remota and self._eh_versao_mais_nova(versao_remota, APP_VERSION):
                pontos_alerta.append(f"Nova versao disponivel: {versao_remota} (atual: {APP_VERSION}).")
                sugestoes.append("Planejar atualizacao para receber correcoes e melhorias.")
            else:
                pontos_ok.append("Versao atual sem alerta de atualizacao obrigatoria.")

        except Exception as e:
            pontos_alerta.append(f"Falha ao executar analise: {e}")

        linhas = [
            "ANALISE INTELIGENTE - OFICINA DE PESCA",
            "",
            "Pontos de atencao:",
        ]
        if pontos_alerta:
            linhas.extend([f"- {p}" for p in pontos_alerta])
        else:
            linhas.append("- Nenhum alerta critico encontrado.")

        linhas.append("")
        linhas.append("Pontos positivos:")
        if pontos_ok:
            linhas.extend([f"- {p}" for p in pontos_ok])
        else:
            linhas.append("- Sem dados suficientes.")

        linhas.append("")
        linhas.append("Sugestoes de melhoria:")
        if sugestoes:
            linhas.extend([f"- {s}" for s in sugestoes])
        else:
            linhas.append("- Continuar monitoramento semanal do sistema.")

        linhas.append("")
        linhas.append(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        return "\n".join(linhas)

    def _salvar_relatorio_ia_em_arquivo(self, relatorio: str, sufixo: str = "manual") -> str:
        pasta_relatorios = os.path.join(os.path.dirname(CAMINHO_BANCO), "logs", "ia_relatorios")
        os.makedirs(pasta_relatorios, exist_ok=True)
        nome_arquivo = f"analise_ia_{sufixo}.txt"
        caminho_arquivo = os.path.join(pasta_relatorios, nome_arquivo)
        with open(caminho_arquivo, "w", encoding="utf-8") as f:
            f.write(relatorio)
        return caminho_arquivo

    def verificacao_ia_mensal_automatica(self):
        if self.role != "ADMIN":
            return

        try:
            chave_mes = datetime.now().strftime("%Y-%m")
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT valor FROM configuracoes WHERE chave = 'ia_relatorio_mes'")
                row = cur.fetchone()
                ultimo_mes = str(row[0] or "").strip() if row else ""

                if ultimo_mes == chave_mes:
                    return

                relatorio = self._montar_relatorio_ia()
                sufixo = f"mensal_{chave_mes.replace('-', '_')}"
                caminho_arquivo = self._salvar_relatorio_ia_em_arquivo(relatorio, sufixo=sufixo)

                cur.execute(
                    "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('ia_relatorio_mes', ?)",
                    (chave_mes,)
                )
                cur.execute(
                    "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('ia_relatorio_arquivo', ?)",
                    (caminho_arquivo,)
                )
                conn.commit()

            logger.info("Analise IA mensal gerada em arquivo: %s", caminho_arquivo)
        except Exception as e:
            logger.exception("Falha na geracao automatica do relatorio IA mensal: %s", e)

    def confirmar_saida(self):
        if messagebox.askokcancel('Sair', 'Deseja encerrar o programa?', parent=self):
            self._encerrar_aplicacao()
        else:
            self.focus_force()

    def _encerrar_aplicacao(self):
        self._encerrando_aplicacao = True
        try:
            for after_id in self.tk.call('after', 'info'):
                self.after_cancel(after_id)
        except Exception:
            pass
        try:
            self.destroy()
        except SystemExit:
            raise
        except Exception:
            fechar_sistema(self)

    def verificacao_ia_melhorias(self):
        if self.role != "ADMIN":
            messagebox.showwarning("Acesso negado", "Somente ADMIN pode executar a analise.", parent=self)
            return

        relatorio = self._montar_relatorio_ia()
        caminho_arquivo = ""
        try:
            sufixo = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            caminho_arquivo = self._salvar_relatorio_ia_em_arquivo(relatorio, sufixo=sufixo)
        except Exception as e:
            logger.warning("Nao foi possivel salvar relatorio IA manual em arquivo: %s", e)

        win = ctk.CTkToplevel(self)
        win.title("Analise IA de Melhorias")
        win.geometry("780x560")
        win.resizable(True, True)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(
            win,
            text="Analise Inteligente de Melhorias",
            font=("Arial", 18, "bold"),
            text_color="orange",
        ).pack(pady=(14, 8))

        if caminho_arquivo:
            ctk.CTkLabel(
                win,
                text=f"Arquivo gerado: {caminho_arquivo}",
                font=("Arial", 10),
                text_color="#95a5a6",
                wraplength=740,
                justify="left",
            ).pack(pady=(0, 6), padx=14, anchor="w")

        txt = ctk.CTkTextbox(win, wrap="word")
        txt.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        txt.insert("1.0", relatorio)
        txt.configure(state="disabled")

        f_btn = ctk.CTkFrame(win, fg_color="#0f1720")
        f_btn.pack(fill="x", padx=14, pady=(0, 12))

        def copiar_relatorio():
            try:
                win.clipboard_clear()
                win.clipboard_append(relatorio)
                messagebox.showinfo("Analise IA", "Relatorio copiado para a area de transferencia.", parent=win)
            except Exception as e:
                messagebox.showwarning("Analise IA", f"Nao foi possivel copiar: {e}", parent=win)

        ctk.CTkButton(f_btn, text="Copiar relatorio", width=150, fg_color="#2980b9", command=copiar_relatorio).pack(side="left")
        ctk.CTkButton(f_btn, text="Fechar", width=120, fg_color="#7f8c8d", command=win.destroy).pack(side="right")

    def configurar_email_nuvem_admin(self) -> str:
        if self.role != "ADMIN":
            messagebox.showwarning("Acesso negado", "Somente ADMIN pode configurar o e-mail de nuvem.", parent=self)
            return ""

        email_atual = obter_email_backup_nuvem()
        email = simpledialog.askstring(
            "E-mail da nuvem do cliente",
            "Informe o e-mail para backup automático na nuvem do cliente:",
            initialvalue=email_atual,
            parent=self,
        )
        if email is None:
            return email_atual

        ok, msg = salvar_email_backup_nuvem(email)
        if ok:
            messagebox.showinfo("Nuvem", msg, parent=self)
            return email.strip().lower()
        messagebox.showerror("Nuvem", msg, parent=self)
        return ""

    def executar_sincronizacao_nuvem(self):
        """Baixa o banco mais recente do Google Drive e substitui o arquivo local."""
        import threading

        if not messagebox.askyesno(
            "Sincronizar com Google Drive",
            "Baixar o banco de dados mais recente do Google Drive?\n\n"
            "⚠  O banco local atual será substituído.\n"
            "Um backup automático será salvo antes.",
            parent=self,
        ):
            return

        def _executar():
            ok, msg = sincronizar_dados_da_nuvem(self.usuario, self._senha_login)
            self.after(0, lambda: _finalizar(ok, msg))

        def _finalizar(ok, msg):
            if ok:
                messagebox.showinfo("Sincronização Concluída", msg, parent=self)
            else:
                nao_autenticado = any(
                    t in (msg or "").lower()
                    for t in ("não autenticado", "nao autenticado", "não está conectado", "nao esta conectado")
                )
                if nao_autenticado:
                    if messagebox.askyesno(
                        "Google Drive",
                        "Você ainda não está conectado ao Google Drive.\n\n"
                        "Deseja conectar agora?\n"
                        "(O navegador será aberto para autenticação)",
                        parent=self,
                    ):
                        self.conectar_google_drive_oficial()
                else:
                    messagebox.showerror("Erro na Sincronização", msg, parent=self)

        threading.Thread(target=_executar, daemon=True).start()

    def backup_nuvem_automatico_admin(self):
        if self.role != "ADMIN" or self._backup_nuvem_executado:
            return
        self._backup_nuvem_executado = True

        if obter_modo_operacao() != "rede":
            logger.info("Backup nuvem automático ignorado: sistema em modo local.")
            return

        email = obter_email_backup_nuvem()
        if not email:
            # E-mail não configurado — sem popup automático; usuário configura em DADOS OFICINA
            logger.info("Backup nuvem: e-mail não configurado. Acesse DADOS OFICINA para configurar.")
            return

        if not self._senha_login:
            messagebox.showwarning(
                "Nuvem",
                "Não foi possível autenticar backup automático (senha de login indisponível).",
                parent=self,
            )
            return

        ok, msg = enviar_backup_nuvem(email, self.usuario, self._senha_login)
        if ok:
            messagebox.showinfo("Nuvem", msg, parent=self)
        else:
            msg_normalizada = str(msg or "").lower()
            indisponivel = (
                "conexão recusada" in msg_normalizada
                or "conexao recusada" in msg_normalizada
                or "10061" in msg_normalizada
                or "servidor de nuvem indisponível" in msg_normalizada
            )
            if indisponivel:
                logger.info("Backup nuvem não executado agora: %s", msg)
            else:
                messagebox.showwarning("Nuvem", msg, parent=self)


def iniciar_sistema(usuario: str = "", role: str = "VENDEDOR", senha_login: str = ""):
    """Ponto de entrada do menu principal chamado pelo fluxo de login."""
    app = FrmMenu(usuario=usuario, role=role, senha_login=senha_login)
    app.mainloop()


if __name__ == "__main__":
    raise SystemExit("Fluxo direto desabilitado. Execute login.py para autenticar.")