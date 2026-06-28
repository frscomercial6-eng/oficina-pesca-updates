# -*- coding: utf-8 -*-
"""
deploy_release.py
=================
Cria/atualiza a Release no GitHub e atualiza o versao.txt no repositório
oficina-pesca-updates para apontar para o novo instalador.

USO:
    python deploy_release.py

O script lê o token do GitHub apenas por variável de ambiente:
    - GH_TOKEN (recomendado)
    - GITHUB_TOKEN (compatibilidade)

REPOSITÓRIOS utilizados:
  - Release (upload do .exe):   frscomercial6-eng / oficina-pesca-updates
  - Manifesto de versão:        frscomercial6-eng / oficina-pesca-updates  (versao.txt)
"""

import base64
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path
from version_info import VERSION as _VI_VERSION

import requests

# ─── Configurações ────────────────────────────────────────────────────────────

# Repositório onde a Release será criada e o .exe hospedado
OWNER = "frscomercial6-eng"
REPO_RELEASE = "oficina-pesca-updates"

# Repositório onde o versao.txt será atualizado (mesmo repo neste caso)
REPO_MANIFESTO = "oficina-pesca-updates"
BRANCH_MANIFESTO = "main"
CAMINHO_MANIFESTO = "versao.txt"

# Versão a lançar
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VERSAO_JSON_PATH = os.path.join(SCRIPT_DIR, "versao.json")
EXE_DIR = os.path.join(SCRIPT_DIR, "INSTALADOR_FINAL")
PORTABLE_ZIP_PATH = os.path.join(SCRIPT_DIR, "Output", "Oficina_Pesca_Portatil.zip")
PORTABLE_DEPLOY_ZIP_PATH = os.path.join(SCRIPT_DIR, "Output", "Oficina_Pesca_Portatil_Core.zip")
DIST_APP_DIR = os.path.join(SCRIPT_DIR, "dist", "Oficina_Pesca")
CORE_DIR = os.path.join(SCRIPT_DIR, "core")


# Versão lida exclusivamente de version_info.py
VERSAO = _VI_VERSION
TAG = f"v{VERSAO}"

# Notas de lançamento (lidas de versao.json se disponível)
def _ler_novidades() -> str:
    try:
        with open(VERSAO_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("novidades") or "").strip()
    except Exception:
        return f"Versão {VERSAO}"


