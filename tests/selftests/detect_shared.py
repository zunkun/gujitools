# -*- coding: utf-8 -*-
"""detect 步骤同源自测：左右框检测必须只有一份实现。

背景：用户的设计是「detect = 检测图中左右两个文本框」，且
`crop = detect + 裁剪`、`cropremove = detect + 裁剪 + 去底色`。但改造前
`functions/` 下**没有** detect 模块：CLI 在 `TextRegionProcessor` 里直接调
`utils.detect_left_right_boxes`，GUI 在 `desktop/stages/detect_stage.py`
里又各写一遍相同的调用与 `[0][:4]` 取值。三处同算法、零共享。

现在检测的唯一入口是 `functions.detect.detect_page_boxes`，本模块守住：

1. 检测只在 `functions/detect.py` 一处调用 `utils.detect_left_right_boxes`；
2. `TextRegionProcessor`（crop/cropremove 的公共基类）走 detect 模块，不再自调原语；
3. GUI 的 detect 阶段走 detect 模块，不再自调原语；
4. `detect` 已登记为真实命令（工厂可构造、CLI 有子命令）；
5. `extract_first_box` 的边界行为（空列表/None → None）。
"""

NAME = "detect_shared"
DEPENDS: list[str] = []
TITLE = "detect 步骤同源"


