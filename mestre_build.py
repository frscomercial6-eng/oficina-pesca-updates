# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import json
import configparser
import os
import shutil
import sys
import subprocess
import re
import time

DIV = "═" * 50
VERSAO = "1.0.27.1"
APP_NAME = "Oficina_Pesca"
ENTRY_SCRIPT = "menu.py"
INSTALLER_SCRIPT = "instalar.iss"
INSTALLER_OUTPUT_DIR = "INSTALADOR_FINAL"
DISTRIBUTION_DIR = "PACOTE_ENVIO"
DISTRIBUTION_INSTALLER_NAME = "Oficina_Pesca_Instalador.exe"
AUTO_MODE = "--auto" in sys.argv or os.environ.get("OFP_BUILD_AUTO") == "1"


RESOURCE_SPECS = [
    ("assets", "assets"),
    ("fundomenu.png", "."),
    ("LOGO.bmp", "."),
    ("icone_oficina.ico", "."),
    ("config.cfg", "."),
    ("versao.json", "."),
    ("version.txt", "."),
    ("Documentos/termos_de_uso.txt", "Documentos"),
    ("Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf", "."),
]

INSTALLER_REQUIRED_SPECS = [
    ("config.json", "."),
    ("iniciar_servidor.bat", "."),
    ("servidor.py", "."),
    ("static", "static"),
    ("templates", "templates"),
]

LOCAL_HIDDEN_IMPORTS = [
    ("adaptador_acbr", "adaptador_acbr.py"),
    ("clientes", "clientes.py"),
    ("config", "config.py"),
    ("gestao_os", "gestao_os.py"),
    ("menu", ENTRY_SCRIPT),
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
        r'(?m)^\s*VERSION\s*=\s*["\']\d+\.\d+\.\d+["\']\s*$',
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
        novo = re.sub(r'(Vers[aã]o\s+)(\d+\.\d+\.\d+)', rf'\g<1>{nova_versao}', novo, flags=re.IGNORECASE)
        # Caso específico em RTF onde "Versão" aparece com escapes.
        novo = re.sub(
            r"(Vers\\'e3\\loch\\f1\s+\\hich\\f1\s*o\s+)(\d+\.\d+\.\d+)",
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
            r'(?im)^\s*#define\s+AppVersion\s+"[0-9]+\.[0-9]+\.[0-9]+"\s*$',
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
            r'(?im)^\s*set\s+"SETUP_NAME=Setup_OficinaPesca_v[0-9]+\.[0-9]+\.[0-9]+\.exe"\s*$',
            f'set "SETUP_NAME=Setup_OficinaPesca_v{nova_versao}.exe"',
            novo,
        )
        novo = re.sub(
            r'(?im)(/DInstallerOutputName=Setup_OficinaPesca_v)[0-9]+\.[0-9]+\.[0-9]+(_FINAL)',
            rf'\g<1>{nova_versao}\g<2>',
            novo,
        )
        novo = re.sub(
            r'(?im)^\s*set\s+"FINAL_SETUP=Setup_OficinaPesca_v[0-9]+\.[0-9]+\.[0-9]+_FINAL\.exe"\s*$',
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


def _resolver_python_build() -> str:
    candidatos = [
        os.path.join(".venv", "Scripts", "python.exe"),
        os.path.join("venv", "Scripts", "python.exe"),
        sys.executable,
    ]
    for caminho in candidatos:
        if caminho and os.path.exists(caminho):
            return caminho
    raise FileNotFoundError("Nenhum interpretador Python válido foi encontrado para o build.")


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
    shutil.copy2(instalador, destino)
    return destino


def _copiar_executavel_com_retry(origem: str, destino: str, tentativas: int = 8, espera_s: float = 1.25) -> str:
    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
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
    print("✅ Build finalizado com sucesso!")

    dist_dir = os.path.join("dist", nome)
    if not os.path.exists(dist_dir):
        raise FileNotFoundError(f"Diretório do bundle não encontrado em {dist_dir}.")

    print("🛠️  Compilando instalador final com Inno Setup...")
    instalador = _compilar_instalador_final(versao)
    print(f"✅ Instalador final gerado: {instalador}")

    destino_distribuicao = _copiar_instalador_para_distribuicao(instalador)
    print(f"📤 Instalador copiado para distribuição: {destino_distribuicao}")
    return instalador, destino_distribuicao

def main():
    print_header()
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