def _garantir_zip_portatil_com_core() -> str:
    """Gera um ZIP portátil contendo o build e a pasta core para deploy."""
    if not os.path.isdir(DIST_APP_DIR):
        print(f"[ERRO] Pasta de build não encontrada: {DIST_APP_DIR}")
        sys.exit(1)

    if not os.path.isdir(CORE_DIR):
        print(f"[ERRO] Pasta core não encontrada: {CORE_DIR}")
        sys.exit(1)

    os.makedirs(os.path.dirname(PORTABLE_DEPLOY_ZIP_PATH), exist_ok=True)
    if os.path.exists(PORTABLE_DEPLOY_ZIP_PATH):
        os.remove(PORTABLE_DEPLOY_ZIP_PATH)

    print(f"[...] Gerando pacote portátil com core: {PORTABLE_DEPLOY_ZIP_PATH}")
    with zipfile.ZipFile(PORTABLE_DEPLOY_ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for raiz, _dirs, arquivos in os.walk(DIST_APP_DIR):
            for nome in arquivos:
                caminho = os.path.join(raiz, nome)
                arcname = os.path.relpath(caminho, SCRIPT_DIR)
                zf.write(caminho, arcname)

        for raiz, _dirs, arquivos in os.walk(CORE_DIR):
            for nome in arquivos:
                caminho = os.path.join(raiz, nome)
                arcname = os.path.relpath(caminho, SCRIPT_DIR)
                zf.write(caminho, arcname)

    print("[ok] Pacote portátil com core gerado.")
    return PORTABLE_DEPLOY_ZIP_PATH


def _resolver_instalador() -> tuple[str, str]:
    """Retorna o caminho e o nome do instalador priorizando a versão atual."""
    versionado = os.path.join(EXE_DIR, f"Setup_OficinaPesca_v{VERSAO}.exe")
    legado = os.path.join(EXE_DIR, "Setup_OficinaPesca.exe")

    print(f"[log] Buscando instalador em: {os.path.abspath(versionado)}")
    if os.path.exists(versionado):
        print(f"[ok] Instalador encontrado: {os.path.abspath(versionado)}")
        return versionado, os.path.basename(versionado)

    print(f"[log] Não encontrado. Tentando: {os.path.abspath(legado)}")
    if os.path.exists(legado):
        print(f"[ok] Instalador encontrado: {os.path.abspath(legado)}")
        return legado, os.path.basename(legado)

    # Fallback: pega qualquer .exe disponível na pasta INSTALADOR_FINAL
    print(f"[aviso] Nomes esperados não encontrados. Buscando qualquer .exe em: {os.path.abspath(EXE_DIR)}")
    exes = [f for f in os.listdir(EXE_DIR) if f.lower().endswith(".exe")] if os.path.isdir(EXE_DIR) else []
    if exes:
        encontrado = os.path.join(EXE_DIR, exes[0])
        print(f"[ok] Instalador alternativo encontrado automaticamente: {os.path.abspath(encontrado)}")
        return encontrado, exes[0]

    print(f"[ERRO] Nenhum instalador .exe encontrado em: {os.path.abspath(EXE_DIR)}")
    print(f"[ERRO] Arquivos tentados:\n  {os.path.abspath(versionado)}\n  {os.path.abspath(legado)}")
    sys.exit(1)


def _caminhos_drive_base() -> list[str]:
    candidatos: list[str] = []

    env_root = str(os.environ.get("OFP_GOOGLE_DRIVE_ROOT", "") or "").strip()
    if env_root:
        candidatos.append(env_root)

    userprofile = os.environ.get("USERPROFILE") or ""
    if userprofile:
        candidatos.extend(
            [
                os.path.join(userprofile, "Meu Drive"),
                os.path.join(userprofile, "My Drive"),
                os.path.join(userprofile, "Google Drive"),
            ]
        )

    candidatos.extend(
        [
            r"G:\Meu Drive",
            r"G:\My Drive",
            r"G:\Google Drive",
        ]
    )

    saida: list[str] = []
    vistos = set()
    for item in candidatos:
        normalizado = os.path.normpath(str(item or "").strip())
        if not normalizado:
            continue
        chave = normalizado.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(normalizado)
    return saida


def _resolver_pasta_updates_google_drive() -> tuple[str, str]:
    for base in _caminhos_drive_base():
        nome_base = os.path.basename(base).lower()
        if nome_base == "updates":
            candidatos = [base]
        elif nome_base == "oficinadepesca":
            candidatos = [os.path.join(base, "Updates")]
        else:
            candidatos = [
                os.path.join(base, "OficinaDePesca", "Updates"),
                os.path.join(base, "Updates"),
            ]

        for candidato in candidatos:
            norm = os.path.normpath(candidato)
            if os.path.isdir(norm):
                return norm, "OK"

    return "", "Google Drive não encontrado. Conecte o Drive para concluir a distribuição automática local."


def copiar_artefatos_para_drive_local(*arquivos: str) -> tuple[bool, str, list[str]]:
    pasta_updates, msg = _resolver_pasta_updates_google_drive()
    if not pasta_updates:
        return False, msg, []

    copiados: list[str] = []
    for arquivo in arquivos:
        caminho = os.path.abspath(str(arquivo or "").strip())
        if not caminho or not os.path.isfile(caminho):
            continue
        destino = os.path.join(pasta_updates, os.path.basename(caminho))
        shutil.copy2(caminho, destino)
        copiados.append(destino)

    if not copiados:
        return False, "Nenhum artefato válido foi encontrado para copiar ao Google Drive.", []

    return True, pasta_updates, copiados

# ─── Token ────────────────────────────────────────────────────────────────────

def _obter_token() -> str:
    token = os.environ.get("GH_TOKEN", "").strip()
    if token:
        print("[token] Usando GH_TOKEN da variável de ambiente.")
        return token

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        print("[token] Usando GITHUB_TOKEN da variável de ambiente.")
        return token

    print("[ERRO] Token GitHub não encontrado.")
    print("Defina GH_TOKEN (ou GITHUB_TOKEN) antes de executar.")
    print("Exemplo PowerShell (sessão atual):")
    print("  $env:GH_TOKEN = 'seu_token_aqui'")
    print("Permissões necessárias: repo (full)")
    sys.exit(1)

# ─── Helpers de API ───────────────────────────────────────────────────────────

def _headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def _checar(resp: requests.Response, contexto: str):
    if resp.status_code not in (200, 201, 204):
        print(f"[ERRO] {contexto}: HTTP {resp.status_code}")
        try:
            print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
        except Exception:
            print(resp.text[:500])
        sys.exit(1)

# ─── Etapa 1: criar ou reutilizar a Release ───────────────────────────────────

def criar_ou_obter_release(token: str) -> dict:
    base = f"https://api.github.com/repos/{OWNER}/{REPO_RELEASE}"
    hdrs = _headers(token)

    # Tenta buscar release existente pela tag
    resp = requests.get(f"{base}/releases/tags/{TAG}", headers=hdrs, timeout=15)
    if resp.status_code == 200:
        release = resp.json()
        print(f"[ok] Release {TAG} já existe (id={release['id']}). Reutilizando.")
        return release

    # Cria nova release
    print(f"[...] Criando Release {TAG} em {OWNER}/{REPO_RELEASE}...")
    body = {
        "tag_name": TAG,
        "name": f"Oficina de Pesca {TAG}",
        "body": _ler_novidades(),
        "draft": False,
        "prerelease": False,
    }
    resp = requests.post(f"{base}/releases", headers=hdrs, json=body, timeout=15)
    _checar(resp, f"criar release {TAG}")
    release = resp.json()
    print(f"[ok] Release criada: {release['html_url']}")
    return release

# ─── Etapa 2: upload do .exe ──────────────────────────────────────────────────

def upload_asset(token: str, release: dict, asset_path: str, nome_asset: str | None = None) -> str:
    if not os.path.exists(asset_path):
        print(f"[ERRO] Asset não encontrado em: {asset_path}")
        sys.exit(1)

    nome_asset = nome_asset or os.path.basename(asset_path)
    tamanho = os.path.getsize(asset_path)
    print(f"[...] Enviando {nome_asset} ({tamanho / 1_048_576:.1f} MB)...")

    # Remove asset existente com o mesmo nome (evita conflito)
    ativos = release.get("assets", [])
    for asset in ativos:
        if asset["name"] == nome_asset:
            print(f"[...] Removendo asset anterior (id={asset['id']})...")
            resp = requests.delete(
                f"https://api.github.com/repos/{OWNER}/{REPO_RELEASE}/releases/assets/{asset['id']}",
                headers=_headers(token),
                timeout=15,
            )
            _checar(resp, "remover asset antigo")
            break

    upload_url = release["upload_url"].split("{")[0]  # remove template {?name,label}
    with open(asset_path, "rb") as f:
        conteudo = f.read()

    hdrs = _headers(token)
    hdrs["Content-Type"] = "application/octet-stream"
    resp = requests.post(
        upload_url,
        headers=hdrs,
        params={"name": nome_asset},
        data=conteudo,
        timeout=300,
    )
    _checar(resp, f"upload do asset {nome_asset}")
    url_download = resp.json()["browser_download_url"]
    print(f"[ok] Upload concluído: {url_download}")
    return url_download

# ─── Etapa 3: atualizar versao.txt no repositório de manifesto ───────────────

def atualizar_manifesto(token: str, url_download: str):
    base = f"https://api.github.com/repos/{OWNER}/{REPO_MANIFESTO}"
    hdrs = _headers(token)

    # Busca o SHA atual do arquivo
    resp = requests.get(
        f"{base}/contents/{CAMINHO_MANIFESTO}",
        headers=hdrs,
        params={"ref": BRANCH_MANIFESTO},
        timeout=15,
    )

    sha_atual = None
    if resp.status_code == 200:
        sha_atual = resp.json()["sha"]
        print(f"[ok] versao.txt encontrado (sha={sha_atual[:7]}...)")
    elif resp.status_code == 404:
        print("[...] versao.txt não existe ainda. Será criado.")
    else:
        _checar(resp, "buscar versao.txt")

    novidades = _ler_novidades()
    novo_conteudo = (
        f"versao={VERSAO}\n"
        f"novidades={novidades}\n"
        f"url_download={url_download}\n"
    )

    payload = {
        "message": f"chore: atualiza manifesto para {TAG}",
        "content": base64.b64encode(novo_conteudo.encode("utf-8")).decode("ascii"),
        "branch": BRANCH_MANIFESTO,
    }
    if sha_atual:
        payload["sha"] = sha_atual

    resp = requests.put(
        f"{base}/contents/{CAMINHO_MANIFESTO}",
        headers=hdrs,
        json=payload,
        timeout=15,
    )
    _checar(resp, "atualizar versao.txt")
    print(f"[ok] versao.txt atualizado no repositório {OWNER}/{REPO_MANIFESTO}")
    print()
    print("─── Conteúdo publicado ────────────────────────────────")
    print(novo_conteudo.rstrip())
    print("───────────────────────────────────────────────────────")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print(f"  DEPLOY AUTOMÁTICO — Oficina de Pesca {TAG}")
    print("=" * 55)
    print()

    token = _obter_token()

    # 1. Release
    release = criar_ou_obter_release(token)

    # 2. Upload do instalador principal
    exe_path, exe_name = _resolver_instalador()
    url_download = upload_asset(token, release, exe_path, exe_name)

    # 3. Upload do pacote portátil com core para atualização manual/nuvem
    pacote_core = _garantir_zip_portatil_com_core()
    url_zip_core = upload_asset(token, release, pacote_core, os.path.basename(pacote_core))

    # 4. Manifesto
    atualizar_manifesto(token, url_download)

    # 5. Cópia automática para a pasta sincronizada do Google Drive (Updates)
    ok_drive, msg_drive, arquivos_drive = copiar_artefatos_para_drive_local(exe_path, pacote_core)
    if ok_drive:
        print(f"[ok] Artefatos copiados para Google Drive local: {msg_drive}")
        for item in arquivos_drive:
            print(f"     - {item}")
    else:
        print(f"[aviso] {msg_drive}")

    print()
    print("✔  Deploy concluído com sucesso!")
    print(f"   Release:    {release['html_url']}")
    print(f"   Download:   {url_download}")
    print(f"   Pacote:     {url_zip_core}")
    print(f"   Manifesto:  https://raw.githubusercontent.com/{OWNER}/{REPO_MANIFESTO}/{BRANCH_MANIFESTO}/{CAMINHO_MANIFESTO}")
    print()

if __name__ == "__main__":
    main()
