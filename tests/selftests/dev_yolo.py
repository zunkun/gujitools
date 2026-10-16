# -*- coding: utf-8 -*-
"""开发者模式与「导出YOLO标注」自测（用户 2026-10-16 提的功能）。

守护五件事：

1. **设置页**：左侧栏底部「设置」进得去，里面两张 ``SwitchSettingCard``
   分别绑到两个配置项上；「启用YOLO标注」是开发者模式的**下级**（关掉开发者
   模式它就藏起来）；
2. **壳层入口**：导航栏底部有「设置」条目，真点它能切过去（``clicked(bool)``
   的坑：槽不吞那个 bool 就会把 ``True`` 当 key，导航静默退回任务管理）；
3. **导出服务（纯函数）**：类别号（左/右 → 0 harfcontent、整幅 → 1
   fullcontent）、归一化公式、无框页写空标签（负样本）、源图不在了要**跳过
   而不是**当负样本；
4. **落点与命名**：``<导出目录>/<名称>/{images,labels}/<名称>-<页序>.…``，
   图片按页序复制过去、非法字符被洗掉；
5. **两个宿主页**：独立「检测文本框」右栏底部与任务流程第二步右栏底部都有
   「导出YOLO标注」，且只在"开发者模式 + YOLO 开关"都打开时出现。

⚠️ 配置项一律**直接改 ``item.value``**（不落盘）；只有"点开关能不能写回配置项"
那一条走 ``qconfig.set``，且先把 ``qconfig.save`` 换成空实现——不然自测会把
开关写进用户的真实 ``~/Documents/guji/config.json``。
"""

from __future__ import annotations

from pathlib import Path

NAME = "dev_yolo"
DEPENDS: list[str] = ["tasklist"]
TITLE = "开发者模式与导出YOLO标注"

W, H = 1000, 800
LEFT = [40, 100, 460, 700]
RIGHT = [540, 100, 960, 700]
FULL = [20, 40, 980, 760]


def _png(path: Path, width: int = W, height: int = H) -> Path:
    """造一张纯色 PNG（用 Qt 现场编码，不把 cv2 拖进 GUI 主进程）。"""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    # ⚠️ PySide6 把 QImage.save 的 format 标注成 bytes 系，运行期收 str
    image.save(str(path), "PNG")  # type: ignore[reportCallIssue]
    return path


def run(ctx) -> None:  # noqa: ARG001 - 用 ctx 的窗口，不共享它的夹具
    from qfluentwidgets import qconfig

    from desktop.settings.config import app_config
    from tests.selftests._context import ok

    tmp = Path(ctx.tmp) / "dev_yolo"
    tmp.mkdir(parents=True, exist_ok=True)
    cfg = app_config()
    before = (bool(cfg.developerMode.value), bool(cfg.yoloAnnotation.value))
    try:
        _check_settings_page(ctx, cfg, ok, qconfig)
        _check_shell_entry(ctx, ok)
        _check_service(tmp, ok)
        _check_store(ctx, ok)
        _check_dialog_defaults(ok)
        _check_module_page(ctx, cfg, tmp, ok)
        _check_detail_page(ctx, cfg, tmp, ok)
    finally:
        cfg.developerMode.value = before[0]
        cfg.yoloAnnotation.value = before[1]


# ------------------------------------------------------------------ ① 设置页
def _check_settings_page(ctx, cfg, ok, qconfig) -> None:
    page = ctx.w.shell.settings_page()
    ok("设置页能构造", page is not None)
    ok("设置页标题/副标题是「设置」", page.TITLE == "设置", page.TITLE)
    ok("「启用开发者模式」卡片绑到配置项",
       page.dev_card.configItem is cfg.developerMode)
    ok("「启用YOLO标注」卡片绑到配置项",
       page.yolo_card.configItem is cfg.yoloAnnotation)

    # 开发者模式关闭 → YOLO 那张卡藏起来（它是下级选项）
    cfg.developerMode.value = False
    ctx.app.processEvents()
    ok("开发者模式关 → 「启用YOLO标注」藏起来", page.yolo_card.isHidden())
    cfg.developerMode.value = True
    ctx.app.processEvents()
    ok("开发者模式开 → 「启用YOLO标注」出现", not page.yolo_card.isHidden())

    # 点开关真的会写回配置项（⚠️ 先把落盘换成空实现，别写用户真实配置）
    saved = qconfig.save
    qconfig.save = lambda *a, **k: None  # type: ignore[method-assign]
    try:
        page.yolo_card.setChecked(True)
        ok("点开关写回配置项（True）", cfg.yoloAnnotation.value is True)
        page.yolo_card.setChecked(False)
        ok("再点一下写回配置项（False）", cfg.yoloAnnotation.value is False)
    finally:
        qconfig.save = saved  # type: ignore[method-assign]


