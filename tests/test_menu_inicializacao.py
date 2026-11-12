import sqlite3
from datetime import datetime

import customtkinter as ctk
import pytest

import abrir_sistema
import config
import menu
import pdv
import rede_validacao


@pytest.fixture
def banco_sintetico(tmp_path, monkeypatch):
    caminho = str(tmp_path / "menu.db")
    monkeypatch.setattr(config, "CAMINHO_BANCO", caminho)
    monkeypatch.setattr(menu, "CAMINHO_BANCO", caminho)
    monkeypatch.setattr(
        config, "_restaurar_banco_por_backup_se_necessario",
        lambda: (False, "Teste isolado."),
    )
    monkeypatch.setattr(menu, "_obter_info_licenca_visual", lambda role: ("Licença: teste", "#ffffff"))
    config.inicializar_banco()
    with sqlite3.connect(caminho) as con:
        con.execute("UPDATE dados_oficina SET nome_oficina = 'Oficina de teste' WHERE id = 1")
        con.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('ia_relatorio_mes', ?)",
            (datetime.now().strftime("%Y-%m"),),
        )
    return caminho


@pytest.mark.parametrize(
    ("role", "comandos"),
    [
        ("ADMIN", {
            "abrir_clientes", "abrir_os", "abrir_gestao_os", "gerar_recibo_menu_lateral",
            "abrir_pdv", "abrir_produtos", "abrir_caixa", "abrir_app_celular_sidebar",
            "abrir_cadastro_usuario", "abrir_relatorio", "abrir_dados_oficina", "buscar_atualizacoes",
        }),
        ("OFICINA", {
            "abrir_clientes", "abrir_os", "abrir_gestao_os", "gerar_recibo_menu_lateral",
            "abrir_app_celular_sidebar",
        }),
        ("VENDEDOR", {"abrir_pdv", "abrir_produtos", "abrir_app_celular_sidebar"}),
    ],
)
def test_inicializacao_monta_menu_conforme_perfil(banco_sintetico, monkeypatch, role, comandos):
    rede_validacao.iniciar_se_solicitado()
    observado = {}
    monkeypatch.setattr(menu.messagebox, "showerror", lambda *args, **kwargs: observado.setdefault("erros", []).append(args))

    def executar_menu(usuario="", role="VENDEDOR", senha_login=""):
        app = menu.FrmMenu(usuario=usuario, role=role, senha_login=senha_login)
        app.report_callback_exception = lambda *erro: observado.setdefault("erros", []).append(erro)

        def verificar():
            botoes = [w for w in app.sidebar_buttons.winfo_children() if isinstance(w, ctk.CTkButton)]
            observado["comandos"] = {w.cget("command").__name__ for w in botoes}
            observado["janela_visivel"] = bool(app.winfo_viewable())
            observado["menu_pronto"] = app._menu_pronto_exibido
            observado["botoes_mapeados"] = all(w.winfo_ismapped() for w in botoes)
            if role in ("ADMIN", "VENDEDOR"):
                next(w for w in botoes if w.cget("command").__name__ == "abrir_pdv").invoke()

                def verificar_pdv():
                    observado["pdv_aberto"] = any(
                        isinstance(w, pdv.FrmPDV) and w.winfo_viewable()
                        for w in app.winfo_children()
                    )
                    app.quit()

                app.after(300, verificar_pdv)
            else:
                app.quit()

        app.after(3000, verificar)
        try:
            app.mainloop()
        finally:
            try:
                app.destroy()
            except SystemExit:
                pass

    if role == "ADMIN":
        monkeypatch.setattr(menu, "iniciar_sistema", executar_menu)
        abrir_sistema.main()
    else:
        executar_menu(usuario="HOMOLOG", role=role)

    assert not observado.get("erros")
    assert observado["menu_pronto"] and observado["janela_visivel"]
    assert observado["botoes_mapeados"]
    assert observado["comandos"] == comandos
    if role in ("ADMIN", "VENDEDOR"):
        assert observado["pdv_aberto"]
