"""Worker de sincronização PostgreSQL -> Google Sheets para CI.

Executa somente a fila idempotente existente no backend. Segredos são
fornecidos exclusivamente por variáveis de ambiente/Secrets do CI.
"""
from sincronizador_google_sheets import processar_fila_google_sheets

if __name__ == "__main__":
    resultado = processar_fila_google_sheets(limit=25)
    print(
        "sync:",
        f"processados={resultado['processados']}",
        f"sucesso={resultado['sucesso']}",
        f"falhas={resultado['falhas']}",
    )
    if resultado["falhas"] > 0:
        raise SystemExit(2)
