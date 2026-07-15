# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import json
import configparser
import hashlib
import os
import shutil
import sys
import subprocess
import re
import time
import zipfile

DIV = "═" * 50
VERSAO = "1.0.34"
APP_NAME = "Oficina_Pesca"
ENTRY_SCRIPT = "login.py"
INSTALLER_SCRIPT = "instalar.iss"
INSTALLER_OUTPUT_DIR = "INSTALADOR_FINAL"
DISTRIBUTION_DIR = "PACOTE_ENVIO"
DISTRIBUTION_INSTALLER_NAME = "Oficina_Pesca_Instalador.exe"
DISTRIBUTION_BOOTSTRAPPER_NAME = "Atualizador.exe"
PORTABLE_STAGE_DIR = os.path.join(INSTALLER_OUTPUT_DIR, APP_NAME)
PORTABLE_OUTPUT_DIR = "Output"
PORTABLE_ZIP_NAME = "Oficina_Pesca_Portatil.zip"
ANDROID_PROJECT_DIR = "android_apk"
ANDROID_APK_DIST_DIR = os.path.join("dist", "apk_celular")
ANDROID_APK_PACKAGE_DIR = os.path.join(DISTRIBUTION_DIR, "apk_celular")
ANDROID_APK_LEGACY_DIR = "apk_celular_distribuicao"
ANDROID_APK_NAME = "Oficina_Pesca_WebView.apk"
ANDROID_APK_INSTALLER_NAME = "oficina_app_signed.apk"
AUTO_MODE = "--auto" in sys.argv or os.environ.get("OFP_BUILD_AUTO") == "1"
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def _resolver_diretorio_build() -> str:
    candidatos = []
    env_build = os.environ.get("OFP_BUILD_SOURCE_DIR", "").strip()
    if env_build:
        candidatos.append(env_build)
    candidatos.append(REPO_ROOT)
    base = os.path.dirname(REPO_ROOT)
    candidatos.extend(
        [
            os.path.join(base, "ORIGINAL", "OFICINA_PESCA_ORIGINAL"),
            os.path.join(base, "OFICINA_PESCA_PRODUCAO"),
        ]
    )
    for candidato in candidatos:
        caminho = os.path.abspath(candidato)
        if not os.path.isdir(caminho):
            continue
        if "LIMPA" in os.path.basename(caminho).upper() and caminho != REPO_ROOT:
            continue
        if os.path.exists(os.path.join(caminho, ENTRY_SCRIPT)) and os.path.exists(os.path.join(caminho, "config.py")):
            return caminho
    return REPO_ROOT


BUILD_ROOT = _resolver_diretorio_build()


RESOURCE_SPECS = [
    ("assets", "assets"),
    ("client_secret_desktop.json", "."),
    ("client_secret_desktop.json", "assets"),
    ("dados_oficina.py", "."),
    ("fundomenu.png", "."),
    ("LOGO.bmp", "."),
    ("icone_oficina.ico", "."),
    ("config.cfg", "."),
    ("versao.json", "."),
    ("version.json", "."),
    ("version.txt", "."),
    ("Documentos/termos_de_uso.txt", "Documentos"),
    ("Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf", "."),
]

INSTALLER_REQUIRED_SPECS = [
    ("config.json", "."),
    ("iniciar_servidor.bat", "."),
    ("servidor.py", "."),
    ("Atualizador.exe", "."),
    ("static", "static"),
    ("templates", "templates"),
]

PORTABLE_REQUIRED_SPECS = [
    ("templates", "templates"),
    ("static", "static"),
    ("assets", "assets"),
    ("servidor.py", "."),
    ("config.py", "."),
    ("iniciar_servidor.bat", "."),
    ("config.json", "."),
    ("config.cfg", "."),
    ("versao.json", "."),
    ("version.txt", "."),
]

FUNDO_MENU_CANDIDATOS = [
    os.path.join("assets", "fundo_menu.jpeg"),
    os.path.join("assets", "fundo_menu.jpg"),
    os.path.join("assets", "fundo_menu.png"),
    os.path.join("assets", "fundomenu.png"),
    os.path.join("_internal", "assets", "fundo_menu.jpeg"),
    os.path.join("_internal", "assets", "fundo_menu.jpg"),
    os.path.join("_internal", "assets", "fundo_menu.png"),
    os.path.join("_internal", "assets", "fundomenu.png"),
    os.path.join("_internal", "fundo_menu.jpeg"),
    os.path.join("_internal", "fundo_menu.jpg"),
    os.path.join("_internal", "fundo_menu.png"),
    os.path.join("_internal", "fundomenu.png"),
    "fundo_menu.jpeg",
    "fundo_menu.jpg",
    "fundo_menu.png",
    "fundomenu.png",
]

LOCAL_HIDDEN_IMPORTS = [
    ("adaptador_acbr", "adaptador_acbr.py"),
    ("clientes", "clientes.py"),
    ("config", "config.py"),
    ("configuracao_fiscal", "configuracao_fiscal.py"),
    ("dados_oficina", "dados_oficina.py"),
    ("gestao_os", "gestao_os.py"),
    ("menu", "menu.py"),
    ("login", "login.py"),
    ("migracao_fiscal_2027", "migracao_fiscal_2027.py"),
    ("pdv", "pdv.py"),
    ("shutdown_utils", "shutdown_utils.py"),
    ("tela_financeiro", "tela_financeiro.py"),
    ("tela_os", "tela_os.py"),
    ("tela_planos", "tela_planos.py"),
    ("util_recibo", "util_recibo.py"),
]

PYINSTALLER_HIDDEN_IMPORTS = [
    "firebase_admin",
    "googleapiclient",
    "googleapiclient.discovery",
    "googleapiclient.errors",
    "googleapiclient.http",
    "googleapiclient._auth",
    "google_auth_oauthlib",
    "google_auth_oauthlib.flow",
    "google.oauth2",
    "google.oauth2.credentials",
    "google.oauth2.service_account",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.auth.exceptions",
    "oauth2client",
    "oauth2client.client",
    "oauth2client.file",
    "oauth2client.tools",
    "httplib2",
    "urllib",
    "urllib.request",
    "urllib.error",
    "ssl",
    "certifi",
]