# ------------------------------------------------------------------ ② 壳层入口
def _check_shell_entry(ctx, ok) -> None:
    from desktop.shell import ROUTE_SETTINGS, ROUTE_TASKS

    shell = ctx.w.shell
    ok("导航栏底部有「设置」条目",
       getattr(shell, "_settings_item", None) is not None)
    ok("设置页在导航里是底部分组（不混进步骤那一列）",
       ROUTE_SETTINGS not in {key for key in shell._module_items})
    shell.show_settings()
    ctx.app.processEvents()
    ok("show_settings 后路由 = settings",
       shell.current_route() == ROUTE_SETTINGS, shell.current_route())
    ok("导航高亮跟到设置", shell.selected_route() == ROUTE_SETTINGS,
       shell.selected_route())
    # ⚠️ 真点：qfluentwidgets 的 clicked 是 Signal(bool)，槽不吞那个 bool 时
    #    key 会收到 True ⇒ 静默退回任务管理（模块条目踩过这个坑）
    shell._settings_item.click()
    ctx.app.processEvents()
    ok("真点导航条目也能切到设置",
       shell.current_route() == ROUTE_SETTINGS, shell.current_route())
    shell._tasks_item.click()
    ctx.app.processEvents()
    ok("点回任务管理", shell.current_route() == ROUTE_TASKS, shell.current_route())


