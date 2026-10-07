# -*- coding: utf-8 -*-
"""自测共享设施：断言计数、样例文件、夹具构建、单模块看门狗。

原先 gui_selftest 是 800+ 行单文件，每次都要整体读取、整体执行；现按
功能拆到本包的一组小模块。模块之间不直接互相引用，只通过 ``Context``
取共享夹具（QApplication/主窗口/任务仓库/样例 PDF）与传递跨模块状态
（主任务 id、插入图路径、注入的检测框等）。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 测试临时文件统一落点（见 tests/tmpdir.py）：本模块被运行器与**每个**用例
# 模块导入，在这里装一次即可覆盖整轮自测（含 worker 子进程）。
# ⚠️ 必须早于任何 tempfile 调用——gettempdir() 算过就缓存，晚了不生效。
from tests.tmpdir import install as _install_tmpdir  # noqa: E402

_install_tmpdir()

PASS = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    """断言并计数：失败抛 AssertionError（携带细节），成功打印 PASS。"""
    global PASS
    if not condition:
        raise AssertionError(f"[FAIL] {name} {detail}")
    PASS += 1
    print(f"  [PASS] {name}")


def silence_source_prompt(page) -> list:
    """关掉详情页的「缺源 PDF」提示层，返回"提示层可见过"的记录列表。

    ⚠️ 那层提示**非模态**（`MissingSourcePrompt`，2026-10-06 从 MessageBox
    换掉），所以离屏自测**可以直接显示它、不用挂住**——只有它上面那个
    「现在选择」按钮会去开模态文件对话框。所以这个助手做两件事：

    1. 把 ``picked`` 接到一个空实现：**点「现在选择」不会真的弹文件框**；
    2. 返回记录列表：``_prompt_missing_source`` 每次被调用就记一笔，可用来
       断言"进这个任务时提示层被请求过"。

    ⚠️ 记录的是"**被请求**"而不是"被显示"——所以要断言"有源文件的任务不该
    提示"时，要看 ``page._source_prompt`` 是不是``None``，别只看这个列表。
    """
    calls: list = []
    picked: list = []
    # ⚠️ 先把原方法**抓在手里**再包一层：写成 `record` 里再调
    #    ``page._prompt_missing_source()`` 会调到自己（那个属性已被替换成
    #    record）⇒无限递归。
    real_prompt = page._prompt_missing_source
    real_pick = page._on_pick_source

    def record() -> None:
        calls.append(1)
        real_prompt()

    def safe_pick() -> None:
        picked.append(1)     # 记"用户点了现在选择"，但不真弹模态文件框

    page._prompt_missing_source = record
    page._on_pick_source = safe_pick
    # 记录"点过现在选择"的列表挂在助手返回值上，两个用途一起拿到
    record.picked = picked          # type: ignore[attr-defined]
    del real_pick
    return calls


def module_sources(root: Path, rel: str) -> list[Path]:
    """把仓库相对路径 ``rel`` 解析成**实际源文件列表**（子包感知）。

    2026-10-07 起若干查看器从**单文件**拆成**子包**（同名目录 + ``__init__.py``）：
    ``image_editor`` / ``image_view`` / ``image_zoom_dialog`` / ``print_preview`` /
    ``image_viewer`` / ``rembg_viewer``。护栏里"读源码文本做断言"的地方若还按
    老路径 ``xxx.py`` 读，会直接 ``FileNotFoundError``（或更糟：断言悄悄变成
    永远为真）。统一走本函数：

    - 仍是单文件（如 ``pdf_viewer.py``）→ 就它一个；
    - 已拆成子包 → 目录下所有 ``.py``（含孙目录，如 ``image_editor/canvas/``）。

    ``__init__.py`` 也在内：它是包的一部分，重导出/惰性导出就写在那儿。
    """
    path = root / rel
    if path.is_dir():
        return sorted(path.rglob("*.py"))
    return [path]


def module_source_text(root: Path, rel: str) -> str:
    """``module_sources`` 的文本版：把解析出的源文件拼成一段（空行分隔）。

    多文件拼接后做 ``in`` 断言时，命中来自哪个文件不重要——这些护栏问的是
    "整条链路里还有没有这个写法"，不是"在哪一行"。
    """
    return "\n".join(
        p.read_text(encoding="utf-8") for p in module_sources(root, rel)
    )


def _class_members(node) -> set[str]:
    """类体成员名：方法 + 类属性 + **实例属性**（``self.X = ...``）。

    ⚠️ 实例属性必须算进来：宿主面声明的正是这些（``_image`` / ``_zoom`` …），
    只数类体赋值会把它们全判成"多余的桩"。
    """
    import ast

    out: set[str] = set()
    for m in node.body:
        if isinstance(m, ast.FunctionDef):
            out.add(m.name)
        elif isinstance(m, ast.Assign):
            for t in m.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
        elif isinstance(m, ast.AnnAssign) and isinstance(m.target, ast.Name):
            out.add(m.target.id)
    for s in ast.walk(node):
        if isinstance(s, ast.Assign):
            targets = s.targets
        elif isinstance(s, ast.AnnAssign):
            targets = [s.target]
        else:
            continue
        for t in targets:
            if (isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "self"):
                out.add(t.attr)
    return out


def _find_class(path: Path, name: str):
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(n for n in tree.body
                if isinstance(n, ast.ClassDef) and n.name == name)


def check_type_only_host(ok, *, label, root, pkg_rel, host_file, host_cls,
                         main_file, main_cls, mixin_modules, expected_bases):
    """钉住「**类型检查期宿主协议**」的四条不变量（2026-10-07 引入）。

    拆分后每个 Mixin 都是独立类，pyright 看不到兄弟 Mixin / 主类 / Qt 基类上的
    成员，于是整块报 ``reportAttributeAccessIssue``。修法是每个子包一个
    ``_host.py``：里面一个宿主类声明「主类 + 全部兄弟 Mixin」的成员面，各 Mixin
    在**类型检查期**继承它（``if TYPE_CHECKING: from ._host import X`` /
    ``else: X = object``）。

    ⚠️ 这套写法一旦漂移就是**静默**的：宿主面漏一个成员 = 某个工具在类型检查里
    失明；宿主类被真继承（而不是 ``object`` 兜底）= 运行期 MRO 变了、行为可能
    悄悄改。四条都钉死：

    1. ``_host.py`` 存在，且宿主类的基类就是主类去掉本地 Mixin 后剩下的那些；
    2. 宿主面**恰好**覆盖主类 + 各 Mixin 的成员（不许漏、也不许留没人用的桩）；
    3. 每个 Mixin 都是「TYPE_CHECKING 期继承宿主、运行期继承 object」的写法；
    4. 运行期主类的 MRO 里**没有**宿主类（证明零副作用）。

    成员数按 ``min_members`` 之类阈值不设——(2) 的双向相等本身就是元守卫。
    """
    import ast
    import importlib

    pkg_dir = root / pkg_rel
    host_path = pkg_dir / host_file

    ok(f"{label}：类型检查期宿主面 {host_file} 存在", host_path.is_file(),
       f"缺 {host_path}")
    if not host_path.is_file():
        return

    host_node = _find_class(host_path, host_cls)
    bases = [ast.unparse(b) for b in host_node.bases]
    ok(f"{label}：宿主类 {host_cls} 的基类 = 主类去掉本地 Mixin 后的基类",
       bases == list(expected_bases), f"实际={bases}，期望={expected_bases}")

    # ---- (2) 宿主面恰好覆盖 主类 + 各 Mixin 的成员 ----
    expected: set[str] = set()
    for name in _class_members(_find_class(pkg_dir / main_file, main_cls)):
        expected.add(name)
    for fname, cname in mixin_modules:
        expected |= _class_members(_find_class(pkg_dir / fname, cname))
    # ⚠️ dunder（只有 __init__）刻意不声明：声明了主类的 super().__init__(parent)
    #    会命中宿主里的桩，parent 被当成别的参数报类型错。
    expected = {n for n in expected if not (n.startswith("__")
                                            and n.endswith("__"))}
    declared = {n for n in _class_members(host_node)
                if not (n.startswith("__") and n.endswith("__"))}

    ok(f"{label}：宿主面没有漏掉任何成员（漏了 = 该成员在类型检查里失明）",
       not (expected - declared), f"漏={sorted(expected - declared)}")
    ok(f"{label}：宿主面没有多余的桩（多了 = 与拆分现状漂移）",
       not (declared - expected), f"多={sorted(declared - expected)}")

    # ---- (3) 各 Mixin 都是「TYPE_CHECKING 期继承、运行期 object」----
    bad: dict[str, str] = {}
    for fname, cname in mixin_modules:
        src = (pkg_dir / fname).read_text(encoding="utf-8")
        cls = _find_class(pkg_dir / fname, cname)
        base_names = [ast.unparse(b) for b in cls.bases]
        guarded = (
            "if TYPE_CHECKING:" in src
            and f"from ._host import {host_cls}" in src
            and f"{host_cls} = object" in src
        )
        if not guarded:
            bad[fname] = "缺 TYPE_CHECKING 条件导入"
        elif base_names != [host_cls]:
            bad[fname] = f"类基类={base_names}"
    ok(f"{label}：各 Mixin 都在类型检查期继承宿主、运行期退化成 object",
       not bad, f"问题={bad}")

    # ---- (4) 运行期 MRO 里没有宿主类 ----
    mod = importlib.import_module(pkg_rel.replace("/", "."))
    runtime_cls = getattr(mod, main_cls)
    leaked = [b.__name__ for b in runtime_cls.__mro__ if b.__name__ == host_cls]
    ok(f"{label}：运行期 {main_cls} 的 MRO 里没有 {host_cls}（零副作用）",
       not leaked, f"MRO 泄漏={leaked}")


def imported_modules(source: str) -> set[str]:
    """把一段源码里所有 import 的模块名抠出来（含 ``from X import Y`` 里的 X）。

    ⚠️ **必须用 AST，不能用文本/正则匹配**：注释与文档字符串里提到某个模块名
    是**允许的**（说明文字经常要写"本模块不 import functions"这类话），
    文本匹配会把这类说明误判成真依赖。

    按设计返回**全部**缩进层级的 import（模块级 + 函数内延迟导入）——调用方
    若只想看模块级依赖，自己按 ``col_offset == 0`` 过滤。
    """
    import ast

    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module)
    return found


def make_pdf(path: Path, pages: int, text_prefix: str = "第") -> Path:
    """生成 pages 页的极简 PDF（每页一行占位文字）。"""
    import pymupdf

    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text_prefix} {i + 1} 页 测试内容")
    doc.save(str(path))
    doc.close()
    return path


def wait_worker(page, app, timeout: float = 180.0) -> int:
    """等待阶段子进程退出，返回退出码。

    注意：只看 QProcess 状态——进程退出时最后一条 finished 事件（才带
    最终 done 值）可能还排在事件队列里，调用方需要按目标值继续轮询。
    """
    deadline = time.time() + timeout
    while page.process and page.process.state() != 0 and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()
    return page.process.exitCode() if page.process else 0


def pump(app, times: int = 6, interval: float = 0.05) -> None:
    """驱动事件循环一小段时间（等信号/异步加载落地）。"""
    for _ in range(times):
        app.processEvents()
        time.sleep(interval)


def wait_until(app, condition, timeout: float = 5.0, interval: float = 0.02) -> bool:
    """驱动事件循环直到 ``condition()`` 成立或超时，返回最终是否成立。

    列表刷新这类**后台线程读盘**的流程是异步的，断言前必须等它回来；
    固定 pump 若干次在慢机器上会偶发失败。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(interval)
    return condition()


