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
    - ``title``：**模块页头大标题**的名字（"图片提取"）。⚠️ 左侧导航那一列
      用自己的 ``nav_title``（见下），磁盘目录用 ``disk_key()``——三者互不相干；
    - ``nav_title``：**左侧导航条目**的名字（空则用 ``title``）；
    - ``subtitle``：**模块页头副标题**（"选择一个 PDF（…），把每页渲染成图片"）；
    - ``nav_tooltip``：**导航条目悬停提示**（空则用 ``subtitle``）；
    - ``nav_icon``：**导航条目图标**（``FluentIcon`` 成员名；或 ``svg:名字``
      引用 ``desktop.ui.icons.CustomIcon`` 的自绘图——内置图标没有的图形），
      由 ``desktop.ui.icons.resolve_nav_icon`` 统一解析；
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
    ``title``         模块页头大标题（**不含**左侧导航，见 ``nav_title``）
    ``nav_title``     左侧导航条目的名字（空则用 ``title``）
    ``subtitle``      模块页头副标题
    ``nav_tooltip``   导航条目悬停提示
    ``stage_title``   流程步骤条上的名字（空则用 ``title``）
    ``short``         流程步骤条上的短名（空则用 ``stage_title``）
    ===============  ==========================================

    **详情页侧**（``run_button_text`` / ``has_submit`` / ``control_width`` /
    ``preview_attr`` / ``panel_extra`` / ``history_skip`` / ``auto_fill_skip``）：
    "这一步在任务流程详情页里长什么样"。⚠️ 这些**曾经散在页面的 if-else 里**
    （``page._select_stage`` 按 stage 改按钮文案与区块显隐、``view.
    _apply_control_width`` 按 stage 换宽度、``history._history_fill_keys``
    按 stage 跳过不同键）——加一步就得改那几处 if，BPM 换顺序更是无从下手。
    现在都是**声明**：页面只查表，不认哪个 step 是谁。

    **流程侧**：

    - ``role``：``"stage"`` = 默认流程主链上的一步；``"optional"`` = 流程条上的
      **可选节点**（拼版就是：``STAGES`` 里没有它，但它有自己的模块页）。
      见 :data:`FLOW_STAGES` / :data:`OPTIONAL_STEPS`；
    - ``nav``：这一步**有没有独立的模块页**、要不要进左侧导航。``False`` 表示
      还没抽出来——壳层据此不过去建页面（``desktop.modules.MODULES`` 会把它
      过滤掉），免得出现"清单里有、页面不存在"；
    - ``inputs`` / ``outputs``：**BPM 端口**——这一步消费/产出哪些产物
      （``pages`` 图片 / ``boxes`` 检测框 / ``pdf``）。⚠️ **已接线**（2026-10-03
      补完）：:mod:`desktop.steps.ports` 按这两个字段 + 它的连线表把步骤连起来，
      任务流程不再靠"约定目录布局"。**声明必须与事实一致**——端口模型靠它做
      依赖检查，写漏一个就等于给 BPM 一条假的边（``rembg`` 漏写 ``boxes`` 就是
      这样被 ``tests/selftests/step_ports.py`` 逮到的）。
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
    nav_title: str = ""
    nav_tooltip: str = ""
    nav_icon: str = ""
    #: 导航里的排位（**小的在前**；留空按 ``SPECS`` 的书写顺序兜底）。
    #:
    #: 为什么要它：``print``（生成PDF）是流程主链的第4 步，却要在导航里排到
    #: **最后**——它吃的是前面几步的产物，"生成"这件事天然是收尾。改
    #: ``SPECS`` 里两段的书写位置也能达到同样效果，但那是**流程顺序**的事实
    #: 来源（``FLOW_STAGES`` 从它派生），为了导航顺序去动它等于把"导航怎么排"
    #: 的意图藏进一个看不出因果的位置里；而且 ``imposition`` 在 ``SPECS`` 里本来
    #: 就写在 ``print`` 之后（可选节点在主链之后），单纯对调书写位置还得再对调
    #: 一次才走得通。显式声明排序意图更直白，也只影响导航这一条线。
    nav_order: int = 0
    # ---- 任务流程详情页的"这一步长什么样"（2026-10-03）----
    #: 详情页**主动作按钮**文案。与 ``run_label``（独立模块页的按钮）**有意不同**：
    #: 流程里点它跑的是"本子任务"这一环节，模块页点它跑的是整个功能。
    run_button_text: str = "执行本子任务"
    #: 有没有「提交本次任务」这类**次动作按钮**（目前只有去底色有：
    #: 先生成预览、用户确认后才提交最终图）。
    has_submit: bool = False
    #: 右栏控制列的宽度区间（px）。第四步参数多，要更宽的编辑区。
    control_width: tuple[int, int] = (340, 440)
    #: 详情页**主预览控件**的属性名（←/→ 翻页、方向键导航都按它寻址）。
    preview_attr: str = ""
    #: 右栏「步骤专属区块」的名字（空 = 显示默认的「执行记录」）。detect 无表单
    #: 参数、历史回填没用武之地，改显「检测结果统计」。页面按名字取控件。
    panel_extra: str = ""
    #: 历史回填（**手动挑历史 + 自动回填都**）要跳过的键。
    history_skip: tuple[str, ...] = ()
    #: **仅自动回填**额外跳过的键（手动挑历史仍原样回填）。
    auto_fill_skip: tuple[str, ...] = ()
    #: 进度计量的**单位**（"页"/"张"/空）。独立功能页的进度条按它写
    #: "完成 12 页"这类收尾文案（``ProgressRow`` 的 ``noun``）。
    #: ⚠️ 与 ``input_noun``（入口文件的称呼，"PDF"/"图片"）**不是一回事**：
    #: 入口是 PDF、处理的是页；入口是图片、处理的是张。
    progress_noun: str = ""

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
        return [p for p in children if p.is_file() and p.suffix.lower() in wanted]

    def nested_listing(self, directory: Path | str, max_depth: int = AUTO_DESCEND_DEPTH) -> list[Path]:
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
           （拖一个文件夹进来是最自然的批量用法）；**不接受目录的步骤直接
           拒绝**（``accepts_dir=False``，如"PDF 只支持文件"的图片提取）——
           别在这里"从文件夹里挑出符合后缀的文件"替用户做主：挑到哪几个、
           为什么是这几个，用户在界面上看不见，而下一步的产物又依赖这个
           选择，错了要等到看结果时才发现；
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

        if folders and not self.accepts_dir:
            names = "、".join(p.name for p in folders[:3])
            more = "…" if len(folders) > 3 else ""
            return None, (f"本步骤只支持{self.input_noun()}**文件**，不支持文件夹" f"（收到：{names}{more}）")

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
            return None, (f"这些文件不是本步骤支持的格式" f"（{'、'.join(self.suffixes())}）")
        if len(matched) == 1:
            note = "" if len(matched) == len(candidates) == 1 else (f"已选用「{matched[0].name}」")
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
                f"「{folder.name}」里没有直接的{self.input_noun()}文件，" f"已自动指向子目录「{deeper[0].name}」"
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

    def progress_unit(self) -> str:
        """进度计量的单位（``progress_noun`` 为空时回落到 ``input_noun``）。

        给 :class:`~desktop.components.progress_row.ProgressRow` 用；回落到
        ``input_noun`` 是为了"没显式声明也能说出个大概"，总比空着强。
        """
        return self.progress_noun or self.input_noun()

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

    def nav_name(self) -> str:
        """左侧导航条目上的名字（``nav_title`` 为空时用 ``title``）。

        ⚠️ 与 ``title`` **有意分开**（同 :attr:`stage_title` 与 ``title`` 的
        道理）：导航那一列是"这一步做什么"的**短标签**，页头是完整标题，
        两处可以各说各的。用户 2026-10-03 就导航文案提过一轮（"图片提取"
        → "PDF图片提取" 等），只改这里不会连带改掉页头与流程条。
        """
        return self.nav_title or self.title

    def disk_key(self) -> str:
        """``singletask/`` 下这个子任务的**目录名**（缓存/手改件的归属）。

        ⚠️ **不是** ``title`` 也不是 ``nav_title``：这两者都是会随文案需求改的
        人类可读名字，而这里是**已经在磁盘上存在的路径**。``singletask/`` 里
        已经躺着按旧标题建的目录（``去底色`` / ``图片提取`` / ``拼图`` /
        ``检测文本框`` / ``生成 PDF``），其中 ``拼图/edited/`` 存着用户手改过
        的版面图——标题一改，这些缓存与手改件就再也找不到了（表现是"我明明
        改过版面，重新打开又变回原样"）。

        所以这里锚在 ``key`` 上（步骤的唯一路由键，改名不会动它）。改动此值
        等于换一整个子任务目录，**必须**先做旧目录迁移。
        """
        return self.key

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
        # 导航文案与 ``title`` 分开：这一列回答"这一步干什么"，页头仍是
        # 完整的「图片提取」（用户 2026-10-03 要求导航统一带对象名）。
        nav_title="PDF图片提取",
        nav_tooltip="从 PDF 提取页面图片",
        # ⚠️ 别用 ZIP_FOLDER：那是"压缩包/解压"，用户会以为这步跟压缩文件
        #    有关；这步的真实语义是"从 PDF 把图导出来"。
        nav_icon="IMAGE_EXPORT",
        subtitle="选择一个 PDF，把每页渲染成图片",
        panel="ExtractPanel",
        pick_label="选择 PDF",
        # ⚠️ 单位是"页"不是"PDF"：这一步处理的是 PDF 里的每一页。
        progress_noun="页",
        run_label="开始提取",
        file_filter=PDF_FILTER,
        flat_output=True,
        output_suffix="_提取",
        inputs=("pdf",),
        outputs=("pages",),
        preview_attr="extract_result_viewer",
        # ⚠️ ``pages`` 是「续跑」时按缺失页**派生**的一次性参数，不是用户意图：
        #    自动回填它会让下一次点执行只跑那一小段页码（用户看到"只提取了一半"）。
        #    只在**自动**回填时跳过；手动挑历史仍原样回填（那是"照那次再跑一遍"）。
        auto_fill_skip=("pages",),
        drop_icon="svg:PDF_FILE",
        drop_title="把 PDF 拖到这里",
        drop_hint="也可以点这里选择一个 PDF 文件",
        # ⚠️ **只支持文件**（用户 2026-10-03：「PDF 只支持文件」）。
        #    extract 之前允许整个文件夹：里面每个 PDF 各自一个子目录摆图。
        #    但那与本模块「选一个 PDF → 看它的每一页」的用法不符——一次拖一
        #    摞书进来，用户在预览里根本分不清哪张图属于哪本书，而单 PDF 的
        #    平铺收尾（`flat_output`）本来也只对"一个 PDF"设计。
        #    `accepts_dir=False` 同时让大输入区不摆「选择文件夹」按钮
        #    （摆一个注定被拒的入口是骗人，见 source_zone._build_buttons）。
        accepts_dir=False,
    ),
    # ---- 流程主链 · 第 2 步 ----
    StepSpec(
        key="detect",
        role="stage",
        command="detect",
        title="检测文本框",
        short="检测",
        nav=True,
        nav_title="检测文本框",
        nav_tooltip="检测每页的内容框并导出坐标",
        # ⚠️ 别用 SEARCH：放大镜会被读成"查找"。这步是"框出页面内容"，
        #    内置图标没有这个图形，用自绘的取景框 + 文本行（``svg:`` 前缀 →
        #    ``desktop.ui.icons.CustomIcon``，壳层经 resolve_nav_icon 解析）。
        nav_icon="svg:SCAN_TEXT_BOX",
        subtitle="拖入图片或图片文件夹，检测每页的内容框；可在图上手绘修正后导出坐标 JSON",
        panel="DetectPanel",
        pick_label="选择图片",
        progress_noun="张",
        file_filter=IMAGE_FILTER,
        output_suffix="_检测",
        inputs=("pages",),
        outputs=("boxes",),
        preview_attr="detect_viewer",
        # detect 无表单参数、历史回填没用武之地，右栏改显「检测结果统计」。
        panel_extra="detect_stats",
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
        nav_title="图片去底色",
        nav_tooltip="整图去底色 / 二值化 / 保留印章",
        # ⚠️ 别用 PALETTE：调色板会被读成"调色/取色"；这步的主语义是
        #    "把底色擦掉"（二值化/保留印章是它的模式），橡皮擦更直白。
        nav_icon="ERASE_TOOL",
        subtitle="拖入图片或图片文件夹，批量去底色 / 二值化（可保留印章）",
        panel="RembgPanel",
        pick_label="选择图片",
        progress_noun="张",
        run_label="开始去底色",
        file_filter=IMAGE_FILTER,
        output_suffix="_去底",
        # ⚠️ **两个输入端口**：页面图来自 extract，检测框来自 detect。
        #    此前这里只写了 ("pages",) —— 因为 ports 那层还没接线，写全也没有
        #    任何地方读它，于是"去底色依赖检测框"这件事在声明上是缺失的
        #    （2026-10-03 由 tests/selftests/step_ports.py 的 BPM 依赖检查发现：
        #    把 rembg 提到 detect 前面跑，依赖检查没能拦住它）。
        #    事实依据：任务流程第三步的预览用 ``boxes_provider=self._detect_boxes_for``
        #    叠框，且 area/border 依框而变（``docs/functions/rembg.md``）。
        inputs=("pages", "boxes"),
        outputs=("pages",),
        preview_attr="rembg_viewer",
        # ⚠️ 这一步有**两个动作**：先「生成预览」（跑一步看效果），再
        #    「提交本次任务」（用户确认后才把最终图落到 stages/rembg 供下一步）。
        #    所以按钮文案不是通用的「执行本子任务」，且多一个提交按钮。
        run_button_text="生成预览",
        has_submit=True,
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
        # 导航里不加空格：「生成PDF」一格排下来与其它几项（都无空格）齐平。
        nav_title="生成PDF",
        # 排到导航**最后**（用户 2026-10-03）：这一步吃的是前几步的产物，
        # "生成"是收尾动作。流程条上的第4 步位置不受影响（那是 FLOW_STAGES）。
        nav_order=100,
        nav_tooltip="把成品图按版面合成 PDF",
        nav_icon="svg:PDF_FILE",
        subtitle="拖入成品图文件夹，按版面合成 PDF（页序按文件名）",
        panel="PrintPanel",
        pick_label="选择图片",
        progress_noun="页",
        run_label="生成 PDF",
        file_filter=IMAGE_FILTER,
        artifact_is_file=True,
        output_suffix="_成书",
        inputs=("pages",),
        outputs=("pdf",),
        preview_attr="print_preview",
        run_button_text="生成PDF",
        # 第四步参数最多（版面/页码/字体…），右栏要更宽才不挤。
        control_width=(400, 580),
        # pdf_name / title_text 始终从源 PDF 名派生：历史里存的是旧值或用户
        # 曾经填的自定义名，**不应覆盖**当前任务的规则值（手动挑历史也不回填）。
        history_skip=("pdf_name", "title_text"),
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
        nav_title="图片拼板",
        nav_tooltip="多页图片拼版与版式调整",
        # ⚠️ 别用 PHOTO：一张照片表达不出"多页拼成一版"，而且 PHOTO 同时是
        #    好几个步骤大输入区的图标，导航里再用就没辨识度。TILES 的
        #    四块平铺正是"多页拼版"的形状。
        nav_icon="TILES",
        subtitle="拖入一批图片，拼版后导出成品图（每两张一页）",
        panel="desktop.components.imposition:ImpositionPanel",
        pick_label="选择图片",
        progress_noun="页",
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
FLOW_STAGES: tuple[str, ...] = tuple(spec.key for spec in SPECS if spec.role == "stage")

#: 流程条上的**可选节点** key（排在主链之后的下标处，见
#: ``desktop.store.IMPOSITION_INDEX``）。目前只有拼版一个，故用元组而非单值，
#: 将来加第二个可选节点时不用改调用方。
OPTIONAL_STEPS: tuple[str, ...] = tuple(spec.key for spec in SPECS if spec.role == "optional")

#: 每个 spec 在 ``SPECS`` 里的书写次序（按身份取 key，不依赖 ``__eq__``）——
#: :data:`NAV_STEPS` 排序的次键，见那里的说明。
_nav_written_index: dict[int, int] = {id(spec): i for i, spec in enumerate(SPECS)}

#: 有独立模块页、要进左侧导航的步骤 key——即 ``desktop.modules.MODULES``
#: 的事实来源。
#:
#: 排序 = ``(nav_order, 书写次序)``：显式给了 ``nav_order`` 的按它排、没给的
#: （``0``）保持书写次序兜底。**显式带序号作次键**——只按 ``nav_order`` 排的话
#: Python 的 ``sorted`` 恰好是稳定排序、原序即 ``SPECS`` 书写序，本就是想要的
#: 兜底；把序号写出来是为了让"没声明的维持原位"这条规则**读得出来**，而不是要读者
#: 知道 ``sorted`` 的稳定性质。
NAV_STEPS: tuple[str, ...] = tuple(
    spec.key
    for spec in sorted(
        (s for s in SPECS if s.nav),
        key=lambda s: (s.nav_order, _nav_written_index[id(s)]),
    )
)


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
