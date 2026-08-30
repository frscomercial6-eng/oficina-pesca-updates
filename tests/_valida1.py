import sys
sys.path.insert(0, r"f:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL")
try:
    from core.gestao_os_repository import listar_orcamentos_para_gestao as f
    rows = f()
    print("RUNTIME_OK rows=%d cols=%s" % (len(rows), len(rows[0]) if rows else "-"))
    if rows:
        print("PRIMEIRA_ROW[0..4]=", rows[0][:5])
except Exception as e:
    print("RUNTIME_ERRO", type(e).__name__, e)