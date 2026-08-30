# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""
Bloco de inicialização blindado para PyInstaller e execução local.
Este bloco garante que sys.path e diretórios estejam corretos ANTES de qualquer importação de módulos locais ou de terceiros.
Coloque este bloco sempre no topo do arquivo!
"""
import sys
import os
import json
import configparser      # <--- ADICIONADO PARA RETIRAR O ERRO DA LINHA 215!
import urllib.request   # <--- Garante as requisições de atualização
import urllib.error
import subprocess
import atexit
import threading
import webbrowser
import sqlite3
from urllib.parse import quote_plus
from datetime import datetime
import tkinter as tk
from tkinter import simpledialog, messagebox

# Imports de bibliotecas externas
import firebase_admin
from firebase_admin import credentials, db
import customtkinter as ctk

# Inicializa o sistema de i18n (internacionalização) ANTES de qualquer outra
# coisa — garante que os textos das telas sejam carregados em português.
from core.i18n import set_default_locale, t  # noqa: E402
from core.eula import carregar_texto_eula, detectar_idioma_sistema  # noqa: E402
set_default_locale()

# ============================================================================== 
# CONFIGURAÇÃO DE DIRETÓRIO DO PYINSTALLER (Mantém o que já está funcionando)
# ==============================================================================
if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)
    
    internal_dir = os.path.join(os.path.dirname(sys.executable), "_internal")
    if os.path.exists(internal_dir) and internal_dir not in sys.path:
        sys.path.insert(0, internal_dir)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

# IMPORTS DOS SEUS MÓDULOS LOCAIS (Que o Mestre já resolveu!)

import importlib
from tela_planos import janela_vendas
from version_info import VERSION
from config import (
    CAMINHO_BANCO,
    hash_password,
    validate_password,
    verify_password,
    inicializar_banco,
    existe_algum_usuario,
    get_db_connection,
    obter_status_trial,
    obter_status_licenca,
    ativar_licenca,
    publicar_licenca_drive,
    get_logger,
    verificar_nova_versao,
    obter_info_nova_versao,
    eh_versao_mais_nova,
    obter_politica_atualizacao,
    executar_atualizacao,
    APP_VERSION,
    VALOR_ATUALIZACAO_NAO_PERMANENTE,
    INTERVALO_DIAS_CHECK_VERSAO,
    URL_CHECK_LICENCAS,
    validar_licenca_remota,
    deve_verificar_atualizacao,
    obter_tipo_licenca,
    obter_chave_licenca_ativa,
    licenca_vence_em_ate_dias,
    INFINITEPAY_API_CHECKOUT_URL,
    INFINITEPAY_API_TOKEN,
    INFINITEPAY_HANDLE,
    WHATSAPP_ADMIN_DESTINO,
    enviar_log_automatico_quinzenal,
    obter_chave_instalacao,
    diagnosticar_chave_licenca,
    validar_chave_licenca,
    iniciar_sincronizacao_hibrida_nuvem,
    iniciar_listener_firebase_realtime,
    obter_status_acesso_centralizado,
    modo_cliente_final_licenciado,
    bloqueio_loop_update_ativo,
)
from shutdown_utils import fechar_sistema

# Compatibilidade com versões de config.py que não expõem mais estas funções.
try:
    from config import preparar_banco_local_priorizando_drive  # type: ignore
except Exception:
    def preparar_banco_local_priorizando_drive() -> tuple[bool, str]:
        return True, "Compatibilidade: rotina de priorização Drive indisponível; login liberado."

try:
    from config import avaliar_risco_banco_antes_atualizacao  # type: ignore
except Exception:
    def avaliar_risco_banco_antes_atualizacao() -> tuple[bool, str]:
        return False, "Compatibilidade: análise de risco indisponível nesta versão."

try:
    from config import limpar_residuos_temp_update  # type: ignore
except Exception:
    def limpar_residuos_temp_update() -> tuple[bool, str]:
        return True, "Compatibilidade: limpeza de resíduos indisponível nesta versão."

logger = get_logger(__name__)
print(f"[OFP][STARTUP] Desktop v{VERSION}")
logger.info("[startup] Versão Desktop inicializada: v%s", VERSION)
_INFINITEPAY_DEBUG_LOGGED = False
_PAGAMENTO_EXPIRADO_JA_EXIBIDO = False
_ALERTA_TRIAL_CONVERSAO_EXIBIDO = False
_APP_INIT_DONE = False
_STARTUP_LOCK_PATH = ""
_LOGIN_SUCESSO_DADOS = None #
_LOGIN_TRANSICAO_EM_ANDAMENTO = False


def _trial_ativo_prioritario() -> tuple[bool, int, str]:
    """Consulta o trial antes de qualquer validação externa."""
    try:
        ativo, dias_restantes, data_limite = obter_status_trial()
        return bool(ativo), int(dias_restantes or 0), str(data_limite or "").strip()
    except Exception as exc:
        logger.warning("[startup] Falha ao consultar trial prioritário: %s", exc)
        return False, 0, ""


def _licenca_local_ativa_prioritaria() -> tuple[bool, str, str, str]:
    """Prioriza licença local/token para liberar uso sem depender do contador de trial."""
    try:
        lic_ativa, msg, cliente, validade = obter_status_licenca()
        if lic_ativa:
            return True, str(msg or ""), str(cliente or ""), str(validade or "")
    except Exception:
        pass

    try:
        chave = obter_chave_licenca_ativa()
        if chave:
            ok, _msg, payload = validar_chave_licenca(chave)
            if ok:
                cliente = str((payload or {}).get("cliente") or "").strip() if isinstance(payload, dict) else ""
                validade = str((payload or {}).get("val") or "PERMANENTE").strip() if isinstance(payload, dict) else "PERMANENTE"
                return True, "Licença ativa (chave local).", cliente, validade
    except Exception:
        pass

    return False, "Licença expirada ou inválida", "", ""

class SafeCTk(ctk.CTk):
    """Custom CTk class with a safe destroy method."""
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


def verificar_banco_vazio() -> bool:
    """Detecta se a tabela de usuários está vazia."""
    try:
        return not existe_algum_usuario()
    except Exception:
        return False


def _base_runtime_dir() -> str:
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))


def _resource_base_dir() -> str:
    return getattr(sys, "_MEIPASS", _base_runtime_dir())


def _resolver_recurso(*partes: str) -> str:
    return os.path.join(_resource_base_dir(), *partes)


def _diretorio_appdata_runtime() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or _base_runtime_dir()
    pasta = os.path.join(base, "OficinaPesca")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _startup_lock_path() -> str:
    return os.path.join(_diretorio_appdata_runtime(), "startup.lock")


def _startup_state_path() -> str:
    return os.path.join(_diretorio_appdata_runtime(), "startup_state.json")


def _processo_existe(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _limpar_arquivo_lock() -> None:
    global _STARTUP_LOCK_PATH
    try:
        if _STARTUP_LOCK_PATH and os.path.exists(_STARTUP_LOCK_PATH):
            os.remove(_STARTUP_LOCK_PATH)
    except Exception:
        pass


def _limpar_cache_temporario() -> None:
    base_dir = _base_runtime_dir()
    candidatos = [
        os.path.join(base_dir, "cache"),
        os.path.join(base_dir, "__pycache__"),
        os.path.join(_diretorio_appdata_runtime(), "cache"),
    ]
    for pasta in candidatos:
        if os.path.isdir(pasta):
            try:
                import shutil
                shutil.rmtree(pasta, ignore_errors=True)
            except Exception:
                pass


def _controlar_falhas_inicio() -> None:
    caminho = _startup_state_path()
    estado = {"consecutivas": 0, "ultima_saida_limpa": True}
    try:
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    estado.update(data)
    except Exception:
        pass

    if not bool(estado.get("ultima_saida_limpa", True)):
        estado["consecutivas"] = int(estado.get("consecutivas", 0)) + 1
    else:
        estado["consecutivas"] = 0

    if int(estado.get("consecutivas", 0)) >= 3:
        logger.warning("[startup] Detectadas 3 falhas seguidas; executando limpeza automática de cache.")
        _limpar_cache_temporario()
        estado["consecutivas"] = 0

    estado["ultima_saida_limpa"] = False
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def _marcar_encerramento_limpo() -> None:
    caminho = _startup_state_path()
    estado = {"consecutivas": 0, "ultima_saida_limpa": True}
    try:
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    estado.update(data)
    except Exception:
        pass
    estado["ultima_saida_limpa"] = True
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def _garantir_instancia_unica() -> tuple[bool, str]:
    global _STARTUP_LOCK_PATH
    _STARTUP_LOCK_PATH = _startup_lock_path()
    os.makedirs(os.path.dirname(_STARTUP_LOCK_PATH), exist_ok=True)
    atual = os.getpid()

    if os.path.exists(_STARTUP_LOCK_PATH):
        try:
            with open(_STARTUP_LOCK_PATH, "r", encoding="utf-8") as f:
                pid_antigo = int((f.read() or "0").strip())
            if pid_antigo and pid_antigo != atual and _processo_existe(pid_antigo):
                return False, "Já existe outra instância do sistema em execução."
            os.remove(_STARTUP_LOCK_PATH)
        except Exception:
            pass

    with open(_STARTUP_LOCK_PATH, "w", encoding="utf-8") as f:
        f.write(str(atual))
    return True, "Trava de instância única aplicada."


def _varrer_config_corrompido() -> tuple[bool, str]:
    cfg_path = os.path.join(_base_runtime_dir(), "config.cfg")
    if not os.path.exists(cfg_path):
        return False, "config.cfg não encontrado; nenhuma correção necessária."

    parser = configparser.ConfigParser()
    try:
        parser.read(cfg_path, encoding="utf-8")
    except Exception:
        nome_backup = f"config_corrompido_{datetime.now().strftime('%Y%m%d_%H%M%S')}.cfg"
        destino = os.path.join(_base_runtime_dir(), nome_backup)
        try:
            os.replace(cfg_path, destino)
        except Exception:
            return False, "config.cfg inválido e não foi possível renomear para backup."

        parser = configparser.ConfigParser()
        parser["app"] = {
            "modo": "local",
            "servidor_url": "http://localhost:8000",
            "url_app_celular_publica": "",
            "whatsapp_admin": "",
        }
        parser["suporte"] = {
            "envio_logs_quinzenal": "true",
            "log_upload_url": "https://script.google.com/macros/s/AKfycbxog8gr4WrMwWKHPcjdeBpFrJn7jHgnhT9K4_SNquQCOjp7psGlEll-Ib2Wu6-oKabR/exec",
            "log_upload_token": "",
            "log_upload_intervalo_dias": "15",
        }
        with open(cfg_path, "w", encoding="utf-8") as f:
            parser.write(f)
        return True, f"config.cfg corrompido foi isolado em {nome_backup} e recriado."

    alterado = False
    chaves_padrao = {
        "app": {
            "modo": "local",
            "servidor_url": "http://localhost:8000",
            "url_app_celular_publica": "",
            "whatsapp_admin": "",
        },
        "suporte": {
            "envio_logs_quinzenal": "true",
            "log_upload_intervalo_dias": "15",
        },
        "cloud_backup": {
            "email_cliente": "",
            "habilitado": "1",
            "auto_sync": "1",
            "sync_interval_seg": "60",
            "api_key": "",
        },
        # Dados críticos da oficina/drive: mantém valores existentes e só injeta faltantes.
        "dados_oficina": {
            "telefone": "",
            "pix": "",
            "caminho_logo": "",
            "email_backup": "",
            "google_drive_email": "",
            "google_drive_file_id": "",
        },
    }

    for secao, opcoes in chaves_padrao.items():
        if not parser.has_section(secao):
            parser.add_section(secao)
            alterado = True
        for chave, valor in opcoes.items():
            if not parser.has_option(secao, chave):
                parser.set(secao, chave, valor)
                alterado = True

    if alterado:
        with open(cfg_path, "w", encoding="utf-8") as f:
            parser.write(f)
        return True, "Varredura de configuração concluída e chaves obrigatórias normalizadas."
    return True, "Varredura de configuração concluída sem necessidade de ajuste."


def _executar_varredura_inicializacao() -> None:
    logger.info("[startup] Iniciando varredura anti-loop.")
    _controlar_falhas_inicio()
    try:
        ok_temp, msg_temp = limpar_residuos_temp_update()
        if ok_temp:
            logger.info("[startup] Limpeza temp_update: %s", msg_temp)
        else:
            logger.warning("[startup] Limpeza temp_update: %s", msg_temp)
    except Exception as exc:
        logger.warning("[startup] Falha ao limpar temp_update: %s", exc)

    ok_instancia, msg_instancia = _garantir_instancia_unica()
    logger.info("[startup] Verificação de instância: %s", msg_instancia)
    if not ok_instancia:
        messagebox.showwarning("Oficina de Pesca", msg_instancia)
        raise SystemExit(0)

    ok_cfg, msg_cfg = _varrer_config_corrompido()
    if ok_cfg:
        logger.info("[startup] Configuração: %s", msg_cfg)
    else:
        logger.warning("[startup] Configuração: %s", msg_cfg)



# ==============================================================================
# EULA / CONTRATO DE LICENÇA — aceite obrigatório no primeiro acesso
# Idioma 100% automático: o contrato é carregado conforme o idioma do Windows
# (pt_BR -> português | en_US -> inglês | es_UY -> espanhol; fallback pt_BR).
# ==============================================================================


def _exibir_janela_eula() -> bool:
    """Exibe o Contrato de Licença no idioma do sistema e retorna o aceite.

    O aceite é memorizado em ``Documentos/eula_aceito.json`` (por versão do
    contrato), evitando repetir a cobrança a cada abertura.
    """
    idioma_sistema = detectar_idioma_sistema() or "pt_BR"
    try:
        set_default_locale()  # aplica o idioma detectado no sistema operacional
    except Exception:
        pass

    texto_contrato = carregar_texto_eula(idioma_sistema)
    if not texto_contrato:
        # Sem arquivo de contrato disponível: não bloqueia o acesso.
        logger.info("[eula] Contrato de licença não encontrado — aceite pulado.")
        return True

    marcador_aceite = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "Documentos", "eula_aceito.json"
    )
    assinatura = f"{idioma_sistema}|{len(texto_contrato)}"
    try:
        if os.path.isfile(marcador_aceite):
            with open(marcador_aceite, "r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
            if dados.get("assinatura") == assinatura:
                logger.info("[eula] Contrato já aceito anteriormente (idioma=%s).", idioma_sistema)
                return True
    except Exception:
        pass

    aceito = {"valor": False}

    janela_eula = ctk.CTkToplevel()
    janela_eula.title(t("eula_titulo", default="Contrato de Licença de Uso"))
    janela_eula.geometry("780x640")
    janela_eula.grab_set()
    janela_eula.protocol("WM_DELETE_WINDOW", lambda: None)  # fecha só pelos botões

    ctk.CTkLabel(
        janela_eula,
        text=t("eula_titulo", default="Contrato de Licença de Uso"),
        font=("Arial", 18, "bold"),
    ).pack(pady=(14, 4))

    ctk.CTkLabel(
        janela_eula,
        text=t(
            "eula_aviso",
            default="Leia o contrato abaixo. Para utilizar o sistema, é necessário aceitar os termos.",
        ),
        wraplength=700,
        text_color="#bdc3c7",
    ).pack(padx=20, pady=(0, 8))

    caixa_texto = ctk.CTkTextbox(janela_eula, wrap="word", font=("Arial", 12))
    caixa_texto.pack(fill="both", expand=True, padx=20, pady=(0, 12))
    caixa_texto.insert("1.0", texto_contrato)
    caixa_texto.configure(state="disabled")

    frame_botoes = ctk.CTkFrame(janela_eula, fg_color="transparent")
    frame_botoes.pack(pady=(0, 16))

    def _salvar_aceite() -> None:
        try:
            pasta_docs = os.path.dirname(marcador_aceite)
            if pasta_docs and not os.path.isdir(pasta_docs):
                os.makedirs(pasta_docs, exist_ok=True)
            with open(marcador_aceite, "w", encoding="utf-8") as arquivo:
                json.dump(
                    {
                        "idioma": idioma_sistema,
                        "aceito_em": datetime.now().isoformat(timespec="seconds"),
                        "assinatura": assinatura,
                    },
                    arquivo,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception:
            pass

    def _confirmar() -> None:
        aceito["valor"] = True
        _salvar_aceite()
        janela_eula.destroy()

    def _recusar() -> None:
        if messagebox.askyesno(
            t("eula_titulo", default="Contrato de Licença de Uso"),
            t(
                "eula_aceite_obrigatorio_msg",
                default="Você precisa aceitar o Contrato de Licença para utilizar o sistema. Deseja encerrar?",
            ),
            parent=janela_eula,
        ):
            janela_eula.destroy()
            raise SystemExit(0)

    ctk.CTkButton(
        frame_botoes,
        text=t("eula_aceitar", default="Aceitar e Continuar"),
        command=_confirmar,
        width=200,
        fg_color="#2e7d32",
        hover_color="#1b5e20",
    ).pack(side="left", padx=10)
    ctk.CTkButton(
        frame_botoes,
        text=t("eula_recusar", default="Recusar e Sair"),
        command=_recusar,
        width=160,
        fg_color="#8b2f2f",
        hover_color="#6d2424",
    ).pack(side="left", padx=10)

    janela_eula.attributes("-topmost", True)
    janela_eula.after(150, lambda: janela_eula.attributes("-topmost", False))
    janela_eula.wait_window()
    return aceito["valor"]


def _inicializar_fluxo_pos_termos() -> None:
    global _APP_INIT_DONE
    if _APP_INIT_DONE:
        return
    _APP_INIT_DONE = True
    trial_ativo, dias_trial, data_limite_trial = _trial_ativo_prioritario()
    if trial_ativo:
        logger.info(
            "[startup] Trial ativo detectado (%s dia(s) restante(s) até %s). Pulando Drive/Firebase/Token.",
            dias_trial,
            data_limite_trial,
        )
        try:
            inicializar_banco()
            logger.info("[startup] Banco inicializado em modo trial sem validações externas.")
        except Exception as exc:
            logger.warning("[startup] Falha ao inicializar banco em modo trial: %s", exc)
        atualizar_status_trial_tela()
        atualizar_status_primeiro_acesso()
        return

    logger.info("[startup] Trial expirado/inativo. Verificando sincronização segura Drive -> Local antes do login.")
    ok_sync_startup, msg_sync_startup = preparar_banco_local_priorizando_drive()
    if ok_sync_startup:
        logger.info("[startup] Sync inicial de banco: %s", msg_sync_startup)
    else:
        logger.error("[startup] Falha no sync inicial de banco: %s", msg_sync_startup)
        try:
            messagebox.showerror(
                "Sincronização obrigatória",
                (
                    "Não foi possível validar/baixar o banco remoto antes do login.\n\n"
                    f"Detalhe: {msg_sync_startup}\n\n"
                    "Para segurança dos dados, o acesso foi bloqueado."
                ),
                parent=janela_login,
            )
        except Exception:
            pass
        label_status.configure(text=t("ui_falha_na_sincroniza_o_de_dados_com_drive"), text_color="red")
        janela_login.deiconify()
        btn_entrar.configure(state="disabled")
        return

    logger.info("[startup] Inicializando conexão com banco de dados.")
    inicializar_banco()
    logger.info("[startup] Banco inicializado com sucesso.")

    try:
        ok_sync_bg, msg_sync_bg = iniciar_sincronizacao_hibrida_nuvem()
        logger.info("[startup] Sync híbrida pós-login preparada: %s", msg_sync_bg)
        if not ok_sync_bg:
            logger.warning("[startup] Sync híbrida não iniciada: %s", msg_sync_bg)
    except Exception as e:
        logger.warning("[startup] Falha ao iniciar sincronização híbrida automática: %s", e)

    try:
        ok_fb_listener, msg_fb_listener = iniciar_listener_firebase_realtime()
        logger.info("[startup] Listener Firebase realtime: %s", msg_fb_listener)
        if not ok_fb_listener:
            logger.warning("[startup] Listener Firebase não iniciado: %s", msg_fb_listener)
    except Exception as e:
        logger.warning("[startup] Falha ao iniciar listener Firebase realtime: %s", e)

    atualizar_status_trial_tela()
    atualizar_status_primeiro_acesso()
    _checar_alerta_vencimento_licenca()

    # Envio automático de logs removido da inicialização para evitar uso de rede.

    # Desativado no login para evitar popup modal capturando teclado/mouse.
    # janela_login.after(450, _mostrar_alerta_conversao_trial)
    # Verificação de versão desativada na inicialização automática para evitar uso de rede.



def abrir_janela_planos(evento=None):
    """Abre a pagina oficial de planos no navegador padrao."""
    try:
        webbrowser.open("https://www.frssolutions.com.br/planos")
    except Exception as exc:
        try:
            messagebox.showerror("Oficina de Pesca", "Nao foi possivel abrir o link: %s" % exc)
        except Exception:
            pass


def _checar_alerta_vencimento_licenca():
    try:
        vence_em_breve, dias_restantes = licenca_vence_em_ate_dias(7)
        if vence_em_breve and dias_restantes is not None:
            janela_login.after(
                350,
                lambda: abrir_janela_planos(),
            )
    except Exception as e:
                logger.info("Não foi possível calcular alerta de vencimento: %s", e)


def _mostrar_alerta_conversao_trial():
    global _ALERTA_TRIAL_CONVERSAO_EXIBIDO
    if _ALERTA_TRIAL_CONVERSAO_EXIBIDO:
        return

    try:
        lic_ativa, _msg_lic, _cliente_lic, _validade_lic = obter_status_licenca()
        if lic_ativa:
            return

        trial_ativo, dias_restantes, _data_limite = obter_status_trial()
        if not trial_ativo or dias_restantes > 3:
            return

        _ALERTA_TRIAL_CONVERSAO_EXIBIDO = True

        pop = ctk.CTkToplevel(janela_login)
        pop.title("Seu Trial Está Terminando")
        pop.geometry("520x260")
        pop.resizable(False, False)
        pop.transient(janela_login)
        pop.grab_set()
        try:
            pop.lift()
            pop.focus_force()
        except Exception:
            pass

        pop.update_idletasks()
        x = (pop.winfo_screenwidth() // 2) - (520 // 2)
        y = (pop.winfo_screenheight() // 2) - (260 // 2)
        pop.geometry(f"520x260+{x}+{y}")

        ctk.CTkLabel(
            pop,
            text=t("ui_aviso_de_renova_o"),
            font=("Arial", 20, "bold"),
            text_color="#f39c12",
        ).pack(pady=(20, 8))

        ctk.CTkLabel(
            pop,
            text=(
                f"Seu período de teste grátis termina em {dias_restantes} dias! "
                "Não perca o acesso à sua oficina.\n"
                "Deseja escolher um plano e continuar agora?"
            ),
            font=("Arial", 14),
            wraplength=470,
            justify="center",
        ).pack(pady=(0, 20), padx=16)

        botoes = ctk.CTkFrame(pop, fg_color="#1f2a38")
        botoes.pack(pady=(0, 18))

        def _abrir_planos_agora():
            try:
                pop.destroy()
            except Exception:
                pass
            abrir_janela_planos()

        def _fechar_popup_trial():
            try:
                pop.grab_release()
            except Exception:
                pass
            try:
                pop.destroy()
            except Exception:
                pass
            _solicitar_foco_login()

        ctk.CTkButton(
            botoes,
            text=t("ui_sim_ver_planos"),
            width=190,
            fg_color="#27ae60",
            hover_color="#229954",
            command=_abrir_planos_agora,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            botoes,
            text=t("ui_depois"),
            width=130,
            fg_color="#7f8c8d",
            hover_color="#707b7c",
            command=_fechar_popup_trial,
        ).pack(side="left", padx=8)
        pop.protocol("WM_DELETE_WINDOW", _fechar_popup_trial)
    except Exception as e:
        logger.info("Falha ao exibir alerta de conversão do trial: %s", e)


def _obter_cfg_pagamento_runtime() -> tuple[str, str, str, str, str]:
    """Relê config.cfg em tempo real para não exigir reinício ao alterar pagamento."""
    try:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        caminhos_cfg = [
            os.path.join(base_dir, "config.cfg"),
            os.path.join(os.getcwd(), "config.cfg"),
            os.path.join(os.path.dirname(base_dir), "config.cfg"),
        ]

        cfg = configparser.ConfigParser()
        cfg_path_usado = ""
        for caminho in caminhos_cfg:
            if os.path.exists(caminho):
                cfg.read(caminho, encoding="utf-8")
                cfg_path_usado = caminho
                break

        if not cfg_path_usado:
            logger.info("config.cfg não encontrado em runtime nos caminhos esperados de pagamento.")

        link = cfg.get("pagamento", "infinitepay_link", fallback=INFINITEPAY_LINK_PAGAMENTO).strip()
        link_atualizacao = cfg.get("pagamento", "infinitepay_link_atualizacao", fallback=link).strip()
        handle = cfg.get("pagamento", "infinitepay_handle", fallback=INFINITEPAY_HANDLE).strip()
        checkout_url = cfg.get("pagamento", "infinitepay_checkout_url", fallback=INFINITEPAY_API_CHECKOUT_URL).strip()
        token = cfg.get("pagamento", "infinitepay_api_token", fallback=INFINITEPAY_API_TOKEN).strip()
        return link, link_atualizacao, handle, checkout_url, token
    except Exception as e:
        logger.info("Falha ao reler config.cfg em runtime: %s", e)
        return (
            INFINITEPAY_LINK_PAGAMENTO,
            INFINITEPAY_LINK_PAGAMENTO,
            INFINITEPAY_HANDLE,
            INFINITEPAY_API_CHECKOUT_URL,
            INFINITEPAY_API_TOKEN,
        )


def _texto_pagamento_infinitepay(tipo: str, valor_reais: float = 0.0) -> str:
    base = f"Pagamento {tipo} pela InfinitePay.\nVocê pode pagar por PIX ou cartão."
    if valor_reais > 0:
        valor = f"{valor_reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        base += f"\n\nValor: R$ {valor}"
    return base


def _obter_numero_whatsapp_admin() -> str:
    numero = "".join(ch for ch in str(WHATSAPP_ADMIN_DESTINO or "") if ch.isdigit())
    if numero and not numero.startswith("55"):
        numero = "55" + numero
    return numero


def _enviar_mensagem_pagamento_whatsapp_admin(tipo_pagamento: str):
    numero_admin = _obter_numero_whatsapp_admin()
    if not numero_admin:
        messagebox.showwarning(
            "WhatsApp",
            "Número do administrador não configurado em config.cfg (app.whatsapp_admin).",
            parent=janela_login,
        )
        return

    usuario = (entry_user.get().strip() if 'entry_user' in globals() else "") or "Cliente"
    texto = (
        f"Olá, sou {usuario}. Acabei de realizar o pagamento ({tipo_pagamento}) no sistema Oficina de Pesca. "
        "Pode verificar e liberar, por favor?"
    )
    link = f"https://wa.me/{numero_admin}?text={quote_plus(texto)}"

    try:
        abriu = bool(webbrowser.open(link, new=2))
        if abriu:
            return
    except Exception as e:
        logger.info("Falha ao abrir WhatsApp com webbrowser: %s", e)

    try:
        if hasattr(os, "startfile"):
            os.startfile(link)  # type: ignore[attr-defined]
            return
    except Exception as e:
        logger.info("Falha ao abrir WhatsApp com os.startfile: %s", e)

    messagebox.showwarning(
        "WhatsApp",
        "Não foi possível abrir o WhatsApp automaticamente.",
        parent=janela_login,
    )


def _oferecer_envio_whatsapp_admin(tipo_pagamento: str):
    enviar = messagebox.askyesno(
        "Avisar Administrador",
        "Deseja enviar agora uma mensagem ao administrador no WhatsApp para confirmar o pagamento?",
        parent=janela_login,
    )
    if enviar:
        _enviar_mensagem_pagamento_whatsapp_admin(tipo_pagamento)


def _obter_link_checkout_por_handle(handle: str = "") -> str:
    handle = str(handle or INFINITEPAY_HANDLE or "").strip().lstrip("@")
    if not handle:
        return ""
    return f"https://checkout.infinitepay.io/{handle}"


def _criar_link_checkout_infinitepay(
    valor_reais: float,
    descricao: str,
    referencia: str = "",
    item_descricao: str = "Atualização",
) -> str:
    """Tenta criar checkout dinâmico na InfinitePay e retorna URL vazia em falha."""
    global _INFINITEPAY_DEBUG_LOGGED
    _link_cfg, _link_atual_cfg, handle_cfg, checkout_url_cfg, token_cfg = _obter_cfg_pagamento_runtime()

    debug_ativo = not _INFINITEPAY_DEBUG_LOGGED
    if debug_ativo:
        _INFINITEPAY_DEBUG_LOGGED = True

    if not token_cfg:
        if debug_ativo:
            logger.info(
                "InfinitePay debug (primeira tentativa): Token não configurado em config.cfg (pagamento.infinitepay_api_token)."
            )
        return ""

    url = checkout_url_cfg or "https://api.checkout.infinitepay.io/links"
    valor_centavos = max(int(round(float(valor_reais) * 100)), 1)
    item_descricao = str(item_descricao or "Atualização").strip() or "Atualização"

    payload = {
        "handle": handle_cfg or "frsoficinadepesca",
        "items": [
            {
                "quantity": 1,
                "price": valor_centavos,
                "description": item_descricao,
            }
        ],
    }
    if referencia:
        payload["external_reference"] = referencia

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token_cfg}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        },
    )

    token_mascarado = f"***{token_cfg[-4:]}" if len(token_cfg) >= 4 else "***"
    if debug_ativo:
        logger.info(
            "InfinitePay debug (primeira tentativa): POST %s | payload=%s | token=%s",
            url,
            payload,
            token_mascarado,
        )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            bruto = resp.read().decode("utf-8", errors="replace")
            if debug_ativo:
                logger.info(
                    "InfinitePay debug (primeira tentativa): HTTP %s | resposta=%s",
                    getattr(resp, "status", "200"),
                    bruto[:1200],
                )
            data = json.loads(bruto)
    except urllib.error.HTTPError as e:
        try:
            erro_bruto = e.read().decode("utf-8", errors="replace")
        except Exception:
            erro_bruto = str(e)
        if debug_ativo:
            logger.info(
                "InfinitePay debug (primeira tentativa): HTTPError %s | resposta=%s",
                getattr(e, "code", "N/A"),
                erro_bruto[:1200],
            )
        logger.info("Falha ao criar checkout InfinitePay: %s", e)
        return ""
    except Exception as e:
        if debug_ativo:
            logger.info("InfinitePay debug (primeira tentativa): Erro inesperado: %s", e)
        logger.info("Falha ao criar checkout InfinitePay: %s", e)
        return ""

    if isinstance(data, dict):
        for chave in ("checkout_url", "payment_url", "url", "link", "short_url"):
            valor = str(data.get(chave, "")).strip()
            if valor.startswith("http"):
                return valor

        nested = data.get("data")
        if isinstance(nested, dict):
            for chave in ("checkout_url", "payment_url", "url", "link", "short_url"):
                valor = str(nested.get(chave, "")).strip()
                if valor.startswith("http"):
                    return valor
    return ""


def _abrir_link_infinitepay_se_configurado(
    valor_reais: float = 0.0,
    descricao: str = "",
    referencia: str = "",
    item_descricao: str = "Atualização",
    link_forcado: str = "",
):
    link_cfg, link_atual_cfg, _handle_cfg, _checkout_url_cfg, _token_cfg = _obter_cfg_pagamento_runtime()
    link_pagamento = ""
    if valor_reais > 0:
        link_pagamento = _criar_link_checkout_infinitepay(
            valor_reais,
            descricao or "Atualização de versão",
            referencia,
            item_descricao,
        )

    if not link_pagamento:
        if link_forcado:
            link_pagamento = link_forcado

    if not link_pagamento:
        link_pagamento = link_atual_cfg or link_cfg

    if not link_pagamento:
        messagebox.showwarning(
            "InfinitePay",
            "Não foi possível obter o link de pagamento.\n\n"
            "Preencha no config.cfg:\n"
            "- pagamento.infinitepay_link (link real criado no app InfinitePay)\n"
            "- pagamento.infinitepay_link_atualizacao\n"
            "ou\n"
            "- pagamento.infinitepay_api_token (para geração automática)",
            parent=janela_login,
        )
        return

    abrir = messagebox.askyesno(
        "InfinitePay",
        "Deseja abrir o link de pagamento da InfinitePay agora?",
        parent=janela_login,
    )
    if not abrir:
        return

    try:
        abriu = bool(webbrowser.open(link_pagamento, new=2))
        if abriu:
            return
    except Exception as e:
        logger.info("Falha ao abrir link com webbrowser: %s", e)

    try:
        if hasattr(os, "startfile"):
            os.startfile(link_pagamento)  # type: ignore[attr-defined]
            return
    except Exception as e:
        logger.info("Falha ao abrir link com os.startfile: %s", e)

    try:
        subprocess.run(["cmd", "/c", "start", "", link_pagamento], check=False)
        return
    except Exception as e:
        logger.info("Falha ao abrir link com cmd start: %s", e)

    try:
        janela_login.clipboard_clear()
        janela_login.clipboard_append(link_pagamento)
    except Exception:
        pass

    messagebox.showwarning(
        "InfinitePay",
        "Não foi possível abrir o link automaticamente.\n\n"
        f"Link: {link_pagamento}\n\n"
        "O link foi copiado para a área de transferência (quando disponível).",
        parent=janela_login,
    )


def abrir_tela_cadastro():
    jan_cad = ctk.CTkToplevel(janela_login)
    jan_cad.geometry("320x360")
    jan_cad.title("Novo Acesso")
    
    ctk.CTkLabel(jan_cad, text=t("ui_cadastrar"), font=("Arial", 18, "bold")).pack(pady=20)
    u_new = ctk.CTkEntry(jan_cad, placeholder_text=t("btn_novo_usuario"))
    u_new.pack(pady=10)
    s_new = ctk.CTkEntry(jan_cad, placeholder_text=t("ui_nova_senha"), show="*")
    s_new.pack(pady=10)
    s_confirm = ctk.CTkEntry(jan_cad, placeholder_text=t("ui_confirmar_senha_1"), show="*")
    s_confirm.pack(pady=10)
    ctk.CTkLabel(
        jan_cad,
        text=t("ui_novos_cadastros_criados_nesta_tela_entram_como_operador"),
        text_color="#95a5a6",
        wraplength=260,
        justify="center"
    ).pack(pady=(0, 10))
    
    def salvar():
        u, s, sc = u_new.get().strip(), s_new.get().strip(), s_confirm.get().strip()
        role = "OPERADOR"
        if u and s and sc:
            if s != sc:
                label_status.configure(text=t("ui_senhas_n_o_coincidem"), text_color="red")
                return
            valid, mensagem = validate_password(s)
            if not valid:
                label_status.configure(text=mensagem, text_color="red")
                return
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO usuarios (usuario, senha, role) VALUES (?, ?, ?)", (u, hash_password(s), role))
                    conn.commit()
                # Fechamento seguro: processa tarefas pendentes antes de agendar a destruição
                jan_cad.update_idletasks()
                jan_cad.after(200, lambda: jan_cad.destroy())
                label_status.configure(text=f"Usuário {u} criado!", text_color="green")
            except sqlite3.IntegrityError:
                label_status.configure(text=t("ui_usu_rio_j_existe_1"), text_color="red")
            except Exception:
                label_status.configure(text=t("ui_erro_ao_criar_usu_rio"), text_color="red")
        else:
            label_status.configure(text=t("ui_preencha_todos_os_campos_1"), text_color="red")

    ctk.CTkButton(jan_cad, text=t("ui_salvar_1"), fg_color="#27ae60", command=salvar).pack(pady=20)


def abrir_tela_primeiro_admin():
    # Evita abrir duplicado se já existe uma janela de criação aberta
    for w in janela_login.winfo_children():
        if isinstance(w, ctk.CTkToplevel) and w.winfo_exists():
            try:
                if w.title() == "Primeiro Acesso":
                    w.focus_force()
                    return
            except Exception:
                pass

    jan_admin = ctk.CTkToplevel(janela_login)
    jan_admin.geometry("360x380")
    jan_admin.title("Primeiro Acesso")
    jan_admin.grab_set()
    jan_admin.focus_force()

    ctk.CTkLabel(jan_admin, text=t("ui_criar_admin"), font=("Arial", 18, "bold")).pack(pady=20)
    ctk.CTkLabel(
        jan_admin,
        text=t("ui_nenhum_usu_rio_encontrado_ncrie_agora_o_admin_inicial"),
        text_color="#f1c40f",
        justify="center"
    ).pack(pady=(0, 12))

    u_new = ctk.CTkEntry(jan_admin, placeholder_text=t("ui_usu_rio_admin"))
    u_new.pack(pady=8)
    s_new = ctk.CTkEntry(jan_admin, placeholder_text=t("ui_senha"), show="*")
    s_new.pack(pady=8)
    s_confirm = ctk.CTkEntry(jan_admin, placeholder_text=t("ui_confirmar_senha_1"), show="*")
    s_confirm.pack(pady=8)

    lbl_local = ctk.CTkLabel(jan_admin, text="", text_color="red")
    lbl_local.pack(pady=(8, 0))

    def salvar_admin():
        u = u_new.get().strip()
        s = s_new.get().strip()
        sc = s_confirm.get().strip()

        if not u or not s or not sc:
            lbl_local.configure(text=t("ui_preencha_todos_os_campos"))
            return
        if s != sc:
            lbl_local.configure(text=t("ui_as_senhas_n_o_coincidem"))
            return

        valid, mensagem = validate_password(s)
        if not valid:
            lbl_local.configure(text=mensagem)
            return

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO usuarios (usuario, senha, role) VALUES (?, ?, 'ADMIN')",
                    (u, hash_password(s))
                )
                conn.commit()
            
            # Uso do after(200) para evitar o erro 'can't delete Tcl command'
            # permitindo que o Tkinter finalize os comandos internos da modal antes de destruí-la.
            jan_admin.update_idletasks()
            jan_admin.after(200, lambda: jan_admin.destroy())
            
            atualizar_status_trial_tela()
            label_status.configure(text=t("ui_admin_inicial_criado_fa_a_login"), text_color="green")
            
            # Comandos de transição agora corretamente indentados dentro do bloco try
            janela_login.deiconify()
            atualizar_status_primeiro_acesso()
        except sqlite3.IntegrityError:
            lbl_local.configure(text=t("ui_usu_rio_j_existe"))
        except Exception as e:
            lbl_local.configure(text=f"Erro ao criar ADMIN: {e}")

    ctk.CTkButton(jan_admin, text=t("ui_criar_admin"), fg_color="#27ae60", command=salvar_admin).pack(pady=18)

def verificar_login():
    global _LOGIN_SUCESSO_DADOS, _LOGIN_TRANSICAO_EM_ANDAMENTO #
    if _LOGIN_TRANSICAO_EM_ANDAMENTO:
        return

    u = entry_user.get().strip()
    s = entry_pass.get().strip()

    print("Log: Botão 'Entrar' disparado.")
    logger.info("[startup] Iniciando tentativa de autenticação de usuário.")
    label_status.configure(text="", text_color="red")

    try:
        print("Log: Verificando se existem usuários no banco...")
        if not existe_algum_usuario():
            print("Log: Banco vazio detectado. Abrindo tela de Primeiro Acesso.")
            label_status.configure(text=t("ui_crie_o_admin_inicial_para_continuar_1"), text_color="#f1c40f")
            # Esconde o login para forçar a criação do admin
            janela_login.withdraw()
            abrir_tela_primeiro_admin()
            return
    except Exception as e:
        logger.exception("Erro ao verificar existência de usuários: %s", e)
        label_status.configure(text=t("ui_erro_ao_acessar_base_de_usu_rios"), text_color="red")
        return

    print(f"Log: Autenticando usuário '{u}'...")

    if not u or not s:
        label_status.configure(text=t("ui_informe_usu_rio_e_senha"), text_color="red")
        return
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, usuario, senha, role FROM usuarios WHERE UPPER(usuario)=UPPER(?) LIMIT 1",
                (u,)
            )
            resultado = cursor.fetchone()
            print(f"Log: Resultado da consulta ao banco: {resultado}")
            print(f"Log: Comparação executada com usuario={u!r} e resultado_verdadeiro={bool(resultado)}")

            if not resultado:
                label_status.configure(text=t("ui_usu_rio_ou_senha_inv_lidos"), text_color="red")
                messagebox.showerror("Erro de Acesso", "Usuário ou senha inválidos.")
                return

            stored_password = resultado[2]
            if not verify_password(s, stored_password):
                print(f"Log: Senha não validada para usuario={u!r}; senha_informada={s!r}; senha_armazenada={stored_password!r}")
                label_status.configure(text=t("ui_usu_rio_ou_senha_inv_lidos"), text_color="red")
                messagebox.showerror("Erro de Acesso", "Usuário ou senha inválidos.")
                return

            lic_local_ativa, msg_lic_local, _cli_local, _val_local = _licenca_local_ativa_prioritaria()
            if lic_local_ativa:
                logger.info("[startup] Login liberado por licença ativa local/token.")
            else:
                trial_ativo, dias_trial, data_limite_trial = _trial_ativo_prioritario()
                if trial_ativo:
                    logger.info(
                        "[startup] Login liberado por trial (%s dia(s) restante(s) até %s).",
                        dias_trial,
                        data_limite_trial,
                    )
                else:
                    status_acesso = obter_status_acesso_centralizado()
                    if not bool(status_acesso.get("ativa")):
                        label_status.configure(
                            text=str(msg_lic_local or status_acesso.get("mensagem") or "Licença expirada ou inválida."),
                            text_color="red",
                        )
                        logger.warning("[startup] Login bloqueado por token/Drive/Firebase: %s", status_acesso)
                        return

            print("Log: Autenticação bem-sucedida.")
            role = resultado[3] if len(resultado) > 3 else "OPERADOR"
            logger.info("[startup] Abrindo interface principal para role=%s", role)
            _LOGIN_SUCESSO_DADOS = (u, role, s)
            _LOGIN_TRANSICAO_EM_ANDAMENTO = True
            print("Log: Tentando abrir o menu agora...")

            def transicao_final_segura():
                global _LOGIN_TRANSICAO_EM_ANDAMENTO
                try:
                    # 1. Esconde a janela de login.
                    janela_login.withdraw()

                    # 2. Inicia apenas o menu principal (fluxo padrão da aplicação).
                    menu_mod = importlib.import_module("menu")
                    menu_mod.iniciar_sistema(usuario=u, role=role, senha_login=s)

                    # 3. Garante encerramento da janela de login ao fechar o menu.
                    try:
                        janela_login.destroy()
                    except Exception:
                        pass
                except Exception as e:
                    _LOGIN_TRANSICAO_EM_ANDAMENTO = False
                    try:
                        janela_login.deiconify()
                    except Exception:
                        pass
                    logger.exception("Falha ao iniciar menu apos login: %s", e)
                    try:
                        messagebox.showerror("Erro", f"Falha ao abrir menu principal: {e}", parent=janela_login)
                    except Exception:
                        pass

            # Dispara a transição segura
            janela_login.after(150, transicao_final_segura)
            return
    except (sqlite3.OperationalError, sqlite3.DatabaseError, PermissionError, OSError) as e:
        logger.exception("Erro de banco/permissão no login: %s", e)
        msg_erro = (
            "Falha ao acessar o banco de dados durante o login.\n\n"
            f"Banco esperado em:\n{CAMINHO_BANCO}\n\n"
            f"Detalhe técnico:\n{e}"
        )
        label_status.configure(text=t("ui_erro_de_banco_de_dados_ou_permiss_o"), text_color="red")
        try:
            messagebox.showerror("Erro de banco de dados", msg_erro, parent=janela_login)
        except Exception:
            pass
        return
    except Exception as e:
        _LOGIN_TRANSICAO_EM_ANDAMENTO = False
        logger.exception("Erro no login: %s", e)
        label_status.configure(text=t("ui_erro_interno_ao_processar_login"), text_color="red")
        try:
            messagebox.showerror(
                "Erro no login",
                f"Ocorreu um erro inesperado ao tentar entrar.\n\nDetalhe técnico:\n{e}",
                parent=janela_login,
            )
        except Exception:
            pass
        return

    label_status.configure(text=t("ui_usu_rio_ou_senha_inv_lidos"), text_color="red")
    return


def abrir_tela_ativacao():
    chave_inst = obter_chave_instalacao()

    dialog = ctk.CTkToplevel(janela_login)
    dialog.title("Ativar Licença")
    dialog.geometry("460x260")
    dialog.resizable(False, False)
    dialog.grab_set()
    dialog.focus_force()
    x = janela_login.winfo_x() + (janela_login.winfo_width() // 2) - 230
    y = janela_login.winfo_y() + (janela_login.winfo_height() // 2) - 150
    dialog.geometry(f"460x260+{x}+{y}")

    ctk.CTkLabel(dialog, text=t("ui_chave_de_instala_o_deste_pc"), text_color="#bdc3c7").pack(pady=(18, 4))

    frame_chave = ctk.CTkFrame(dialog, fg_color="#1f2a38")
    frame_chave.pack(pady=(0, 14))
    ctk.CTkLabel(frame_chave, text=chave_inst, text_color="#f1c40f", font=("Courier", 13, "bold")).pack(side="left", padx=(0, 8))

    def _copiar_chave():
        dialog.clipboard_clear()
        dialog.clipboard_append(chave_inst)
        btn_copiar.configure(text=t("ui_copiado_1"))
        dialog.after(2000, lambda: btn_copiar.configure(text=t("ui_copiar_chave")))

    btn_copiar = ctk.CTkButton(frame_chave, text=t("ui_copiar_chave"), command=_copiar_chave,
                               width=130, height=30, fg_color="#2980b9", hover_color="#3498db")
    btn_copiar.pack(side="left")

    ctk.CTkLabel(dialog, text=t("ui_contra_senha_de_ativa_o"), text_color="#bdc3c7").pack(pady=(0, 4))
    entry_chave = ctk.CTkEntry(dialog, width=380, height=40, placeholder_text=t("ui_cole_aqui_a_chave_enviada_pelo_suporte"))
    entry_chave.pack(pady=(0, 12))

    def _confirmar_ativacao():
        chave = entry_chave.get().strip()
        if not chave:
            messagebox.showwarning("Ativação", "Informe a contra-senha de ativação.", parent=dialog)
            return

        btn_confirmar.configure(state="disabled", text=t("ui_ativando"))
        ok, msg = ativar_licenca(chave)
        if ok:
            def _publicar_drive_background() -> None:
                try:
                    publicar_licenca_drive(chave)
                except Exception as exc:
                    logger.warning("Falha silenciosa ao publicar licença no Drive após ativação: %s", exc)

            threading.Thread(
                target=_publicar_drive_background,
                daemon=True,
                name="ofp-licenca-drive-auto",
            ).start()

            label_status.configure(text=t("ui_licen_a_ativada_com_sucesso"), text_color="#2ecc71")
            atualizar_status_trial_tela()
            dialog.after(80, dialog.destroy)
            return

        try:
            diag = diagnosticar_chave_licenca(chave)
            detalhe = str(diag.get("motivo") or "").strip()
            if detalhe:
                msg = f"{msg}\n\nDiagnóstico: {detalhe}"
        except Exception:
            pass
        btn_confirmar.configure(state="normal", text=t("ui_ativar_agora"))
        messagebox.showerror("Ativação", msg, parent=dialog)

    frame_acoes = ctk.CTkFrame(dialog, fg_color="transparent")
    frame_acoes.pack(pady=(0, 10))

    btn_confirmar = ctk.CTkButton(
        frame_acoes,
        text=t("ui_ativar_agora"),
        command=_confirmar_ativacao,
        width=320,
        height=36,
        fg_color="#27ae60",
        hover_color="#2ecc71",
    )
    btn_confirmar.grid(row=0, column=0)
    entry_chave.bind("<Return>", lambda _e: _confirmar_ativacao())

ctk.set_appearance_mode("dark")
janela_login = SafeCTk() # Use the custom SafeCTk class
janela_login.withdraw()  # Inicia oculta para validação de banco vazio
janela_login.title(f"Login Oficina v{VERSION}")
janela_login.geometry("400x520")
janela_login.resizable(False, False)

try:
    icone_login = _resolver_recurso("icone_oficina.ico")
    if os.path.exists(icone_login):
        janela_login.iconbitmap(icone_login)
except Exception:
    pass

# Centralizar
x = (janela_login.winfo_screenwidth() // 2) - 200
y = (janela_login.winfo_screenheight() // 2) - 340
janela_login.geometry(f"400x680+{x}+{y}")

main_frame = ctk.CTkFrame(janela_login, corner_radius=20, fg_color="#252525")
main_frame.pack(expand=True, fill="both", padx=16, pady=12)

ctk.CTkLabel(main_frame, text=t("titulo_oficina"), font=("Segoe UI Semibold", 18), text_color="orange").pack(pady=(16, 4))
ctk.CTkLabel(main_frame, text=f"v{VERSION}", text_color="#f6b26b", font=("Segoe UI", 11)).pack(pady=(0, 10))
ctk.CTkLabel(main_frame, text=t("ui_preencha_usu_rio_e_senha_para_entrar_no_sistema"), text_color="#95a5a6").pack(pady=(0, 14))

ctk.CTkLabel(main_frame, text=t("ui_usu_rio_de_acesso"), text_color="#dfe6e9", anchor="w").pack(padx=50, pady=(0, 4), fill="x")
entry_user = ctk.CTkEntry(main_frame, placeholder_text=t("ui_usu_rio"), width=320, height=44)
entry_user.pack(pady=(0, 10))

ctk.CTkLabel(main_frame, text=t("ui_senha_de_acesso"), text_color="#dfe6e9", anchor="w").pack(padx=50, pady=(0, 4), fill="x")
entry_pass = ctk.CTkEntry(main_frame, placeholder_text=t("ui_senha"), show="*", width=320, height=44)
entry_pass.pack(pady=(0, 10))

# Bindings para permitir login ao pressionar Enter nos campos de texto
entry_user.bind("<Return>", lambda e: verificar_login())
entry_pass.bind("<Return>", lambda e: verificar_login())

# Mantém entradas em configuração padrão, focáveis e sem bloqueio.
entry_user.configure(state="normal", takefocus=True)
entry_pass.configure(state="normal", takefocus=True)


def _solicitar_foco_login():
    try:
        janela_login.lift()
        janela_login.focus_force()
    except Exception:
        pass
    try:
        entry_user.focus_set()
    except Exception:
        pass

btn_entrar = ctk.CTkButton(main_frame, text=t("btn_entrar_maiusculo"), command=verificar_login, width=320, height=48, fg_color="#27ae60", hover_color="#2ecc71")
btn_entrar.pack(pady=(18, 12))
print("Log: Interface de Login montada e botão vinculado.")

btn_ativar = ctk.CTkButton(
    main_frame,
    text=t("ui_ativar_licen_a"),
    command=abrir_tela_ativacao,
    width=320,
    height=38,
    fg_color="#34495e",
    hover_color="#3c5a71"
)
btn_pagamento = ctk.CTkButton(
    main_frame,
    text=t("ui_comprar_licen_a"),
    command=abrir_janela_planos,
    width=320,
    height=38,
    fg_color="#8e44ad",
    hover_color="#7d3c98"
)
btn_pagamento.pack(pady=(0, 10))

btn_ativar.pack(pady=(0, 8))

ctk.CTkLabel(main_frame, text=t("ui_cadastro_de_usu_rios_dispon_vel_apenas_no_menu_do_admin"), text_color="#95a5a6", wraplength=360, justify="center", font=("Segoe UI", 10)).pack(pady=(2, 14))

label_trial = ctk.CTkLabel(main_frame, text="", text_color="#f1c40f", wraplength=320, justify="center")
label_trial.pack_forget()

label_status = ctk.CTkLabel(main_frame, text="", text_color="red")
label_status.pack_forget()


def _mostrar_botao_ativar() -> None:
    try:
        if not btn_ativar.winfo_manager():
            btn_ativar.pack(pady=(0, 8), after=btn_pagamento)
    except Exception:
        pass


def _ocultar_botao_ativar() -> None:
    try:
        if not btn_ativar.winfo_manager():
            btn_ativar.pack(pady=(0, 8), after=btn_pagamento)
    except Exception:
        pass

progress_update = ctk.CTkProgressBar(main_frame, width=320)
progress_update.set(0)
progress_update.pack(pady=(0, 8))
progress_update.pack_forget()

logger.info("[startup] Interface de login carregada com sucesso.")

_url_update_disponivel = ""
_auto_update_liberado = False
_mensagem_politica_update = ""
_popup_update_exibido = False
_auto_update_disparada = False
_janela_update = None
_label_update = None
_barra_update = None
_update_versao_detectada = ""
_update_novidades_detectadas = ""


def _fechar_popup_atualizacao():
    global _janela_update, _label_update, _barra_update
    try:
        if _janela_update and _janela_update.winfo_exists():
            _janela_update.destroy()
    except Exception:
        pass
    _janela_update = None
    _label_update = None
    _barra_update = None


def _avisar_atualizacao_unica(versao: str, novidades: str = ""):
    """Exibe UMA única mensagem de atualização por sessão.

    Substitui o antigo popup com contagem regressiva (que abria janelas
    duplicadas). Ao confirmar, o download é feito e o sistema é totalmente
    encerrado ANTES de o instalador baixado ser executado: o launcher (.cmd)
    aguarda este processo terminar e só então roda o instalador.
    """
    global _popup_update_exibido, _update_versao_detectada, _update_novidades_detectadas

    if _popup_update_exibido or _auto_update_disparada:
        return
    if not janela_login.winfo_exists():
        return

    _popup_update_exibido = True
    _update_versao_detectada = str(versao or "").strip()
    _update_novidades_detectadas = str(novidades or "").strip()

    resposta = messagebox.askokcancel(
        "Atualização",
        "Uma nova versão está disponível. O sistema será encerrado para aplicar a atualização.",
        parent=janela_login,
    )
    if not resposta:
        # Usuário optou por atualizar depois: não insiste nesta sessão.
        return

    _executar_instalacao_update(confirmar_usuario=False)


def _executar_instalacao_update(confirmar_usuario: bool = True):
    global _auto_update_disparada
    versao_alvo = str(_update_versao_detectada or "").strip()
    if bloqueio_loop_update_ativo(versao_alvo=versao_alvo):
        messagebox.showinfo("Atualização", "Sistema atualizado", parent=janela_login)
        return

    if not _url_update_disponivel:
        messagebox.showwarning("Atualização", "Link de atualização indisponível no momento.", parent=janela_login)
        return

    if _auto_update_disparada:
        return
    _auto_update_disparada = True

    if confirmar_usuario:
        # Fluxo legado (compatibilidade). O caminho principal (_avisar_atualizacao_unica)
        # já exibe a mensagem única antes de chamar esta função.
        confirmar = messagebox.askokcancel(
            "Atualização",
            "Uma nova versão está disponível. O sistema será encerrado para aplicar a atualização.",
            parent=janela_login,
        )
        if not confirmar:
            _auto_update_disparada = False
            return

    risco_banco, msg_risco = avaliar_risco_banco_antes_atualizacao()
    if risco_banco:
        confirmado_risco = messagebox.askyesno(
            "Confirmação de segurança do banco",
            msg_risco,
            parent=janela_login,
        )
        if not confirmado_risco:
            _auto_update_disparada = False
            return

    def _status(mensagem: str):
        try:
            label_versao.configure(
                text=mensagem,
                text_color="#2ecc71",
                font=("Arial", 11, "bold"),
            )
        except Exception:
            pass

    _status("Preparando atualização...")

    def _progresso(valor: float, mensagem: str = ""):
        texto = str(mensagem or "").strip() or "Baixando atualização..."
        pct = float(valor or 0.0)
        try:
            janela_login.after(
                0,
                lambda: _status(f"{texto} ({int(pct * 100)}%)" if 0 < pct < 1 else texto),
            )
        except Exception:
            pass

    def _worker_update():
        ok, msg = executar_atualizacao(
            _url_update_disponivel,
            app_executavel=sys.executable,
            processo_pid=os.getpid(),
            silenciosa=True,
            progresso_cb=_progresso,
            versao_alvo=_update_versao_detectada,
        )

        def _finalizar():
            global _auto_update_disparada
            if ok:
                _status("Atualização baixada. Encerrando o sistema para instalar...")
                # Fechamento TOTAL da aplicação ANTES de o instalador executar:
                # o launcher (.cmd) aguarda este processo terminar e só então
                # dispara o instalador baixado.
                try:
                    janela_login.after(400, lambda: fechar_sistema(janela_login))
                except Exception:
                    fechar_sistema(janela_login)
            else:
                _auto_update_disparada = False
                _status("")
                msg_final = str(msg or "").strip()
                if msg_final in {"Sistema atualizado", "Sem novas atualizações"}:
                    messagebox.showinfo("Atualização", msg_final, parent=janela_login)
                else:
                    messagebox.showerror("Atualização", msg_final or "Falha ao baixar/instalar atualização.", parent=janela_login)

        try:
            janela_login.after(0, _finalizar)
        except Exception:
            _finalizar()

    threading.Thread(target=_worker_update, daemon=True, name="ofp-update-ui").start()


def _fluxo_pagamento_atualizacao_mensal():
    prosseguir = messagebox.askyesno(
        "Pagamento da atualização",
        _texto_pagamento_infinitepay("da atualização mensal", VALOR_ATUALIZACAO_NAO_PERMANENTE),
        parent=janela_login,
    )
    if not prosseguir:
        return

    _abrir_link_infinitepay_se_configurado(
        valor_reais=VALOR_ATUALIZACAO_NAO_PERMANENTE,
        descricao="Atualização mensal Oficina de Pesca",
        referencia="ATUALIZACAO_MENSAL",
        item_descricao="Atualização",
    )
    _oferecer_envio_whatsapp_admin("Atualização")

    confirmou = messagebox.askyesno(
        "Confirmação de pagamento",
        "Pagamento realizado?\n\nSe sim, clique em 'Sim' para liberar a atualização agora.",
        parent=janela_login,
    )
    if not confirmou:
        return

    _executar_instalacao_update()


def atualizar_agora():
    global _url_update_disponivel, _auto_update_liberado, _mensagem_politica_update
    _executar_instalacao_update()


def atualizar_status_trial_tela():
    global _PAGAMENTO_EXPIRADO_JA_EXIBIDO
    lic_ativa, _msg_lic, cliente_lic, validade_lic = _licenca_local_ativa_prioritaria()
    _mostrar_botao_ativar()
    if lic_ativa:
        _PAGAMENTO_EXPIRADO_JA_EXIBIDO = False
        entry_user.configure(state="normal")
        entry_pass.configure(state="normal")
        btn_entrar.configure(state="normal", fg_color="#27ae60", hover_color="#2ecc71")

        expira_breve = False
        try:
            expira_breve, _dias = licenca_vence_em_ate_dias(7)
        except Exception:
            expira_breve = False

        if expira_breve:
            btn_ativar.configure(
                state="normal",
                text=t("ui_ativar_licen_a"),
                width=320,
                height=38,
                fg_color="#34495e",
                hover_color="#3c5a71",
            )
        else:
            btn_ativar.configure(
                state="disabled",
                text=t("ui_ativar_licen_a"),
                width=320,
                height=38,
                fg_color="#7f8c8d",
                hover_color="#7f8c8d",
            )

        try:
            label_trial.configure(text="")
            label_trial.pack_forget()
            label_status.configure(text="")
        except Exception:
            pass
        return

    trial_ativo, dias_trial, data_limite_trial = _trial_ativo_prioritario()

    entry_user.configure(state="normal")
    entry_pass.configure(state="normal")
    btn_entrar.configure(state="normal", fg_color="#27ae60", hover_color="#2ecc71")
    btn_ativar.configure(
        state="normal",
        text=t("ui_ativar_licen_a"),
        width=320,
        height=38,
        fg_color="#34495e",
        hover_color="#3c5a71"
    )
    try:
        if trial_ativo:
            label_trial.configure(text=f"Modo Trial ativo: {dias_trial} dia(s) restante(s) (até {data_limite_trial}).")
            if not label_trial.winfo_manager():
                label_trial.pack(pady=(0, 8), before=label_status)
        else:
            label_trial.configure(text=t("ui_trial_expirado_ative_uma_licen_a_para_continuar"))
            if not label_trial.winfo_manager():
                label_trial.pack(pady=(0, 8), before=label_status)
        label_status.configure(text="")
    except Exception:
        pass

def atualizar_status_primeiro_acesso():
    """Verifica se existem usuários cadastrados e atualiza o alerta na tela de login."""
    try:
        # Verificação robusta no banco conforme solicitado (SELECT count)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM usuarios")
            usuario_count = cursor.fetchone()[0]

        if usuario_count == 0:
            logger.info("[startup] Nenhum usuário detectado. Forçando tela de Primeiro Acesso.")
            janela_login.withdraw()
            label_status.configure(text=t("ui_crie_o_admin_inicial_para_continuar"), text_color="#f1c40f")
            abrir_tela_primeiro_admin()
        else:
            # Se houver usuários, garante que a tela de login apareça
            janela_login.deiconify()
            if label_status.cget("text") == "Crie o ADMIN inicial para continuar.":
                label_status.configure(text="")
    except Exception as e:
        logger.error(f"Falha ao checar primeiro acesso no startup: {e}")

# Verificação de nova versão (em background, não bloqueia o login)
label_versao = ctk.CTkLabel(
    main_frame,
    text=f"v{VERSION}",
    text_color="#555555",
    font=("Arial", 10),
)
label_versao.pack(pady=(0, 4))

def _checar_versao_bg():
    global _url_update_disponivel, _auto_update_liberado, _mensagem_politica_update, _popup_update_exibido, _auto_update_disparada
    try:
        # Mantém registro histórico, mas sem bloquear a checagem no startup.
        deve_verificar_atualizacao(INTERVALO_DIAS_CHECK_VERSAO)
    except Exception:
        pass

    info_versao = obter_info_nova_versao()
    erro = str(info_versao.get("erro", "")).strip()
    if erro:
        def _mostrar_erro_drive():
            label_versao.configure(
                text=erro,
                text_color="#f39c12",
                font=("Arial", 11, "bold"),
            )
        janela_login.after(0, _mostrar_erro_drive)
        return

    versao_nova = str(info_versao.get("versao", "")).strip()
    novidades = str(info_versao.get("novidades", "")).strip()
    url_download = str(info_versao.get("url_download", "")).strip()

    if versao_nova and not url_download:
        # Fallback defensivo para manifests antigos sem URL explícita.
        url_download = (
            f"https://github.com/frscomercial6-eng/oficina-pesca-updates/"
            f"releases/download/v{versao_nova}/Oficina_Pesca_Instalador.exe"
        )

    disponivel = bool(versao_nova and eh_versao_mais_nova(versao_nova, APP_VERSION))

    if disponivel:
        _url_update_disponivel = url_download
        _auto_update_liberado = True
        _mensagem_politica_update = "Atualização automática liberada."

        def _mostrar():
            global _url_update_disponivel, _auto_update_liberado, _mensagem_politica_update
            texto_update = f"Nova versão {versao_nova} disponível."
            if novidades:
                texto_update = f"{texto_update} {novidades}".strip()
            try:
                label_versao.configure(
                    text=texto_update,
                    text_color="#2ecc71",
                    font=("Arial", 11, "bold"),
                )
            except Exception:
                pass
            # Exibe UMA única mensagem de atualização; ao confirmar, o app é
            # totalmente encerrado antes de o instalador ser executado.
            if _url_update_disponivel:
                _avisar_atualizacao_unica(versao_nova, novidades)
        janela_login.after(0, _mostrar)
    else:
        janela_login.after(0, _fechar_popup_atualizacao)

def _inicializar_fluxo_com_eula() -> None:
    """Exibe o EULA (primeiro acesso) e só então inicia o fluxo do sistema."""
    try:
        _exibir_janela_eula()
    except SystemExit:
        raise
    except Exception:
        logger.exception("[eula] Falha na janela de aceite — seguindo fluxo padrão.")
    _inicializar_fluxo_pos_termos()


janela_login.after(120, _inicializar_fluxo_com_eula)
janela_login.after(50, _solicitar_foco_login)
janela_login.after(250, _solicitar_foco_login)
janela_login.after(
    1500,
    lambda: threading.Thread(target=_checar_versao_bg, daemon=True, name="ofp-check-update-login").start(),
)

janela_login.mainloop()