PYINSTALLER_COLLECT_ALL = [
    "customtkinter",
    "fpdf",
    "googleapiclient",
    "google_auth_oauthlib",
    "google",
    "google_auth",
    "google_api_python_client",
    "reportlab",
]

def print_header():
    print(f"\n{'🚀 FRS Solutions - Orquestrador de Build 🚀':^50}")
    print(DIV)

def get_input():
    # Tenta obter argumentos da linha de comando
    import sys
    default_projeto = "oficina de pesca"
    default_versao = VERSAO
    if AUTO_MODE:
        return default_projeto, default_versao
    args = [arg for arg in sys.argv[1:] if not str(arg).startswith("--")]
    if len(args) >= 2:
        return args[0], args[1]
    elif len(args) == 1:
        return args[0], default_versao
    # Se não for terminal interativo, retorna padrão
    if not sys.stdin.isatty():
        return default_projeto, default_versao
    # Modo interativo
    projeto = input("📦 Nome do Projeto: ").strip() or default_projeto
    versao = input("🔖 Versão Atual (ex: 1.0.6): ").strip() or default_versao
    return projeto, versao

def atualizar_versao_json(nova_versao):
    caminho = "versao.json"
    if not os.path.exists(caminho):
        print(f"⚠️  Arquivo {caminho} não encontrado!")
        return
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    versao_antiga = dados.get("versao", "")
    if versao_antiga == nova_versao:
        print(f"ℹ️  versao.json já está na versão {nova_versao}.")
        return
    dados["versao"] = nova_versao
    if "novidades" in dados and isinstance(dados["novidades"], str):
        dados["novidades"] = f"v{nova_versao}: Atualização de versão automática."
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    print(f"✅ versao.json atualizado de {versao_antiga} para {nova_versao}.")

    caminho_version = "version.json"
    dados_version = {
        "versao": nova_versao,
        "novidades": f"v{nova_versao}: Atualização de versão automática.",
        "url_download": f"https://github.com/frscomercial6-eng/oficina-pesca-updates/releases/download/v{nova_versao}/Oficina_Pesca_Instalador.exe",
        "download_url": f"https://github.com/frscomercial6-eng/oficina-pesca-updates/releases/download/v{nova_versao}/Oficina_Pesca_Instalador.exe",
        "force_update": False,
        "apk": {
            "versao": nova_versao,
            "canal": "webview",
        },
    }
    with open(caminho_version, "w", encoding="utf-8") as f:
        json.dump(dados_version, f, ensure_ascii=False, indent=2)
    print(f"✅ version.json sincronizado para {nova_versao}.")


def _sincronizar_manifests(nova_versao: str) -> None:
    """Propaga a versão para config.cfg, versao.json e version.txt."""
    atualizar_versao_json(nova_versao)
    with open("version.txt", "w", encoding="utf-8") as _f:
        _f.write(nova_versao + "\n")
    _cfg = configparser.ConfigParser()
    if os.path.exists("config.cfg"):
        _cfg.read("config.cfg", encoding="utf-8")
    if not _cfg.has_section("versao"):
        _cfg.add_section("versao")
    _cfg.set("versao", "versao_atual", nova_versao)
    with open("config.cfg", "w", encoding="utf-8") as _f:
        _cfg.write(_f)
    print(f"✅ Manifests sincronizados: config.cfg, versao.json, version.txt → {nova_versao}.")


def _read_text_any(path: str) -> tuple[str, str]:
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc
        except Exception:
            continue
    with open(path, "rb") as f:
        return f.read().decode("latin-1", errors="ignore"), "latin-1"


def _write_text(path: str, content: str, enc: str) -> None:
    with open(path, "w", encoding=enc, errors="ignore") as f:
        f.write(content)


def _atualizar_version_info(nova_versao: str) -> None:
    path = "version_info.py"
    if not os.path.exists(path):
        print("⚠️  version_info.py não encontrado; pulando sincronização.")
        return
    txt, enc = _read_text_any(path)
    novo = re.sub(
        r'(?m)^\s*VERSION\s*=\s*["\'][0-9]+(?:\.[0-9]+){2,}["\']\s*$',
        f'VERSION = "{nova_versao}"',
        txt,
    )
    if novo != txt:
        _write_text(path, novo, enc)
        print(f"✅ version_info.py atualizado para {nova_versao}.")
    else:
        print(f"ℹ️  version_info.py já está em {nova_versao}.")


def _atualizar_eula(nova_versao: str) -> None:
    candidatos = [
        "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf",
        os.path.join("Documentos", "termos_de_uso.txt"),
    ]
    for path in candidatos:
        if not os.path.exists(path):
            continue
        txt, enc = _read_text_any(path)
        novo = txt
        novo = re.sub(r'(Vers[aã]o\s+)([0-9]+(?:\.[0-9]+){2,})', rf'\g<1>{nova_versao}', novo, flags=re.IGNORECASE)
        # Caso específico em RTF onde "Versão" aparece com escapes.
        novo = re.sub(
            r"(Vers\\'e3\\loch\\f1\s+\\hich\\f1\s*o\s+)([0-9]+(?:\.[0-9]+){2,})",
            rf"\g<1>{nova_versao}",
            novo,
            flags=re.IGNORECASE,
        )
        if novo != txt:
            _write_text(path, novo, enc)
            print(f"✅ EULA/termos atualizados em {path} para versão {nova_versao}.")
        else:
            print(f"ℹ️  Nenhuma linha de versão alterada em {path}.")