def run(ctx) -> None:
    import inspect
    import re
    from pathlib import Path

    from tests.selftests._context import ok

    root = Path(__file__).resolve().parents[2]

    # ---- 1. 只有 detect.py 允许调用 utils.detect_left_right_boxes ----
    callers = []
    for path in root.rglob("*.py"):
        text = str(path)
        if any(part in text for part in ("dist", "build", "__pycache__", "tests")):
            continue
        if path.name == "yolo_utils.py":
            continue  # 定义处
        src = path.read_text(encoding="utf-8", errors="ignore")
        # 只认真正的调用，不认 docstring / 注释里的提及
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "detect_left_right_boxes(" in line:
                callers.append(path.relative_to(root).as_posix())
                break
    ok("只有 functions/detect.py 调用检测原语",
       callers == ["functions/detect.py"], f"实际调用方={callers}")

    # ---- 2. TextRegionProcessor 复用 detect 模块 ----
    from functions import text_region

    tr_src = inspect.getsource(text_region)
    ok("TextRegionProcessor 复用 detect_page_boxes",
       "detect_page_boxes" in tr_src, "crop/cropremove 未走统一检测入口")
    ok("TextRegionProcessor 不再自调检测原语",
       "utils.detect_left_right_boxes(" not in tr_src,
       "基类仍自行调用 utils 检测原语")

    # ---- 3. GUI detect 阶段复用 detect 模块 ----
    from desktop.stages import detect_stage

    ds_src = inspect.getsource(detect_stage)
    ok("GUI detect 阶段复用 detect_page_boxes",
       "detect_page_boxes" in ds_src, "GUI 仍在自行检测")
    ok("GUI detect 阶段不再自调检测原语",
       "utils.detect_left_right_boxes(" not in ds_src,
       "GUI 仍自行调用 utils 检测原语")
    # 曾重复两遍的 [0][:4] 取值应已消失
    ok("GUI 不再重复写 [0][:4] 取值",
       not re.search(r"\[0\]\[:4\]", ds_src), "GUI 仍自带取框逻辑")

    # ---- 4. detect 是真实命令 ----
    from functions import _COMMAND_MAP, get_function
    from core.args import CommandArgs

    ok("detect 已登记进命令工厂", "detect" in _COMMAND_MAP, str(sorted(_COMMAND_MAP)))
    func = get_function("detect", CommandArgs(command="detect", input="."))
    ok("工厂能构造 DetectFunction", func is not None, "get_function('detect') 返回 None")
    from functions.detect import DetectFunction

    ok("构造出的实例类型正确", isinstance(func, DetectFunction), type(func).__name__)

    # detect 默认不落地（outpath=None）；--save 时才产出标注图
    ok("默认构造 detect 时无输出目录（不落地）",
       getattr(func, "outpath", "missing") is None,
       f"outpath={getattr(func, 'outpath', 'missing')}")

    # ---- 5. extract_first_box 边界行为 ----
    from functions.detect import detect_page_boxes, extract_first_box

    ok("空列表 → None", extract_first_box([]) is None)
    ok("None → None", extract_first_box(None) is None)
    # (x1,y1,x2,y2,area) → 只取前 4 个并转 int
    ok("取面积最大框的前 4 个坐标并转 int",
       extract_first_box([(10.7, 20.2, 30.9, 40.1, 999)]) == (10, 20, 30, 40),
       str(extract_first_box([(10.7, 20.2, 30.9, 40.1, 999)])))
    ok("只取 [0]（面积最大者）",
       extract_first_box([(1, 2, 3, 4, 500), (9, 9, 9, 9, 10)]) == (1, 2, 3, 4))

    # 无框图片不应抛异常
    import numpy as np

    blank = np.full((300, 200, 3), 255, np.uint8)
    left, right = detect_page_boxes(blank)
    ok("纯白图不抛异常且两侧为 None", left is None and right is None,
       f"left={left} right={right}")

    # ---- 6. --save：默认不落地、开启才落地 ----
    import tempfile
    from pathlib import Path as _P

    from core.args import CommandArgs
    from functions.detect import DetectFunction
    from utils.box_draw import BOX_COLORS_BGR, box_name

    work = _P(tempfile.mkdtemp(prefix="guji_detect_save_"))
    (work / "a.png").write_bytes(b"")  # 内容无所谓，构造实例不读盘
    (work / "b.png").write_bytes(b"")

    # 默认：save=False 时没有输出目录
    plain = DetectFunction(CommandArgs(command="detect", input=str(work)))
    ok("默认（不带 --save）不设输出目录", plain.outpath is None, str(plain.outpath))
    ok("默认模式 save 标志为假", plain.save is False)

    # 开启：save=True 时算出输出目录。
    # ⚠️ 目录与输入**并列**（`<输入父目录>/detect`），不是嵌在输入目录里——
    # detect 与 crop / rembg / cropremove 是同级步骤，都走
    # `utils.path_utils.resolve_final_output_dir`。曾经的实现写成
    # `self.input / "detect"`（嵌进去），与 crop 不一致，已修正。
    saved = DetectFunction(
        CommandArgs(command="detect", input=str(work), save=True)
    )
    ok("--save 时输出目录与输入目录并列（<父目录>/detect）",
       saved.outpath == work.parent / "detect", str(saved.outpath))
    ok("--save 时输出目录不是嵌套在输入目录内",
       saved.outpath != work / "detect", "又嵌回输入目录里了")
    ok("--save 时输出目录尚未创建（延迟到 execute）",
       not saved.outpath.exists(), "构造即建目录不符合预期")
    ok("默认后缀为 .png", saved.output_suffix == ".png", saved.output_suffix)

    # ---- 6b. --output 只在 --save 时生效，且规则与 crop 一致 ----
    # 这是本次修正的回归点：用户实测 `detect -i .../a/images --save`
    # 期望输出 `.../a/detect`，但旧实现落到 `.../a/images/detect`。
    from utils.path_utils import resolve_final_output_dir

    verifications = [
        (None, work.parent / "detect"),               # 默认：与输入并列
        ("out", work.parent / "out" / "detect"),      # 纯名称：父目录/out/detect
    ]
    for out_arg, expected in verifications:
        got = DetectFunction(
            CommandArgs(command="detect", input=str(work), save=True, output=out_arg)
        ).outpath
        ok(f"--save + output={out_arg!r} 解析正确", got == expected, str(got))

    # 与 crop 在同一输入下的解析结果必须只差「子目录名」
    crop_like = resolve_final_output_dir(work, None, False, "crop")
    detect_like = resolve_final_output_dir(work, None, False, "detect")
    ok("detect 与 crop 的目录规则同源（仅子目录名不同）",
       crop_like.parent == detect_like.parent,
       f"crop={crop_like} detect={detect_like}")

    # 不带 --save 时，即使给了 --output 也不计算、不落地
    no_save = DetectFunction(
        CommandArgs(command="detect", input=str(work), output="shouldNotMatter")
    )
    ok("不带 --save 时 --output 不生效（outpath 仍为 None）",
       no_save.outpath is None, str(no_save.outpath))

    # ---- 7. 画框：颜色与 GUI 约定一致，且跳过 None 框 ----
    import numpy as np2

    from utils.box_draw import draw_boxes

    canvas = np2.full((200, 200, 3), 255, np.uint8)
    only_left = draw_boxes(canvas, [(10, 10, 50, 50), None])
    # 采左侧边（顶边被标注文字的白底覆盖，属预期设计）
    ok("只画左框时左框边上是绿色", tuple(only_left[30, 10]) == BOX_COLORS_BGR[0],
       str(only_left[30, 10]))
    ok("左框底边同样是绿色", tuple(only_left[50, 30]) == BOX_COLORS_BGR[0],
       str(only_left[50, 30]))
    # None 框被跳过：右框序号不串位，右侧区域保持原样
    ok("None 框被跳过，右侧无残留画痕",
       tuple(only_left[30, 150]) == (255, 255, 255), str(only_left[30, 150]))
    both = draw_boxes(canvas, [(10, 10, 50, 50), (100, 10, 150, 50)])
    ok("右框边上是蓝色", tuple(both[30, 100]) == BOX_COLORS_BGR[1], str(both[30, 100]))
    ok("左框名/右框名与 GUI 一致", (box_name(0), box_name(1)) == ("左框", "右框"),
       f"{box_name(0)},{box_name(1)}")

    # ---- 8. 标注标签用中文（有中文字体时），无字体时降级不崩 ----
    from utils.box_draw import find_cjk_font

    font = find_cjk_font()
    ok("中文字体探测有确定结果（路径或 None）",
       font is None or _P(font).exists(), str(font))
    labeled = draw_boxes(canvas, [(10, 10, 50, 50)])
    ok("画框后图像尺寸不变", labeled.shape == canvas.shape, str(labeled.shape))
    ok("画框不修改入参原图", tuple(canvas[30, 10]) == (255, 255, 255),
       "draw_boxes 污染了输入图像")
    import shutil as _sh

    _sh.rmtree(work, ignore_errors=True)

    # ---- 9. 命令行空跑拦截：detect 不带 --save 直接拒绝 ----
    # 命令行下 detect 不落盘 = 没有任何产出，纯属白算一趟；
    # 但代码调用（crop/cropremove 的中间步骤、GUI detect 阶段）必须照常可用，
    # 所以拦截只放在 CLI 入口，不进 CommandArgs.validate()。
    from cli.__main__ import _reject_dry_run

    # 拦截会打印一大段中文提示，压掉以免污染自测输出
    import contextlib as _ctx
    import io as _io

    def _quiet_reject(cmd, cargs):
        with _ctx.redirect_stdout(_io.StringIO()):
            return _reject_dry_run(cmd, cargs)

    ok("无 --save 的命令行 detect 被拒绝",
       _quiet_reject("detect", CommandArgs(command="detect", input=".")) is True,
       "空跑未被拦截")
    ok("有 --save 的命令行 detect 放行",
       _quiet_reject(
           "detect", CommandArgs(command="detect", input=".", save=True)
       ) is False,
       "带 --save 却被拦截")
    ok("--save 来自配置文件时同样放行（run detect）",
       _quiet_reject("detect", CommandArgs(command="detect", input=".", save=True))
       is False)
    for other in ("crop", "rembg", "cropremove", "extract"):
        ok(f"{other} 不受空跑拦截影响",
           _quiet_reject(other, CommandArgs(command=other, input=".")) is False,
           f"{other} 被误拦")

    # 拦截必须**没有副作用**：不能因为拒绝就建目录/写文件
    _before = set(_P(".").iterdir())
    _quiet_reject("detect", CommandArgs(command="detect", input="."))
    ok("拦截本身不产生任何文件",
       set(_P(".").iterdir()) == _before, "拒绝路径上产生了磁盘副作用")

    # 提示文本必须真的给出可执行的替代方案，而不是干巴巴一句报错
    _hint = _io.StringIO()
    with _ctx.redirect_stdout(_hint):
        _reject_dry_run("detect", CommandArgs(command="detect", input="."))
    _msg = _hint.getvalue()
    ok("拒绝提示写明缺失的是 --save", "--save" in _msg, _msg[:80])
    ok("拒绝提示给出 crop / cropremove 替代路径",
       "cropremove" in _msg and "crop" in _msg, _msg[:80])
    ok("拒绝提示说明代码调用不受限",
       "detect_page_boxes" in _msg, _msg[:80])

    # 关键约束：validate() 不得强制 save（否则 GUI detect 阶段会被拦死）
    # ⚠️ 必须剥掉 docstring 只查**函数体**——校验器的文档里正是在解释
    # 「为什么不在这里强制 save」，直接搜整段源码会假失败。
    import ast as _ast
    import core.command_spec as _cs

    _fn = _ast.parse(inspect.getsource(_cs._validate_detect).strip()).body[0]
    _body = [
        node for node in _fn.body
        if not (isinstance(node, _ast.Expr) and isinstance(node.value, _ast.Constant))
    ]
    _body_src = _ast.unparse(_body)
    ok("validate() 的函数体不读取 save（GUI 不落盘也要能过）",
       "save" not in _body_src, f"校验器体里出现了 save：{_body_src}")
    ok("validate() 仍正常校验 detect 的 ext",
       "_check_choice" in _body_src, _body_src)

    # GUI 的 detect 阶段不落盘，必须与 CLI 拦截解耦
    from desktop.stages import detect_stage as _ds

    ok("GUI detect 阶段不经过 CLI 拦截",
       "_reject_dry_run" not in inspect.getsource(_ds), "GUI 被 CLI 规则污染")

