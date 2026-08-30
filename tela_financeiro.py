# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import csv
import csv
import customtkinter as ctk
import sqlite3
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk
from version_info import VERSION
from core.financeiro.calculos import formatar_monetario, parse_monetario
from core.financeiro.repository import (
    editar_lancamento_financeiro,
    estornar_lancamento_financeiro,
    inserir_lancamento_financeiro,
    listar_lancamentos_financeiro,
)
from core.financeiro.service import carregar_dados_financeiros
from core.i18n import t
from reforma_tributaria import garantir_estrutura_reforma_tributaria, ler_config_reforma_tributaria, salvar_config_reforma_tributaria

from config import CAMINHO_BANCO, inicializar_banco, verify_password, get_db_connection

caminho_banco = CAMINHO_BANCO


class FrmFinanceiro(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        inicializar_banco()
        self.title(f"{t('titulo_financeiro')} - OFICINA DE PESCA v{VERSION}")
        self.geometry("1280x740")
        self.minsize(1120, 700)
        self.grab_set()
        self.focus_force()
        self.configure(fg_color="#161b22")
        self._aplicar_maximizacao()
        self.after(120, self._aplicar_maximizacao)

        hoje = datetime.now()
        inicio_mes = hoje.replace(day=1)

        header = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=20)
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(header, text=t("titulo_financeiro"), font=("Arial", 26, "bold"), text_color="orange").pack(side="left", padx=20, pady=20)
        self.lbl_saldo = ctk.CTkLabel(header, text=f"{t('saldo_geral_caixa', default='SALDO GERAL EM CAIXA')}: R$ 0.00", font=("Arial", 18, "bold"), text_color="#2ecc71")
        self.lbl_saldo.pack(side="right", padx=20, pady=20)

        content = ctk.CTkFrame(self, fg_color="#161b22")
        content.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.frame_botoes = ctk.CTkFrame(content, fg_color="#1f2a38", corner_radius=20)
        self.frame_botoes.pack(fill="x", pady=(0, 10), padx=10)
        ctk.CTkButton(self.frame_botoes, text=f"+ {t('btn_lancar_despesa')}", fg_color="#c0392b", width=170, command=self.lancar_saida).pack(side="left", padx=8, pady=15)
        ctk.CTkButton(self.frame_botoes, text=f"+ {t('btn_lancar_receita')}", fg_color="#27ae60", width=170, command=self.lancar_entrada).pack(side="left", padx=8, pady=15)
        ctk.CTkButton(self.frame_botoes, text=t('btn_editar'), fg_color="#8e44ad", width=130, command=self.editar_lancamento).pack(side="left", padx=8, pady=15)
        ctk.CTkButton(self.frame_botoes, text=t('btn_estornar'), fg_color="#7f8c8d", width=130, command=self.estornar_lancamento).pack(side="left", padx=8, pady=15)
        ctk.CTkButton(self.frame_botoes, text=t('btn_exportar_csv'), fg_color="#2980b9", width=160, command=self.exportar_csv).pack(side="left", padx=8, pady=15)
        ctk.CTkButton(self.frame_botoes, text=t('btn_atualizar'), fg_color="#34495e", width=140, command=self.carregar_dados).pack(side="right", padx=10, pady=15)

        filter_frame = ctk.CTkFrame(content, fg_color="#1f2a38", corner_radius=20)
        filter_frame.pack(fill="x", pady=(0, 10), padx=10)
        ctk.CTkLabel(filter_frame, text=t('label_de'), font=("Arial", 12, "bold"), text_color="#ecf0f1").pack(side="left", padx=(20, 8), pady=12)
        self.ent_data_inicio = ctk.CTkEntry(filter_frame, width=110, placeholder_text="01/04/2026")
        self.ent_data_inicio.insert(0, inicio_mes.strftime("%d/%m/%Y"))
        self.ent_data_inicio.pack(side="left", padx=5, pady=12)
        ctk.CTkLabel(filter_frame, text=t('label_ate'), font=("Arial", 12, "bold"), text_color="#ecf0f1").pack(side="left", padx=(10, 8), pady=12)
        self.ent_data_fim = ctk.CTkEntry(filter_frame, width=110, placeholder_text="30/04/2026")
        self.ent_data_fim.insert(0, hoje.strftime("%d/%m/%Y"))
        self.ent_data_fim.pack(side="left", padx=5, pady=12)
        self.ent_busca = ctk.CTkEntry(filter_frame, placeholder_text=t("ui_buscar_descricao_categoria_ou_pagamento"), width=330)
        self.ent_busca.pack(side="left", padx=12, pady=12)
        ctk.CTkButton(filter_frame, text=t('btn_aplicar'), fg_color="#2980b9", width=120, command=self.carregar_dados).pack(side="left", padx=6, pady=12)
        ctk.CTkButton(filter_frame, text=t('btn_limpar'), fg_color="#7f8c8d", width=100, command=self.limpar_filtros).pack(side="left", padx=6, pady=12)

        tabela_card = ctk.CTkFrame(content, fg_color="#1f2a38", corner_radius=20)
        tabela_card.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=30, font=("Arial", 11), background="#1f2a38", fieldbackground="#1f2a38", foreground="#ecf0f1")
        style.configure("Treeview.Heading", font=("Arial", 11, "bold"))

        self.tab_caixa = ttk.Treeview(
            tabela_card,
            columns=("id", "data", "desc", "tipo", "valor", "categoria", "metodo"),
            show="headings"
        )
        self.tab_caixa.heading("id", text=t('col_id').upper())
        self.tab_caixa.heading("data", text=t('col_data').upper())
        self.tab_caixa.heading("desc", text=t('col_descricao').upper())
        self.tab_caixa.heading("tipo", text=t('col_tipo').upper())
        self.tab_caixa.heading("valor", text=t('col_valor').upper())
        self.tab_caixa.heading("categoria", text=t('col_categoria').upper())
        self.tab_caixa.heading("metodo", text=t('col_pagamento').upper())
        self.tab_caixa.column("id", width=60, anchor="center")
        self.tab_caixa.column("data", width=110, anchor="center")
        self.tab_caixa.column("desc", width=390)
        self.tab_caixa.column("tipo", width=90, anchor="center")
        self.tab_caixa.column("valor", width=120, anchor="e")
        self.tab_caixa.column("categoria", width=190, anchor="center")
        self.tab_caixa.column("metodo", width=150, anchor="center")
        self.tab_caixa.tag_configure("entrada", background="#0d2b18", foreground="#9ef0b2")
        self.tab_caixa.tag_configure("saida", background="#341313", foreground="#ffb3b3")
        self.tab_caixa.pack(fill="both", expand=True, padx=20, pady=20)

        self.frame_resumo = ctk.CTkFrame(content, fg_color="#1f2a38", corner_radius=20)
        self.frame_resumo.pack(fill="x", pady=(0, 10), padx=10)
        self.lbl_entradas = ctk.CTkLabel(self.frame_resumo, text=t("ui_entradas_filtradas_nr_0_00"), font=("Arial", 14, "bold"), text_color="#000000", fg_color="#c8f7c5", corner_radius=8, width=240, height=58)
        self.lbl_entradas.pack(side="left", padx=10, pady=15)
        self.lbl_saidas = ctk.CTkLabel(self.frame_resumo, text=t("ui_saidas_filtradas_nr_0_00"), font=("Arial", 14, "bold"), text_color="#000000", fg_color="#ff9f9a", corner_radius=8, width=240, height=58)
        self.lbl_saidas.pack(side="left", padx=10, pady=15)
        self.lbl_saldo_resumo = ctk.CTkLabel(self.frame_resumo, text=t("ui_saldo_do_filtro_nr_0_00"), font=("Arial", 14, "bold"), text_color="#000000", fg_color="#b7ef8a", corner_radius=8, width=240, height=58)
        self.lbl_saldo_resumo.pack(side="left", padx=10, pady=15)
        self.lbl_saldo_receber = ctk.CTkLabel(self.frame_resumo, text=t("ui_saldo_a_receber_nr_0_00"), font=("Arial", 14, "bold"), text_color="#000000", fg_color="#fff36d", corner_radius=8, width=240, height=58)
        self.lbl_saldo_receber.pack(side="left", padx=10, pady=15)

        self.frame_pagamento = ctk.CTkFrame(content, fg_color="#1f2a38", corner_radius=20)
        self.frame_pagamento.pack(fill="x", pady=(0, 10), padx=10)
        ctk.CTkLabel(self.frame_pagamento, text=t('recebimentos_pagamento', default='RECEBIMENTOS NO PERÍODO POR PAGAMENTO'), font=("Arial", 12, "bold"), text_color="#bdc3c7").pack(anchor="w", padx=15, pady=(8, 0))
        self.lbl_pix = ctk.CTkLabel(self.frame_pagamento, text=t("ui_pix_nr_0_00"), font=("Arial", 13, "bold"), text_color="#000000", fg_color="#a8e6ff", corner_radius=8, width=220, height=56)
        self.lbl_pix.pack(side="left", padx=10, pady=12)
        self.lbl_dinheiro = ctk.CTkLabel(self.frame_pagamento, text=t("ui_dinheiro_nr_0_00"), font=("Arial", 13, "bold"), text_color="#000000", fg_color="#d2f8c8", corner_radius=8, width=220, height=56)
        self.lbl_dinheiro.pack(side="left", padx=10, pady=12)
        self.lbl_cartao = ctk.CTkLabel(self.frame_pagamento, text=t("ui_cartao_nr_0_00"), font=("Arial", 13, "bold"), text_color="#000000", fg_color="#f2d5ff", corner_radius=8, width=220, height=56)
        self.lbl_cartao.pack(side="left", padx=10, pady=12)

        self.btn_reforma = ctk.CTkButton(
            self.frame_botoes,
            text=t("ui_ibs_cbs"),
            fg_color="#566573",
            width=130,
            command=self.abrir_config_reforma_tributaria,
        )
        self.btn_reforma.pack(side="right", padx=8, pady=15)

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
            return datetime.strptime(texto.strip(), "%d/%m/%Y")
        except Exception:
            return None

    def _data_sql(self, coluna):
        return f"date(substr({coluna},7,4)||'-'||substr({coluna},4,2)||'-'||substr({coluna},1,2))"

    def _selecionado(self):
        selecao = self.tab_caixa.selection()
        if not selecao:
            return None
        return self.tab_caixa.item(selecao[0], "values")

    def _eh_lancamento_automatico_os(self, descricao, categoria):
        texto_desc = str(descricao or "").upper()
        texto_cat = str(categoria or "").upper()
        return ("SINAL O.S." in texto_desc) or ("ORDEM DE SERV" in texto_cat)

    def _autenticar_admin(self, acao):
        usuario = simpledialog.askstring("Autorizacao Admin", f"Usuario ADMIN para {acao}:", parent=self)
        if not usuario:
            return False

    def abrir_config_reforma_tributaria(self):
        dialogo = ctk.CTkToplevel(self)
        dialogo.title("Reforma Tributaria (latente)")
        dialogo.geometry("620x360")
        dialogo.resizable(False, False)
        dialogo.configure(fg_color="#161b22")
        dialogo.grab_set()
        dialogo.focus_force()

        with get_db_connection() as conn:
            cursor = conn.cursor()
            garantir_estrutura_reforma_tributaria(cursor)
            cfg = ler_config_reforma_tributaria(cursor)

        ctk.CTkLabel(dialogo, text=t("ui_configuracao_latente_de_ibs_cbs"), font=("Arial", 18, "bold"), text_color="orange").pack(pady=(18, 8))
        ctk.CTkLabel(dialogo, text=t("ui_nada_aqui_altera_o_fluxo_atual_esta_tela_apenas_prepara_o_ma"), font=("Arial", 12), text_color="#d5d8dc", wraplength=560).pack(pady=(0, 12))

        frame = ctk.CTkFrame(dialogo, fg_color="#1f2a38", corner_radius=18)
        frame.pack(fill="both", expand=True, padx=20, pady=10)

        ent_regime = ctk.CTkEntry(frame, width=220)
        ent_regime.insert(0, str(cfg.get("regime") or "latente"))
        ent_regime.grid(row=0, column=0, padx=12, pady=10, sticky="ew")
        ent_aliq_ibs = ctk.CTkEntry(frame, width=220)
        ent_aliq_ibs.insert(0, f"{float(cfg.get('aliquota_ibs_padrao') or 0):.2f}")
        ent_aliq_ibs.grid(row=0, column=1, padx=12, pady=10, sticky="ew")
        ent_aliq_cbs = ctk.CTkEntry(frame, width=220)
        ent_aliq_cbs.insert(0, f"{float(cfg.get('aliquota_cbs_padrao') or 0):.2f}")
        ent_aliq_cbs.grid(row=1, column=0, padx=12, pady=10, sticky="ew")
        ent_vigencia = ctk.CTkEntry(frame, width=220)
        ent_vigencia.insert(0, str(cfg.get("vigencia_inicio") or ""))
        ent_vigencia.grid(row=1, column=1, padx=12, pady=10, sticky="ew")
        ent_split = ctk.CTkSwitch(frame, text=t("ui_split_payment_padrao"))
        if int(cfg.get("split_payment_padrao") or 0):
            ent_split.select()
        ent_split.grid(row=2, column=0, padx=12, pady=10, sticky="w")
        ent_obs = ctk.CTkEntry(frame, width=460, placeholder_text=t("ui_observacoes_opcionais"))
        ent_obs.insert(0, str(cfg.get("observacoes") or ""))
        ent_obs.grid(row=2, column=1, padx=12, pady=10, sticky="ew")

        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        def salvar():
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    garantir_estrutura_reforma_tributaria(cursor)
                    salvar_config_reforma_tributaria(
                        cursor,
                        {
                            "regime": ent_regime.get().strip() or "latente",
                            "ativo": 0,
                            "vigencia_inicio": ent_vigencia.get().strip(),
                            "aliquota_ibs_padrao": float(ent_aliq_ibs.get().replace(",", ".") or 0),
                            "aliquota_cbs_padrao": float(ent_aliq_cbs.get().replace(",", ".") or 0),
                            "split_payment_padrao": 1 if ent_split.get() else 0,
                            "observacoes": ent_obs.get().strip(),
                        },
                    )
                    conn.commit()
                messagebox.showinfo("Sucesso", "Configuracao latente salva com sucesso.", parent=dialogo)
                dialogo.destroy()
            except Exception as exc:
                messagebox.showerror("Erro", f"Nao foi possivel salvar a configuracao: {exc}", parent=dialogo)

        ctk.CTkButton(dialogo, text=t("ui_salvar_1"), fg_color="green", width=150, command=salvar).pack(side="left", padx=20, pady=16)
        ctk.CTkButton(dialogo, text=t("ui_fechar"), fg_color="#7f8c8d", width=150, command=dialogo.destroy).pack(side="right", padx=20, pady=16)

        dialogo.wait_window()
        senha = simpledialog.askstring("Autorizacao Admin", "Senha ADMIN:", show="*", parent=self)
        if not senha:
            return False
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT senha, role FROM usuarios WHERE UPPER(usuario)=UPPER(?) LIMIT 1", (usuario.strip(),))
                row = cursor.fetchone()
            if not row:
                messagebox.showwarning("Acesso negado", "Usuario ADMIN nao encontrado.", parent=self)
                return False
            senha_hash, role = row
            if str(role or "").upper() != "ADMIN":
                messagebox.showwarning("Acesso negado", "Somente ADMIN pode executar esta acao.", parent=self)
                return False
            if not verify_password(senha, str(senha_hash or "")):
                messagebox.showwarning("Acesso negado", "Senha ADMIN invalida.", parent=self)
                return False
            return True
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao validar ADMIN: {e}", parent=self)
            return False

    def _perguntar_metodo_pagamento(self, titulo="Forma de pagamento", valor_inicial=None):
        dialogo = ctk.CTkToplevel(self)
        dialogo.title(titulo)
        dialogo.geometry("300x250")
        dialogo.resizable(False, False)
        dialogo.configure(fg_color="#161b22")
        dialogo.grab_set()
        dialogo.focus_force()

        ctk.CTkLabel(dialogo, text=titulo, font=("Arial", 13, "bold"), text_color="orange", wraplength=250).pack(pady=(18, 12))
        resultado = {"metodo": valor_inicial}

        def escolher(metodo):
            resultado["metodo"] = metodo
            dialogo.destroy()

        f = ctk.CTkFrame(dialogo, fg_color="#161b22")
        f.pack()
        ctk.CTkButton(f, text=t("ui_dinheiro_1"), fg_color="#1a6b30", hover_color="#27ae60", width=200, command=lambda: escolher("DINHEIRO")).pack(pady=5)
        ctk.CTkButton(f, text=t("ui_pix"), fg_color="#1a4b6b", hover_color="#2980b9", width=200, command=lambda: escolher("PIX")).pack(pady=5)
        ctk.CTkButton(f, text=t("ui_cartao"), fg_color="#4b1a6b", hover_color="#8e44ad", width=200, command=lambda: escolher("CARTAO")).pack(pady=5)
        ctk.CTkButton(f, text=t("ui_cancelar"), fg_color="#7f8c8d", hover_color="#95a5a6", width=200, command=dialogo.destroy).pack(pady=(12, 0))

        dialogo.wait_window()
        return resultado["metodo"]

    def limpar_filtros(self):
        hoje = datetime.now()
        self.ent_data_inicio.delete(0, "end")
        self.ent_data_inicio.insert(0, hoje.replace(day=1).strftime("%d/%m/%Y"))
        self.ent_data_fim.delete(0, "end")
        self.ent_data_fim.insert(0, hoje.strftime("%d/%m/%Y"))
        self.ent_busca.delete(0, "end")
        self.carregar_dados()

    def lancar_saida(self):
        desc = simpledialog.askstring("Gasto", "Descricao do gasto:", parent=self)
        if not desc:
            return
        valor = simpledialog.askfloat("Gasto", "Valor da saida (R$):", parent=self)
        if valor is None or valor <= 0:
            messagebox.showwarning("Atencao", "Informe um valor valido para a saida.", parent=self)
            return
        categoria = simpledialog.askstring("Gasto", "Categoria da saida:", initialvalue="DESPESA OPERACIONAL", parent=self) or "DESPESA OPERACIONAL"
        metodo = self._perguntar_metodo_pagamento("Como foi paga essa despesa?")
        if not metodo:
            return
        try:
            inserir_lancamento_financeiro(
                datetime.now().strftime("%d/%m/%Y"),
                desc.upper(),
                "SAIDA",
                valor,
                categoria.upper(),
                metodo,
            )
            self.carregar_dados()
            messagebox.showinfo("Sucesso", "Despesa lancada com sucesso.", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar gasto: {e}", parent=self)

    def lancar_entrada(self):
        descricao = simpledialog.askstring("Receita", "Descricao da receita:", parent=self)
        if not descricao:
            return
        valor = simpledialog.askfloat("Receita", "Valor da entrada (R$):", parent=self)
        if valor is None or valor <= 0:
            messagebox.showwarning("Atencao", "Informe um valor valido para a entrada.", parent=self)
            return
        categoria = simpledialog.askstring("Receita", "Categoria da entrada:", initialvalue="RECEITA AVULSA", parent=self) or "RECEITA AVULSA"
        metodo = self._perguntar_metodo_pagamento("Qual a forma de recebimento?")
        if not metodo:
            return
        try:
            inserir_lancamento_financeiro(
                datetime.now().strftime("%d/%m/%Y"),
                descricao.upper(),
                "ENTRADA",
                valor,
                categoria.upper(),
                metodo,
            )
            self.carregar_dados()
            messagebox.showinfo("Sucesso", "Entrada lancada com sucesso.", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar entrada: {e}", parent=self)

    def editar_lancamento(self):
        item = self._selecionado()
        if not item:
            messagebox.showwarning("Atencao", "Selecione um lancamento para editar.", parent=self)
            return

        if not self._autenticar_admin("editar lancamento"):
            return

        id_mov, _data, descricao_atual, _tipo, valor_txt, categoria_atual, metodo_atual = item
        valor_base = parse_monetario(valor_txt)

        descricao = simpledialog.askstring("Editar", "Descricao:", initialvalue=descricao_atual, parent=self)
        if not descricao:
            return
        valor = simpledialog.askfloat("Editar", "Valor (R$):", initialvalue=valor_base, parent=self)
        if valor is None or valor <= 0:
            messagebox.showwarning("Atencao", "Informe um valor valido.", parent=self)
            return
        categoria = simpledialog.askstring("Editar", "Categoria:", initialvalue=categoria_atual, parent=self) or categoria_atual
        metodo = self._perguntar_metodo_pagamento("Forma de pagamento", valor_inicial=metodo_atual)
        if not metodo:
            return

        try:
            editar_lancamento_financeiro(id_mov, descricao.upper(), valor, categoria.upper(), metodo)
            self.carregar_dados()
        except Exception as e:
            messagebox.showerror("Erro", f"Nao foi possivel editar: {e}", parent=self)

    def estornar_lancamento(self):
        item = self._selecionado()
        if not item:
            messagebox.showwarning("Atencao", "Selecione um lancamento para estornar.", parent=self)
            return

        if not self._autenticar_admin("estornar lancamento"):
            return

        id_mov, _data, descricao, tipo, valor_txt, categoria, metodo = item
        valor = parse_monetario(valor_txt)
        tipo_estorno = "SAIDA" if str(tipo).upper() == "ENTRADA" else "ENTRADA"
        descricao_estorno = f"ESTORNO REF. #{id_mov} - {descricao}"[:255]

        if not messagebox.askyesno("Estorno", f"Gerar estorno do lancamento #{id_mov}?", parent=self):
            return

        try:
            inserir_lancamento_financeiro(
                datetime.now().strftime("%d/%m/%Y"),
                descricao_estorno.upper(),
                tipo_estorno,
                valor,
                f"ESTORNO {categoria}".upper(),
                metodo,
            )
            self.carregar_dados()
            messagebox.showinfo("Sucesso", "Estorno lancado com sucesso.", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", f"Nao foi possivel estornar: {e}", parent=self)

    def exportar_csv(self):
        if not self.tab_caixa.get_children():
            messagebox.showwarning("Atencao", "Nao ha dados para exportar com o filtro atual.", parent=self)
            return
        caminho = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar financeiro",
            defaultextension=".csv",
            initialfile=f"financeiro_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            filetypes=[("CSV", "*.csv")]
        )
        if not caminho:
            return
        try:
            with open(caminho, "w", newline="", encoding="utf-8-sig") as arquivo:
                writer = csv.writer(arquivo, delimiter=";")
                writer.writerow(["ID", "DATA", "DESCRICAO", "TIPO", "VALOR", "CATEGORIA", "PAGAMENTO"])
                for item_id in self.tab_caixa.get_children():
                    writer.writerow(self.tab_caixa.item(item_id, "values"))
            messagebox.showinfo("Sucesso", "CSV exportado com sucesso.", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", f"Nao foi possivel exportar: {e}", parent=self)

    def carregar_dados(self):
        if not hasattr(self, "tab_caixa") or not self.tab_caixa.winfo_exists():
            return
        for item_id in self.tab_caixa.get_children():
            self.tab_caixa.delete(item_id)

        dt_ini = self._parse_data(self.ent_data_inicio.get())
        dt_fim = self._parse_data(self.ent_data_fim.get())
        if not dt_ini or not dt_fim:
            messagebox.showwarning("Atencao", "Use datas validas no formato dd/mm/aaaa.", parent=self)
            return

        d_ini = dt_ini.strftime("%Y-%m-%d")
        d_fim = dt_fim.strftime("%Y-%m-%d")
        busca = self.ent_busca.get().strip()

        try:
            registros, saldo_total, pagamentos, texto_saldo, cor_saldo = carregar_dados_financeiros(d_ini, d_fim, busca=busca)
            entradas = 0.0
            saidas = 0.0
            for row in registros:
                id_mov, data, descricao, tipo, valor, categoria, metodo = row
                valor = parse_monetario(valor)
                if str(tipo).upper() == "ENTRADA":
                    entradas += valor
                    tag = "entrada"
                else:
                    saidas += valor
                    tag = "saida"
                self.tab_caixa.insert(
                    "",
                    "end",
                    values=(id_mov, data, descricao, tipo, formatar_monetario(valor), categoria, metodo),
                    tags=(tag,)
                )

            saldo_filtro = entradas - saidas
            saldo_receber = 0.0
            total_pix = 0.0
            total_dinheiro = 0.0
            total_cartao = 0.0
            for metodo_pg, valor_pg in pagamentos:
                m = str(metodo_pg or "").upper()
                v = parse_monetario(valor_pg)
                if "PIX" in m:
                    total_pix += v
                elif "DINHEIRO" in m:
                    total_dinheiro += v
                elif "CART" in m:
                    total_cartao += v

            self.lbl_saldo.configure(text=texto_saldo, text_color=cor_saldo)
            self.lbl_entradas.configure(text=f"ENTRADAS FILTRADAS\n{formatar_monetario(entradas)}")
            self.lbl_saidas.configure(text=f"SAIDAS FILTRADAS\n{formatar_monetario(saidas)}")
            self.lbl_saldo_resumo.configure(text=f"SALDO DO FILTRO\n{formatar_monetario(saldo_filtro)}", fg_color="#b7ef8a" if saldo_filtro >= 0 else "#ff9f9a")
            self.lbl_saldo_receber.configure(text=f"SALDO A RECEBER\n{formatar_monetario(saldo_receber)}")
            self.lbl_pix.configure(text=f"PIX\n{formatar_monetario(total_pix)}")
            self.lbl_dinheiro.configure(text=f"DINHEIRO\n{formatar_monetario(total_dinheiro)}")
            self.lbl_cartao.configure(text=f"CARTAO\n{formatar_monetario(total_cartao)}")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao carregar financeiro: {e}", parent=self)


if __name__ == "__main__":
    inicializar_banco()
    app = ctk.CTk()
    app.withdraw()
    FrmFinanceiro(app)
    app.mainloop()