def _atualizar_scripts_instalador(nova_versao: str) -> None:
    iss_files = [
        "instalar.iss",
        "instalar_oficial_completo.iss",
    ]
    for path in iss_files:
        if not os.path.exists(path):
            continue
        txt, enc = _read_text_any(path)
        novo = txt
        novo = re.sub(
            r'(?im)^\s*#define\s+AppVersion\s+"[0-9]+(?:\.[0-9]+){2,}"\s*$',
            f'#define AppVersion "{nova_versao}"',
            novo,
        )
        if os.path.basename(path).lower() == "instalar.iss":
            novo = re.sub(
                r'(?im)^\s*OutputBaseFilename\s*=\s*.*$',
                f'OutputBaseFilename=Setup_OficinaPesca_v{nova_versao}',
                novo,
            )
        if os.path.basename(path).lower() == "instalar_oficial_completo.iss":
            novo = re.sub(
                r'(?im)^\s*OutputBaseFilename\s*=\s*.*$',
                f'OutputBaseFilename=Instalador_Oficina_Pesca_Oficial_v{nova_versao}',
                novo,
            )
        if novo != txt:
            _write_text(path, novo, enc)
            print(f"✅ Script de instalador atualizado: {path}")
        else:
            print(f"ℹ️  Script de instalador já alinhado: {path}")

    bat_files = [
        "gerar_release.bat",
        "build_final_setup.bat",
        "gerar_instalador_final.bat",
    ]
    for path in bat_files:
        if not os.path.exists(path):
            continue
        txt, enc = _read_text_any(path)
        novo = txt
        novo = re.sub(
            r'(?im)^\s*set\s+"SETUP_NAME=Setup_OficinaPesca_v[0-9]+(?:\.[0-9]+){2,}\.exe"\s*$',
            f'set "SETUP_NAME=Setup_OficinaPesca_v{nova_versao}.exe"',
            novo,
        )
        novo = re.sub(
            r'(?im)(/DInstallerOutputName=Setup_OficinaPesca_v)[0-9]+(?:\.[0-9]+){2,}(_FINAL)',
            rf'\g<1>{nova_versao}\g<2>',
            novo,
        )
        novo = re.sub(
            r'(?im)^\s*set\s+"FINAL_SETUP=Setup_OficinaPesca_v[0-9]+(?:\.[0-9]+){2,}_FINAL\.exe"\s*$',
            f'set "FINAL_SETUP=Setup_OficinaPesca_v{nova_versao}_FINAL.exe"',
            novo,
        )
        if novo != txt:
            _write_text(path, novo, enc)
            print(f"✅ Script BAT atualizado: {path}")
        else:
            print(f"ℹ️  Script BAT já alinhado: {path}")


def _sincronizar_versao_global(nova_versao: str) -> None:
    print(DIV)
    print(f"🔁 Sincronizando versão global para {nova_versao}...")
    _atualizar_version_info(nova_versao)
    _sincronizar_manifests(nova_versao)
    _atualizar_eula(nova_versao)
    _atualizar_scripts_instalador(nova_versao)
    print("✅ Sincronização global de versão concluída.")
    print(DIV)


def _caminho_gradle_wrapper() -> str:
    return os.path.join(ANDROID_PROJECT_DIR, "gradlew.bat" if os.name == "nt" else "gradlew")


def _resolver_comando_gradle() -> list[str]:
    wrapper = _caminho_gradle_wrapper()
    if os.path.exists(wrapper):
        return [os.path.abspath(wrapper)]
    gradle_cmd = shutil.which("gradle")
    if gradle_cmd:
        return [gradle_cmd]
    raise FileNotFoundError(
        "Gradle não encontrado. Gere o wrapper em android_apk/ ou instale gradle no PATH."
    )


def _gerar_wrapper_gradle_android() -> str:
    wrapper = _caminho_gradle_wrapper()
    if os.path.exists(wrapper):
        print(f"ℹ️  Gradle wrapper já disponível: {wrapper}")
        return wrapper

    gradle_cmd = shutil.which("gradle")
    if not gradle_cmd:
        raise FileNotFoundError(
            "Gradle não encontrado para gerar wrapper do APK. Instale gradle ou versione o wrapper em android_apk/."
        )

    print("🧰 Gerando gradle wrapper do APK...")
    subprocess.run([gradle_cmd, "wrapper"], cwd=ANDROID_PROJECT_DIR, check=True)
    if not os.path.exists(wrapper):
        raise FileNotFoundError("Gradle wrapper não foi gerado em android_apk/.")
    return wrapper


def _validar_apk_gerado(caminho_apk: str) -> dict:
    caminho = os.path.abspath(str(caminho_apk or ""))
    if not caminho or not os.path.exists(caminho):
        raise FileNotFoundError("Falha ao localizar APK para distribuição")

    tamanho = int(os.path.getsize(caminho) or 0)
    if tamanho < 256 * 1024:
        raise RuntimeError("Falha ao localizar APK para distribuição")

    with open(caminho, "rb") as f:
        assinatura = f.read(2)
        f.seek(0)
        sha256 = hashlib.sha256(f.read()).hexdigest()

    if assinatura != b"PK":
        raise RuntimeError("Falha ao localizar APK para distribuição")

    return {"path": caminho, "size": tamanho, "sha256": sha256}


def _gerar_log_saude_sistema(versao: str, apk_path: str, instalador_path: str = "") -> str:
    from config import inicializar_banco, obter_status_acesso_centralizado, obter_firebase_web_config, obter_config_backup_nuvem

    os.makedirs("logs", exist_ok=True)
    caminho_log = os.path.join("logs", "saude_sistema_producao.json")
    apk_info = _validar_apk_gerado(apk_path)
    instalador_abs = os.path.abspath(instalador_path) if instalador_path else ""

    try:
        inicializar_banco()
    except Exception:
        pass

    payload = {
        "status": "Produção Autônoma",
        "versao": versao,
        "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "licenca": obter_status_acesso_centralizado(),
        "firebase": obter_firebase_web_config(),
        "backup": obter_config_backup_nuvem(),
        "artefatos": {
            "apk": apk_info,
            "instalador": {
                "path": instalador_abs,
                "exists": bool(instalador_abs and os.path.exists(instalador_abs)),
                "size": int(os.path.getsize(instalador_abs) or 0) if instalador_abs and os.path.exists(instalador_abs) else 0,
            },
        },
    }

    with open(caminho_log, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"🩺 Log único de saúde do sistema gerado: {caminho_log}")
    return caminho_log