def painted_color(widget) -> tuple[int, int, int] | None:
    """把控件**真渲染出来**，返回最像"文字"的那个像素的 RGB。

    取的是"彩度 + 暗度"最高的像素（背景是白/浅灰，文字像素得分明显更高）。

    ⚠️ **校验文字颜色必须看渲染结果，不能查 ``palette()``**：qfluentwidgets 的
    标签（``FluentLabelBase`` 子类）根本不读调色板，它用样式表自己画。2026-09-23
    踩到——调色板里明明写着 ``#C93A3A``，画出来是纯黑，而"查调色板"的护栏一直
    是**假绿**。同理也别只查 ``styleSheet()``：它只能证明"设了"，证明不了"画了"。

    返回 ``None`` 表示控件一个非背景像素都没有（没字 / 没显示）。
    """
    image = widget.grab().toImage()
    best, best_score = None, -1
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            score = (255 - color.value()) + color.saturation()
            if score > best_score:
                best, best_score = color, score
    return (best.red(), best.green(), best.blue()) if best is not None else None


def rgb3(color) -> tuple[int, ...]:
    """取一个 QColor 的 (r, g, b) 三个分量（丢掉 alpha）。

    ⚠️ PySide6 的 ``QColor.getRgb()`` 注解写成 ``-> object``（其实返回 4 元组），
    这里收口一次，免得每处切片都写 ``cast``。
    """
    r, g, b, _a = color.getRgb()
    return (r, g, b)


