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
import shutil
import zipfile
import webbrowser
import socket
import sys
import json
import csv
import configparser
import traceback
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from util_recibo import gerar_recibo_entrega
from config import (
    CAMINHO_BANCO,
    APP_VERSION,
)

# --- Funções auxiliares para resolver caminhos de recursos em ambiente PyInstaller ---
def _base_runtime_dir() -> str:
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

def _resource_base_dir() -> str:
    return getattr(sys, "_MEIPASS", _base_runtime_dir())

def _resolver_recurso(*partes: str) -> str:
    return os.path.join(_resource_base_dir(), *partes)
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
    obter_tipo_licenca,
    eh_versao_mais_nova,
    obter_modo_operacao,
    URL_APP_CELULAR_PUBLICA,
    WHATSAPP_ADMIN_DESTINO,
    obter_info_nova_versao,
    sincronizar_dados_da_nuvem,
    conectar_google_drive_usuario,
    garantir_banco_no_drive_usuario,
    iniciar_sincronizacao_hibrida_nuvem,
)

logger = get_logger(__name__)

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
                    compatibilidade TEXT,
                    quantidade_minima INTEGER DEFAULT 3
                )
            """)
            cursor.execute("PRAGMA table_info(produtos)")
            colunas = {str(row[1] or "") for row in cursor.fetchall()}
            if "compatibilidade" not in colunas:
                cursor.execute("ALTER TABLE produtos ADD COLUMN compatibilidade TEXT")
            if "quantidade_minima" not in colunas:
                cursor.execute("ALTER TABLE produtos ADD COLUMN quantidade_minima INTEGER DEFAULT 3")
            conn.commit()
        logger.info("Tabelas verificadas e prontas.")
    except Exception as e:
        logger.exception("Erro ao criar tabelas de produtos: %s", e)

# 3º: CHAMA A FUNÇÃO
verificar_e_criar_tabelas()

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
        
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (1100 // 2)
        y = (self.winfo_screenheight() // 2) - (700 // 2)
        self.geometry(f"+{x}+{y}")

        self.lift()
        self.focus_force()
        self.grab_set() 

        ctk.CTkLabel(self, text="🛠️ GESTÃO DE ESTOQUE E MARGEM", font=("Arial", 22, "bold")).pack(pady=15)

        f_busca = ctk.CTkFrame(self)
        f_busca.pack(pady=(0, 8), padx=20, fill="x")
        self.ent_busca_estoque = ctk.CTkEntry(
            f_busca,
            placeholder_text="Buscar por Nome ou Compatibilidade",
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

        self.ent_custo = ctk.CTkEntry(f_inputs, placeholder_text="R$ Custo", width=90)
        self.ent_custo.grid(row=0, column=2, padx=5, pady=5)

        # NOVO CAMPO: % Margem
        self.ent_margem = ctk.CTkEntry(f_inputs, placeholder_text="% Margem", width=90)
        self.ent_margem.grid(row=0, column=3, padx=5, pady=5)
        # Ao digitar na margem, ele pode calcular a venda automaticamente
        self.ent_margem.bind("<KeyRelease>", self.calcular_venda_por_margem)

        self.ent_venda = ctk.CTkEntry(f_inputs, placeholder_text="R$ Venda", width=90)
        self.ent_venda.grid(row=0, column=4, padx=5, pady=5)

        self.ent_qtd = ctk.CTkEntry(f_inputs, placeholder_text="Qtd", width=60)
        self.ent_qtd.grid(row=0, column=5, padx=5, pady=5)

        self.ent_qtd_min = ctk.CTkEntry(f_inputs, placeholder_text="Qtd Min (3)", width=90)
        self.ent_qtd_min.grid(row=0, column=6, padx=5, pady=5)
        self.ent_qtd_min.insert(0, "3")

        # BOTÕES
        ctk.CTkButton(f_inputs, text="Salvar", fg_color="green", width=100, command=self.salvar_produto).grid(row=0, column=7, padx=5)
        ctk.CTkButton(f_inputs, text="Excluir", fg_color="red", width=100, command=self.excluir_produto).grid(row=0, column=8, padx=5)

        f_acoes = ctk.CTkFrame(self)
        f_acoes.pack(pady=(0, 6), padx=20, fill="x")
        ctk.CTkButton(f_acoes, text="📥 Importar Produtos", fg_color="#2980b9",
            hover_color="#1f618d", width=180,
            command=self.importar_produtos).pack(side="left", padx=(8, 6), pady=6)
        ctk.CTkButton(f_acoes, text="📤 Exportar Produtos", fg_color="#16a085",
            hover_color="#117864", width=180,
            command=self.exportar_produtos).pack(side="left", padx=6, pady=6)
        ctk.CTkLabel(f_acoes, text="Formatos: JSON e CSV.",
            text_color="#7f8c8d", font=("Arial", 10)
        ).pack(side="left", padx=(12, 8), pady=6)


        # --- TABELA ---
        self.tabela = ttk.Treeview(
            self,
            columns=("id", "nome", "custo", "venda", "margem", "qtd", "compat", "qtd_min"),
            show="headings",
        )
        self.tabela.heading("id", text="ID")
        self.tabela.heading("nome", text="PRODUTO")
        self.tabela.heading("custo", text="R$ CUSTO")
        self.tabela.heading("venda", text="R$ VENDA")
        self.tabela.heading("margem", text="LUCRO %")
        self.tabela.heading("qtd", text="QTD")
        self.tabela.heading("compat", text="COMPATIBILIDADE")
        self.tabela.heading("qtd_min", text="QTD MIN")
        
        self.tabela.column("id", width=40)
        self.tabela.column("nome", width=250)
        self.tabela.column("margem", width=100, anchor="center")
        self.tabela.column("compat", width=220)
        self.tabela.column("qtd_min", width=90, anchor="center")
        self.tabela.pack(pady=20, padx=20, fill="both", expand=True)

        self.tabela.bind("<Double-1>", self.selecionar_produto)
        self.carregar_dados()

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
            compat = self.ent_compat.get().strip().upper()
            qtd_min_txt = self.ent_qtd_min.get().strip()

            # 3. Se o campo estiver vazio, vira 0.0 (evita o erro de valor inválido)
            c = float(custo_txt) if custo_txt else 0.0
            m = float(margem_txt) if margem_txt else 0.0
            v = float(venda_txt) if venda_txt else 0.0
            q = int(qtd_txt) if qtd_txt else 0
            q_min = int(qtd_min_txt) if qtd_min_txt else 3

            # 4. Lógica: Se você digitou a Margem mas não a Venda, ele calcula agora
            if v == 0 and m > 0 and c > 0:
                v = c + (c * (m / 100))

            # 5. Salva no Banco de Dados
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # Nota: O banco só guarda Nome, Custo, Venda e Qtd.
                # A margem a gente calcula apenas para mostrar na tela.
                cursor.execute(
                    """
                    INSERT INTO produtos
                        (nome, preco_custo, preco_venda, estoque, compatibilidade, quantidade_minima)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (nome, c, v, q, compat, q_min),
                )
                conn.commit()
            
            # 6. Atualiza a lista e limpa os campos
            self.carregar_dados()
            for e in [self.ent_nome, self.ent_compat, self.ent_custo, self.ent_margem, self.ent_venda, self.ent_qtd, self.ent_qtd_min]:
                e.delete(0, 'end')
            self.ent_qtd_min.insert(0, "3")
            
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
                termo = ""
                if hasattr(self, "ent_busca_estoque"):
                    termo = str(self.ent_busca_estoque.get() or "").strip().upper()
                if termo:
                    like = f"%{termo}%"
                    cursor.execute(
                        """
                        SELECT id, nome, preco_custo, preco_venda, estoque,
                               COALESCE(compatibilidade,''), COALESCE(quantidade_minima, 3)
                        FROM produtos
                        WHERE UPPER(COALESCE(nome, '')) LIKE ?
                           OR UPPER(COALESCE(compatibilidade, '')) LIKE ?
                        ORDER BY nome
                        """,
                        (like, like),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, nome, preco_custo, preco_venda, estoque,
                               COALESCE(compatibilidade,''), COALESCE(quantidade_minima, 3)
                        FROM produtos
                        ORDER BY nome
                        """
                    )
                for linha in cursor.fetchall():
                    id_p, nome, custo, venda, qtd, compat, qtd_min = linha
                    margem = ((venda - custo) / custo * 100) if custo > 0 else 0
                    self.tabela.insert(
                        "",
                        "end",
                        values=(id_p, nome, f"{custo:.2f}", f"{venda:.2f}", f"{margem:.1f}%", qtd, compat, qtd_min),
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
            self.destroy()
            # item[1] é o nome, item[3] é o preço de venda
            self.master.adicionar_item_ao_orcamento(item[1], float(item[3]))



    # ======================================================================
    # IMPORTAÇÃO / EXPORTAÇÃO EM MASSA DE PRODUTOS
    # ======================================================================
    _PRODUTOS_COLUNAS_NUMERICAS = {
        "preco_custo": float, "preco_venda": float, "estoque": int,
        "quantidade_minima": int, "aliquota_ibs": float, "aliquota_cbs": float,
        "valor_ibs": float, "valor_cbs": float,
    }

    def _produtos_obter_colunas(self, cursor) -> list:
        cursor.execute("PRAGMA table_info(produtos)")
        return [str(row[1]) for row in cursor.fetchall() if row and row[1]]

    def _produtos_obter_colunas_editaveis(self, cursor) -> list:
        return [c for c in self._produtos_obter_colunas(cursor)
                if str(c).lower() != "id"]

    def _produtos_coagir_valor(self, coluna, valor):
        if valor is None:
            return None, None
        col_lower = str(coluna).lower()
        if col_lower in self._PRODUTOS_COLUNAS_NUMERICAS:
            conversor = self._PRODUTOS_COLUNAS_NUMERICAS[col_lower]
            if isinstance(valor, bool):
                return None, "Booleano invalido para campo numerico em '" + coluna + "'."
            if isinstance(valor, (int, float)):
                return conversor(valor), None
            s = str(valor).strip()
            if s == "":
                return conversor(0), None
            s_norm = s.replace(".", "").replace(",", ".") if "," in s else s
            try:
                return conversor(s_norm), None
            except (TypeError, ValueError):
                return None, "Valor invalido em '" + coluna + "': '" + str(valor) + "'."
        if isinstance(valor, (dict, list)):
            return json.dumps(valor, ensure_ascii=False), None
        return str(valor).strip(), None

    def _produtos_backup_pre_importacao(self) -> str:
        try:
            caminho = CAMINHO_BANCO
            if not caminho or not os.path.exists(caminho):
                logger.warning("Backup ignorado: banco nao encontrado.")
                return ""
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = caminho + ".bak.preimport_" + ts
            shutil.copy2(caminho, backup_path)
            logger.info("Backup criado: %s", backup_path)
            return backup_path
        except Exception as exc:
            logger.exception("Falha backup: %s", exc)
            return ""


    def exportar_produtos(self):
        try:
            destino = filedialog.asksaveasfilename(
                parent=self, title="Exportar Produtos",
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
                initialfile="produtos_export_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json",
            )
            if not destino:
                return
            dl = str(destino).lower()
            with get_db_connection() as conn:
                cursor = conn.cursor()
                colunas = self._produtos_obter_colunas(cursor)
                if not colunas:
                    messagebox.showwarning("Exportar Produtos",
                        "Nao foi possivel ler a estrutura da tabela.", parent=self)
                    return
                col_select = ", ".join(["\"" + c + "\"" for c in colunas])
                cursor.execute("SELECT " + col_select + " FROM produtos ORDER BY nome")
                raw = cursor.fetchall()
            regs = []
            for row in raw:
                item = {}
                for i2, col in enumerate(colunas):
                    v = row[i2]
                    if isinstance(v, (bytes, bytearray)):
                        v = v.decode("utf-8", errors="ignore")
                    item[col] = v
                regs.append(item)
            if dl.endswith(".csv"):
                with open(destino, "w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=colunas, extrasaction="ignore")
                    w.writeheader()
                    for item in regs:
                        linha = {}
                        for c in colunas:
                            v = item.get(c)
                            if isinstance(v, (dict, list)):
                                linha[c] = json.dumps(v, ensure_ascii=False)
                            else:
                                linha[c] = "" if v is None else v
                        w.writerow(linha)
                msg = "Exportacao CSV concluida.\n" + str(len(regs)) + " produto(s) salvos em:\n" + destino
            else:
                payload = {
                    "formato": "oficina_pesca.produtos",
                    "versao_app": APP_VERSION,
                    "exportado_em": datetime.now().isoformat(timespec="seconds"),
                    "colunas": colunas,
                    "produtos": regs,
                }
                with open(destino, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                msg = "Exportacao JSON concluida.\n" + str(len(regs)) + " produto(s) salvos em:\n" + destino
            logger.info("Exportacao OK: %s -> %s", len(regs), destino)
            messagebox.showinfo("Exportar Produtos", msg, parent=self)
        except Exception as exc:
            logger.exception("Falha exportacao: %s", exc)
            messagebox.showerror("Exportar Produtos", "Erro:\n" + str(exc), parent=self)


    def importar_produtos(self):
        backup_path = ""
        try:
            origem = filedialog.askopenfilename(
                parent=self, title="Importar Produtos",
                filetypes=[("JSON", "*.json"), ("CSV", "*.csv"), ("Todos", "*.*")],
            )
            if not origem:
                return
            dl = str(origem).lower()
            with open(origem, "r", encoding="utf-8-sig", newline="") as f:
                if dl.endswith(".csv"):
                    leitor = csv.DictReader(f)
                    linhas = [dict(row) for row in leitor]
                else:
                    dados = json.load(f)
                    if isinstance(dados, list):
                        linhas = dados
                    elif isinstance(dados, dict):
                        linhas = dados.get("produtos", [dados])
                    else:
                        raise ValueError("Estrutura JSON invalida.")
            if not linhas:
                messagebox.showwarning("Importar Produtos",
                    "O arquivo nao contem registros.", parent=self)
                return
            backup_path = self._produtos_backup_pre_importacao()
            if not backup_path:
                if not messagebox.askyesno("Importar Produtos",
                        "Backup nao disponivel. Continuar?", parent=self):
                    return
            imp, at, rej = self._produtos_importar_transacao(linhas)
            rel = [
                "Importacao concluida.",
                "  Importados (novos): " + str(imp),
                "  Atualizados (por ID existente): " + str(at),
                "  Rejeitados: " + str(len(rej)),
            ]
            if backup_path:
                rel.append("  Backup: " + backup_path)
            if rej:
                rel.append("")
                rel.append("Motivos das rejeicoes:")
                for i_r, mot, _ in rej[:25]:
                    rel.append("  - linha " + str(i_r) + ": " + mot)
                if len(rej) > 25:
                    rel.append("  ... e mais " + str(len(rej) - 25) + " rejeicao(oes).")
            messagebox.showinfo("Importar Produtos", "\n".join(rel), parent=self)
            logger.info("Importacao: imp=%s at=%s rej=%s", imp, at, len(rej))
            self.carregar_dados()
        except _ProdutosImportacaoErro as rb:
            logger.exception("Rollback importacao: %s", rb)
            messagebox.showerror("Importar Produtos",
                "Erro estrutural. A operacao foi DESFEITA.\n\n" +
                "Motivo: " + str(rb) + "\n\nBackup: " + (backup_path or "nao gerado"),
                parent=self)
        except Exception as exc:
            logger.exception("Falha importacao: %s", exc)
            messagebox.showerror("Importar Produtos", "Erro:\n" + str(exc), parent=self)


    def _produtos_importar_transacao(self, linhas):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            colunas_db = self._produtos_obter_colunas(cursor)
            colunas_set = {c.lower(): c for c in colunas_db}
            editaveis_set = {c.lower() for c in self._produtos_obter_colunas_editaveis(cursor)}
            primeira = linhas[0] or {}
            if not isinstance(primeira, dict):
                raise ValueError("Primeiro registro nao e um objeto.")
            campos_arquivo = list(primeira.keys())
            colunas_alvo = []
            for c_orig in campos_arquivo:
                chave = str(c_orig).strip()
                if not chave:
                    colunas_alvo.append(None)
                elif chave.lower() in colunas_set:
                    colunas_alvo.append(colunas_set[chave.lower()])
                else:
                    colunas_alvo.append(None)
            if not any(c is not None for c in colunas_alvo):
                raise ValueError("Nenhum campo corresponde a tabela.")
            imp = at = 0
            rej = []
            try:
                conn.execute("BEGIN")
                for idx_reg, registro in enumerate(linhas, start=1):
                    if not isinstance(registro, dict):
                        rej.append((idx_reg, "(registro nao e objeto)", "-"))
                        continue
                    id_forn = None
                    cols_usadas = []
                    vals = []
                    erro = None
                    for idx_campo, (col_alvo, nome_campo) in enumerate(
                            zip(colunas_alvo, list(registro.keys()))):
                        if col_alvo is None:
                            continue
                        v_bruto = registro.get(nome_campo)
                        v_ok, erro = self._produtos_coagir_valor(col_alvo, v_bruto)
                        if erro is not None:
                            rej.append((idx_reg, erro, nome_campo))
                            break
                        if col_alvo.lower() == "id":
                            try:
                                raw_id = v_ok
                                id_forn = int(float(raw_id)) if raw_id is not None else None
                            except (TypeError, ValueError):
                                rej.append((idx_reg, "ID invalido: " + str(v_bruto), nome_campo))
                                break
                            if id_forn is not None and id_forn <= 0:
                                id_forn = None
                        if v_ok is not None and v_bruto not in (None, ""):
                            vals.append(v_ok)
                            cols_usadas.append(col_alvo)
                    if erro is not None:
                        continue
                    if "nome" in editaveis_set and "nome" in cols_usadas:
                        if not vals[cols_usadas.index("nome")]:
                            rej.append((idx_reg, "Nome vazio.", "nome"))
                            continue
                    if id_forn is not None and id_forn > 0:
                        cursor.execute("SELECT 1 FROM produtos WHERE id = ?", (id_forn,))
                        if cursor.fetchone():
                            sets_str = ", ".join(["\"" + c + "\" = ?"
                                for c in cols_usadas])
                            params = list(vals) + [id_forn]
                            cursor.execute("UPDATE produtos SET " + sets_str +
                                " WHERE id = ?", params)
                            if cursor.rowcount > 0:
                                at += 1
                            else:
                                rej.append((idx_reg, "UPDATE nao afetou linhas.", "id"))
                        else:
                            ph = ", ".join(["?"] * len(cols_usadas))
                            cs = ", ".join(["\"" + c + "\"" for c in cols_usadas])
                            cursor.execute("INSERT INTO produtos (" + cs +
                                ") VALUES (" + ph + ")", vals)
                            imp += 1
                    else:
                        if not cols_usadas:
                            rej.append((idx_reg, "Sem colunas validas.", "-"))
                            continue
                        ph = ", ".join(["?"] * len(cols_usadas))
                        cs = ", ".join(["\"" + c + "\"" for c in cols_usadas])
                        cursor.execute("INSERT INTO produtos (" + cs +
                            ") VALUES (" + ph + ")", vals)
                        imp += 1
                conn.execute("COMMIT")
            except _ProdutosImportacaoErro:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
            except Exception as exc_est:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise _ProdutosImportacaoErro(str(exc_est)) from exc_est
        return imp, at, rej


class _ProdutosImportacaoErro(Exception):
    """Erro estrutural durante importacao de produtos."""
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

        ctk.CTkLabel(self, text="👤 NOVO USUÁRIO", font=("Arial", 22, "bold")).pack(pady=(20, 15))

        form = ctk.CTkFrame(self)
        form.pack(fill="both", expand=True, padx=20, pady=10)

        self.ent_usuario = ctk.CTkEntry(form, placeholder_text="Usuário", width=320, height=40)
        self.ent_usuario.pack(pady=(20, 10))

        self.ent_senha = ctk.CTkEntry(form, placeholder_text="Senha", show="*", width=320, height=40)
        self.ent_senha.pack(pady=10)

        self.ent_confirma = ctk.CTkEntry(form, placeholder_text="Confirmar senha", show="*", width=320, height=40)
        self.ent_confirma.pack(pady=10)

        self.role_var = ctk.StringVar(value="OPERADOR")
        self.opt_role = ctk.CTkOptionMenu(form, values=["OPERADOR", "ADMIN"], variable=self.role_var, width=320)
        self.opt_role.pack(pady=10)

        ctk.CTkLabel(
            form,
            text="Somente usuários ADMIN podem acessar esta tela.",
            text_color="#95a5a6"
        ).pack(pady=(0, 10))

        self.lbl_status = ctk.CTkLabel(form, text="", text_color="red")
        self.lbl_status.pack(pady=(0, 10))

        ctk.CTkButton(form, text="SALVAR USUÁRIO", fg_color="#27ae60", command=self.salvar_usuario, width=320, height=42).pack(pady=(5, 20))

    def salvar_usuario(self):
        usuario = self.ent_usuario.get().strip()
        senha = self.ent_senha.get().strip()
        confirma = self.ent_confirma.get().strip()
        role = self.role_var.get().strip().upper() or "OPERADOR"

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
        self.grab_set()
        self.focus_force()
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
                    "SELECT COUNT(*) FROM orcamentos_aguardo WHERE UPPER(status) = 'AGUARDANDO'"
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
    def inicializar_firebase(self):
        """
        Inicializa o Firebase Admin SDK com as credenciais e URL do Realtime Database.
        """
        import os
        try:
            cred_path = _resolver_recurso('google-services.json') # Padronizado para google-services.json
            if not firebase_admin._apps:
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': 'https://oficinapescasystem-default-rtdb.firebaseio.com/'
                })
        except Exception as e:
            print(f"Erro ao inicializar Firebase: {e}")
            # Não interrompe o fluxo caso falhe

    def __init__(self, master):
        super().__init__(master)
        self.title("Dados da Oficina")
        self.geometry("980x680")
        self.resizable(False, True)
        self.grab_set()
        self.focus_force()

        ctk.CTkLabel(self, text="🏪 DADOS DA OFICINA", font=("Arial", 22, "bold"), text_color="orange").pack(pady=(16, 6))

        # scroll para caber em telas menores
        scroll = ctk.CTkScrollableFrame(self, fg_color="#1f2a38", corner_radius=12)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        form = scroll

        ctk.CTkLabel(form, text="Nome da oficina", anchor="w", text_color="orange", font=("Arial", 12, "bold")).pack(fill="x", padx=15, pady=(15, 2))
        self.ent_nome = ctk.CTkEntry(form, placeholder_text="Nome da oficina")
        self.ent_nome.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(form, text="Endereço da oficina", anchor="w", text_color="orange", font=("Arial", 12, "bold")).pack(fill="x", padx=15, pady=(2, 2))
        self.ent_endereco = ctk.CTkEntry(form, placeholder_text="Endereço da oficina")
        self.ent_endereco.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(form, text="Telefone", anchor="w", text_color="orange", font=("Arial", 12, "bold")).pack(fill="x", padx=15, pady=(2, 2))
        self.ent_telefone = ctk.CTkEntry(form, placeholder_text="Telefone")
        self.ent_telefone.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(form, text="Chave PIX", anchor="w", text_color="orange", font=("Arial", 12, "bold")).pack(fill="x", padx=15, pady=(2, 2))
        self.ent_pix = ctk.CTkEntry(form, placeholder_text="Chave PIX")
        self.ent_pix.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(form, text="Logo da oficina (usado no PDF)", anchor="w", text_color="orange", font=("Arial", 12, "bold")).pack(fill="x", padx=15, pady=(2, 2))
        f_logo = ctk.CTkFrame(form, fg_color="#1f2a38")
        f_logo.pack(fill="x", padx=15, pady=(0, 8))
        self.ent_logo = ctk.CTkEntry(f_logo, placeholder_text="Caminho do logo da oficina")
        self.ent_logo.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(f_logo, text="Escolher", width=90, fg_color="#2980b9", command=self.escolher_logo).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(form, text="Imagem do patrocinador (direita)", anchor="w", text_color="orange", font=("Arial", 12, "bold")).pack(fill="x", padx=15, pady=(2, 2))
        f_logo_dir = ctk.CTkFrame(form, fg_color="#1f2a38")
        f_logo_dir.pack(fill="x", padx=15, pady=(0, 8))
        self.ent_logo_dir = ctk.CTkEntry(f_logo_dir, placeholder_text="Caminho da imagem do patrocinador (direita)")
        self.ent_logo_dir.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(f_logo_dir, text="Escolher", width=90, fg_color="#8e44ad", command=self.escolher_logo_direita).pack(side="left", padx=(8, 0))

        # ── Separador ──
        ctk.CTkFrame(form, height=2, fg_color="#2e4a6a").pack(fill="x", padx=15, pady=(12, 4))
        ctk.CTkLabel(form, text="☁️  BACKUP NA NUVEM", anchor="w", text_color="#3498db", font=("Arial", 13, "bold")).pack(fill="x", padx=15, pady=(4, 2))

        ctk.CTkLabel(form, text="E-mail para backup na nuvem", anchor="w", text_color="#aab4be", font=("Arial", 11)).pack(fill="x", padx=15, pady=(2, 2))
        self.ent_email = ctk.CTkEntry(form, placeholder_text="exemplo@gmail.com")
        self.ent_email.pack(fill="x", padx=15, pady=(0, 8))

        f_cloud_login = ctk.CTkFrame(form, fg_color="#1f2a38")
        f_cloud_login.pack(fill="x", padx=15, pady=(0, 10))
        self.btn_google = ctk.CTkButton(
            f_cloud_login,
            text="Entrar no Google Drive",
            width=170,
            fg_color="#1a73e8",
            hover_color="#1558b0",
            command=self.conectar_google_drive_oficial,
        )
        self.btn_google.pack(side="left")

        ctk.CTkLabel(form, text="Configuração de rede da oficina", anchor="w", text_color="#aab4be", font=("Arial", 11)).pack(fill="x", padx=15, pady=(2, 2))
        f_rede = ctk.CTkFrame(form, fg_color="#1f2a38")
        f_rede.pack(fill="x", padx=15, pady=(0, 10))
        self.btn_localizar_rede = ctk.CTkButton(
            f_rede,
            text="LOCALIZAR OFICINA NA REDE",
            width=280,
            height=34,
            fg_color="#1f6aa5",
            hover_color="#1a5a8b",
            command=self.localizar_oficina_rede_cfg,
        )
        self.btn_localizar_rede.pack(side="left", padx=(10, 8), pady=10)
        self.lbl_rede = ctk.CTkLabel(f_rede, text="", anchor="w", text_color="#94a3b8", font=("Arial", 10))
        self.lbl_rede.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=10)

        # ── Separador ──
        ctk.CTkFrame(form, height=2, fg_color="#2e4a6a").pack(fill="x", padx=15, pady=(8, 4))
        ctk.CTkLabel(form, text="ℹ️  INFORMAÇÕES DO SISTEMA", anchor="w", text_color="#95a5a6", font=("Arial", 13, "bold")).pack(fill="x", padx=15, pady=(4, 2))

        # Versão e licença — read-only, carregados em carregar()
        fi = ctk.CTkFrame(form, fg_color="#1f2a38")
        fi.pack(fill="x", padx=15, pady=(2, 10))
        self.lbl_versao = ctk.CTkLabel(fi, text="Versão: carregando...", anchor="w", text_color="#7f8c8d", font=("Arial", 11))
        self.lbl_versao.pack(fill="x")
        self.lbl_licenca = ctk.CTkLabel(fi, text="Licença: carregando...", anchor="w", text_color="#7f8c8d", font=("Arial", 11))
        self.lbl_licenca.pack(fill="x")

        ctk.CTkButton(form, text="  SALVAR DADOS", fg_color="#27ae60", width=220, font=("Arial", 13, "bold"), command=self.salvar).pack(pady=(4, 10))

        ctk.CTkFrame(form, height=2, fg_color="#2e4a6a").pack(fill="x", padx=15, pady=(6, 4))
        ctk.CTkLabel(form, text="RECUPERACAO DE BACKUP", anchor="w", text_color="#f1c40f", font=("Arial", 13, "bold")).pack(fill="x", padx=15, pady=(4, 2))
        ctk.CTkLabel(
            form,
            text="Use esta opcao apos reinstalacao para restaurar um arquivo .db antigo.",
            anchor="w",
            text_color="#aab4be",
            font=("Arial", 11),
        ).pack(fill="x", padx=15, pady=(0, 8))
        ctk.CTkButton(
            form,
            text="RESTAURAR BACKUP AGORA",
            fg_color="#d68910",
            hover_color="#b9770e",
            width=260,
            font=("Arial", 12, "bold"),
            command=self.restaurar_backup_manual,
        ).pack(pady=(0, 10))

        ctk.CTkFrame(form, height=2, fg_color="#2e4a6a").pack(fill="x", padx=15, pady=(6, 4))
        ctk.CTkLabel(form, text="SERVIDOR PARA CLIENTE", anchor="w", text_color="#64b5f6", font=("Arial", 13, "bold")).pack(fill="x", padx=15, pady=(4, 2))
        ctk.CTkLabel(
            form,
            text="Gera um pacote para o cliente clicar e instalar o servidor local.",
            anchor="w",
            text_color="#aab4be",
            font=("Arial", 11),
        ).pack(fill="x", padx=15, pady=(0, 8))
        f_servidor = ctk.CTkFrame(form, fg_color="#1f2a38")
        f_servidor.pack(fill="x", padx=15, pady=(0, 18))
        ctk.CTkButton(
            f_servidor,
            text="GERAR INSTALADOR DO SERVIDOR",
            fg_color="#2980b9",
            hover_color="#3498db",
            width=320,
            height=36,
            font=("Arial", 12, "bold"),
            command=self.gerar_instalador_servidor,
        ).pack(side="left", padx=10, pady=10)
        ctk.CTkLabel(
            f_servidor,
            text="Gera um pacote para o cliente instalar o servidor local com poucos cliques.",
            anchor="w",
            justify="left",
            text_color="#aab4be",
            font=("Arial", 10),
        ).pack(side="left", fill="x", expand=True, padx=(4, 10), pady=10)

        self.carregar()

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
                row = cursor.fetchone()
            if row:
                self.ent_nome.insert(0, row[0] or "")
                self.ent_endereco.insert(0, row[1] or "")
                self.ent_telefone.insert(0, row[2] or "")
                self.ent_pix.insert(0, row[3] or "")
                self.ent_logo.insert(0, row[4] or "")
                self.ent_logo_dir.insert(0, row[5] or "")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível carregar dados da oficina: {e}", parent=self)

        # email backup
        try:
            email_atual = obter_email_backup_nuvem()
            if email_atual:
                self.ent_email.insert(0, email_atual)
        except Exception:
            pass

        # versão e licença
        try:
            self.lbl_versao.configure(text=f"Versão do sistema: {APP_VERSION}")
        except Exception:
            pass
        try:
            lic_ativa, _msg, _cli, validade = obter_status_licenca()
            if lic_ativa:
                tipo = obter_tipo_licenca()
                val_txt = str(validade or "").strip().upper()
                if val_txt == "PERMANENTE":
                    self.lbl_licenca.configure(text=f"Licença: {tipo} — PERMANENTE", text_color="#2ecc71")
                else:
                    self.lbl_licenca.configure(text=f"Licença: {tipo} — válida até {validade}", text_color="#2ecc71")
            else:
                trial_ativo, dias, data_lim = obter_status_trial()
                if trial_ativo:
                    self.lbl_licenca.configure(text=f"Trial ativo: {dias} dia(s) restante(s) (até {data_lim})", text_color="#f1c40f")
                else:
                    self.lbl_licenca.configure(text=f"Trial expirado (em {data_lim})", text_color="#e74c3c")
        except Exception:
            pass

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

    def salvar(self):
        nome = self.ent_nome.get().strip()
        endereco = self.ent_endereco.get().strip()
        telefone = self.ent_telefone.get().strip()
        pix = self.ent_pix.get().strip()
        logo = self.ent_logo.get().strip()
        logo_dir = self.ent_logo_dir.get().strip()
        email_nuvem = self.ent_email.get().strip().lower()

        if not nome:
            messagebox.showwarning("Atenção", "Informe o nome da oficina.", parent=self)
            return

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO dados_oficina
                        (id, nome_oficina, endereco_oficina, telefone_oficina, chave_pix, logo_path, logo_patrocinador_path)
                    VALUES
                        (1, ?, ?, ?, ?, ?, ?)
                    """,
                    (nome, endereco, telefone, pix, logo, logo_dir)
                )
                conn.commit()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível salvar dados da oficina: {e}", parent=self)
            return
        # Inicializa o Firebase após salvar localmente
        self.inicializar_firebase()

        # salvar email backup se informado
        if email_nuvem:
            ok, msg = salvar_email_backup_nuvem(email_nuvem)
            if not ok:
                messagebox.showwarning("E-mail Nuvem", f"Dados salvos, mas não foi possível salvar e-mail: {msg}", parent=self)

        messagebox.showinfo("Sucesso", "Dados da oficina atualizados com sucesso.", parent=self)
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
                self.master.destroy()
                os._exit(0)
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
        self.grab_set()
        self.focus_force()
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

        self.carregar_os_finalizadas()

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
    def __init__(self, usuario="", role="OPERADOR", senha_login=""):
        super().__init__()
        self.withdraw()
        self.usuario = usuario or "USUÁRIO"
        self.role = (role or "OPERADOR").upper()
        self._senha_login = senha_login or ""
        self._backup_nuvem_executado = False
        self._janela_gestao_os = None
        self._janela_os_atual = None
        self._ultima_os_contexto = None
        self._encerrando_aplicacao = False
        self.title("Sistema Oficina de Pesca v1.0.5")
        self.geometry("1100x750")
        self.configure(fg_color="#0f1720")

        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (1100 // 2)
        y = (self.winfo_screenheight() // 2) - (750 // 2)
        self.geometry(f"+{x}+{y}")

        self._aplicar_maximizacao()
        self.after(150, self._aplicar_maximizacao)
        self.after(900, self._aplicar_maximizacao)

        self.protocol("WM_DELETE_WINDOW", self.confirmar_saida)

        # ── Fundo (imagem de fundo, opcional) ──────────────────────────
        self._bg_image = None
        self._bg_photo = None
        self._bg_ctk_image = None
        self._bg_pil_original = None
        self._bg_cache_size = None
        self._bg_label = ctk.CTkLabel(self, text="", fg_color="#0f1720")
        self._bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        imagem_carregada = False
        pasta_banco = os.path.dirname(CAMINHO_BANCO)
        pasta_exec = os.path.dirname(os.path.abspath(__file__))
        pastas_base = [
            DIRETORIO_RECURSOS,
            pasta_banco,
            os.path.join(pasta_banco, "_internal"),
            pasta_exec,
            os.getcwd(),
        ]

        candidatos = []
        for pasta_base in pastas_base:
            candidatos.extend([
                os.path.join(pasta_base, "fundomenu.jpg"),
                os.path.join(pasta_base, "fundomenu.jpeg"),
                os.path.join(pasta_base, "fundomenu.png"),
                os.path.join(pasta_base, "fundomenu.bmp"),
                os.path.join(pasta_base, "fundo_menu.jpg"),
                os.path.join(pasta_base, "fundo_menu.jpeg"),
                os.path.join(pasta_base, "fundo_menu.png"),
                os.path.join(pasta_base, "fundo_menu.bmp"),
            ])

        vistos = set()
        candidatos_unicos = []
        for caminho in candidatos:
            chave = os.path.abspath(caminho)
            if chave in vistos:
                continue
            vistos.add(chave)
            candidatos_unicos.append(caminho)

        for caminho_fundo in candidatos_unicos:
            if not os.path.exists(caminho_fundo):
                continue
            try:
                if Image is not None and ImageTk is not None:
                    self._bg_pil_original = Image.open(caminho_fundo).convert("RGB")
                    self.bind("<Configure>", self._atualizar_fundo)
                    self.after(120, self._atualizar_fundo)
                else:
                    if caminho_fundo.lower().endswith(".png"):
                        self._bg_image = tk.PhotoImage(file=caminho_fundo)
                        self._bg_label.configure(image=self._bg_image, text="")
                    else:
                        continue
                imagem_carregada = True
                break
            except Exception:
                self._bg_image = None
                self._bg_pil_original = None
                continue
        if not imagem_carregada:
            self.configure(fg_color="#0f1720")

        # ── Layout: sidebar esquerda + área de conteúdo ─────────────────
        self.frame_layout = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_layout.pack(fill="both", expand=True)

        # Sidebar vertical
        self.sidebar = ctk.CTkFrame(self.frame_layout, width=210, fg_color="#0d1b2a", corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo / Título na sidebar
        ctk.CTkLabel(
            self.sidebar,
            text="🎣",
            font=("Arial", 34),
            text_color="orange",
            fg_color="#0d1b2a",
        ).pack(pady=(10, 2))
        ctk.CTkLabel(
            self.sidebar,
            text="OFICINA DE PESCA",
            font=("Arial", 12, "bold"),
            text_color="orange",
            fg_color="#0d1b2a",
            wraplength=190,
            justify="center",
        ).pack(padx=8, pady=(0, 2))
        ctk.CTkLabel(
            self.sidebar,
            text=f"👤 {self.usuario.upper()}",
            font=("Arial", 10),
            text_color="#7f8c8d",
            fg_color="#0d1b2a",
        ).pack(padx=8, pady=(0, 2))
        ctk.CTkLabel(
            self.sidebar,
            text=f"({self.role})",
            font=("Arial", 9),
            text_color="#555f6a",
            fg_color="#0d1b2a",
        ).pack(padx=8, pady=(0, 5))

        self.lbl_contador_licenca = ctk.CTkLabel(
            self.sidebar,
            text="",
            font=("Arial", 9, "bold"),
            text_color="#f1c40f",
            fg_color="#0d1b2a",
            wraplength=190,
            justify="center",
        )
        self.lbl_contador_licenca.pack(padx=8, pady=(0, 5))
        self._atualizar_contador_licenca()
        self._adicionar_status_nuvem()

        # Separador
        ctk.CTkFrame(self.sidebar, height=1, fg_color="#1e3a5f").pack(fill="x", padx=12, pady=(0, 5))

        # Botões do menu
        self.sidebar_buttons = ctk.CTkFrame(self.sidebar, fg_color="#0d1b2a")
        self.sidebar_buttons.pack(fill="x", padx=6, pady=(0, 0), anchor="n")

        botoes_menu = [
            ("🧑‍🤝‍🧑  PESCADORES", self.abrir_clientes, "#34495e"),
            ("📋  NOVA O.S.", self.abrir_os, "#27ae60"),
            ("🔍  CONSULTA", self.abrir_gestao_os, "#d35400"),
            ("📦  ESTOQUE", self.abrir_produtos, "#e67e22"),
            ("💰  FINANCEIRO", self.abrir_caixa, "#16a085"),
            ("🧾  GERAR RECIBO", self.gerar_recibo_menu_lateral, "#8e6b3b"),
            ("📱  APP CELULAR", self.abrir_app_celular_sidebar, "#25D366"),
        ]
        if self.role == "ADMIN":
            botoes_menu.extend([
                ("👤  NOVO USUÁRIO", self.abrir_cadastro_usuario, "#2980b9"),
                ("📊  RELATÓRIO", self.abrir_relatorio, "#6c3483"),
                ("🏪  DADOS OFICINA", self.abrir_dados_oficina, "#7f8c8d"),
                ("🔄  SINCRONIZAR NUVEM", self.executar_sincronizacao_nuvem, "#2980b9"),
                ("🤖  ANALISE IA", self.verificacao_ia_melhorias, "#2c3e50"),
            ])

        for texto, comando, cor in botoes_menu:
            self.add_btn(self.sidebar_buttons, texto, comando, cor)

        # Botão Sair fixo no rodapé
        self.add_btn(self.sidebar, "🚪  SAIR", self.confirmar_saida, "#c0392b", side="bottom")

        # Área de conteúdo (direita – fica com o fundo)
        area = ctk.CTkFrame(self.frame_layout, fg_color="#0f1720")
        area.pack(side="left", fill="both", expand=True)

        # Fundo também na área direita para garantir visual em diferentes temas/versões do CTk.
        self._bg_area_label = ctk.CTkLabel(area, text="", fg_color="#0f1720")
        self._bg_area_label.place(x=0, y=0, relwidth=1, relheight=1)
        self._bg_area_label.lift()

        # ── Pós-inicialização ──────────────────────────────────────────
        self._bg_label.lower() # Garante que o background fique por baixo de tudo

        if self.role == "ADMIN":
            self.after(600, self._verificar_primeira_instalacao)
            self.after(1800, self.verificacao_ia_mensal_automatica)

        # Google Drive sync é disparado manualmente pelo botão em Dados da Oficina

        self.after(80, self._mostrar_menu_pronto)
        self.after(550, self._verificar_e_exibir_painel_pendencias)
    def _adicionar_status_nuvem(self):
        self.lbl_status_nuvem = ctk.CTkLabel(self.sidebar, text="Verificando nuvem...", text_color="#f1c40f", font=("Arial", 10, "bold"), fg_color="#0d1b2a")
        self.lbl_status_nuvem.pack(padx=8, pady=(0, 5))
        self._atualizar_status_nuvem()

    def _atualizar_status_nuvem(self):
        try:
            online = checar_status_firebase()
            status = "Drive: online" if online else "Drive: offline"
            cor = "#2ecc71" if online else "#e74c3c"
            self.lbl_status_nuvem.configure(text=status, text_color=cor)
        except Exception:
            self.lbl_status_nuvem.configure(text="Drive: offline", text_color="#e74c3c")
        self.after(60000, self._atualizar_status_nuvem)
    def _verificar_e_exibir_painel_pendencias(self):
        try:
            orcamentos, bancada, status_finalizados = self._consultar_pendencias_login()
        except Exception as exc:
            logger.info("Falha ao consultar pendencias do login: %s", exc)
            return
        if orcamentos or bancada or status_finalizados:
            self._exibir_popup_pendencias_login(orcamentos, bancada, status_finalizados)


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
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            self.update_idletasks()
            self.after(150, self._atualizar_fundo)
        except Exception:
            pass

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
                SELECT id, COALESCE(data,''), COALESCE(cliente,'')
                FROM orcamentos_aguardo
                WHERE UPPER(COALESCE(status,'')) = 'AGUARDANDO'
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
                WHERE UPPER(COALESCE(status,'')) IN ('FINALIZADO', 'REPROVADO')
                  AND {fmt_data} >= ?
                ORDER BY id DESC
                """,
                (limite,),
            )
            status_finalizados = cursor.fetchall()
        return orcamentos, bancada, status_finalizados

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
            lic_ativa, _msg_lic, _cliente_lic, validade_lic = obter_status_licenca()
            if lic_ativa:
                validade_txt = str(validade_lic or "").strip().upper()
                if validade_txt == "PERMANENTE":
                    texto = "🔒 Licença: PERMANENTE"
                    cor = "#2ecc71"
                else:
                    texto = f"🔒 Licença ativa até: {validade_lic}"
                    cor = "#2ecc71"
            else:
                trial_ativo, dias_restantes, data_limite = obter_status_trial()
                if trial_ativo:
                    texto = f"⏳ Trial: {dias_restantes} dia(s)\nAté {data_limite}"
                    cor = "#f1c40f"
                else:
                    texto = f"❌ Trial expirado\nEm {data_limite}"
                    cor = "#e74c3c"

            self.lbl_contador_licenca.configure(text=texto, text_color=cor)
        except Exception as e:
            logger.exception("Erro ao atualizar contador de licença/trial: %s", e)
            self.lbl_contador_licenca.configure(text="", text_color="#f1c40f")
        finally:
            self.after(60000, self._atualizar_contador_licenca)

    def _verificar_primeira_instalacao(self):
        """Abre tela de dados da oficina na primeira instalação (ADMIN)."""
        try:
            if dados_oficina_sao_padrao():
                messagebox.showinfo(
                    "Primeira Instalação",
                    "Bem-vindo! Por favor, preencha os dados da sua oficina antes de começar.",
                    parent=self,
                )
                FrmDadosOficina(self)
        except Exception as e:
            logger.exception("Erro ao verificar primeira instalação: %s", e)

    def _atualizar_fundo(self, _event=None):
        if self._bg_pil_original is None or Image is None or ImageTk is None:
            return

        largura = max(self.winfo_width(), 1)
        altura = max(self.winfo_height(), 1)

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
        if hasattr(Image, "Resampling"):
            redimensionada = self._bg_pil_original.resize((nova_largura, nova_altura), Image.Resampling.BILINEAR)
        else:
            redimensionada = self._bg_pil_original.resize((nova_largura, nova_altura), Image.BILINEAR)

        left = max((nova_largura - largura) // 2, 0)
        top = max((nova_altura - altura) // 2, 0)
        recorte = redimensionada.crop((left, top, left + largura, top + altura))

        self._bg_ctk_image = ctk.CTkImage(light_image=recorte, dark_image=recorte, size=(largura, altura))
        self._bg_label.configure(image=self._bg_ctk_image, text="")
        if hasattr(self, "_bg_area_label") and self._bg_area_label is not None:
            self._bg_area_label.configure(image=self._bg_ctk_image, text="")
            self._bg_area_label.lift()
        self._bg_label.lower()

    def abrir_gestao_os(self):
        try:
            from gestao_os import FrmGestaoOrcamentos
            janela = FrmGestaoOrcamentos(self)
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
            import tela_os
            janela = tela_os.FrmOS(self)
            self._janela_os_atual = janela
        except Exception as e:
            messagebox.showerror("Erro", f"Erro: {e}", parent=self)

    def abrir_produtos(self):
        FrmProdutos(self)

    def abrir_caixa(self):
        try:
            from tela_financeiro import FrmFinanceiro
            FrmFinanceiro(self)
        except Exception as e: messagebox.showerror("Erro", f"Erro: {e}", parent=self)

    def gerar_recibo_menu_lateral(self):
        FrmBaixaRecibo(self)

    def abrir_app_celular_sidebar(self):
        messagebox.showwarning(
            "APP CELULAR",
            "ATENÇÃO: DEVIDO ÀS NORMAS E EXIGÊNCIAS DO GOOGLE, ESTA FUNÇÃO AINDA NÃO ESTÁ FUNCIONANDO...",
            parent=self,
        )
        self.abrir_pasta_apk_distribuicao()

    def abrir_pasta_apk_distribuicao(self):
        pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apk_celular_distribuicao")
        if not os.path.isdir(pasta):
            messagebox.showwarning("APK", "Pasta apk_celular_distribuicao não encontrada.", parent=self)
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
        FrmDadosOficina(self)

    def abrir_cadastro_usuario(self):
        if self.role != "ADMIN":
            messagebox.showwarning("Acesso negado", "Somente ADMIN pode cadastrar usuários.", parent=self)
            return
        FrmCadastroUsuarios(self)

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

        # Caminho do APK gerado
        caminho_apk = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                   "android_apk", "app", "build", "outputs", "apk", "debug", "app-debug.apk")

        # Caminho da Área de Trabalho do usuário
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        apk_destino = os.path.join(desktop, "app-oficina-pesca.apk")

        if os.path.exists(caminho_apk):
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
            texto += (f"\nO arquivo APK foi copiado para sua Área de Trabalho como 'app-oficina-pesca.apk'.\n"
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
            if versao_remota and eh_versao_mais_nova(versao_remota, APP_VERSION):
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

    def confirmar_saida(self):
        if messagebox.askokcancel("Sair", "Deseja encerrar o programa?", parent=self):
            self._encerrando_aplicacao = True
            try:
                self.withdraw()
            except Exception:
                pass
            try:
                self.quit()
            except Exception:
                try:
                    self.destroy()
                except Exception:
                    pass

if __name__ == "__main__":
    app = FrmMenu()
    app.mainloop()