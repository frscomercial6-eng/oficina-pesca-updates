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
VERSAO = "1.0.12"


RESOURCE_SPECS = [
    ("assets", "assets"),
    ("fundomenu.png", "."),
    ("icone_oficina.ico", "."),
    ("config.cfg", "."),
    ("versao.json", "."),
    ("version.txt", "."),
    ("google-services.json", "."),
    ("client_secret_desktop.json", "."),
    ("credentials.json", "."),
    ("credentials.txt", "."),
    ("chave_firebase.json", "."),
    ("Documentos/termos_de_uso.txt", "Documentos"),
    ("Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf", "."),
]

def print_header():
    print(f"\n{'🚀 FRS Solutions - Orquestrador de Build 🚀':^50}")
    print(DIV)

def get_input():
    # Tenta obter argumentos da linha de comando
    import sys
    default_projeto = "oficina de pesca"
    default_versao = VERSAO
    args = sys.argv[1:]
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
    if not os.path.exists("main.py"):
        print("❌ Arquivo main.py não encontrado!")
        sys.exit(1)
    alteracoes = []
    with open("main.py", encoding="utf-8") as f:
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
    nome = f"Oficina_Pesca_v{versao}"
    print(f"⚙️  Executando PyInstaller para {nome}...")
    venv_py = os.path.join(".venv", "Scripts", "python.exe")

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

    # Mapeamento de todos os módulos locais para evitar ModuleNotFoundError no executável
    modulos_locais = [
        'menu', 'config', 'tela_planos', 'tela_os',
        'tela_financeiro', 'clientes', 'gestao_os', 'util_recibo',
        'core', 'core.modulos', 'core.financeiro', 'core.financeiro.calculos'
    ]
    # Executa o PyInstaller apenas para gerar um novo .spec limpo
    cmd_spec = [
        venv_py, '-m', 'PyInstaller',
        '--clean',
        '--paths=.',
        '--hidden-import=menu',
        '--hidden-import=config',
        '--hidden-import=tela_planos',
        '--hidden-import=tela_os',
        '--hidden-import=tela_financeiro',
        '--hidden-import=clientes',
        '--hidden-import=gestao_os',
        '--hidden-import=util_recibo',
        '--hidden-import=core',
        '--hidden-import=core.modulos',
        '--hidden-import=core.financeiro',
        '--hidden-import=core.financeiro.calculos',
        'login.py',
    ]
    subprocess.run(cmd_spec, check=True)
    print("✅ Novo arquivo .spec gerado com sucesso!")

    # Agora executa o build final usando o script login.py como alvo
    cmd_build = [
        ".venv\\Scripts\\python.exe", "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--paths=.",
        "--name", nome,
        "--version-file", version_file_path,
        "--hidden-import=menu",
        "--hidden-import=config",
        "--hidden-import=tela_planos",
        "--hidden-import=tela_os",
        "--hidden-import=tela_financeiro",
        "--hidden-import=clientes",
        "--hidden-import=gestao_os",
        "--hidden-import=util_recibo",
        "--hidden-import=core",
        "--hidden-import=core.modulos",
        "--hidden-import=core.financeiro",
        "--hidden-import=core.financeiro.calculos",
        "--hidden-import=firebase_admin",
        # Google API e OAuth2
        "--hidden-import=googleapiclient",
        "--hidden-import=googleapiclient.discovery",
        "--hidden-import=googleapiclient.errors",
        "--hidden-import=googleapiclient.http",
        "--hidden-import=googleapiclient._auth",
        "--hidden-import=google_auth_oauthlib",
        "--hidden-import=google_auth_oauthlib.flow",
        "--hidden-import=google.oauth2",
        "--hidden-import=google.oauth2.credentials",
        "--hidden-import=google.oauth2.service_account",
        "--hidden-import=google.auth",
        "--hidden-import=google.auth.transport",
        "--hidden-import=google.auth.transport.requests",
        "--hidden-import=google.auth.exceptions",
        "--hidden-import=oauth2client",
        "--hidden-import=oauth2client.client",
        "--hidden-import=oauth2client.file",
        "--hidden-import=oauth2client.tools",
        "--hidden-import=httplib2",
        # Garantir dependências de atualização automática
        "--hidden-import=urllib",
        "--hidden-import=urllib.request",
        "--hidden-import=urllib.error",
        "--hidden-import=ssl",
        "--hidden-import=certifi",
        # Coleta completa de dados/metadados dos pacotes Google
        "--collect-all=googleapiclient",
        "--collect-all=google_auth_oauthlib",
        "--collect-all=google",
        "--collect-all=google_auth",
        "--collect-all=google_api_python_client",
        *add_data_args,
        "login.py"
    ]
    if icone_build:
        cmd_build[cmd_build.index("login.py"):cmd_build.index("login.py")] = ["--icon", icone_build]
        print(f"🎨 Ícone do executável configurado: {icone_build}")
    else:
        print("⚠️  Nenhum arquivo .ico encontrado; executável pode sair com ícone padrão.")
    subprocess.run(cmd_build, check=True)
    print("✅ Build finalizado com sucesso!")

    # 3. Localizar o executável na pasta dist, copiar para INSTALADOR_FINAL e renomear
    origem = os.path.join("dist", f"{nome}.exe")
    pasta_final = "INSTALADOR_FINAL"
    novo_nome = f"Setup_OficinaPesca_v{versao}.exe"
    destino = os.path.join(pasta_final, novo_nome)

    print(f"📂 Organizando executável para o deploy...")
    if not os.path.exists(pasta_final):
        os.makedirs(pasta_final)
        print(f"📁 Pasta '{pasta_final}' criada.")

    if os.path.exists(origem):
        destino_real = _copiar_executavel_com_retry(origem, destino)
        print(f"✔️  Executável copiado e renomeado para: {destino_real}")
    else:
        print(f"❌ ERRO: Executável não encontrado em {origem}. Verifique o log do PyInstaller.")
        sys.exit(1)

def executar_distribuicao_github():
    print("🚀 Iniciando Upload para o GitHub (deploy_release.py)...")
    venv_py = os.path.join(".venv", "Scripts", "python.exe")
    if os.path.exists("deploy_release.py"):
        subprocess.run([venv_py, "deploy_release.py"], check=True)
    else:
        print("⚠️  Arquivo deploy_release.py não encontrado.")

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
    limpar_pastas()
    build(projeto, versao)
    print("\n📦 Iniciando o empacotamento e validações com gerar_release.bat...")
    subprocess.run(['gerar_release.bat'], shell=True, check=True)

    print("\n" + DIV)
    confirmar_deploy = input("🚀 Deseja realizar o Deploy automático para o GitHub agora? (s/n): ").strip().lower()
    if confirmar_deploy == 's':
        executar_distribuicao_github()
    else:
        print("⏭️  Deploy para o GitHub cancelado pelo usuário.")

    print(DIV)
    print("🎉 Fluxo de Build e Deploy concluído com sucesso!")
    print(DIV)

if __name__ == "__main__":
    main()