# ------------------------------------------------------------ ③ 导出服务（纯函数）
def _check_service(tmp: Path, ok) -> None:
    from desktop.services.detect_export import (
        export_yolo,
        yolo_dataset_dir,
        yolo_entries,
        yolo_label_lines,
    )

    half = yolo_label_lines([LEFT, RIGHT], (W, H)) or []
    full = yolo_label_lines([FULL], (W, H)) or []
    ok("半幅两个框都写 0 号（harfcontent）",
       [line.split()[0] for line in half] == ["0", "0"], str(half))
    ok("标签行 = 「类别 cx cy w h」（归一化、6 位小数）",
       half[0] == "0 0.250000 0.500000 0.420000 0.750000", half[0])
    ok("整幅框写 1 号（fullcontent）", full[0].startswith("1 "), full[0])
    ok("无框页 → 空标签（负样本）", yolo_label_lines([], (W, H)) == [])
    ok("有框但尺寸读不出来 → None（跳过，不是当负样本）",
       yolo_label_lines([LEFT], None) is None)
    ok("名称里的非法字符会被洗掉（它要当目录名 + 文件名前缀）",
       yolo_dataset_dir(tmp, "a/b:c").name == "a-b-c",
       yolo_dataset_dir(tmp, "a/b:c").name)

    # ---- 端到端：两张图（一张有框、一张无框）+ 一张源图已不在 ----
    pages = tmp / "svc_pages"
    first = _png(pages / "0001.png")
    second = _png(pages / "0002.png")
    gone = pages / "0003.png"
    entries = yolo_entries([first, second, gone], {"0001": [LEFT, RIGHT]})
    ok("yolo_entries 一张不落（含无框页）", len(entries) == 3, str(len(entries)))

    dest = tmp / "svc_out"
    summary = export_yolo(entries, dest, "b1", task_id="0020", source="古籍样例.pdf")
    folder = dest / "b1"
    ok("父节点目录 = <导出目录>/<名称>", folder.is_dir(), str(folder))
    ok("图片按页序复制过来（b1-1 / b1-2，保留原后缀）",
       (folder / "images" / "b1-1.png").is_file()
       and (folder / "images" / "b1-2.png").is_file(),
       str(sorted(p.name for p in (folder / "images").iterdir())))
    ok("有框页的标签是 <名称>-1.txt 且内容归一化",
       (folder / "labels" / "b1-1.txt").read_text(encoding="utf-8")
       == "0 0.250000 0.500000 0.420000 0.750000\n"
       + "0 0.750000 0.500000 0.420000 0.750000\n",
       repr((folder / "labels" / "b1-1.txt").read_text(encoding="utf-8")))
    ok("无框页写**空**标签（负样本）",
       (folder / "labels" / "b1-2.txt").read_text(encoding="utf-8") == "")
    ok("源图不在了 → 跳过，且**不**给它补空标签",
       summary["skipped"] == ["0003.png"]
       and not (folder / "labels" / "b1-3.txt").exists(),
       f"skipped={summary['skipped']}")
    ok("统计：1 页有框（2 个框）、1 页负样本",
       (summary["labeled"], summary["boxes"], summary["empty"]) == (1, 2, 1),
       str({k: summary[k] for k in ("labeled", "boxes", "empty")}))

    # ---- 切片凭据 data.json（用户 2026-10-16：任务编号写进去）----
    from desktop.services.detect_export import SLICE_META_NAME
    from utils.box_geometry import YOLO_CLASS_NAMES

    meta_path = folder / SLICE_META_NAME
    ok("导出一并写了切片凭据 data.json", meta_path.is_file(), str(meta_path))
    if meta_path.is_file():
        import json as _json

        meta = _json.loads(meta_path.read_text(encoding="utf-8"))
        ok("凭据里带上了任务号与源",
           meta.get("task_id") == "0020" and meta.get("source") == "古籍样例.pdf",
           str({k: meta.get(k) for k in ("task_id", "source")}))
        ok("凭据记下类别顺序（与代码里的唯一来源一致）",
           meta.get("class_names") == list(YOLO_CLASS_NAMES),
           str(meta.get("class_names")))
        ok("凭据记下了统计与跳过的页",
           (meta.get("pages"), meta.get("labeled"), meta.get("empty")) == (3, 1, 1)
           and meta.get("skipped") == ["0003.png"],
           str(meta))
    # 校验工具按这个文件名去读凭据，两处必须同名（工具不 import desktop，字面量写死）
    from desktop.utils.files import project_root

    tool_src = (project_root() / "tools" / "check_yolo_dataset.py").read_text(
        encoding="utf-8"
    )
    ok("校验工具认的凭据文件名与导出的同一个",
       f'SLICE_META_NAME = "{SLICE_META_NAME}"' in tool_src,
       "tools/check_yolo_dataset.py 里没写 SLICE_META_NAME = "
       f'"{SLICE_META_NAME}"')


# ------------------------------------------------- ③b 按任务记住名称 + 导出目录
def _check_store(ctx, ok) -> None:
    """「跟任务绑定」：名称与导出目录都记在 ``tasks/<id>/ui.json`` 里。"""
    from desktop.store.json_io import read_json, write_json

    repo = ctx.repo
    if not ctx.tid:
        print("    （跳过：本轮没有主任务，测不了任务级记忆）")
        return
    path = repo.ui_state_path(ctx.tid)
    before_doc = read_json(path, None)
    before_doc = dict(before_doc) if isinstance(before_doc, dict) else {}
    before_stage = repo.load_last_stage(ctx.tid)
    try:
        ok("没记过时给两个空串（调用方据此回落默认值）",
           repo.load_yolo_export_state(ctx.tid) == {"name": "", "directory": ""},
           str(repo.load_yolo_export_state(ctx.tid)))
        repo.save_yolo_export_state(ctx.tid, "b1", "D:/ds/bookcontent")
        state = repo.load_yolo_export_state(ctx.tid)
        ok("名称与导出目录都记住了",
           state == {"name": "b1", "directory": "D:/ds/bookcontent"}, str(state))
        ok("写这两项不动同一个文件里的 last_stage",
           repo.load_last_stage(ctx.tid) == before_stage,
           f"{repo.load_last_stage(ctx.tid)} vs {before_stage}")
        ok("不存在的任务不写（不把已删任务重新创建出来）",
           repo.save_yolo_export_state("9999", "b1", "D:/ds") is False)
    finally:
        # ⚠️ 直接改 ui.json 还原（走 save_* 还原不了：目录为空时它按约定拒写）
        write_json(path, before_doc)


