# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import customtkinter as ctk
import sqlite3
import os
import requests
import threading
from tkinter import messagebox, ttk
from datetime import datetime
from version_info import VERSION
from config import CAMINHO_BANCO, inicializar_banco, get_db_connection, get_logger

logger = get_logger(__name__)

inicializar_banco()

class FrmClientes(ctk.CTkToplevel):
    def __init__(self, master, nome_inicial="", ao_salvar=None, cliente_id=None, dados_cliente=None):
        super().__init__(master)
        self.ao_salvar = ao_salvar
        self.cliente_id = cliente_id
        self.title(f"Ficha de Cadastro - Oficina de Pesca v{VERSION}")
        self.geometry("860x860")
        self.minsize(840, 820)
        self._aplicar_maximizacao()
        self.after(120, self._aplicar_maximizacao)

        self.lift()
        self.focus_force()
        self.grab_set()
        self.configure(fg_color="#161b22")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="#161b22")
        self.scroll.pack(pady=10, padx=10, fill="both", expand=True)

        self.f_header = ctk.CTkFrame(self.scroll, fg_color="#1f2a38", corner_radius=20)
        self.f_header.pack(pady=15, padx=20, fill="x")
        ctk.CTkLabel(self.f_header, text="🎣 CADASTRO DE PESCADOR", font=("Arial", 24, "bold"), text_color="orange").pack(side="left", padx=20, pady=20)
        ctk.CTkButton(self.f_header, text="🗂️ VER LISTA / HISTÓRICO", fg_color="#2980b9", width=180,
                      command=self.abrir_lista_completa).pack(side="right", padx=20, pady=20)

        self.f_dados = ctk.CTkFrame(self.scroll, fg_color="#1f2a38", corner_radius=20)
        self.f_dados.pack(pady=10, padx=20, fill="x")
        self.f_dados.grid_columnconfigure(0, weight=1)
        self.f_dados.grid_columnconfigure(1, weight=1)

        self.txt_nome = self.criar_campo("NOME COMPLETO:", 0, 0)
        self.txt_fone = self.criar_campo("TELEFONE/WHATSAPP:", 1, 0)
        self.txt_email = self.criar_campo("E-MAIL:", 2, 0)

        # Campo de CEP com busca automática ao perder o foco
        lbl_cep = ctk.CTkLabel(self.f_dados, text="CEP:", font=("Arial", 12, "bold"), text_color="#ecf0f1")
        lbl_cep.grid(row=6, column=0, padx=20, pady=(20, 5), sticky="w")
        self.txt_cep = ctk.CTkEntry(self.f_dados, width=200)
        self.txt_cep.grid(row=7, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.txt_cep.bind("<FocusOut>", self.buscar_cep)

        # CPF/CNPJ separado do CEP e tratado como identificador único de cliente.
        lbl_cpf = ctk.CTkLabel(self.f_dados, text="CPF/CNPJ:", font=("Arial", 12, "bold"), text_color="#ecf0f1")
        lbl_cpf.grid(row=8, column=0, padx=20, pady=(4, 5), sticky="w")
        self.txt_cpf_cnpj = ctk.CTkEntry(self.f_dados, width=320)
        self.txt_cpf_cnpj.grid(row=9, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.txt_rua = self.criar_campo("LOGRADOURO (Rua/Av):", 0, 1)
        self.txt_num = self.criar_campo("NÚMERO:", 1, 1)
        self.txt_bairro = self.criar_campo("BAIRRO:", 2, 1)
        self.txt_cidade = self.criar_campo("CIDADE:", 3, 1)
        self.txt_estado = self.criar_campo("ESTADO:", 4, 1)

        if nome_inicial:
            self.txt_nome.insert(0, nome_inicial.upper())
            self.txt_fone.focus_set()

        if dados_cliente:
            self._preencher_dados_cliente(dados_cliente)

        botoes_frame = ctk.CTkFrame(self.scroll, fg_color="#1f2a38")
        botoes_frame.pack(pady=20, padx=20, fill="x")
        texto_salvar = "💾 ATUALIZAR CADASTRO" if self.cliente_id else "💾 SALVAR CADASTRO"
        ctk.CTkButton(botoes_frame, text=texto_salvar, fg_color="#27ae60", height=50, font=("Arial", 18, "bold"), command=self.salvar_cliente).pack(side="left", expand=True, fill="x", padx=(0,10))
        ctk.CTkButton(botoes_frame, text="🧹 LIMPAR", fg_color="#7f8c8d", height=50, font=("Arial", 18, "bold"), command=self.limpar_campos).pack(side="left", expand=True, fill="x", padx=(10,0))

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

    def limpar_campos(self):
        for campo in [
            self.txt_nome, self.txt_fone, self.txt_email, self.txt_cep, self.txt_cpf_cnpj,
            self.txt_rua, self.txt_num, self.txt_bairro, self.txt_cidade, self.txt_estado
        ]:
            campo.delete(0, 'end')
        self.txt_nome.focus_set()

    def _normalizar_cpf_cnpj(self, valor: str) -> str:
        bruto = str(valor or "").strip()
        return "".join(ch for ch in bruto.upper() if ch.isalnum())

    def _garantir_schema_identificador(self):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(clientes)")
                cols = {str(row[1] or "").lower() for row in cursor.fetchall()}
                if "cpf_cnpj_normalizado" not in cols:
                    cursor.execute("ALTER TABLE clientes ADD COLUMN cpf_cnpj_normalizado TEXT")
                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_cpf_cnpj_unico
                    ON clientes(cpf_cnpj_normalizado)
                    WHERE cpf_cnpj_normalizado IS NOT NULL AND cpf_cnpj_normalizado <> ''
                    """
                )
                conn.commit()
        except Exception:
            pass

    def criar_campo(self, label, linha, coluna):
        lbl = ctk.CTkLabel(self.f_dados, text=label, font=("Arial", 12, "bold"), text_color="#ecf0f1")
        lbl.grid(row=linha*2, column=coluna, padx=20, pady=(20, 5), sticky="w")
        ent = ctk.CTkEntry(self.f_dados, width=320)
        ent.grid(row=linha*2 + 1, column=coluna, padx=20, pady=(0, 10), sticky="ew")
        return ent

    def _preencher_dados_cliente(self, dados_cliente):
        _id = dados_cliente[0] if len(dados_cliente) > 0 else None
        nome = dados_cliente[1] if len(dados_cliente) > 1 else ""
        telefone = dados_cliente[2] if len(dados_cliente) > 2 else ""
        email = dados_cliente[3] if len(dados_cliente) > 3 else ""
        cpf_cnpj = dados_cliente[4] if len(dados_cliente) > 4 else ""
        cep = dados_cliente[5] if len(dados_cliente) > 5 else ""
        rua = dados_cliente[6] if len(dados_cliente) > 6 else ""
        numero = dados_cliente[7] if len(dados_cliente) > 7 else ""
        bairro = dados_cliente[8] if len(dados_cliente) > 8 else ""
        cidade = dados_cliente[9] if len(dados_cliente) > 9 else ""
        estado = dados_cliente[10] if len(dados_cliente) > 10 else ""
        self.txt_nome.delete(0, 'end'); self.txt_nome.insert(0, str(nome or "").upper())
        self.txt_fone.delete(0, 'end'); self.txt_fone.insert(0, str(telefone or ""))
        self.txt_email.delete(0, 'end'); self.txt_email.insert(0, str(email or ""))
        self.txt_cpf_cnpj.delete(0, 'end'); self.txt_cpf_cnpj.insert(0, str(cpf_cnpj or ""))
        self.txt_cep.delete(0, 'end'); self.txt_cep.insert(0, str(cep or ""))
        self.txt_rua.delete(0, 'end'); self.txt_rua.insert(0, str(rua or "").upper())
        self.txt_num.delete(0, 'end'); self.txt_num.insert(0, str(numero or ""))
        self.txt_bairro.delete(0, 'end'); self.txt_bairro.insert(0, str(bairro or "").upper())
        self.txt_cidade.delete(0, 'end'); self.txt_cidade.insert(0, str(cidade or "").upper())
        self.txt_estado.delete(0, 'end'); self.txt_estado.insert(0, str(estado or "").upper())

    def buscar_cep(self, event=None):
        import urllib.request
        import json
        cep = self.txt_cep.get().replace("-", "").replace(".", "").strip()
        if len(cep) == 8:
            def _thread_task():
                try:
                    url = f"https://viacep.com.br/ws/{cep}/json/"
                    with urllib.request.urlopen(url, timeout=5) as response:
                        data = response.read()
                        retorno = json.loads(data.decode("utf-8"))
                    if "erro" not in retorno:
                        def _atualizar_ui():
                            self.txt_rua.delete(0, 'end')
                            self.txt_rua.insert(0, retorno.get('logradouro', '').upper())
                            self.txt_bairro.delete(0, 'end')
                            self.txt_bairro.insert(0, retorno.get('bairro', '').upper())
                            self.txt_cidade.delete(0, 'end')
                            self.txt_cidade.insert(0, retorno.get('localidade', '').upper())
                            self.txt_estado.delete(0, 'end')
                            self.txt_estado.insert(0, retorno.get('uf', '').upper())
                            self.txt_num.focus_set()
                        self.after(0, _atualizar_ui)
                    else:
                        self.after(0, lambda: messagebox.showwarning("CEP", "CEP não encontrado!", parent=self))
                except Exception:
                    self.after(0, lambda: messagebox.showerror("Conexão", "Falha ao consultar CEP.", parent=self))
            threading.Thread(target=_thread_task, daemon=True).start()

    def salvar_cliente(self):
        nome = self.txt_nome.get().upper().strip() or "CLIENTE NÃO INFORMADO"
        cpf_cnpj_bruto = self.txt_cpf_cnpj.get().strip()
        cpf_cnpj_norm = self._normalizar_cpf_cnpj(cpf_cnpj_bruto)

        self._garantir_schema_identificador()
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                id_por_doc = None
                if cpf_cnpj_norm:
                    cursor.execute(
                        "SELECT id FROM clientes WHERE cpf_cnpj_normalizado = ? LIMIT 1",
                        (cpf_cnpj_norm,),
                    )
                    row_doc = cursor.fetchone()
                    id_por_doc = int(row_doc[0]) if row_doc and row_doc[0] is not None else None

                if self.cliente_id and id_por_doc and id_por_doc != int(self.cliente_id):
                    messagebox.showwarning(
                        "CPF/CNPJ já cadastrado",
                        "Já existe outro cliente com este CPF/CNPJ. Use o registro existente para editar.",
                        parent=self,
                    )
                    return

                alvo_id = int(self.cliente_id) if self.cliente_id else id_por_doc

                if alvo_id:
                    cursor.execute(
                        """
                        UPDATE clientes
                        SET nome = ?, telefone = ?, email = ?, cpf_cnpj = ?, cpf_cnpj_normalizado = ?, cep = ?, rua = ?, numero = ?, bairro = ?, cidade = ?, estado = ?
                        WHERE id = ?
                        """,
                        (
                            nome,
                            self.txt_fone.get(),
                            self.txt_email.get(),
                            cpf_cnpj_bruto,
                            cpf_cnpj_norm,
                            self.txt_cep.get(),
                            self.txt_rua.get(),
                            self.txt_num.get(),
                            self.txt_bairro.get(),
                            self.txt_cidade.get(),
                            self.txt_estado.get(),
                            alvo_id,
                        ),
                    )
                else:
                    cursor.execute("""INSERT INTO clientes (nome, telefone, email, cpf_cnpj, cpf_cnpj_normalizado, cep, rua, numero, bairro, cidade, estado, data_cadastro) 
                                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                                   (nome, self.txt_fone.get(), self.txt_email.get(), cpf_cnpj_bruto, cpf_cnpj_norm, self.txt_cep.get(), 
                                    self.txt_rua.get(), self.txt_num.get(), self.txt_bairro.get(), self.txt_cidade.get(), 
                                    self.txt_estado.get(), datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
            if callable(self.ao_salvar):
                self.ao_salvar(nome)
            if alvo_id:
                messagebox.showinfo("Sucesso", "Cadastro atualizado com sucesso!", parent=self)
            else:
                messagebox.showinfo("Sucesso", "Pescador cadastrado com sucesso!", parent=self)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar: {e}", parent=self)

    def abrir_lista_completa(self):
        JanelaListaClientes(self.master)

# --- CLASSE DA LISTA COM HISTÓRICO ---
class JanelaListaClientes(ctk.CTkToplevel):
    def __init__(self, master, on_cliente_escolhido=None):
        super().__init__(master)
        self.on_cliente_escolhido = on_cliente_escolhido
        self.title("Consulta e Histórico de Pescadores")
        self.geometry("1250x750")
        self.lift(); self.focus_force(); self.grab_set()
        self._aplicar_maximizacao()
        self.after(120, self._aplicar_maximizacao)
        
        ctk.CTkLabel(self, text="🔎 CONSULTA DE CLIENTES E HISTÓRICO", font=("Arial", 20, "bold"), text_color="orange").pack(pady=15)

        topo_busca = ctk.CTkFrame(self, fg_color="#1f2a38")
        topo_busca.pack(fill="x", padx=20, pady=5)

        self.ent_busca = ctk.CTkEntry(topo_busca, placeholder_text="🔍 Digite o nome para pesquisar...", width=500, height=35)
        self.ent_busca.pack(side="left", pady=5)
        self.ent_busca.bind("<KeyRelease>", lambda e: self.carregar_dados())
        ctk.CTkButton(topo_busca, text="Editar", width=120, fg_color="#2980b9", command=self.editar_cliente_selecionado).pack(side="left", padx=(10, 6), pady=5)
        ctk.CTkButton(topo_busca, text="Excluir", width=120, fg_color="#c0392b", hover_color="#e74c3c", command=self.excluir_cliente_selecionado).pack(side="left", padx=(0, 6), pady=5)

        self.f_tab = ctk.CTkFrame(self)
        self.f_tab.pack(fill="both", expand=True, padx=20, pady=10)

        colunas = ("id", "nome", "whatsapp", "endereco", "bairro", "cidade")
        self.tabela = ttk.Treeview(self.f_tab, columns=colunas, show="headings")
        
        self.tabela.heading("id", text="ID"); self.tabela.column("id", width=40)
        self.tabela.heading("nome", text="NOME"); self.tabela.column("nome", width=250)
        self.tabela.heading("whatsapp", text="WHATSAPP"); self.tabela.column("whatsapp", width=120)
        self.tabela.heading("endereco", text="ENDEREÇO"); self.tabela.column("endereco", width=250)
        self.tabela.heading("bairro", text="BAIRRO"); self.tabela.column("bairro", width=150)
        self.tabela.heading("cidade", text="CIDADE"); self.tabela.column("cidade", width=120)

        self.tabela.pack(side="left", fill="both", expand=True)
        scrol = ttk.Scrollbar(self.f_tab, orient="vertical", command=self.tabela.yview)
        self.tabela.configure(yscroll=scrol.set); scrol.pack(side="right", fill="y")

        self.tabela.bind("<<TreeviewSelect>>", self.carregar_historico_selecionado)
        self.tabela.bind("<Double-1>", self.selecionar_cliente_duplo_clique)

        self.f_hist = ctk.CTkFrame(self, fg_color="#2c3e50")
        self.f_hist.pack(fill="x", padx=20, pady=(0, 20))
        
        ctk.CTkLabel(self.f_hist, text="📜 ÚLTIMO SERVIÇO DESTA PESSOA:", font=("Arial", 12, "bold"), text_color="white").pack(pady=5)
        self.txt_historico = ctk.CTkTextbox(self.f_hist, height=100, font=("Arial", 13), fg_color="#34495e", text_color="white")
        self.txt_historico.pack(fill="x", padx=10, pady=10)

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

    def carregar_dados(self):
        for i in self.tabela.get_children(): self.tabela.delete(i)
        busca = f"%{self.ent_busca.get().upper()}%"
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""SELECT id, nome, COALESCE(telefone, ''), (COALESCE(rua, '') || ', ' || COALESCE(numero, '')), COALESCE(bairro, ''), COALESCE(cidade, '') 
                                  FROM clientes WHERE UPPER(nome) LIKE ? ORDER BY nome""", (busca,))
                for linha in cursor.fetchall():
                    self.tabela.insert("", "end", values=linha)
        except Exception as e:
            logger.exception("Erro ao carregar lista de clientes: %s", e)

    def _obter_cliente_selecionado(self):
        selecao = self.tabela.selection()
        if not selecao:
            return None
        valores = self.tabela.item(selecao[0], "values")
        if not valores:
            return None
        return {
            "id": int(valores[0]),
            "nome": str(valores[1] or ""),
            "whatsapp": str(valores[2] or ""),
            "endereco": str(valores[3] or ""),
        }

    def editar_cliente_selecionado(self):
        cliente = self._obter_cliente_selecionado()
        if not cliente:
            messagebox.showwarning("Clientes", "Selecione um cliente para editar.", parent=self)
            return
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, nome, telefone, email, COALESCE(cpf_cnpj, ''), cep, rua, numero, bairro, cidade, estado
                    FROM clientes WHERE id = ?
                    """,
                    (cliente["id"],),
                )
                dados = cursor.fetchone()
            if not dados:
                messagebox.showwarning("Clientes", "Cliente não encontrado.", parent=self)
                return

            def _apos_atualizar(_nome):
                self.carregar_dados()

            FrmClientes(self, ao_salvar=_apos_atualizar, cliente_id=cliente["id"], dados_cliente=dados)
        except Exception as e:
            messagebox.showerror("Clientes", f"Não foi possível editar o cliente: {e}", parent=self)

    def excluir_cliente_selecionado(self):
        cliente = self._obter_cliente_selecionado()
        if not cliente:
            messagebox.showwarning("Clientes", "Selecione um cliente para excluir.", parent=self)
            return
        if not messagebox.askyesno("Excluir cliente", f"Deseja excluir o cliente {cliente['nome']}?", parent=self):
            return
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM clientes WHERE id = ?", (cliente["id"],))
                conn.commit()
            self.carregar_dados()
            self.txt_historico.delete("0.0", "end")
            self.txt_historico.insert("0.0", "Cliente excluído com sucesso.")
        except Exception as e:
            messagebox.showerror("Clientes", f"Não foi possível excluir o cliente: {e}", parent=self)

    def selecionar_cliente_duplo_clique(self, _event=None):
        cliente = self._obter_cliente_selecionado()
        if not cliente:
            return
        if callable(self.on_cliente_escolhido):
            self.on_cliente_escolhido(cliente)
        self.destroy()

    def carregar_historico_selecionado(self, event):
        selecao = self.tabela.selection()
        if not selecao: return
        nome_cliente = self.tabela.item(selecao[0], "values")[1]
        self.txt_historico.delete("0.0", "end")
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""SELECT data, equipamento, itens_detalhes, valor_total 
                                  FROM orcamentos_aguardo WHERE cliente = ? 
                                  ORDER BY id DESC LIMIT 1""", (nome_cliente,))
                h = cursor.fetchone()
            if h:
                resumo = f"📅 DATA: {h[0]}  |  🎣 EQUIPAMENTO: {h[1]}\n🛠️ SERVIÇO: {h[2]}\n💰 VALOR: R$ {h[3]:.2f}"
                self.txt_historico.insert("0.0", resumo)
            else:
                self.txt_historico.insert("0.0", "Nenhum serviço registrado para este pescador.")
        except Exception as e:
            logger.exception("Erro ao buscar histórico do cliente: %s", e)
            self.txt_historico.insert("0.0", "Erro ao buscar histórico.")

if __name__ == "__main__":
    root = ctk.CTk()
    root.withdraw()
    app = FrmClientes(root)
    app.mainloop()