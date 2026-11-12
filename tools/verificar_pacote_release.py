"""Inspeção local de artefatos, sem exibir conteúdo sensível."""
import hashlib
import os
import re
import zipfile
from pathlib import Path, PurePosixPath

_NOME = re.compile(
    r"^(?:client_secret.*|token\.json|google_drive_user_token\.json|"
    r"credentials\.json|\.env|.*\.(?:key|p12|pfx))$", re.I,
)
_SEGREDO = re.compile(
    rb"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----\s*(?:[A-Za-z0-9+/=]{20,}\s*){3,}"
    rb"-----END (?:[A-Z]+ )?PRIVATE KEY-----|"
    rb"GOCSPX-[A-Za-z0-9_-]{20,}|ya29\.[A-Za-z0-9_-]{20,}|"
    rb"1//[A-Za-z0-9_-]{20,}|(?<![A-Za-z0-9])AKIA[A-Z0-9]{16}(?![A-Za-z0-9])",
)


def _verificar_nome(nome):
    if _NOME.fullmatch(Path(nome.replace("\\", "/")).name):
        raise RuntimeError(f"Arquivo de credencial no pacote: {nome}")


def _verificar_bytes(dados, origem):
    if _SEGREDO.search(dados):
        raise RuntimeError(f"Padrão de credencial no pacote: {origem}")


def verificar_executavel(caminho):
    from PyInstaller.archive.readers import CArchiveReader

    caminho = Path(caminho)
    arquivo = CArchiveReader(str(caminho))
    for nome, entrada in arquivo.toc.items():
        tipo = entrada[-1]
        if tipo not in {"m", "M", "s", "z"}:
            _verificar_nome(nome)
        if tipo == "z":
            pyz = arquivo.open_embedded_archive(nome)
            for modulo in pyz.toc:
                origem = f"{caminho.name}:{modulo}"
                dados = pyz.extract(modulo, raw=True)
                if dados is None:
                    continue
                _verificar_bytes(dados, origem)
                if pyz.toc[modulo][0] not in (0, 1):
                    _verificar_nome(modulo)
        else:
            _verificar_bytes(arquivo.extract(nome), f"{caminho.name}:{nome}")


def verificar_diretorio(raiz):
    import mestre_build

    raiz = Path(raiz)
    problemas = mestre_build._arquivos_sensiveis_assets(str(raiz))
    if problemas:
        raise RuntimeError("Arquivos sensíveis no pacote: " + ", ".join(problemas))
    for pasta, _, arquivos in os.walk(raiz, onerror=lambda erro: (_ for _ in ()).throw(erro)):
        for nome in arquivos:
            caminho = Path(pasta) / nome
            _verificar_nome(str(caminho.relative_to(raiz)))
            with caminho.open("rb") as arquivo:
                anterior = b""
                for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
                    _verificar_bytes(anterior + bloco, str(caminho.relative_to(raiz)))
                    anterior = bloco[-4096:]
    for nome in ("Oficina_Pesca.exe", "Atualizador.exe"):
        verificar_executavel(raiz / nome)


def verificar_zip(zip_path, raiz):
    raiz = Path(raiz)
    vistos = set()
    with zipfile.ZipFile(zip_path) as arquivo:
        for item in arquivo.infolist():
            if item.is_dir():
                continue
            caminho = PurePosixPath(item.filename)
            if (caminho.is_absolute() or ".." in caminho.parts or "\\" in item.filename
                    or ":" in item.filename or item.filename in vistos):
                raise RuntimeError(f"Entrada ZIP inválida ou duplicada: {item.filename}")
            vistos.add(item.filename)
            _verificar_nome(item.filename)
            local = raiz.joinpath(*caminho.parts)
            if not local.is_file():
                raise RuntimeError(f"Entrada ZIP não corresponde ao stage: {item.filename}")
            hash_zip = hashlib.sha256()
            hash_local = hashlib.sha256()
            with arquivo.open(item) as origem, local.open("rb") as destino:
                for bloco in iter(lambda: origem.read(1024 * 1024), b""):
                    hash_zip.update(bloco)
                for bloco in iter(lambda: destino.read(1024 * 1024), b""):
                    hash_local.update(bloco)
            if hash_zip.digest() != hash_local.digest():
                raise RuntimeError(f"Entrada ZIP divergente: {item.filename}")
    esperados = {p.relative_to(raiz).as_posix() for p in raiz.rglob("*") if p.is_file()}
    if vistos != esperados:
        raise RuntimeError("Conteúdo do ZIP não corresponde integralmente ao stage.")
