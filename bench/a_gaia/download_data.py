"""GAIA 数据集下载：validation 165 题 + 附件（一次性脚本）。

用法：
    python -m bench.a_gaia.download_data [--split validation]

输出：
    bench/data/gaia/gaia_validation.jsonl   每题 {task_id, question, level, file_path, tools_hint, has_file}
    bench/data/gaia/attachments/            附件（按 task_id 命名）
    bench/data/gaia/metadata_full.jsonl    原始 metadata（含 final_answer，评分阶段单独持有）

网络：走 127.0.0.1:7897 代理；失败备选 HF_ENDPOINT=https://hf-mirror.com。
依赖：pip install huggingface_hub pyarrow（conda env poirot）。
认证：GAIA 是 gated 数据集，.env 需有 HF_TOKEN（先在 HF 页面同意条款）。

数据集结构（2024 年版）：
    gaia-benchmark/GAIA → 2023/validation/metadata.parquet + 附件文件
    parquet 列：task_id, Question, Level, Final answer, file_name, file_path, Annotator Metadata
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from bench.common.env import PROJECT_ROOT, ensure_project_root, load_env, setup_proxy

REPO_ID = "gaia-benchmark/GAIA"
SPLIT = "validation"
# HF repo 实际路径前缀（2023 年版）
_YEAR_PREFIX = "2023"


def _get_hf_token() -> str | None:
    """从 env 取 HF token（支持 HF_TOKEN / HUGGING_FACE_HUB_TOKEN）。"""
    return os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or None


def _download_metadata(split: str, proxy: bool = True) -> list[dict]:
    """下载 parquet metadata 并转为 dict list。"""
    from huggingface_hub import hf_hub_download

    filename = f"{_YEAR_PREFIX}/{split}/metadata.parquet"
    if proxy:
        setup_proxy()
    token = _get_hf_token()
    try:
        local = hf_hub_download(
            repo_id=REPO_ID, filename=filename, repo_type="dataset", token=token,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] metadata 下载失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return []

    import pyarrow.parquet as pq

    table = pq.read_table(local)
    rows = []
    for i in range(table.num_rows):
        row = {}
        for col in table.column_names:
            val = table.column(col)[i].as_py()
            row[col] = val
        # 统一列名 → 小写 snake_case（parquet 原列名是 Title Case）
        rows.append({
            "task_id": row.get("task_id", ""),
            "question": row.get("Question", ""),
            "level": row.get("Level"),
            "final_answer": row.get("Final answer", ""),
            "file_name": row.get("file_name", ""),
            "file_path": row.get("file_path", ""),
            "annotator_metadata": row.get("Annotator Metadata", ""),
        })
    return rows


def _download_attachment(file_name: str, split: str, attachments_dir: Path, task_id: str) -> bool:
    """下载单个附件。file_name 是文件名（不含目录），实际 repo 路径 = 2023/{split}/{file_name}。"""
    from huggingface_hub import hf_hub_download

    token = _get_hf_token()
    candidates = [
        f"{_YEAR_PREFIX}/{split}/{file_name}",
        f"{split}/{file_name}",
        file_name,
    ]
    last_exc: Exception | None = None
    for candidate in candidates:
        try:
            local = hf_hub_download(
                repo_id=REPO_ID, filename=candidate, repo_type="dataset", token=token,
            )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue
        # 以 task_id 重命名避免跨题冲突
        suffix = Path(local).suffix
        target = attachments_dir / f"{task_id}{suffix}"
        target.write_bytes(Path(local).read_bytes())
        return True
    if last_exc is not None:
        print(f"  [warn] 附件下载失败 {task_id} {file_name}: {last_exc}", file=sys.stderr)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="GAIA validation 数据集下载")
    parser.add_argument("--split", default=SPLIT)
    parser.add_argument("--skip-attachments", action="store_true", help="跳过附件下载（调试用）")
    args = parser.parse_args()

    ensure_project_root()
    load_env()

    if not _get_hf_token():
        print("[error] .env 缺 HF_TOKEN（GAIA 是 gated 数据集，需先在 HF 页面同意条款）", file=sys.stderr)
        sys.exit(1)

    out_dir = PROJECT_ROOT / "bench" / "data" / "gaia"
    attachments_dir = out_dir / "attachments"
    out_dir.mkdir(parents=True, exist_ok=True)
    attachments_dir.mkdir(parents=True, exist_ok=True)

    rows = _download_metadata(args.split)
    if not rows:
        # 备选：镜像端点
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        print("[info] 直连下载失败，改用 hf-mirror.com 镜像重试", file=sys.stderr)
        rows = _download_metadata(args.split, proxy=False)
    if not rows:
        print("[error] GAIA metadata 下载失败（检查代理 / HF 可达性 / HF_TOKEN）", file=sys.stderr)
        sys.exit(1)

    print(f"[info] metadata 共 {len(rows)} 题")

    n_file = 0
    with (out_dir / "gaia_validation.jsonl").open("w", encoding="utf-8") as fw:
        for row in rows:
            task_id = row["task_id"]
            file_name = row.get("file_name") or ""
            has_file = bool(file_name)
            if has_file and not args.skip_attachments:
                ok = _download_attachment(file_name, args.split, attachments_dir, task_id)
                if not ok:
                    has_file = False
                    print(f"  [warn] {task_id} 附件缺失，按无附件处理")
            if has_file:
                n_file += 1
            fw.write(json.dumps({
                "task_id": task_id,
                "question": row["question"],
                "level": row.get("level"),
                "file_name": file_name,
                "has_file": has_file,
            }, ensure_ascii=False) + "\n")

    # 原始 metadata（含 final_answer）单独持有，不写入工作文件
    with (out_dir / "metadata_full.jsonl").open("w", encoding="utf-8") as fw:
        for row in rows:
            fw.write(json.dumps(row, ensure_ascii=False) + "\n")

    levels: dict = {}
    for row in rows:
        levels[row.get("level")] = levels.get(row.get("level"), 0) + 1
    print(f"[done] gaia_validation.jsonl 写盘完成：{len(rows)} 题，level 分布 {levels}，附件题 {n_file}")


if __name__ == "__main__":
    main()