# ---------------------------------------------------- ③c 弹窗的默认值
def _check_dialog_defaults(ok) -> None:
    """用户 2026-10-16：导出目录默认 ``~/Documents``；空值也必须非空。"""
    from desktop.components.yolo_export_dialog import YoloExportPanel
    from desktop.utils.files import default_open_dir

    expected = str(default_open_dir())
    panel = YoloExportPanel()
    ok("导出目录为空时默认文档目录（~/Documents）",
       panel.directory() == expected, f"{panel.directory()} vs {expected}")
    panel2 = YoloExportPanel("D:/ds", "0020")
    ok("给了值就用给的值（回填优先）", panel2.values() == ("0020", "D:/ds"),
       str(panel2.values()))


# ---------------------------------------------------- ④ 独立「检测文本框」模块页
def _check_module_page(ctx, cfg, tmp: Path, ok) -> None:
    from desktop.modules.detect.page import DetectModulePage
    from tests.selftests._context import wait_until
    import desktop.modules.detect.page as page_module

    pages = tmp / "module_pages"
    first = _png(pages / "0001.png")
    second = _png(pages / "0002.png")
    page = DetectModulePage()
    original = page_module.ask_yolo_export
    # ⚠️ 导出成功会真去 `os.startfile` 打开资源管理器（用户 2026-10-16 的要求），
    #    离屏自测跑起来会真的弹窗——换成记录器，只记"打开了哪个目录"。
    original_reveal = page_module.reveal_dir
    opened: list = []
    page_module.reveal_dir = lambda path: (opened.append(str(path)), True)[1]
    # ⚠️ 这个记忆文件落在**真实数据目录**（singletask 缓存区，自测不重定向它）：
    #    进来先存一份，收工还原，别把测试前缀留在用户机器上。
    state_path = page._yolo_export_state_path()
    previous_state = state_path.read_text(encoding="utf-8") if state_path.is_file() else None
    try:
        page.control.set_source(pages)
        page.viewer.set_images([first, second])
        ctx.app.processEvents()

        ok("摆出「导出YOLO标注」按钮（排在导出区最底部）",
           page.yolo_button.text() == "导出YOLO标注", page.yolo_button.text())
        cfg.developerMode.value = False
        cfg.yoloAnnotation.value = False
        ctx.app.processEvents()
        ok("两个开关都关着 → 按钮不显示", page.yolo_button.isHidden())
        cfg.developerMode.value = True
        ok("只开开发者模式 → 仍不显示", page.yolo_button.isHidden())
        cfg.yoloAnnotation.value = True
        ctx.app.processEvents()
        ok("两个开关都打开 → 按钮出现", not page.yolo_button.isHidden())

        page._boxes["0001"] = [LEFT, RIGHT]
        page._origins["0001"] = "manual"
        page._sync_export_buttons()
        ok("有框 → 导出按钮解禁", page.yolo_button.isEnabled())

        # ---- 第一次弹窗：还没记过 → 名称回落源目录名、导出目录留空 ----
        seen: list = []
        page_module.ask_yolo_export = lambda *a, **k: (seen.append(k), None)[1]
        page.export_yolo_labels()
        ok("弹窗取消 → 不启动导出", not page._export_kernel.busy())
        ok("弹窗拿到两个回填参数", len(seen) == 1, str(seen))
        ok("没记过时：目录回落文档目录、名称回落源目录名",
           seen[0].get("directory") is None  # 面板自己兜底成 ~/Documents
           and seen[0].get("name") == pages.name,
           str(seen[0]))

        # ---- 第二次：确认 → 真的导出，并把名称 + 目录记下来 ----
        dest = tmp / "module_out"
        page_module.ask_yolo_export = lambda *a, **k: ("b9", str(dest))
        page.export_yolo_labels()
        done = wait_until(
            ctx.app, lambda: not page._export_kernel.busy(), timeout=60
        )
        ok("导出线程正常结束", done, "线程仍在跑")
        folder = dest / "b9"
        ok("导出到 <导出目录>/<名称>/images 与 labels",
           (folder / "images" / "b9-1.png").is_file()
           and (folder / "labels" / "b9-1.txt").is_file(),
           str(folder))
        ok("无框的第 2 页也导了（图片 + 空标签 = 负样本）",
           (folder / "images" / "b9-2.png").is_file()
           and (folder / "labels" / "b9-2.txt").read_text(encoding="utf-8") == "")
        ok("导出后按钮恢复可点", page.yolo_button.isEnabled())
        ok("导出成功后打开了导出目录（用户 2026-10-16）",
           opened == [str(folder)], str(opened))
        # 独立页没有任务号：凭据里 task_id 为空、source 记的是源名
        import json as _json

        meta = _json.loads(
            (folder / "data.json").read_text(encoding="utf-8")
        )
        ok("独立页导出的凭据：没有任务号，但记下了源名",
           meta.get("task_id") == "" and meta.get("source") == pages.name,
           str({k: meta.get(k) for k in ("task_id", "source")}))
        ok("名称与导出目录都记下来了（跟这一次导出绑定）",
           page._load_yolo_export_state()
           == {"name": "b9", "directory": str(dest)},
           str(page._load_yolo_export_state()))

        # ---- 第三次：再点一次，弹窗回填的就是上次记住的那一份 ----
        seen.clear()
        page_module.ask_yolo_export = lambda *a, **k: (seen.append(k), None)[1]
        page.export_yolo_labels()
        ok("再点一次时弹窗回填上次记住的名称与导出目录",
           seen[0].get("name") == "b9" and seen[0].get("directory") == str(dest),
           str(seen[0]))
    finally:
        page_module.ask_yolo_export = original
        page_module.reveal_dir = original_reveal
        page.shutdown_workers()
        page.deleteLater()
        if previous_state is None:
            state_path.unlink(missing_ok=True)
        else:
            state_path.write_text(previous_state, encoding="utf-8")