def _build_apk_android(versao: str) -> tuple[str, str]:
    print("📱 Compilando APK WebView com a mesma versão do Desktop...")
    _gerar_wrapper_gradle_android()
    gradle_cmd = _resolver_comando_gradle()
    subprocess.run([*gradle_cmd, "assembleDebug"], cwd=ANDROID_PROJECT_DIR, check=True)

    candidatos_origem = [
        os.path.join(ANDROID_PROJECT_DIR, "build", "outputs", "apk", "debug", "app-debug.apk"),
        os.path.join(ANDROID_PROJECT_DIR, "app", "build", "outputs", "apk", "debug", "app-debug.apk"),
    ]
    origem_apk = next((c for c in candidatos_origem if os.path.exists(c)), "")
    if not origem_apk:
        raise FileNotFoundError("Falha ao localizar APK para distribuição")

    _validar_apk_gerado(origem_apk)

    os.makedirs(ANDROID_APK_DIST_DIR, exist_ok=True)
    os.makedirs(ANDROID_APK_PACKAGE_DIR, exist_ok=True)
    os.makedirs(ANDROID_APK_LEGACY_DIR, exist_ok=True)

    nome_versionado = f"Oficina_Pesca_WebView_v{versao}.apk"
    destino_dist = os.path.join(ANDROID_APK_DIST_DIR, nome_versionado)
    destino_pacote = os.path.join(ANDROID_APK_PACKAGE_DIR, ANDROID_APK_NAME)
    destino_legacy = os.path.join(ANDROID_APK_LEGACY_DIR, ANDROID_APK_INSTALLER_NAME)

    shutil.copy2(origem_apk, destino_dist)
    shutil.copy2(origem_apk, destino_pacote)
    shutil.copy2(origem_apk, destino_legacy)

    _validar_apk_gerado(destino_dist)
    _validar_apk_gerado(destino_pacote)
    _validar_apk_gerado(destino_legacy)

    print(f"📦 APK copiado para dist: {destino_dist}")
    print(f"📤 APK copiado para distribuição: {destino_pacote}")
    print(f"📤 APK copiado para pasta legada do instalador: {destino_legacy}")
    return destino_dist, destino_pacote


def analisar_todos():
    if not os.path.exists(ENTRY_SCRIPT):
        print(f"❌ Arquivo de entrada {ENTRY_SCRIPT} não encontrado!")
        sys.exit(1)
    alteracoes = []
    with open(ENTRY_SCRIPT, encoding="utf-8") as f:
        for linha in f:
            if "# TODO:" in linha or "# FIX:" in linha or "# MOD:" in linha:
                alteracoes.append(linha.strip())
    return alteracoes

def resumo(projeto, versao, alteracoes):
    print(DIV)
    print(f"📦 Projeto: {projeto}")
    print(f"🔖 Versão: {versao}")
    print("📝 Alterações encontradas:")
    if alteracoes:
        for alt in alteracoes:
            print(f"   • {alt}")
    else:
        print("   Nenhuma alteração marcada encontrada.")
    print(DIV)
    if AUTO_MODE or not sys.stdin.isatty():
        print("🤖 Modo automático ativo: seguindo sem confirmação interativa.")
        return True
    resp = input("🚀 Deseja iniciar o Build e Release? (s/n): ").strip().lower()
    return resp == "s"

def limpar_pastas():
    for pasta in ["build", "dist"]:
        if os.path.exists(pasta):
            print(f"🧹 Limpando pasta: {pasta}/")
            if os.name == "nt":
                subprocess.run(f'rmdir /s /q {pasta}', shell=True)
            else:
                subprocess.run(f'rm -rf {pasta}', shell=True)

def _coletar_add_data_args() -> tuple[list[str], list[tuple[str, str, bool]]]:
    add_data_args: list[str] = []
    resumo: list[tuple[str, str, bool]] = []
    for origem, destino in RESOURCE_SPECS:
        existe = os.path.exists(origem)
        resumo.append((origem, destino, existe))
        if existe:
            add_data_args.extend(["--add-data", f"{origem};{destino}"])
    return add_data_args, resumo


def _coletar_resumo_recursos(specs: list[tuple[str, str]]) -> list[tuple[str, str, bool]]:
    return [(origem, destino, os.path.exists(origem)) for origem, destino in specs]


def _hidden_import_args() -> list[str]:
    args: list[str] = []
    for modulo, caminho in LOCAL_HIDDEN_IMPORTS:
        if os.path.exists(caminho):
            args.extend(["--hidden-import", modulo])
    for modulo in PYINSTALLER_HIDDEN_IMPORTS:
        args.extend(["--hidden-import", modulo])
    return args


def _collect_all_args() -> list[str]:
    args: list[str] = []
    for pacote in PYINSTALLER_COLLECT_ALL:
        args.append(f"--collect-all={pacote}")
    return args


