# -*- coding: utf-8 -*-
"""文档目录结构与 `guji help` 依赖的自测。

背景（用户明确要求的两条约束）：

1. **文档按读者分流**：`docs/guide/` 给使用者、`docs/dev/` 给开发者、
   `docs/functions/` 是命令手册。三类混在一起时，使用者会误入架构文档。
2. **`guji help` 不能因为挪文档而失效**：`utils/help.py` 在**运行时**
   读取 `docs/functions/<命令>.md`，且 `guji.spec` 把该目录打进安装包。
   这个依赖是隐式的——挪了目录、代码不报错，只有打包后执行 `guji help`
   才会暴露（退化为「No help available」）。

本模块把「目录该在哪」和「help 依赖还成立」都钉住。
"""

NAME = "docs_layout"
DEPENDS: list[str] = []
TITLE = "文档结构与 help 依赖"


# `utils/help.py` 的 _DOC_MAP：命令名 → 文件名。
# ⚠️ 与 utils/help.py 同步：那边加命令，这里要加条目。
_HELP_TOPICS = (
    "extract", "detect", "crop", "rembg", "cropremove", "print", "overview",
)


def run(ctx) -> None:
    from pathlib import Path

    from tests.selftests._context import ok

    root = Path(__file__).resolve().parents[2]
    docs = root / "docs"

    # ---- 1. 三类目录必须存在且各司其职 ----
    ok("docs/guide/ 存在（使用者文档）", (docs / "guide").is_dir(),
       str(docs / "guide"))
    ok("docs/dev/ 存在（开发者文档）", (docs / "dev").is_dir(),
       str(docs / "dev"))
    ok("docs/functions/ 存在（help 依赖）", (docs / "functions").is_dir(),
       str(docs / "functions"))

    # 操作指南与命令行说明属于「给使用者」
    ok("操作指南在 docs/guide/ 下",
       (docs / "guide" / "gui-guide.md").exists(),
       "gui-guide.md 不在 guide/")
    ok("命令行说明在 docs/guide/ 下",
       (docs / "guide" / "cli.md").exists(),
       "cli.md 不在 guide/")

    # 旧的 docs/gui/ 不应再存在（否则说明迁移没做干净）
    ok("旧的 docs/gui/ 已清理",
       not (docs / "gui").exists(),
       "docs/gui/ 仍存在，迁移不完整")

    # ---- 2. 技术细节必须落在 docs/dev/，不得混进 guide/ ----
    dev_gui = docs / "dev" / "gui"
    tech_docs = [
        "gui-architecture.md", "gui-technical-spec.md", "gui-design.md",
        "gui-layout.md", "gui-requirements.md", "gui-ui-system.md",
    ]
    missing = [d for d in tech_docs if not (dev_gui / d).exists()]
    ok("桌面端 6 份技术文档都在 docs/dev/gui/", not missing, f"缺失={missing}")

    # ⚠️ 关键：技术细节不得出现在 docs/guide/ 下（使用者会误入）
    guide_only = {
        "gui-guide.md", "cli.md", "readme.md", "screenshots",
    }
    guide_root = docs / "guide"
    leaked = sorted(
        p.name for p in guide_root.iterdir()
        if p.name not in guide_only and not p.name.startswith(".")
    )
    ok("docs/guide/ 下没有混入技术文档", not leaked, f"混入={leaked}")

    # ---- 3. ⚠️ guji help 的运行时依赖 ----
    # utils/help.py 读 docs/functions/<cmd>.md；少一个就静默退化成
    # 「No help available」，用户只会觉得 help 没内容，不会报路径错。
    missing_topics = [
        t for t in _HELP_TOPICS if not (docs / "functions" / f"{t}.md").exists()
    ]
    ok("guji help 的每个主题都有手册文件", not missing_topics,
       f"缺失={missing_topics}")

    # help 系统硬编码的路径常量（utils/help.py）必须仍指向有效目录
    help_py = root / "utils" / "help.py"
    ok("utils/help.py 存在", help_py.exists(), str(help_py))
    if help_py.exists():
        src = help_py.read_text(encoding="utf-8")
        ok("utils/help.py 仍指向 docs/functions",
           '"docs" / "functions"' in src or '"docs", "functions"' in src,
           "help.py 的目录常量变了，请同步 docs/functions 与 guji.spec")
        # _DOC_MAP 里的每个值都必须真实存在。
        # 正则拿到的是 `docs/functions` 下的**文件名**，拼接后再校验存在性。
        import re

        mapped = set(re.findall(r'"(\w+\.md)"', src))
        bad = sorted(m for m in mapped if not (docs / "functions" / m).exists())
        ok("help.py 的 _DOC_MAP 每个文件都存在", not bad, f"失效={bad}")
        ok("help.py 的 _DOC_MAP 覆盖全部命令",
           {t + ".md" for t in _HELP_TOPICS} <= mapped,
           f"_DOC_MAP={sorted(mapped)}，缺少主题")

    # ---- 4. 打包配置必须包含 docs/functions ----
    spec = root / "guji.spec"
    ok("guji.spec 存在", spec.exists(), str(spec))
    if spec.exists():
        spec_text = spec.read_text(encoding="utf-8")
        ok("guji.spec 打包了 docs/functions",
           "docs/functions" in spec_text,
           "打包清单缺 docs/functions，打包后 guji help 会失效")

    # ---- 5. 三份索引文档都要能找到指南 ----
    for index in ("README.md", "docs/README.md"):
        text = (root / index).read_text(encoding="utf-8")
        ok(f"{index} 索引了操作指南", "gui-guide.md" in text,
           f"{index} 未收录，用户会找不到")

    # ---- 6. 真跑一遍 help 加载（行为断言，不只是文件存在）----
    # 上面查的是「文件在不在」；这里直接调 utils.help.get_help_text()，
    # 确保真能取到内容而不是退化成「No help available」。
    # 这是唯一能在**打包前**发现 help 路径失效的检查。
    try:
        from utils.help import get_help_text
    except ImportError as exc:
        ok("可导入 utils.help", False, f"{exc!r}")
        return

    fallback = [t for t in _HELP_TOPICS if "No help available" in get_help_text(t)]
    ok("每个命令的 help 都能取到内容（未退化）", not fallback,
       f"退化的主题={fallback}")

    overview = get_help_text(None)
    ok("help 总览能取到内容",
       "No help available" not in overview and len(overview) > 50,
       f"长度={len(overview)}")
