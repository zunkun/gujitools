# -*- coding: utf-8 -*-
"""旧数据一次性迁移：SQLite（guji.db）与旧目录布局 → 纯文件 + 新目录布局。

旧布局：
- 数据根目录 guji.db（tasks / stage_runs / stage_settings / detect_boxes / image_meta 表）
- 任务目录：stages/extract/<pdf名>/images、stages/detect（旧 crop 切图）、
  previews/（PDF 预览缓存）、imported/（手动插入图片）、logs/、
  根下散落的 run-*.json / detect-config.json

迁移规则：
- SQLite 各表 → tasks.json / runs.json / boxes.json / sizes.json，完成后
  guji.db 改名为 guji.db.migrated 保留备份；
- stages/extract/<pdf名>/images/* 上移到 stages/extract/；
- stages/detect、previews、logs 删除（可重新生成或已无用）；
- imported/* 的图片移到 stages/extract/，pages.json 中对应路径同步改写；
- run-*.json / detect-config.json 移入 runs/ 子目录。
"""

from __future__ import annotations

import json  # 仅用于解析 SQLite 里的 TEXT 列，文件读写统一走 json_io
import shutil
import sqlite3
from pathlib import Path

from desktop.store.json_io import read_json, write_json

from desktop.store.runs import MAX_RUN_HISTORY
from desktop.utils.files import THUMBNAIL_EDGE

_TASK_FIELDS = (
    "id", "name", "source_path", "source_hash", "status",
    "created_at", "updated_at", "duplicate_confirmed",
)


def migrate_legacy(root: Path) -> None:
    """一次性迁移旧数据（SQLite + 旧目录布局）→ 纯文件新布局。

    存在 guji.db 时导出 tasks/runs/boxes/sizes 的 JSON 并改名
    guji.db.migrated 备份；uuid 任务目录重编号为 0001… 顺序号；
    旧嵌套 extract、散落配置等按本模块规则归位。迁移失败（sqlite3.Error）
    不抛异常，旧库保留、启动不阻塞。
    """
    db_path = root / "guji.db"
    if db_path.exists():
        try:
            _migrate_sqlite(root, db_path)
        except sqlite3.Error:
            pass  # 迁移失败不阻塞启动，旧库保留
    _renumber_uuid_tasks(root)
    for task_dir in (root / "tasks").glob("*"):
        if task_dir.is_dir():
            _migrate_task_dir(task_dir)


def _renumber_uuid_tasks(root: Path) -> None:
    """uuid 任务目录 → 顺序任务号：按创建时间排序，依次编号 0001、0002…"""
    tasks_path = root / "tasks.json"
    if not tasks_path.exists():
        return
    tasks = read_json(tasks_path, None)
    if not isinstance(tasks, list):
        return
    if all(str(t.get("id", "")).isdigit() for t in tasks):
        return  # 全部已是任务号

    tasks.sort(key=lambda t: t.get("created_at", 0))
    tasks_root = root / "tasks"
    used = set()
    for task in tasks:
        tid = str(task.get("id", ""))
        if tid.isdigit():
            used.add(int(tid))
    if tasks_root.exists():
        for entry in tasks_root.iterdir():
            if entry.is_dir() and entry.name.isdigit():
                used.add(int(entry.name))
    next_no = max(used, default=0) + 1

    changed = False
    for task in tasks:
        old_id = str(task.get("id", ""))
        if old_id.isdigit():
            continue
        new_id = f"{next_no:04d}"
        next_no += 1
        old_dir = tasks_root / old_id
        if old_dir.exists():
            old_dir.rename(tasks_root / new_id)
        task["id"] = new_id
        changed = True
    if changed:
        tasks.sort(key=lambda t: t.get("created_at", 0))
        write_json(tasks_path, tasks)