# ------------------------------------------------------ ⑤ 任务流程第二步右栏
def _check_detail_dialog_defaults(d, ctx, ok) -> None:
    """没记过时弹窗回填什么：名称 = **任务号**、目录留空（面板兜 ~/Documents）。"""
    import desktop.pages.taskdetail.detect as detect_module

    if not d._manifest_paths():
        print("    （跳过：本任务还没有页面清单，走不到弹窗那一步）")
        return
    seen: list = []
    original = detect_module.ask_yolo_export
    # 弹的是真模态窗（离屏会把用例挂住）——换成记录器，只记"回填了什么"
    detect_module.ask_yolo_export = lambda *a, **k: (seen.append(k), None)[1]
    try:
        d.export_yolo_labels()
    finally:
        detect_module.ask_yolo_export = original
    ok("没记过时弹窗回填：名称 = b+任务号、目录留空",
       len(seen) == 1
       and seen[0].get("name") == f"b{ctx.tid}"
       and seen[0].get("directory") is None,
       str(seen))


def _check_detail_export_request(d, ctx, tmp, ok) -> None:
    """任务流程那条链起导出时，**请求里必须带任务号**（要写进 data.json）。

    用替身内核接住请求（不真跑），断的是"喂给 export_yolo 的参数对不对"。
    """
    import desktop.pages.taskdetail.detect as detect_module

    if not d._manifest_paths():
        print("    （跳过：本任务还没有页面清单，走不到起导出那一步）")
        return

    class _FakeKernel:
        """替身内核：记下 request，不真跑（真跑会复制几百张图）。"""

        def __init__(self) -> None:
            self.request = None

        @staticmethod
        def busy() -> bool:
            return False

        def run(self, request) -> bool:
            self.request = request
            return True

    fake = _FakeKernel()
    originals = (detect_module.ask_yolo_export, d._ensure_yolo_kernel)
    detect_module.ask_yolo_export = lambda *a, **k: ("b7", str(tmp / "detail_out"))
    d._ensure_yolo_kernel = lambda: fake  # type: ignore[method-assign]
    try:
        d.export_yolo_labels()
    finally:
        detect_module.ask_yolo_export, d._ensure_yolo_kernel = originals
    args = (fake.request.args if fake.request is not None else {})
    ok("起导出时请求里带了任务号（写进 data.json 的那一项）",
       args.get("task_id") == ctx.tid, str(args.get("task_id")))
    ok("起导出时请求里也带了源文件名", bool(args.get("source")), str(args.get("source")))
    ok("导出目录来自弹窗（名称 b7 → 目录 <导出目录>/b7）",
       fake.request is not None
       and str(fake.request.dest) == str(tmp / "detail_out"),
       str(fake.request.dest if fake.request is not None else None))

    # ---- 导出过一次之后，**下次进来回填的是这次改过的名字** ----
    saved = ctx.repo.load_yolo_export_state(ctx.tid)
    ok("导出成功后按任务记住了改过的名称（b7）",
       saved.get("name") == "b7", str(saved))
    seen: list = []
    originals = (detect_module.ask_yolo_export, d._ensure_yolo_kernel)
    detect_module.ask_yolo_export = lambda *a, **k: (seen.append(k), None)[1]
    d._ensure_yolo_kernel = lambda: fake  # type: ignore[method-assign]
    try:
        d.export_yolo_labels()
    finally:
        detect_module.ask_yolo_export, d._ensure_yolo_kernel = originals
    ok("再进弹窗回填的还是上次那个名字（不会被 b+任务号 盖回去）",
       seen and seen[0].get("name") == "b7", str(seen))


