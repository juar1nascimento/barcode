"""Reconciliação não destrutiva do espelhamento local do Inventário GTI SESA.

Compara o estado esperado no PostgreSQL com os artefatos locais.
Nunca exclui nem altera arquivos de inventário.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import openpyxl
import psycopg
from psycopg.rows import dict_row

DEFAULT_ROOT = r"\\172.17.27.246\t.i\02 - SUPORTE\BACKUP\Inventário gti-sesa"
TIMEOUT = int(os.getenv("INVENTARIO_MIRROR_DB_TIMEOUT", "15"))


def db_connection():
    url = os.getenv("DATABASE_URL")
    if url:
        return psycopg.connect(url, connect_timeout=TIMEOUT, row_factory=dict_row)
    required = ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("Configuração PostgreSQL ausente: " + ", ".join(missing))
    return psycopg.connect(
        host=os.environ["PGHOST"],
        port=os.getenv("PGPORT", "5432"),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode=os.getenv("PGSSLMODE", "require"),
        connect_timeout=TIMEOUT,
        row_factory=dict_row,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def load_json(path: Path) -> Any:
    if not path.is_file():
        raise RuntimeError(f"Arquivo ausente: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def db_snapshot(conn) -> tuple[list[dict], list[dict]]:
    with conn.cursor() as cur:
        cur.execute(
            """select p.id, p.numero_patrimonio, p.ativo,
                      coalesce(s.nome,'') as setor, coalesce(p.tipo,'') as tipo,
                      coalesce(p.fabricante,'') as fabricante,
                      p.data_cadastro, u.nome as unidade
                 from public.patrimonios p
                 join public.unidades u on u.id=p.unidade_id
                 left join public.setores s on s.id=p.setor_id
                order by u.nome, s.nome, p.id"""
        )
        patrimonios = cur.fetchall()

        cur.execute(
            """select f.id, f.patrimonio_id, f.ordem, f.storage_bucket,
                      f.storage_path, f.arquivo_nome, f.sha256,
                      p.numero_patrimonio
                 from public.patrimonio_fotos f
                 join public.patrimonios p on p.id=f.patrimonio_id
                order by p.numero_patrimonio, f.ordem, f.id"""
        )
        fotos = cur.fetchall()
    return patrimonios, fotos


def validate(root: Path) -> dict[str, Any]:
    result = {
        "status": "ok",
        "erros": [],
        "avisos": [],
        "patrimonios_banco": 0,
        "patrimonios_json": 0,
        "patrimonios_xlsx": 0,
        "fotos_banco": 0,
        "fotos_validas": 0,
        "fotos_divergentes": 0,
        "arquivos_orfaos": 0,
    }

    required = (
        root / "dados" / "inventario_site.xlsx",
        root / "dados" / "inventario_completo.json",
        root / "manifest" / "checksums.json",
        root / "manifest" / "estado.json",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        result["erros"].extend("Artefato ausente: " + path for path in missing)
        result["status"] = "divergente"
        return result

    archive = load_json(required[1])
    checksums = load_json(required[2])
    manifest = load_json(required[3])

    with db_connection() as conn:
        patrimonios, fotos = db_snapshot(conn)

    result["patrimonios_banco"] = len(patrimonios)
    result["patrimonios_json"] = len(archive.get("patrimonios", []))
    result["fotos_banco"] = len(fotos)

    if manifest.get("status") != "ok":
        result["avisos"].append("estado.json não está com status=ok.")

    if len(archive.get("patrimonios", [])) != len(patrimonios):
        result["erros"].append("Quantidade de patrimônios no JSON difere do PostgreSQL.")

    workbook = openpyxl.load_workbook(required[0], read_only=True, data_only=True)
    workbook_rows = 0
    try:
        for sheet in workbook.worksheets:
            first = True
            for row in sheet.iter_rows(values_only=True):
                if first:
                    first = False
                    continue
                if any(value not in (None, "") for value in row):
                    workbook_rows += 1
    finally:
        workbook.close()

    expected_active = sum(1 for row in patrimonios if bool(row["ativo"]))
    result["patrimonios_xlsx"] = workbook_rows
    if workbook_rows != expected_active:
        result["erros"].append(
            f"Quantidade de patrimônios ativos no XLSX ({workbook_rows}) "
            f"difere do PostgreSQL ({expected_active})."
        )

    expected_paths: set[str] = set()
    for foto in fotos:
        expected = str(foto["sha256"] or "").lower()
        patrimonio = str(foto["numero_patrimonio"])
        filename = Path(str(foto["arquivo_nome"] or f"foto_{foto['id']}.jpg")).name
        relative = Path("fotos") / "patrimonio" / patrimonio / f"{int(foto['ordem']):02d}_{filename}"
        relative_key = str(relative).replace("\\", "/")
        expected_paths.add(relative_key)
        path = root / relative
        if not path.is_file():
            result["fotos_divergentes"] += 1
            result["erros"].append(f"Foto ausente: {relative_key}")
            continue
        if expected and sha256(path) != expected:
            result["fotos_divergentes"] += 1
            result["erros"].append(f"SHA-256 divergente: {relative_key}")
            continue
        result["fotos_validas"] += 1

    local_files: set[str] = set()
    photo_root = root / "fotos" / "patrimonio"
    if photo_root.exists():
        for path in photo_root.rglob("*"):
            if path.is_file():
                local_files.add(str(path.relative_to(root)).replace("\\", "/"))

    orphaned = sorted(local_files - expected_paths)
    result["arquivos_orfaos"] = len(orphaned)
    if orphaned:
        result["avisos"].append(
            f"{len(orphaned)} arquivo(s) local(is) não estão registrados no PostgreSQL. "
            "Nenhum foi excluído."
        )

    if result["erros"]:
        result["status"] = "divergente"

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=os.getenv("INVENTARIO_MIRROR_ROOT", DEFAULT_ROOT))
    args = parser.parse_args()

    try:
        result = validate(Path(args.root))
    except Exception as exc:
        print(json.dumps({"status": "erro", "erros": [str(exc)]}, ensure_ascii=False))
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