def _sincronizar_fonte_para_build() -> None:
    if os.path.abspath(BUILD_ROOT) == os.path.abspath(REPO_ROOT):
        return

    itens = [
        ENTRY_SCRIPT,
        "config.py",
        "configuracao_fiscal.py",
        "dados_oficina.py",
        "config.json",
        "config.cfg",
        "versao.json",
        "version.json",
        "version.txt",
        "version_info.py",
        "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf",
        INSTALLER_SCRIPT,
        "instalar_oficial_completo.iss",
        "fundomenu.png",
        "LOGO.bmp",
        "icone_oficina.ico",
        "Atualizador.exe",
        "instala",
        "iniciar_servidor.bat",
        "servidor.py",
        "menu.py",
        "core",
        "assets",
        "Documentos",
        "templates",
        "static",
        "apk_celular_distribuicao",
        ANDROID_PROJECT_DIR,
    ]

    for rel_path in itens:
        origem = os.path.join(REPO_ROOT, rel_path)
        destino = os.path.join(BUILD_ROOT, rel_path)
        if not os.path.exists(origem):
            continue
        if os.path.isdir(origem):
            shutil.copytree(origem, destino, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.copy2(origem, destino)


def _resolver_python_build() -> str:
    candidatos = [
        os.path.join(".venv", "Scripts", "python.exe"),
        os.path.join("venv", "Scripts", "python.exe"),
        sys.executable,
    ]
    for caminho in candidatos:
        caminho_abs = os.path.abspath(caminho) if caminho else ""
        if caminho_abs and os.path.exists(caminho_abs):
            return caminho_abs
    raise FileNotFoundError("Nenhum interpretador Python válido foi encontrado para o build.")


def _validar_pasta_trabalho() -> bool:
    """Avisa quando o build está ocorrendo em um diretório rotulado como LIMPA."""
    cwd = os.path.abspath(os.getcwd())
    nome_pasta = os.path.basename(cwd).upper()
    if "LIMPA" not in nome_pasta:
        return True

    if os.environ.get("OFP_ALLOW_CLEAN_BUILD") == "1":
        print("⚠️  OFP_ALLOW_CLEAN_BUILD=1 detectado. Prosseguindo mesmo em pasta 'LIMPA'.")
        return True

    print("⚠️  Diretório atual contém 'LIMPA'. Continue apenas se este for o workspace com os dados corretos.")
    print(f"   Pasta atual: {cwd}")
    return True


def executar_smoke_test() -> bool:
    print(DIV)
    print(f"🧪 Smoke test de imports: {ENTRY_SCRIPT}")
    try:
        subprocess.run(
            [sys.executable, "-c", "import menu; print('SMOKE_IMPORT_OK')"],
            check=True,
        )
        print("✅ Smoke test aprovado.")
        return True
    except subprocess.CalledProcessError as exc:
        print(f"❌ Smoke test falhou com código {exc.returncode}.")
        return False


def validar_pre_build() -> bool:
    faltando: list[str] = []
    if not os.path.exists(ENTRY_SCRIPT):
        faltando.append(ENTRY_SCRIPT)

    _add_data_args, resumo = _coletar_add_data_args()
    for origem, _destino, existe in resumo:
        if not existe:
            faltando.append(origem)

    resumo_instalador = _coletar_resumo_recursos(INSTALLER_REQUIRED_SPECS)
    for origem, _destino, existe in resumo_instalador:
        if not existe:
            faltando.append(origem)

    print(DIV)
    print("🔎 Verificação de pré-build")
    print(f"   Entry script: {ENTRY_SCRIPT} -> {'OK' if os.path.exists(ENTRY_SCRIPT) else 'FALTANDO'}")
    _imprimir_resumo_recursos(resumo)
    print("📦 Recursos adicionais do instalador:")
    for origem, destino, existe in resumo_instalador:
        status = "OK" if existe else "FALTANDO"
        print(f"   [{status}] {origem} -> {destino}")
    print(DIV)

    if faltando:
        print("❌ Pré-build reprovado. Itens ausentes:")
        for item in faltando:
            print(f"   - {item}")
        return False

    print("✅ Pré-build aprovado. Recursos e entrypoint localizados.")
    return True


def _imprimir_resumo_recursos(resumo: list[tuple[str, str, bool]]) -> None:
    print(DIV)
    print("📎 Recursos mapeados para empacotamento (PyInstaller):")
    for origem, destino, existe in resumo:
        status = "OK" if existe else "FALTANDO"
        print(f"   [{status}] {origem} -> {destino}")
    print(DIV)


def _gerar_arquivo_versao_pyinstaller(versao: str) -> str:
    partes = [int(p) for p in str(versao).strip().split(".") if p.isdigit()]
    while len(partes) < 4:
        partes.append(0)
    partes = partes[:4]
    arq = os.path.join("build", "version_file.txt")
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    conteudo = f"""# UTF-8
VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=({partes[0]}, {partes[1]}, {partes[2]}, {partes[3]}),
        prodvers=({partes[0]}, {partes[1]}, {partes[2]}, {partes[3]}),
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0)
    ),
    kids=[
        StringFileInfo([
            StringTable(
                '040904B0',
                [
                    StringStruct('CompanyName', 'FRS Solutions'),
                    StringStruct('FileDescription', 'Sistema Oficina de Pesca'),
                    StringStruct('FileVersion', '{versao}'),
                    StringStruct('InternalName', 'Oficina_Pesca'),
                    StringStruct('LegalCopyright', 'FRS Solutions'),
                    StringStruct('OriginalFilename', 'Oficina_Pesca_v{versao}.exe'),
                    StringStruct('ProductName', 'Oficina de Pesca'),
                    StringStruct('ProductVersion', '{versao}')
                ]
            )
        ]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])
    ]
)
"""
    with open(arq, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return arq


def _resolver_icone_build() -> str | None:
    candidatos = [
        "icone_oficina.ico",
        os.path.join("assets", "logo.ico"),
    ]
    for caminho in candidatos:
        if os.path.exists(caminho):
            return caminho
    return None


def _localizar_iscc() -> str:
    candidatos = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for caminho in candidatos:
        if os.path.exists(caminho):
            return caminho
    raise FileNotFoundError("Inno Setup 6 (ISCC.exe) não encontrado.")


def _nome_instalador_final(versao: str) -> str:
    return f"Setup_OficinaPesca_v{versao}.exe"


def _compilar_instalador_final(versao: str) -> str:
    iscc = _localizar_iscc()
    output_name = os.path.splitext(_nome_instalador_final(versao))[0]
    cmd_installer = [
        iscc,
        f"/DAppVersion={versao}",
        f"/DInstallerOutputName={output_name}",
        INSTALLER_SCRIPT,
    ]
    subprocess.run(cmd_installer, check=True)
    instalador = os.path.join(INSTALLER_OUTPUT_DIR, f"{output_name}.exe")
    if not os.path.exists(instalador):
        candidatos = sorted(
            [
                os.path.join(INSTALLER_OUTPUT_DIR, nome)
                for nome in os.listdir(INSTALLER_OUTPUT_DIR)
                if nome.lower().startswith(f"setup_oficinapesca_v{versao}".lower()) and nome.lower().endswith(".exe")
            ],
            key=os.path.getmtime,
            reverse=True,
        )
        if candidatos:
            instalador = candidatos[0]
        else:
            raise FileNotFoundError(f"Instalador final não encontrado em {instalador}.")
    return instalador


def _copiar_instalador_para_distribuicao(instalador: str) -> str:
    os.makedirs(DISTRIBUTION_DIR, exist_ok=True)
    destino = os.path.join(DISTRIBUTION_DIR, DISTRIBUTION_INSTALLER_NAME)
    print(f"🧾 CÓPIA instalador -> origem: {os.path.abspath(instalador)}")
    print(f"🧾 CÓPIA instalador -> destino: {os.path.abspath(destino)}")
    shutil.copy2(instalador, destino)
    return destino


def _resolver_origem_bootstrapper() -> str:
    candidatos = [
        os.path.join(BUILD_ROOT, "Atualizador.exe"),
        os.path.join(REPO_ROOT, "Atualizador.exe"),
    ]
    for caminho in candidatos:
        if os.path.exists(caminho):
            return caminho
    raise FileNotFoundError(
        "Atualizador.exe não encontrado. Verifique a presença do arquivo em: "
        + " | ".join(candidatos)
    )


def _garantir_bootstrapper_no_bundle(dist_dir: str) -> str:
    origem = _resolver_origem_bootstrapper()

    # Se o arquivo vier da raiz do repositório, replica também para BUILD_ROOT
    # para manter o diretório de build consistente para próximas etapas.
    destino_build_root = os.path.join(BUILD_ROOT, "Atualizador.exe")
    if os.path.abspath(origem) != os.path.abspath(destino_build_root):
        _copiar_executavel_com_retry(origem, destino_build_root)

    destino = os.path.join(dist_dir, "Atualizador.exe")
    _copiar_executavel_com_retry(origem, destino)
    if not os.path.exists(destino):
        raise FileNotFoundError(f"Falha ao garantir Atualizador.exe no bundle: {destino}")
    return destino


def _copiar_bootstrapper_para_distribuicao(bootstrapper_bundle: str) -> str:
    os.makedirs(DISTRIBUTION_DIR, exist_ok=True)
    destino = os.path.join(DISTRIBUTION_DIR, DISTRIBUTION_BOOTSTRAPPER_NAME)
    print(f"🧾 CÓPIA bootstrapper -> origem: {os.path.abspath(bootstrapper_bundle)}")
    print(f"🧾 CÓPIA bootstrapper -> destino: {os.path.abspath(destino)}")
    shutil.copy2(bootstrapper_bundle, destino)
    if not os.path.exists(destino):
        raise FileNotFoundError(f"Falha ao copiar bootstrapper para distribuição: {destino}")
    return destino


def _resolver_origem_recurso(rel_path: str) -> str:
    candidatos = [
        os.path.join(BUILD_ROOT, rel_path),
        os.path.join(REPO_ROOT, rel_path),
    ]
    for caminho in candidatos:
        if os.path.exists(caminho):
            return caminho
    raise FileNotFoundError(f"Recurso obrigatório não encontrado: {rel_path}")


def _copiar_recurso_para_stage(rel_path: str, dest_rel: str, stage_dir: str) -> str:
    origem = _resolver_origem_recurso(rel_path)
    if dest_rel in (".", ""):
        destino_base = stage_dir
    else:
        destino_base = os.path.join(stage_dir, dest_rel)

    if os.path.isdir(origem):
        destino = os.path.join(destino_base, os.path.basename(rel_path.rstrip("\\/"))) if dest_rel in (".", "") else destino_base
        os.makedirs(os.path.dirname(destino) if os.path.splitext(destino)[1] else destino, exist_ok=True)
        if os.path.splitext(destino)[1]:
            # Segurança: se por engano destino for arquivo, ajusta para pasta de mesmo nome.
            destino = os.path.splitext(destino)[0]
        shutil.copytree(origem, destino, dirs_exist_ok=True)
        return destino

    os.makedirs(destino_base, exist_ok=True)
    destino = os.path.join(destino_base, os.path.basename(rel_path))
    shutil.copy2(origem, destino)
    return destino


def _montar_stage_portatil(dist_dir: str, bootstrapper_bundle: str) -> str:
    stage_dir = PORTABLE_STAGE_DIR
    if os.path.exists(stage_dir):
        shutil.rmtree(stage_dir, ignore_errors=True)

    print(f"🧾 Stage portátil -> origem bundle: {os.path.abspath(dist_dir)}")
    print(f"🧾 Stage portátil -> destino: {os.path.abspath(stage_dir)}")
    shutil.copytree(dist_dir, stage_dir, dirs_exist_ok=True)

    destino_bootstrapper = os.path.join(stage_dir, "Atualizador.exe")
    _copiar_executavel_com_retry(bootstrapper_bundle, destino_bootstrapper)

    for rel_path, dest_rel in PORTABLE_REQUIRED_SPECS:
        destino = _copiar_recurso_para_stage(rel_path, dest_rel, stage_dir)
        print(f"🧾 Stage portátil recurso -> {rel_path} => {os.path.abspath(destino)}")

    return stage_dir


def _validar_stage_portatil(stage_dir: str) -> None:
    obrigatorios = [
        os.path.join(stage_dir, f"{APP_NAME}.exe"),
        os.path.join(stage_dir, "Atualizador.exe"),
        os.path.join(stage_dir, "templates"),
        os.path.join(stage_dir, "static"),
        os.path.join(stage_dir, "assets"),
        os.path.join(stage_dir, "servidor.py"),
        os.path.join(stage_dir, "config.py"),
        os.path.join(stage_dir, "iniciar_servidor.bat"),
    ]
    faltando = [p for p in obrigatorios if not os.path.exists(p)]
    if faltando:
        raise FileNotFoundError(
            "Pacote portátil incompleto em INSTALADOR_FINAL/Oficina_Pesca. Itens ausentes: " + ", ".join(faltando)
        )


def _validar_fundo_menu_em_diretorio(base_dir: str, contexto: str) -> str:
    candidatos_abs = [os.path.abspath(os.path.join(base_dir, rel)) for rel in FUNDO_MENU_CANDIDATOS]
    encontrados = [c for c in candidatos_abs if os.path.exists(c)]
    for caminho in candidatos_abs:
        status = "FOUND" if os.path.exists(caminho) else "FileNotFound"
        print(f"🖼️  Fundo menu ({contexto}) tentativa: {caminho} -> {status}")
    if not encontrados:
        raise FileNotFoundError(
            f"Imagem de fundo_menu não encontrada em {contexto} ({os.path.abspath(base_dir)})."
        )
    selecionado = encontrados[0]
    print(f"✅ Fundo menu validado em {contexto}: {selecionado}")
    return selecionado


def _validar_assets_bundle_interno(dist_dir: str) -> None:
    """Garante que o bundle interno tenha assets visuais antes da etapa do instalador."""
    pasta_assets = os.path.abspath(os.path.join(dist_dir, "_internal", "assets"))
    print(f"🧪 Verificando assets internos do bundle: {pasta_assets}")

    if not os.path.isdir(pasta_assets):
        raise FileNotFoundError(
            f"Pasta de assets internos ausente: {pasta_assets}. Build abortado."
        )

    imagens = []
    for nome in sorted(os.listdir(pasta_assets)):
        caminho = os.path.join(pasta_assets, nome)
        if not os.path.isfile(caminho):
            continue
        ext = os.path.splitext(nome)[1].lower()
        if ext in {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".ico"}:
            imagens.append(nome)

    if not imagens:
        raise RuntimeError(
            f"Assets internos sem imagens em {pasta_assets}. Build abortado."
        )

    if "fundo_menu.jpeg" not in imagens:
        raise RuntimeError(
            f"Arquivo obrigatório 'fundo_menu.jpeg' ausente em {pasta_assets}. Build abortado."
        )

    print(f"✅ Assets internos validados ({len(imagens)} imagem(ns)): {', '.join(imagens)}")


def _gerar_zip_portatil(stage_dir: str) -> tuple[str, str]:
    os.makedirs(PORTABLE_OUTPUT_DIR, exist_ok=True)
    zip_output = os.path.join(PORTABLE_OUTPUT_DIR, PORTABLE_ZIP_NAME)
    if os.path.exists(zip_output):
        os.remove(zip_output)

    with zipfile.ZipFile(zip_output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for raiz, _dirs, arquivos in os.walk(stage_dir):
            for nome in arquivos:
                caminho = os.path.join(raiz, nome)
                arcname = os.path.relpath(caminho, stage_dir)
                zf.write(caminho, arcname)

    os.makedirs(DISTRIBUTION_DIR, exist_ok=True)
    destino_pacote = os.path.join(DISTRIBUTION_DIR, PORTABLE_ZIP_NAME)
    shutil.copy2(zip_output, destino_pacote)
    return zip_output, destino_pacote


def _copiar_artefatos_para_instalador_final(instalador: str, bootstrapper_bundle: str, versao: str) -> tuple[str, str]:
    os.makedirs(INSTALLER_OUTPUT_DIR, exist_ok=True)

    setup_destino = os.path.join(INSTALLER_OUTPUT_DIR, _nome_instalador_final(versao))
    bootstrapper_destino = os.path.join(INSTALLER_OUTPUT_DIR, "Atualizador.exe")

    print(f"🧾 CÓPIA INSTALADOR_FINAL setup -> origem: {os.path.abspath(instalador)}")
    print(f"🧾 CÓPIA INSTALADOR_FINAL setup -> destino: {os.path.abspath(setup_destino)}")
    print(f"🧾 CÓPIA INSTALADOR_FINAL bootstrapper -> origem: {os.path.abspath(bootstrapper_bundle)}")
    print(f"🧾 CÓPIA INSTALADOR_FINAL bootstrapper -> destino: {os.path.abspath(bootstrapper_destino)}")

    _copiar_executavel_com_retry(instalador, setup_destino)
    _copiar_executavel_com_retry(bootstrapper_bundle, bootstrapper_destino)

    # Força atualização da data de modificação para evidenciar o refresh no INSTALADOR_FINAL.
    agora = time.time()
    for caminho in [setup_destino, bootstrapper_destino]:
        if os.path.exists(caminho):
            os.utime(caminho, (agora, agora))

    faltando: list[str] = []
    for caminho in [setup_destino, bootstrapper_destino]:
        if not os.path.exists(caminho):
            faltando.append(caminho)

    if faltando:
        raise FileNotFoundError(
            "Falha ao atualizar INSTALADOR_FINAL. Itens ausentes: " + ", ".join(faltando)
        )

    return setup_destino, bootstrapper_destino


def _validar_pacote_distribuicao(instalador_destino: str, bootstrapper_destino: str) -> None:
    faltando: list[str] = []
    zip_portatil = os.path.join(DISTRIBUTION_DIR, PORTABLE_ZIP_NAME)
    apk_distribuicao = os.path.join(ANDROID_APK_PACKAGE_DIR, ANDROID_APK_NAME)
    for caminho in [instalador_destino, bootstrapper_destino, zip_portatil, apk_distribuicao]:
        if not os.path.exists(caminho):
            faltando.append(caminho)
    if faltando:
        raise FileNotFoundError(
            "Pacote final incompleto em PACOTE_ENVIO. Itens ausentes: " + ", ".join(faltando)
        )


def _copiar_executavel_com_retry(origem: str, destino: str, tentativas: int = 8, espera_s: float = 1.25) -> str:
    origem_abs = os.path.abspath(origem)
    destino_abs = os.path.abspath(destino)
    if origem_abs == destino_abs:
        if os.path.exists(origem_abs):
            print(f"🧾 CÓPIA ignorada (origem=destino): {origem_abs}")
            return destino
        raise FileNotFoundError(f"Origem e destino apontam para arquivo inexistente: {origem}")

    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            print(f"🧾 CÓPIA executável tentativa {tentativa}/{tentativas} -> origem: {origem_abs}")
            print(f"🧾 CÓPIA executável tentativa {tentativa}/{tentativas} -> destino: {destino_abs}")
            if os.path.exists(destino):
                os.remove(destino)
            shutil.copy2(origem, destino)
            return destino
        except PermissionError as e:
            ultimo_erro = e
            print(f"⚠️  Arquivo de destino em uso (tentativa {tentativa}/{tentativas}). Aguardando...")
            time.sleep(espera_s)
        except OSError as e:
            ultimo_erro = e
            print(f"⚠️  Falha de IO na cópia (tentativa {tentativa}/{tentativas}): {e}")
            time.sleep(espera_s)

    base, ext = os.path.splitext(destino)
    destino_fallback = f"{base}_novo_{time.strftime('%Y%m%d_%H%M%S')}{ext}"
    try:
        shutil.copy2(origem, destino_fallback)
        print(
            "⚠️  Destino principal permaneceu bloqueado. "
            f"Arquivo copiado com nome alternativo: {destino_fallback}"
        )
        return destino_fallback
    except Exception as e:
        raise RuntimeError(
            f"Não foi possível copiar o executável para '{destino}' após {tentativas} tentativas, "
            f"nem para fallback '{destino_fallback}'. "
            "Feche instaladores, explorador ou antivírus que possam estar usando o arquivo."
        ) from (e if e else ultimo_erro)

def build(projeto, versao):
    versao = str(versao or VERSAO).strip() or VERSAO
    nome = APP_NAME
    print(f"⚙️  Executando PyInstaller para {nome}...")
    venv_py = _resolver_python_build()
    _sincronizar_fonte_para_build()
    old_cwd = os.getcwd()
    if os.path.abspath(BUILD_ROOT) != os.path.abspath(old_cwd):
        os.chdir(BUILD_ROOT)

    try:
        # 1. Limpa as pastas build e dist antigas antes de iniciar a geração de novos arquivos
        for pasta in ["build", "dist"]:
            if os.path.exists(pasta):
                print(f"🧹 Limpando pasta: {pasta}/")
                if os.name == "nt":
                    subprocess.run(f'rmdir /s /q {pasta}', shell=True)
                else:
                    subprocess.run(f'rm -rf {pasta}', shell=True)

        # 2. Agora gera os arquivos necessários para o build (incluindo o version_file.txt dentro da pasta build recriada)
        add_data_args, resumo_recursos = _coletar_add_data_args()
        _imprimir_resumo_recursos(resumo_recursos)
        version_file_path = _gerar_arquivo_versao_pyinstaller(versao)
        icone_build = _resolver_icone_build()
        hidden_import_args = _hidden_import_args()
        collect_all_args = _collect_all_args()

        if not validar_pre_build():
            raise RuntimeError("Pré-build falhou; ajuste os recursos antes de gerar o executável.")

        # Executa diretamente o build final; gerar .spec antes disso só duplica a análise.
        cmd_build = [
            venv_py, "-m", "PyInstaller",
            "--onedir",
            "--windowed",
            "--clean",
            "--noconfirm",
            "--paths=.",
            "--name", nome,
            "--version-file", version_file_path,
            *hidden_import_args,
            *collect_all_args,
            *add_data_args,
            ENTRY_SCRIPT
        ]
        if icone_build:
            cmd_build[cmd_build.index(ENTRY_SCRIPT):cmd_build.index(ENTRY_SCRIPT)] = ["--icon", icone_build]
            print(f"🎨 Ícone do executável configurado: {icone_build}")
        else:
            print("⚠️  Nenhum arquivo .ico encontrado; executável pode sair com ícone padrão.")
        subprocess.run(cmd_build, check=True)

        dist_dir = os.path.join("dist", nome)
        if not os.path.exists(dist_dir):
            raise FileNotFoundError(f"Diretório do bundle não encontrado em {dist_dir}.")

        _validar_assets_bundle_interno(dist_dir)
        print("✅ Build finalizado com sucesso!")

        _validar_fundo_menu_em_diretorio(dist_dir, "bundle dist")

        caminho_bootstrapper = _garantir_bootstrapper_no_bundle(dist_dir)
        print(f"✅ Bootstrapper de atualização garantido no bundle: {caminho_bootstrapper}")

        apk_dist, apk_distribuicao = _build_apk_android(versao)
        print(f"✅ APK WebView alinhado à versão {versao}: {apk_dist}")

        stage_portatil = _montar_stage_portatil(dist_dir, caminho_bootstrapper)
        _validar_stage_portatil(stage_portatil)
        _validar_fundo_menu_em_diretorio(stage_portatil, "stage portátil")
        print(f"✅ Stage portátil validado em: {stage_portatil}")

        zip_portatil, zip_portatil_distribuicao = _gerar_zip_portatil(stage_portatil)
        print(f"📦 ZIP portátil gerado: {zip_portatil}")
        print(f"📤 ZIP portátil copiado para distribuição: {zip_portatil_distribuicao}")

        print("🛠️  Compilando instalador final com Inno Setup...")
        instalador = _compilar_instalador_final(versao)
        print(f"✅ Instalador final gerado: {instalador}")

        setup_instalador_final, bootstrapper_instalador_final = _copiar_artefatos_para_instalador_final(
            instalador,
            caminho_bootstrapper,
            versao,
        )
        print(f"📦 Setup garantido em INSTALADOR_FINAL: {setup_instalador_final}")
        print(f"📦 Bootstrapper garantido em INSTALADOR_FINAL: {bootstrapper_instalador_final}")

        destino_distribuicao = _copiar_instalador_para_distribuicao(instalador)
        destino_bootstrapper = _copiar_bootstrapper_para_distribuicao(caminho_bootstrapper)
        _validar_pacote_distribuicao(destino_distribuicao, destino_bootstrapper)
        print(f"📤 Instalador copiado para distribuição: {destino_distribuicao}")
        print(f"📤 Bootstrapper copiado para distribuição: {destino_bootstrapper}")
        print(f"📤 APK copiado para distribuição: {apk_distribuicao}")
        _gerar_log_saude_sistema(versao, apk_dist, instalador)
        return instalador, destino_distribuicao
    finally:
        os.chdir(old_cwd)

def main():
    print_header()
    if not _validar_pasta_trabalho():
        sys.exit(1)
    projeto, versao = get_input()
    if versao != VERSAO:
        print(f"ℹ️  Versão informada ({versao}) ignorada. Usando fonte única do mestre_build.py: {VERSAO}")
    versao = VERSAO
    _sincronizar_versao_global(versao)
    alteracoes = analisar_todos()
    if not resumo(projeto, versao, alteracoes):
        print("❌ Build cancelado pelo usuário.")
        return
    if not executar_smoke_test():
        print("❌ Abortando build por falha no smoke test.")
        sys.exit(1)
    limpar_pastas()
    instalador, destino_distribuicao = build(projeto, versao)

    print(DIV)
    print(f"🎉 Fluxo concluído com sucesso. Instalador: {instalador}")
    print(f"📦 Distribuição atualizada em: {destino_distribuicao}")
    print(DIV)

if __name__ == "__main__":
    main()