def _check_detail_page(ctx, cfg, tmp: Path, ok) -> None:
    d = ctx.d
    ok("详情页有「导出YOLO标注」卡片", hasattr(d, "yolo_export_card"))
    ok("详情页默认藏起这张卡（开发者模式关着）", d.yolo_export_card.isHidden())
    ok("卡片上的按钮文案是「导出YOLO标注」",
       d.yolo_export_button.text() == "导出YOLO标注",
       d.yolo_export_button.text())

    if not ctx.tid:
        print("    （跳过：本轮没有主任务，测不了「第二步才显示」）")
        return
    if d.task_id != ctx.tid and not d.set_task(ctx.tid):
        print("    （跳过：set_task 没成功，详情页没落到这个任务上）")
        return
    bar = d.bar_index_of_step("detect")
    if bar is None:
        print("    （跳过：本任务的流程里没有「检测文本框」这一步）")
        return

    ok("「名称」默认值 = b + 任务号（如 b0020，用户 2026-10-16）",
       d._yolo_dataset_name() == f"b{ctx.tid}", d._yolo_dataset_name())

    cfg.developerMode.value = True
    cfg.yoloAnnotation.value = True
    # 把"上次记住的那一份"清成空，才能测"没记过时回填什么"
    from desktop.store.json_io import read_json, write_json

    state_path = ctx.repo.ui_state_path(ctx.tid)
    before_doc = read_json(state_path, None)
    before_doc = dict(before_doc) if isinstance(before_doc, dict) else {}
    write_json(
        state_path,
        {**before_doc, "yolo_export_name": "", "yolo_export_dir": ""},
    )
    try:
        _check_detail_dialog_defaults(d, ctx, ok)
        _check_detail_export_request(d, ctx, tmp, ok)
    finally:
        write_json(state_path, before_doc)
    d._select_stage(bar)
    ctx.app.processEvents()
    ok("两个开关都开 + 停在第二步 → 卡片出现", not d.yolo_export_card.isHidden())
    cfg.developerMode.value = False
    ctx.app.processEvents()
    ok("开发者模式一关 → 卡片立刻收起", d.yolo_export_card.isHidden())
    cfg.developerMode.value = True
    ctx.app.processEvents()
    ok("再开回来 → 卡片又出现（同一步不用切页）",
       not d.yolo_export_card.isHidden())


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
