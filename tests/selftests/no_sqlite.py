# -*- coding: utf-8 -*-
"""存储无数据库守卫：确认存储层不依赖 sqlite3，也没有旧数据迁移残留。

背景：desktop/store/migrate.py 曾用于把早期 SQLite 版 guji.db 迁移到纯 JSON
文件，其顶层 `import sqlite3` 让 PyInstaller 把 sqlite3.dll 当成必需依赖打进
安装包（1.6MB）。存储一直是纯 JSON，迁移代码已整体删除，本模块防止其回归。

守卫分三层：
1. 源码层：desktop/ 与 cli/ 下不出现 sqlite3 导入；
2. 模块层：desktop.store 不再导出 migrate_legacy（旧的一次性迁移入口）；
3. 行为层：构造 TaskStore 不创建任何 .db 文件，也不触发 sqlite3 导入。
"""

NAME = "no_sqlite"
DEPENDS: list[str] = []
TITLE = "存储无数据库"


def run(ctx) -> None:
    import re
    import subprocess
    import sys
    from pathlib import Path

    from tests.selftests._context import ok

    project_root = Path(__file__).resolve().parents[2]

    # ---- 1. 源码层：业务代码不得 import sqlite3 ----
    offenders = []
    for rel in ("desktop", "cli", "functions", "utils"):
        base = project_root / rel
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            text = py.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(r"^\s*(import\s+sqlite3\b|from\s+sqlite3\b)", line):
                    offenders.append(f"{py.relative_to(project_root).as_posix()}:{i}")
    ok("业务代码不 import sqlite3", not offenders, "; ".join(offenders[:5]))

    # ---- 2. 模块层：不再有旧数据迁移入口 ----
    has_migrate = (project_root / "desktop" / "store" / "migrate.py").exists()
    ok("旧数据迁移模块已移除", not has_migrate)

    import desktop.store as store_pkg

    ok("store 不再导出 migrate_legacy",
       not hasattr(store_pkg, "migrate_legacy"))

    # ---- 3. 行为层：构造 TaskStore 不引入 sqlite3、不产生 .db ----
    probe = (
        "import sys; "
        "from pathlib import Path; "
        "import tempfile; "
        "from desktop.store.store import TaskStore; "
        "root = Path(tempfile.mkdtemp(prefix='guji_nodb_')); "
        "store = TaskStore(root); "
        "store.list_tasks(); "
        "dbs = sorted(p.name for p in root.rglob('*.db')); "
        "print('SQLITE_LOADED', 'sqlite3' in sys.modules); "
        "print('DB_FILES', dbs); "
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = proc.stdout or ""
    ok("构造 TaskStore 可正常退出", proc.returncode == 0,
       (proc.stderr or "")[-300:])

    loaded = "SQLITE_LOADED True" in out
    ok("构造 TaskStore 不触发 sqlite3 导入", not loaded, out[-200:])

    m = re.search(r"DB_FILES \[(.*?)\]", out)
    db_files = [x.strip().strip("'") for x in (m.group(1).split(",") if m else []) if x.strip()]
    ok("数据根目录不产生任何 .db 文件", not db_files, str(db_files))
