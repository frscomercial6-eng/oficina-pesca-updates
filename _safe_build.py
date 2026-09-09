#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build seguro v1.0.64 -绕过 o crash do PyInstaller 6.22.2 no ambiente com .venv dentro do repo.
Estratégia: usar o spec file existente (cache de análise) + restaurar bytecode antes do build.
"""
import subprocess, sys, os, shutil, time

BASE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(BASE, ".venv", "Scripts", "python.exe")
SPEC = os.path.join(BASE, "Oficina_Pesca.spec")
LOG = os.path.join(BASE, "build_safe.log")
BUILD_LOG = os.path.join(BASE, "build_safe_pyi.log")

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(cmd, timeout=None):
    log(f"CMD: {' '.join(cmd[:5])}...")
    log(f"  CWD: {os.getcwd()}")
    with open(BUILD_LOG, "w", encoding="utf-8") as bl:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=BASE)
    with open(BUILD_LOG, "r", encoding="utf-8") as bl:
        content = bl.read()
    lines = content.split("\n")
    log(f"  Exit: {result.returncode}")
    if lines:
        log(f"  Last: {lines[-2] if len(lines)>1 else lines[-1]}")
    return result

def restaurar_bytecode_venv():
    """Recompila bytecode dos módulos .venv para garantir que não estão corrompidos."""
    venv_lib = os.path.join(BASE, ".venv", "Lib", "site-packages")
    if not os.path.exists(venv_lib):
        log("  __pycache__ restore: venv not found, skip")
        return
    count = 0
    for raiz, dirs, arquivos in os.walk(venv_lib):
        for arq in arquivos:
            if arq.endswith(".py"):
                py_path = os.path.join(raiz, arq)
                pyc_dir = os.path.join(raiz, "__pycache__")
                os.makedirs(pyc_dir, exist_ok=True)
                try:
                    subprocess.run([VENV_PY, "-m", "py_compile", py_path],
                                   capture_output=True, timeout=10, cwd=BASE)
                    count += 1
                except Exception:
                    pass
    log(f"  __pycache__ restore: recompiled {count} modules")

def main():
    log("=" * 60)
    log("SAFE BUILD v1.0.64")
    log("=" * 60)

    if not os.path.exists(SPEC):
        log(f"ERRO: spec file nao encontrado: {SPEC}")
        return 1

    if not os.path.exists(VENV_PY):
        log(f"ERRO: python nao encontrado: {VENV_PY}")
        return 1

    log("Fase 1: Restaurar bytecode do venv...")
    restaurar_bytecode_venv()

    log("Fase 2: Verificar Analysis cache...")
    cache_toc = os.path.join(BASE, "build", "Oficina_Pesca", "Analysis-00.toc")
    if os.path.exists(cache_toc):
        log(f"  Cache encontrado: {cache_toc}")
    else:
        log("  AVISO: Cache nao encontrado (Analysis sera refeita)")

    log("Fase 3: Executar PyInstaller via spec...")
    cmd = [VENV_PY, "-m", "PyInstaller", SPEC, "--noconfirm"]
    log(f"  Executando: {' '.join(cmd)}")

    # Timeout de 2 horas
    timeout = 7200
    t_start = time.time()

    with open(BUILD_LOG, "w", encoding="utf-8") as bl:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, cwd=BASE, bufsize=1)
        for line in proc.stdout:
            bl.write(line)
            bl.flush()
        proc.wait()

    elapsed = time.time() - t_start
    exit_code = proc.returncode

    # Ler resultado
    with open(BUILD_LOG, "r", encoding="utf-8") as bl:
        content = bl.read()

    log(f"  PyInstaller exit: {exit_code}")
    log(f"  Tempo: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    last_lines = [l for l in content.split("\n") if l.strip()][-5:]
    for l in last_lines:
        log(f"  LAST: {l[:120]}")

    dist_exe = os.path.join(BASE, "dist", "Oficina_Pesca", "Oficina_Pesca.exe")
    if os.path.exists(dist_exe):
        mb = os.path.getsize(dist_exe) // 1024 // 1024
        log(f"SUCCESS: EXE gerado! {mb}MB")
        return 0
    else:
        log("FALHA: EXE nao encontrado")
        return 1

if __name__ == "__main__":
    sys.exit(main())