def is_reddish(rgb: tuple[int, int, int] | None, margin: int = 40) -> bool:
    """这个颜色算不算"红字"（红通道明显高于绿蓝）。

    比"等于某个色值"稳：抗锯齿会让边缘像素混白，但**最深的那一撮**仍是主色。
    ``margin=40`` 能把 ``#4E5862``（常规柔和墨色，r=78 g=88 b=98）判为非红。
    """
    if rgb is None:
        return False
    red, green, blue = rgb
    return red > green + margin and red > blue + margin


class Context:
    """跨模块共享的夹具与状态。

    prepare() 在第一个模块执行前调用一次；各模块产生的跨模块状态直接
    挂在实例属性上（见各属性注释）。
    """

    def __init__(self) -> None:
        self.app = None
        self.w = None            # MainWindow
        self.d = None            # 任务详情页（w.detail_page 别名）
        self.repo = None         # 重定向到临时目录的 TaskStore
        self.tmp: Path | None = None
        self.pdf: Path | None = None      # 6 页样例 PDF
        self.big_pdf: Path | None = None  # 80 页样例 PDF
        # —— 模块间传递的状态 ——
        self.tid: str | None = None             # tasklist 创建的主任务
        self.tid_dup: str | None = None         # 同指纹重复任务（task_delete 删）
        self.tid_big: str | None = None         # resume 创建的大部头任务
        self.inserted_img: Path | None = None   # pages 插入清单的外部图
        self.injected_boxes = None              # rembg 注入的确定性检测框
        self.preview_dir = None                 # rembg 预览目录（print 断言用）

    def prepare(self) -> None:
        """构建 QApplication + 主窗口，并把数据目录重定向到临时目录。"""
        from PySide6.QtWidgets import QApplication

        from desktop.app import MainWindow
        from desktop.store import TaskStore
        from tests.tmpdir import temp_dir

        self.tmp = temp_dir("guji_selftest_")
        print(f"工作目录：{self.tmp}")
        self.pdf = make_pdf(self.tmp / "古籍样例.pdf", 6)
        self.big_pdf = make_pdf(self.tmp / "大部头.pdf", 80)

        self.app = QApplication([])
        self.w = MainWindow()
        self.w.close()  # 重定向数据目录到临时目录
        self.repo = TaskStore(self.tmp)
        self.w.store = self.repo
        self.w.list_page.store = self.repo
        self.w.detail_page.store = self.repo
        self.d = self.w.detail_page


