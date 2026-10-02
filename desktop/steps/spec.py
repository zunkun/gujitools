# -*- coding: utf-8 -*-
"""步骤的**声明式元数据**：一个步骤"是什么"，与流程顺序无关。

用户口径（2026-10-02）：

> 任务管理每个步骤组件有先后关系，因此我们的组件不需要相互关联，
> 公共组件定义好 API 就行，比如入口文件目录，输出文件目录等。

所以 :class:`StepSpec` 只描述**这一步自己**：跑哪个命令、用哪个参数面板、
输入是 PDF 还是图片（单张 / 目录 / 一批）、默认输出目录怎么从输入推出来。
「上一步是谁、下一步是谁、产物给谁用」**一概不写**——那是任务管理自己的
编排，不是步骤的属性。正因如此，同一个 spec 既能被任务流程用，也能被左侧
导航的独立模块用。

「入口」这一侧的三件事也都收在这里，**不散到界面代码**去（用户 2026-10-02：
「页面上有一个大的输入框，可以输入图片和输入文件，或者输入目录，也可以把
文件拖进去」）：

1. 认哪些后缀 —— :meth:`StepSpec.suffixes`（从 ``file_filter`` 里抠，过滤串
   仍是唯一事实来源）；
2. 允不允许直接拿目录当输入 —— ``accepts_dir``；
3. 用户给了一堆东西（拖进来的文件/文件夹混在一起）**到底算哪个源** ——
   :meth:`StepSpec.resolve_source`。这是纯逻辑，可以脱离 Qt 单测。

⚠️ 面板只记**类名**（字符串），到用的时候才从 ``desktop.components.panels``
惰性取——本模块因此不 import 任何 Qt 面板，可以被纯逻辑（CLI、自测、未来的
批处理）安全导入。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: 认得的图片后缀（选文件时的过滤串与"这是不是图片"的判断共用一份）
IMAGE_FILTER = "图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)"
PDF_FILTER = "PDF 文件 (*.pdf)"

#: 从过滤串里抠后缀用的正则：``*.jpg`` → ``.jpg``
_SUFFIX_RE = re.compile(r"\*(\.[A-Za-z0-9]+)")

#: 「顶层找不到、自动往下钻」的最大层数（见 :meth:`StepSpec.nested_listing`）。
#:
#: 2 层是有来历的：图片提取模块的产物固定落在 ``<输出根>/<PDF名>/images/``
#: （``utils.pdf_extract.run_on_input_directory`` 的布局，与 CLI 同源），
#: 用户很自然会把这个**输出根目录**直接拖给「去底色」——那就是"下一层没有、
#: 再下一层有"。更深就没必要猜了。
AUTO_DESCEND_DEPTH = 2


@dataclass(frozen=True)
class StepSpec:
    """一个处理步骤的元数据（不可变，可当字典键/常量用）。

    字段含义：

    - ``key``：唯一路由键，与 ``desktop.modules.MODULES`` 的 key 同名同义；
    - ``command``：``functions.get_function`` 的命令名；``None`` 表示这一步
      不是 CLI 命令（如拼版是纯函数 ``compose_doc``，由调用方给 job）；
    - ``title``：**模块页头大标题 + 左侧导航条目**的名字（"图片提取"）；
    - ``subtitle``：**模块页头副标题**（"选择一个 PDF（…），把每页渲染成图片"）；
    - ``nav_tooltip``：**导航条目悬停提示**（空则用 ``subtitle``）；
    - ``nav_icon``：**导航条目图标**（``FluentIcon`` 成员名）；
    - ``panel``：参数面板**类名**（``desktop.components.panels`` 里的名字）；
      ``None`` 表示这一步没有可调参数；
    - ``pick_label``：源选择对话框的标题（"选择 PDF" / "选择图片"）；
    - ``run_label``：执行按钮文案（空则回落到"开始 + 标题"）；
    - ``file_filter``：``QFileDialog`` 的文件过滤串，**同时是后缀的唯一来源**
      （见 :meth:`suffixes`）；
    - ``accepts_dir``：源能不能直接是目录（拖进来一个文件夹算不算一个源）；
    - ``allow_multi``：对话框允许一次多选（拖拽天然支持多选，此项只管对话框）；
    - ``flat_output``：单源时要不要把产物**平铺到输出目录根下**。置 ``True`` 的
      只有 ``extract``——它的命令习惯是 ``<输出>/<PDF名>/images/``（见
      :func:`desktop.steps.kernel.job_for`），单 PDF 时这层嵌套既多余又断链；
    - ``artifact_is_file``：这一步的产物是**单个文件**（而不是一目录文件）。
      ``print`` 为 ``True``——它的 ``--output`` 是**目录**，文件名由命令自己在其下
      取（``<输出>/output.pdf``），所以执行内核**不能**把 ``function.outpath``
      覆盖成那个目录（覆盖了就会拿目录当文件路径写，直接报错）；内核还会把
      **真正的产物路径**（而不是目录）回传给 ``finished``；
    - ``output_suffix``：默认输出目录名 = 源名 + 这个后缀；
    - ``output_name``：给了就用**固定名**（如"拼图成品"），不再用后缀规则；
    - ``drop_icon`` / ``drop_title`` / ``drop_hint``：共用大输入区
      （:class:`desktop.steps.source_zone.SourceZone`）的图标与两行文案；
      后两者留空时按 ``title`` 生成兜底文案。

    ⚠️ **文案字段按"界面上有哪几个地方要显示"逐个建，不合并**。同一步在流程条
    和左侧导航里叫法确实不一样（流程条说的是**动作**「提取图片」，导航说的是
    **东西**「图片提取」），硬合成一个名字就会改动其中一处界面。所以：

    ===============  ==========================================
    字段              用在哪
    ===============  ==========================================
    ``title``         模块页头大标题、左侧导航条目
    ``subtitle``      模块页头副标题
    ``nav_tooltip``   导航条目悬停提示
    ``stage_title``   流程步骤条上的名字（空则用 ``title``）
    ``short``         流程步骤条上的短名（空则用 ``stage_title``）
    ===============  ==========================================

    **流程侧**：

    - ``role``：``"stage"`` = 默认流程主链上的一步；``"optional"`` = 流程条上的
      **可选节点**（拼版就是：``STAGES`` 里没有它，但它有自己的模块页）。
      见 :data:`FLOW_STAGES` / :data:`OPTIONAL_STEPS`；
    - ``nav``：这一步**有没有独立的模块页**、要不要进左侧导航。``False`` 表示
      还没抽出来——壳层据此不过去建页面（``desktop.modules.MODULES`` 会把它
      过滤掉），免得出现"清单里有、页面不存在"；
    - ``inputs`` / ``outputs``：**BPM 端口预留**——将来自定义流程要靠它们把步骤
      连起来。⚠️ 现在**还没接线**：任务流程走的仍是"约定目录布局"（提取的输出
      目录就是去底色的输入目录）。先声明出来，是为了让端口模型落地时不用回头
      改五条 spec。
    """

    key: str
    command: str | None
    title: str
    panel: str | None
    pick_label: str
    file_filter: str
    subtitle: str = ""
    run_label: str = ""
    accepts_dir: bool = True
    allow_multi: bool = False
    flat_output: bool = False
    artifact_is_file: bool = False
    output_suffix: str = ""
    output_name: str = ""
    drop_icon: str = "FOLDER_ADD"
    drop_title: str = ""
    drop_hint: str = ""
    # ---- 流程侧（是不是主链的一步、步骤条上叫什么）----
    role: str = "stage"
    stage_title: str = ""
    short: str = ""
    # ---- BPM 端口（本次只声明、未接线，见类 docstring）----
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    # ---- 左侧导航侧（有没有独立模块页、图标、悬停提示）----
    nav: bool = False
    nav_tooltip: str = ""
    nav_icon: str = ""

    # ------------------------------------------------------------------ 面板
    def panel_class(self):
        """惰性取参数面板类（``None`` 表示这一步没有面板）。

        ``panel`` 支持两种写法：

        - ``"ExtractPanel"``：在 ``desktop.components.panels`` 里找（四个阶段
          面板都在那儿，是绝大多数情况）；
        - ``"desktop.components.imposition:ImpositionPanel"``：**指定模块**再找
          ——拼版面板住在 ``desktop.components.imposition``，不在上面那个包里。
        """
        if not self.panel:
            return None
        import importlib

        if ":" in self.panel:
            module_name, class_name = self.panel.split(":", 1)
        else:
            module_name, class_name = "desktop.components.panels", self.panel
        return getattr(importlib.import_module(module_name), class_name)

    # ------------------------------------------------------------------ 入口
    def suffixes(self) -> tuple[str, ...]:
        """本步骤认的文件后缀（小写，含点）；从 ``file_filter`` 推导。

        ⚠️ 故意**解析过滤串**而不是另写一份后缀表：两处一旦并存就一定会漂移
        （用户看到的对话框按过滤串，拖拽判定却按另一份表）。
        """
        return tuple(s.lower() for s in _SUFFIX_RE.findall(self.file_filter or ""))

    def input_noun(self) -> str:
        """输入物的中文称呼（"PDF" / "图片"），由 ``pick_label`` 派生，用于提示语。"""
        return self.pick_label.removeprefix("选择").strip() or "文件"

    def accepts_path(self, path: Path | str) -> bool:
        """这个路径能不能当源：目录看 ``accepts_dir``，文件看后缀。"""
        path = Path(path)
        if path.is_dir():
            return self.accepts_dir
        return path.suffix.lower() in self.suffixes()

    def collect_files(self, paths) -> list[Path]:
        """把一批路径展开成**文件清单**（给"要一批文件"的调用方，如拼图）。

        与 :meth:`resolve_source` 的分工：那个把一堆路径收成**一个源**（文件
        提取 / 去底色要的），这个把它们**摊平成一份清单**（拼图要的）。

        - 文件：后缀对就留下；
        - 目录：先取顶层的；顶层没有、但只有**一个**子目录装着 → 用那一层
          （同 :meth:`resolve_source` 的下钻理由：提取模块的产物是
          ``<输出根>/<PDF名>/images/``）；
        - 结果去重并按文件名排序（"前一页左半幅 + 当前页右半幅"的配对规则
          依赖一个稳定顺序）。
        """
        found: dict[str, Path] = {}
        for raw in paths or []:
            path = Path(raw)
            if path.is_dir():
                files = self.listing(path)
                if not files:
                    deeper = self.nested_listing(path)
                    if len(deeper) == 1:
                        files = self.listing(deeper[0])
            elif path.is_file() and self.accepts_path(path):
                files = [path]
            else:
                files = []
            for file in files:
                found.setdefault(str(file), file)
        return sorted(found.values(), key=lambda p: p.name.lower())

    def listing(self, directory: Path | str) -> list[Path]:
        """目录里符合本步骤后缀的文件（**只看顶层**，与功能层
        ``collect_image_files`` / ``run_on_input_directory`` 同口径）。

        读不了（不存在/没权限）时返回空表——调用方据此给"这里没有可用文件"。
        """
        directory = Path(directory)
        try:
            children = sorted(directory.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return []
        wanted = self.suffixes()
        return [
            p for p in children if p.is_file() and p.suffix.lower() in wanted
        ]

    def nested_listing(self, directory: Path | str,
                       max_depth: int = AUTO_DESCEND_DEPTH) -> list[Path]:
        """在下面 1~``max_depth`` 层里找**装着本步骤文件的子目录**（广度优先）。

        命中一层就停在该层——找到更浅的就不再往下挖，避免把"某一层唯一"误判成
        "最深处唯一"。返回的是目录清单（不是文件），调用方按数量决定怎么办。
        """
        directory = Path(directory)
        frontier = [directory]
        for _ in range(max(0, max_depth)):
            found: list[Path] = []
            nxt: list[Path] = []
            for current in frontier:
                try:
                    children = sorted(current.iterdir(), key=lambda p: p.name.lower())
                except OSError:
                    continue
                for child in children:
                    if not child.is_dir():
                        continue
                    (found if self.listing(child) else nxt).append(child)
            if found:
                return found
            frontier = nxt
            if not frontier:
                break
        return []

    def resolve_source(self, paths) -> tuple[Path | None, str]:
        """把用户给的一批路径**归一成"这一步的源"**（文件或目录）。

        返回 ``(源, 说明)``：说明为空 = 顺利且无需交代；非空是一句给用户看的
        话（可能是我替你选了哪一个，也可能是不接受的理由）。

        规则（顺序即优先级）：

        1. 混着文件夹进来时，只要 ``accepts_dir`` 就**取第一个文件夹当源**
           （拖一个文件夹进来是最自然的批量用法）；不接受目录的步骤则改为
           从文件夹里挑出符合后缀的文件继续走第 3 步；
        2. 文件夹**顶层没有**本步骤能用的文件时，往下钻一~两层（见
           :meth:`nested_listing`）：恰好一个子目录装着 → 自动指向它并说明；
           多个 → 拒绝并让用户挑一个（混着处理会把不同书的页拼在一起）；
        3. 单个文件 → 它自己；
        4. 多个文件 → 它们的**共同父目录**（批量语义就是"处理这个目录"）；
           共同父目录不存在（跨盘）时退到第一个文件所在的目录；
        5. 一件都不匹配 → ``(None, 理由)``。
        """
        candidates = [Path(p) for p in (paths or []) if str(p or "").strip()]
        if not candidates:
            return None, "没有收到任何文件或文件夹"

        folders = [p for p in candidates if p.is_dir()]
        files = [p for p in candidates if p.is_file()]

        if folders and self.accepts_dir:
            chosen = folders[0]
            note = ""
            if len(candidates) > 1:
                note = f"已从 {len(candidates)} 个路径里选用文件夹「{chosen.name}」"
            if not self.listing(chosen):
                picked, deeper_note = self._descend_for_source(chosen)
                if picked is None:
                    return None, deeper_note
                if picked != chosen:
                    note = (note + "；" if note else "") + deeper_note
                    chosen = picked
            return chosen, note

        if folders:
            for folder in folders:
                files.extend(self.listing(folder))

        if not files:
            if not any(p.exists() for p in candidates):
                return None, "这些路径都不存在了，请重新选择"
            return None, f"里面没有本步骤能用的{self.input_noun()}文件"

        matched = [p for p in files if p.suffix.lower() in self.suffixes()]
        if not matched:
            return None, (
                f"这些文件不是本步骤支持的格式"
                f"（{'、'.join(self.suffixes())}）"
            )
        if len(matched) == 1:
            note = "" if len(matched) == len(candidates) == 1 else (
                f"已选用「{matched[0].name}」"
            )
            return matched[0], note

        parents = {p.parent for p in matched}
        parent = parents.pop() if len(parents) == 1 else matched[0].parent
        return parent, f"共 {len(matched)} 个文件，按目录「{parent.name}」批量处理"

    def _descend_for_source(self, folder: Path) -> tuple[Path | None, str]:
        """文件夹顶层没有可用文件时，决定要不要自动指向某个子目录。

        返回 ``(源, 说明)``：``源`` 为 ``None`` 表示**必须让用户自己挑**
        （此时说明是拒绝理由）；``源`` 就是 ``folder`` 本身表示"没得选，
        照旧交给功能层去报错"（保持改造前的行为）。
        """
        deeper = self.nested_listing(folder)
        if len(deeper) == 1:
            return deeper[0], (
                f"「{folder.name}」里没有直接的{self.input_noun()}文件，"
                f"已自动指向子目录「{deeper[0].name}」"
            )
        if len(deeper) > 1:
            names = "、".join(p.name for p in deeper[:3])
            more = "…" if len(deeper) > 3 else ""
            return None, (
                f"「{folder.name}」下有 {len(deeper)} 个子目录各装着"
                f"{self.input_noun()}文件（{names}{more}），"
                "请直接把其中一个拖进来"
            )
        return folder, ""

    # ------------------------------------------------------------------ 输出
    def default_output(self, source: Path | None) -> Path | None:
        """从源路径推出默认输出目录（源为空则返回 ``None``）。

        规则（与三个模块改造前的行为逐字一致，改动会让老用户找不到产物）：

        - 固定名（``output_name``）优先，放在源的**同级目录**下；
        - 否则：源是目录 → ``<父目录>/<目录名><后缀>``；
          源是文件 → ``<父目录>/<文件名去后缀><后缀>``。
        """
        if source is None:
            return None
        source = Path(source)
        parent = source.parent
        if self.output_name:
            return parent / self.output_name
        if source.is_dir():
            return parent / (source.name + self.output_suffix)
        return parent / (source.stem + self.output_suffix)

    def accepts_files(self) -> bool:
        """源可以是一批文件吗（多选 / 单选都算）。"""
        return bool(self.file_filter)

    def run_text(self) -> str:
        """执行按钮文案（``run_label`` 为空时回落到"开始 + 标题"）。"""
        return self.run_label or f"开始{self.title}"

    def short_name(self) -> str:
        """流程步骤条上的短名（``short`` 为空时用 ``stage_name()``）。"""
        return self.short or self.stage_name()

    def stage_name(self) -> str:
        """流程步骤条上的名字（``stage_title`` 为空时用 ``title``）。

        ⚠️ 与 ``title``（模块页头/导航）**有意分开**：见类 docstring 的文案表。
        """
        return self.stage_title or self.title

    def nav_tip(self) -> str:
        """导航条目悬停提示（``nav_tooltip`` 为空时用 ``subtitle``）。"""
        return self.nav_tooltip or self.subtitle

    # ------------------------------------------------------------------ 文案
    def drop_title_text(self) -> str:
        """大输入区空态的标题（``drop_title`` 为空时兜底）。"""
        return self.drop_title or f"把{self.input_noun()}拖到这里"

    def drop_hint_text(self) -> str:
        """大输入区空态的提示行（``drop_hint`` 为空时按能否选目录兜底）。"""
        if self.drop_hint:
            return self.drop_hint
        tail = "（文件或文件夹都行）" if self.accepts_dir else ""
        return f"也可以点这里选{self.input_noun()}{tail}"

    def summary(self) -> str:
        """一行可读描述（日志/自测用，别拿它做判断）。"""
        kind = "目录或文件" if self.accepts_dir else "文件"
        return f"{self.title}（{self.command or '纯函数'} ← {kind} → 目录）"


#: 左侧导航 / 任务流程共用的步骤清单（顺序即界面顺序）。
#:
#: ⚠️ 这里是**步骤元数据的唯一事实来源**：新增一个步骤 = 加一条 + 写它的 job，
#: 壳层、模块页、任务流程都不需要各自再写一份文案/过滤串/输出规则。
SPECS: tuple[StepSpec, ...] = (
    # ---- 流程主链 · 第 1 步 ----
    StepSpec(
        key="extract",
        role="stage",
        command="extract",
        title="图片提取",
        stage_title="提取图片",
        short="提取",
        nav=True,
        nav_tooltip="从 PDF 提取页面图片",
        nav_icon="ZIP_FOLDER",
        subtitle="选择一个 PDF（或一整个 PDF 文件夹），把每页渲染成图片",
        panel="ExtractPanel",
        pick_label="选择 PDF",
        run_label="开始提取",
        file_filter=PDF_FILTER,
        flat_output=True,
        output_suffix="_提取",
        inputs=("pdf",),
        outputs=("pages",),
        drop_icon="DOCUMENT",
        drop_title="把 PDF 拖到这里",
        drop_hint="也可以点这里选 PDF 或整个文件夹（文件夹里全部 PDF 一起提）",
    ),
    # ---- 流程主链 · 第 2 步 ----
    StepSpec(
        key="detect",
        role="stage",
        command="detect",
        title="检测文本框",
        short="检测",
        nav=True,
        nav_tooltip="检测每页的内容框并导出坐标",
        nav_icon="SEARCH",
        subtitle="拖入图片或图片文件夹，检测每页的内容框；可在图上手绘修正后导出坐标 JSON",
        panel="DetectPanel",
        pick_label="选择图片",
        file_filter=IMAGE_FILTER,
        output_suffix="_检测",
        inputs=("pages",),
        outputs=("boxes",),
        drop_icon="PHOTO",
    ),
    # ---- 流程主链 · 第 3 步 ----
    StepSpec(
        key="rembg",
        role="stage",
        command="rembg",
        title="去底色",
        stage_title="图片去底色",
        short="去底",
        nav=True,
        nav_tooltip="整图去底色 / 二值化 / 保留印章",
        nav_icon="PALETTE",
        subtitle="拖入图片或图片文件夹，批量去底色 / 二值化（可保留印章）",
        panel="RembgPanel",
        pick_label="选择图片",
        run_label="开始去底色",
        file_filter=IMAGE_FILTER,
        output_suffix="_去底",
        inputs=("pages",),
        outputs=("pages",),
        drop_icon="PHOTO",
        drop_title="把图片拖到这里",
        drop_hint="也可以点这里选图片或整个文件夹（一张、一批都行）",
    ),
    # ---- 流程主链 · 第 4 步 ----
    StepSpec(
        key="print",
        role="stage",
        command="print",
        title="生成 PDF",
        short="PDF",
        nav=True,
        nav_tooltip="把成品图按版面合成 PDF",
        nav_icon="DOCUMENT",
        subtitle="拖入成品图文件夹，按版面合成 PDF（页序按文件名）",
        panel="PrintPanel",
        pick_label="选择图片",
        run_label="生成 PDF",
        file_filter=IMAGE_FILTER,
        artifact_is_file=True,
        output_suffix="_成书",
        inputs=("pages",),
        outputs=("pdf",),
        drop_icon="PHOTO",
        drop_title="把成品图拖到这里",
        drop_hint="也可以点这里选图片或整个文件夹（页序按文件名排序）",
    ),
    # ---- 流程条上的可选节点（有独立模块页，但不在 STAGES 里）----
    StepSpec(
        key="imposition",
        role="optional",
        command=None,
        title="拼图",
        stage_title="图片拼版",
        short="拼版",
        nav=True,
        nav_tooltip="多页图片拼版与版式调整",
        nav_icon="PHOTO",
        subtitle="拖入一批图片，拼版后导出成品图（每两张一页）",
        panel="desktop.components.imposition:ImpositionPanel",
        pick_label="选择图片",
        file_filter=IMAGE_FILTER,
        allow_multi=True,
        output_name="拼图成品",
        inputs=("pages",),
        outputs=("pages",),
        drop_icon="PHOTO",
        drop_title="把这批图片拖到这里",
        drop_hint="也可以点这里选一批图片，或直接拖一个图片文件夹进来",
    ),
)

#: 全部步骤 key（顺序同 :data:`SPECS`）
STEP_KEYS: tuple[str, ...] = tuple(spec.key for spec in SPECS)

#: 默认流程**主链**的步骤 key（顺序即执行顺序）——即 ``desktop.store.STAGES``
#: 的事实来源。⚠️ 只取 ``role == "stage"``：可选节点（拼版）不在主链上。
FLOW_STAGES: tuple[str, ...] = tuple(
    spec.key for spec in SPECS if spec.role == "stage"
)

#: 流程条上的**可选节点** key（排在主链之后的下标处，见
#: ``desktop.store.IMPOSITION_INDEX``）。目前只有拼版一个，故用元组而非单值，
#: 将来加第二个可选节点时不用改调用方。
OPTIONAL_STEPS: tuple[str, ...] = tuple(
    spec.key for spec in SPECS if spec.role == "optional"
)

#: 有独立模块页、要进左侧导航的步骤 key——即 ``desktop.modules.MODULES``
#: 的事实来源。
NAV_STEPS: tuple[str, ...] = tuple(spec.key for spec in SPECS if spec.nav)


def spec_by_key(key: str) -> StepSpec | None:
    """按 key 取步骤元数据；不存在返回 ``None``。"""
    for spec in SPECS:
        if spec.key == key:
            return spec
    return None


__all__ = [
    "FLOW_STAGES",
    "IMAGE_FILTER",
    "NAV_STEPS",
    "OPTIONAL_STEPS",
    "PDF_FILTER",
    "SPECS",
    "STEP_KEYS",
    "StepSpec",
    "spec_by_key",
]