def _migrate_sqlite(root: Path, db_path: Path) -> None:
    if (root / "tasks.json").exists():
        return  # 已迁移过
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        tasks = [
            {field: row[field] for field in _TASK_FIELDS}
            for row in connection.execute("SELECT * FROM tasks")
        ]
        if not tasks:
            return
        write_json(root / "tasks.json", tasks)

        # stage_runs：每个 (task, stage) 保留完整历史，最新在前
        history: dict[tuple[str, str], list] = {}
        for row in connection.execute("SELECT * FROM stage_runs ORDER BY started_at DESC"):
            record = {
                "run_id": row["id"],
                "status": row["status"],
                "parameters": json.loads(row["parameters_json"] or "{}"),
                "done": row["progress_done"],
                "total": row["progress_total"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "output_path": row["output_path"],
            }
            history.setdefault((row["task_id"], row["stage"]), []).append(record)
        for (task_id, stage), records in history.items():
            _merge_json(
                root / "tasks" / task_id / "runs.json", stage, records[:MAX_RUN_HISTORY]
            )

        # detect_boxes → boxes.json
        for row in connection.execute("SELECT * FROM detect_boxes"):
            _merge_json(
                root / "tasks" / row["task_id"] / "boxes.json",
                row["image_key"],
                {
                    "boxes": json.loads(row["boxes_json"]),
                    "origin": row["origin"],
                    "updated_at": row["updated_at"],
                },
            )

        # image_meta → sizes.json
        for row in connection.execute("SELECT * FROM image_meta"):
            _merge_json(
                root / "tasks" / row["task_id"] / "sizes.json",
                row["image_key"],
                [row["width"], row["height"]],
            )
    finally:
        connection.close()
    db_path.rename(root / "guji.db.migrated")


def _merge_json(path: Path, key: str, value) -> None:
    if not path.parent.exists():
        return  # 任务目录已删除，跳过
    data = read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    data[key] = value
    write_json(path, data)


def _migrate_task_dir(task_dir: Path) -> None:
    # extract 旧嵌套布局：<pdf名>/images/* 上移
    extract_dir = task_dir / "stages" / "extract"
    if extract_dir.is_dir():
        for child in list(extract_dir.iterdir()):
            images = child / "images" if child.is_dir() else None
            if images is not None and images.is_dir():
                for img in images.iterdir():
                    shutil.move(str(img), str(extract_dir / img.name))
                shutil.rmtree(child, ignore_errors=True)

    # detect 旧切图、previews 缓存、logs：删除
    for name in ("detect",):
        old = task_dir / "stages" / name
        if old.is_dir():
            shutil.rmtree(old, ignore_errors=True)
    for name in ("previews", "logs"):
        old = task_dir / name
        if old.is_dir():
            shutil.rmtree(old, ignore_errors=True)

    # imported/* → stages/extract/，pages.json 路径同步改写
    imported = task_dir / "imported"
    if imported.is_dir():
        extract_dir.mkdir(parents=True, exist_ok=True)
        for img in list(imported.iterdir()):
            shutil.move(str(img), str(extract_dir / img.name))
        imported.rmdir()
        pages_path = task_dir / "pages.json"
        if pages_path.exists():
            pages = read_json(pages_path, [])
            if not isinstance(pages, list):
                pages = []
            changed = False
            for entry in pages:
                file_path = entry.get("file", "")
                if "imported" in file_path:
                    entry["file"] = file_path.replace(
                        str(imported), str(extract_dir)
                    )
                    changed = True
            if changed:
                write_json(pages_path, pages)

    # 散落的运行配置 → runs/
    runs_dir = task_dir / "runs"
    for config in list(task_dir.glob("run-*.json")) + list(
        task_dir.glob("detect-config.json")
    ):
        runs_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(config), str(runs_dir / config.name))

    # 缩略图清理：仅当分辨率标记缺失/不匹配时清理（旧版 96px 等低分辨率
    # 或旧命名文件会导致预览模糊/命不中），清理后由预览打开时自动重建
    thumbnails = task_dir / "thumbnails"
    if thumbnails.is_dir():
        for child in thumbnails.iterdir():
            if child.is_file():
                child.unlink()  # 旧版直接散落在 thumbnails/ 下的 jpg
            elif child.name in ("source", "print"):
                meta = child / ".meta"
                if not meta.exists() or meta.read_text(encoding="utf-8").strip() != str(
                    THUMBNAIL_EDGE
                ):
                    for img in child.glob("*.jpg"):
                        img.unlink()
                    meta.write_text(str(THUMBNAIL_EDGE), encoding="utf-8")