def show_detail(ctx, stage: int = 0, size: tuple[int, int] = (1080, 720)):
    """真正把详情页显示出来并切到指定阶段，返回该阶段的控制面板。

    必须这样做才能测布局：QStackedWidget 里没被选中的页面从未参与布局，
    其中的 qfluentwidgets ScrollArea 是懒构建的——未显示时 layout() 为
    None、viewport/inner 全是 480x640 之类的脏默认值，据此断言的「有没
    有滚动条」结论都是假的。真显示后 inner=302、viewport=81、vbarMax=221。
    """
    from PySide6.QtWidgets import QStackedWidget

    app, w, d = ctx.app, ctx.w, ctx.d
    pages = w.findChild(QStackedWidget, "pageRoot")
    if pages is not None:
        pages.setCurrentWidget(d)
    w.resize(*size)
    w.show()
    pump(app, times=12)
    d._select_stage(stage)
    pump(app, times=12)
    return d.control_stack.widget(stage)


def install_module_watchdog(app, state: dict, limit: float):
    """按模块计时的看门狗，返回 arm(module_name) 函数。

    QTimer 在任何事件循环（包括模态 exec）里都会触发，因此模块内若有
    控件卡进模态/死循环，超时后打印模块名并 os._exit(3)，避免整条测试
    无声挂起（真实发生过：整条测试卡在续跑段 20+ 分钟无输出）。
    """
    from PySide6.QtCore import QTimer

    def _fire() -> None:
        print(
            f"\n[看门狗] 模块 {state.get('module')} 超过 {limit:.0f}s 未完成，"
            "疑似卡死，强制退出（可用 --module-timeout 调整）"
        )
        os._exit(3)

    timer = QTimer(app)
    timer.setSingleShot(True)
    timer.timeout.connect(_fire)
    state["timer"] = timer

    def arm(module: str) -> None:
        state["module"] = module
        timer.start(int(limit * 1000))

    return arm
