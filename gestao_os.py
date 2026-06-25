# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import customtkinter as ctk
import os
import json
import re
from tkinter import messagebox, ttk
from datetime import datetime
from config import CAMINHO_BANCO, inicializar_banco, get_db_connection, enviar_registro_os_central_silencioso
from util_recibo import gerar_recibo_entrega

import tela_os

caminho_banco = CAMINHO_BANCO


def _garantir_colunas_entrega():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(orcamentos_aguardo)")
            cols = {row[1] for row in cursor.fetchall()}
            if "status_entrega" not in cols:
                cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN status_entrega TEXT")
            if "data_finalizacao" not in cols:
                cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN data_finalizacao TEXT")
            if "data_entrega" not in cols:
                cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN data_entrega TEXT")
            conn.commit()
    except Exception:
        pass

class FrmGestaoOrcamentos(ctk.CTkToplevel):
    def __init__(self, master, on_os_update_callback=None):
        super().__init__(master)
        inicializar_banco()
        _garantir_colunas_entrega()
        self.title("CONSULTA DE O.S.")
        self.geometry("980x620")
        self.minsize(900, 580)
        self.on_os_update_callback = on_os_update_callback # Callback para notificar o dashboard
        self.configure(fg_color="#161b22")
        self.grab_set()
        self.focus_force()
        self._aplicar_maximizacao()
        self.after(120, self._aplicar_maximizacao)

        header = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=20)
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(header, text="📋 CONSULTA DE O.S.", font=("Arial", 22, "bold"), text_color="orange").pack(side="left", padx=20, pady=20)
        ctk.CTkButton(header, text="Atualizar", fg_color="#2980b9", width=120, command=self.buscar_os).pack(side="right", padx=20, pady=20)

        f_busca = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=20)
        f_busca.pack(pady=10, padx=20, fill="x")
        self.ent_busca = ctk.CTkEntry(f_busca, placeholder_text="Buscar por Nº da O.S., nome do cliente ou WhatsApp", width=300)
        self.ent_busca.pack(side="left", padx=(20, 10), pady=10, fill="x", expand=True)
        ctk.CTkButton(f_busca, text="PESQUISAR", fg_color="#2980b9", width=120, command=self.buscar_os).pack(side="left", padx=(0, 20), pady=10)
        self.ent_busca.bind("<Return>", lambda _e: self.buscar_os())
        self.ent_busca.bind("<KeyRelease>", lambda _e: self.buscar_os())

        # --- BOTÕES DE AÇÃO (movidos para cima) ---
        self.f_botoes = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=20)
        self.f_botoes.pack(pady=(0, 6), padx=20, fill="x")
        ctk.CTkButton(
            self.f_botoes, text="🔄 ALTERAR STATUS", fg_color="#7d4e00", hover_color="#a86500",
            width=180, command=self.alterar_status_orcamento
        ).pack(side="left", padx=(20, 10), pady=10)
        ctk.CTkButton(
            self.f_botoes, text="📂 ABRIR O.S.", fg_color="#2980b9", width=140,
            command=self.abrir_orcamento_selecionado
        ).pack(side="left", padx=(0, 10), pady=10)
        self.lbl_info = ctk.CTkLabel(self.f_botoes, text="Selecione um orçamento...", justify="left",
                                     font=("Arial", 12), text_color="#bdc3c7")
        self.lbl_info.pack(side="left", padx=15, pady=10)

        tabela_frame = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=20)
        tabela_frame.pack(pady=(0, 10), padx=20, fill="both", expand=True)

        style = ttk.Style()
        style.configure("Treeview", rowheight=28, font=("Arial", 10))
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"))

        self.tab = ttk.Treeview(
            tabela_frame,
            columns=("id", "id_cliente", "whatsapp", "equipamento", "defeito", "valor_total", "sinal", "saldo", "status", "data", "descricao"),
            show="headings",
            height=12
        )
        self.tab.heading("id", text="Nº OC")
        self.tab.heading("id_cliente", text="ID / NOME")
        self.tab.heading("whatsapp", text="WhatsApp")
        self.tab.heading("equipamento", text="Equipamento")
        self.tab.heading("defeito", text="Defeito")
        self.tab.heading("valor_total", text="ValorTotal")
        self.tab.heading("sinal", text="Sinal")
        self.tab.heading("saldo", text="Saldo")
        self.tab.heading("status", text="Status")
        self.tab.heading("data", text="Data")
        self.tab.heading("descricao", text="PEÇAS / SERVIÇOS")

        self.tab.column("id", width=60, anchor="center")
        self.tab.column("id_cliente", width=150, anchor="w")
        self.tab.column("whatsapp", width=120, anchor="w")
        self.tab.column("equipamento", width=140)
        self.tab.column("defeito", width=140)
        self.tab.column("valor_total", width=90, anchor="e")
        self.tab.column("sinal", width=90, anchor="e")
        self.tab.column("saldo", width=90, anchor="e")
        self.tab.column("status", width=110, anchor="center")
        self.tab.column("data", width=95, anchor="center")
        self.tab.column("descricao", width=240)
        self.tab.pack(fill="both", expand=True, padx=15, pady=15)

        self.tab.tag_configure("st_amarelo", background="#3a2e00", foreground="#FFD700")
        self.tab.tag_configure("st_verde", background="#003a10", foreground="#00e676")
        self.tab.tag_configure("st_vermelho", background="#3a0000", foreground="#ff6b6b")
        self.tab.tag_configure("st_padrao", background="#1a2a3a", foreground="#ecf0f1")

        self.tab.bind("<<TreeviewSelect>>", self.selecionar_orcamento)
        self.tab.bind("<Double-1>", self.gerar_recibo_duplo_clique)

        self.dados_os = None
        self.buscar_os()

    def _notificar_dashboard(self):
        try:
            if callable(self.on_os_update_callback):
                self.on_os_update_callback()
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

    def _formatar_itens(self, itens_json):
        """Formata o JSON de itens como: M.O / 1x ROLAMENTO"""
        if not itens_json:
            return ""
        try:
            import json
            itens = json.loads(itens_json)
            partes = []
            for it in itens:
                if len(it) >= 2:
                    descricao = str(it[0])
                    qtd = str(it[1])
                    partes.append(f"{qtd}x {descricao}" if qtd != "1" else descricao)
            resultado = " / ".join(partes)
            return resultado[:80] + "..." if len(resultado) > 80 else resultado
        except Exception:
            return ""

    def alterar_status_orcamento(self):
        selecao = self.tab.selection()
        if not selecao:
            messagebox.showwarning("Aviso", "Selecione um orçamento na lista.", parent=self)
            return
        item = self.tab.item(selecao[0], "values")
        num_os = item[0]

        dialogo = ctk.CTkToplevel(self)
        dialogo.title("ALTERAR STATUS")
        dialogo.geometry("320x200")
        dialogo.resizable(False, False)
        dialogo.configure(fg_color="#161b22")
        dialogo.grab_set()
        dialogo.focus_force()

        ctk.CTkLabel(dialogo, text=f"Orçamento Nº {num_os}", font=("Arial", 14, "bold"),
                     text_color="orange").pack(pady=(18, 6))
        ctk.CTkLabel(dialogo, text="Selecione o novo status:", font=("Arial", 12),
                     text_color="#ecf0f1").pack(pady=(0, 12))

        def aplicar(novo_status):
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    if str(novo_status).upper() == "FINALIZADO":
                        data_finalizacao = datetime.now().strftime("%d/%m/%Y")
                        cursor.execute(
                            """
                            UPDATE orcamentos_aguardo
                            SET status = ?,
                                data_finalizacao = ?,
                                status_entrega = COALESCE(NULLIF(status_entrega, ''), 'PENDENTE')
                            WHERE id = ?
                            """,
                            (novo_status, data_finalizacao, num_os),
                        )
                    else:
                        cursor.execute("UPDATE orcamentos_aguardo SET status = ? WHERE id = ?", (novo_status, num_os))
                    conn.commit()
                try:
                    enviar_registro_os_central_silencioso(
                        {
                            "id": int(num_os),
                            "status": str(novo_status).upper(),
                            "data": datetime.now().strftime("%d/%m/%Y"),
                        },
                        operacao="status",
                    )
                except Exception:
                    pass
                dialogo.destroy()
                self.buscar_os()
                self._notificar_dashboard()
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao alterar status: {e}", parent=dialogo)

        f_btns = ctk.CTkFrame(dialogo, fg_color="#161b22")
        f_btns.pack()
        ctk.CTkButton(f_btns, text="🟡  EM ANDAMENTO", fg_color="#7d6400", hover_color="#a88700",
                      width=200, command=lambda: aplicar("EM ANDAMENTO")).pack(pady=5)
        ctk.CTkButton(f_btns, text="🟢  FINALIZADO", fg_color="#1a6b30", hover_color="#27ae60",
                      width=200, command=lambda: aplicar("FINALIZADO")).pack(pady=5)

    def buscar_os(self):
        termo_bruto = self.ent_busca.get().strip()
        termo = termo_bruto.upper()
        termo_digitos = re.sub(r"\D", "", termo_bruto)
        for item in self.tab.get_children():
            self.tab.delete(item)

        self.dados_os = None

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                if termo:
                    like_termo = f"%{termo}%"
                    like_telefone = f"%{termo_digitos}%" if termo_digitos else like_termo
                    cursor.execute(
                        """
                        SELECT oa.id, COALESCE(c.id, ''), oa.cliente, oa.equipamento, oa.defeito, oa.valor_total,
                               oa.sinal, oa.saldo, oa.status, oa.data, COALESCE(oa.itens_detalhes, ''),
                               COALESCE(c.telefone, ''), COALESCE(oa.dados_adicionais, '')
                        FROM orcamentos_aguardo oa
                        LEFT JOIN clientes c ON UPPER(c.nome) = UPPER(oa.cliente)
                        WHERE CAST(oa.id AS TEXT) LIKE ?
                           OR UPPER(oa.cliente) LIKE ?
                           OR REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(c.telefone, ''), '(', ''), ')', ''), '-', ''), ' ', '') LIKE ?
                                    OR REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(oa.dados_adicionais, ''), '(', ''), ')', ''), '-', ''), ' ', '') LIKE ?
                        ORDER BY oa.id DESC
                        """,
                        (like_termo, like_termo, like_telefone, like_termo)
                    )
                else:
                    cursor.execute(
                        """
                        SELECT oa.id, COALESCE(c.id, ''), oa.cliente, oa.equipamento, oa.defeito, oa.valor_total,
                               oa.sinal, oa.saldo, oa.status, oa.data, COALESCE(oa.itens_detalhes, ''),
                               COALESCE(c.telefone, ''), COALESCE(oa.dados_adicionais, '')
                        FROM orcamentos_aguardo oa
                        LEFT JOIN clientes c ON UPPER(c.nome) = UPPER(oa.cliente)
                        ORDER BY oa.id DESC
                        """
                    )

                rows = cursor.fetchall()

            for row in rows:
                id_orc, id_cli, nome_cli, equipamento, defeito, total, sinal, saldo, status, data, itens_json, telefone_cli, dados_adicionais = row
                id_nome = f"{id_cli} - {nome_cli}" if id_cli else str(nome_cli or "")
                descricao_fmt = self._formatar_itens(itens_json)
                telefone = str(telefone_cli or "").strip()
                if not telefone and dados_adicionais:
                    try:
                        json_adicional = json.loads(dados_adicionais)
                        telefone = str(json_adicional.get("cliente_telefone", "") or "").strip()
                    except Exception:
                        telefone = ""
                status_upper = (status or "").upper()
                if status_upper in ("AGUARDANDO", "EM ANDAMENTO"):
                    tag = "st_amarelo"
                elif status_upper in ("FINALIZADO", "APROVADO"):
                    tag = "st_verde"
                elif status_upper == "REPROVADO":
                    tag = "st_vermelho"
                else:
                    tag = "st_padrao"
                self.tab.insert(
                    "",
                    "end",
                    values=(
                        id_orc,
                        id_nome,
                        telefone,
                        equipamento or "",
                        defeito or "",
                        f"R$ {float(total or 0):.2f}",
                        f"R$ {float(sinal or 0):.2f}",
                        f"R$ {float(saldo or 0):.2f}",
                        status or "",
                        data or "-",
                        descricao_fmt,
                    ),
                    tags=(tag,)
                )

            if rows:
                self.lbl_info.configure(text=f"{len(rows)} O.S.(s) encontrada(s). Filtro dinâmico por nº, cliente e WhatsApp ativo.")
            else:
                self.lbl_info.configure(text="Nenhuma O.S. encontrada para o filtro informado.")
        except Exception as e:
            self.lbl_info.configure(text=f"Erro ao consultar orçamentos: {e}")

    def gerar_recibo_duplo_clique(self, event=None):
        if event is not None:
            self.selecionar_orcamento()

        if not self.dados_os:
            messagebox.showwarning("Aviso", "Selecione um orçamento na lista.", parent=self)
            return

        num_os = int(self.dados_os[0])
        status_atual = str(self.dados_os[7] or "").upper().strip()
        if status_atual not in {"FINALIZADO", "APROVADO", "ENTREGUE"}:
            messagebox.showwarning(
                "Recibo",
                "O recibo de entrega só pode ser gerado para O.S. FINALIZADA/APROVADA/ENTREGUE.",
                parent=self,
            )
            return

        confirmar = messagebox.askyesno(
            "Gerar recibo",
            f"Gerar recibo de entrega da O.S. {num_os}?\n\n"
            "Ao gerar, o status será atualizado para ENTREGUE e o financeiro será lançado automaticamente.",
            parent=self,
        )
        if not confirmar:
            return

        try:
            caminho_pdf = gerar_recibo_entrega(self.dados_os)
            messagebox.showinfo("Recibo", f"Recibo gerado com sucesso:\n{caminho_pdf}", parent=self)
            self.buscar_os()
            self._notificar_dashboard()
        except Exception as e:
            messagebox.showerror("Recibo", f"Erro ao gerar recibo: {e}", parent=self)

    def selecionar_orcamento(self, event=None):
        selecao = self.tab.selection()
        if not selecao:
            self.dados_os = None
            return

        item = self.tab.item(selecao[0], "values")
        num_os = item[0]

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, cliente, equipamento, defeito, valor_total, sinal, saldo, status, data
                    FROM orcamentos_aguardo
                    WHERE id = ?
                    """,
                    (num_os,)
                )
                self.dados_os = cursor.fetchone()

            if hasattr(self.master, "_ultima_os_contexto"):
                self.master._ultima_os_contexto = self.dados_os

            if not self.dados_os:
                self.lbl_info.configure(text="Não foi possível carregar os detalhes do orçamento selecionado.")
                return

            status = (self.dados_os[7] or "").upper()
            resumo = (
                f"Nº {self.dados_os[0]}  |  {self.dados_os[1] or ''}  |  "
                f"{self.dados_os[2] or ''}  |  R$ {float(self.dados_os[4] or 0):.2f}  |  {status or '-'}"
            )
            self.lbl_info.configure(text=resumo)
        except Exception as e:
            self.lbl_info.configure(text=f"Erro ao carregar detalhes: {e}")

    def abrir_orcamento_selecionado(self, event=None):
        if event is not None:
            self.selecionar_orcamento()

        if not self.dados_os:
            messagebox.showwarning("Aviso", "Selecione um orçamento na lista.", parent=self)
            return

        try:
            janela = tela_os.FrmOS(self.master, id_orc=self.dados_os[0], on_save_callback=self.on_os_update_callback)
            if hasattr(self.master, "_janela_os_atual"):
                self.master._janela_os_atual = janela
            if hasattr(self.master, "_ultima_os_contexto"):
                self.master._ultima_os_contexto = self.dados_os
            janela.focus_force()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir o orçamento: {e}", parent=self)

    def aprovar_os(self):
        if not self.dados_os:
            messagebox.showwarning("Aviso", "Selecione um orçamento na lista.", parent=self)
            return
        try:
            num_os = self.dados_os[0]
            status_atual = (self.dados_os[7] or "").upper()
            janela = tela_os.FrmOS(self.master, id_orc=num_os)
            janela.focus_force()
            if status_atual == "APROVADO":
                janela.gerar_documento_pdf("ORDEM DE SERVIÇO")
            else:
                messagebox.showinfo(
                    "Aprovação",
                    f"O orçamento {num_os} foi aberto na tela de O.S.\nA aprovação e o lançamento no financeiro devem ser feitos por lá.",
                    parent=self
                )
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao abrir aprovação: {e}")

    def reprovar_os(self):
        if not self.dados_os:
            messagebox.showwarning("Aviso", "Selecione um orçamento na lista.", parent=self)
            return
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE orcamentos_aguardo SET status = 'REPROVADO' WHERE id = ?", (self.dados_os[0],))
            conn.commit()
        messagebox.showwarning("Aviso", "Orçamento marcado como REPROVADO.")
        self.buscar_os()
        self._notificar_dashboard()