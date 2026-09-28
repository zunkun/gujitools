"""YOLO 检测封装：模型加载与页面内容框检测。

此模块封装了 YOLO 目标检测模型的使用，提供两个核心功能：

1. **模型加载** (`load_yolo_model`)
   延迟加载 + 模块级单例 + 双重检查锁，确保多线程下模型只加载一次。
   权重文件查找路径: `gujitools/weights/bookcontent.pt`。

2. **页面内容框检测** (`detect_content_boxes`)
   权重 `weights/bookcontent.pt` 是**两类**模型，两类对一页而言互斥：

   - ``harfcontent``（半幅，即原 `bookcontent` 改名）——双栏排版中的**一栏**。
     双页扫描时一页出左右两栏，故按检测框水平中心与图像中线的关系分为
     left / right 两组，供 crop / cropremove 使用；
   - ``fullcontent``（整幅）——整页只有一个内容区（单页排版）。它**只有
     一个框**，不参与左右分割，否则会被中线误判成某一半。

   ⚠️ **类别名决定路由，不靠几何猜**：`harfcontent` 的框宽实测约 43%、
   `fullcontent` 约 95%，但单栏书的 ``harfcontent`` 框也可能横跨整幅
   （实测最宽 98.5%）。用宽度阈值区分二者并不可靠，所以一律按模型的
   **类别号**路由（类别号由 `model.names` 按**类名**解析，见
   :func:`_content_class_ids`）。

   模型偶尔会在同一页同时给出两类（实测把推理尺寸调到 1280 时会出现
   「整幅-半幅-整幅-半幅」四个框），因此检测后按**互斥规则**强制消解
   （见 :func:`resolve_content_boxes`）：窄整幅剔除 → 双半幅压制整幅 →
   单半幅与整幅比置信度。返回结果保证两类互斥，`notes` 说明触发了哪条规则。

左右分割算法（仅对半幅）:
    以图像宽度一半为分界线，检测框中心 cx < w/2 归入 left，否则归入 right。
    每组按面积降序排序，调用方取 [0] 即可获得最大候选框。
"""

import os
import sys
import time
import types
import threading
import warnings
from pathlib import Path
from importlib.machinery import ModuleSpec
from typing import List, NamedTuple, Tuple

import numpy as np

# ---------------------------------------------------------------- 启动开关
# 本项目只用本地权重推理：不需要 ultralytics 去查 PyPI、上报匿名事件，更不需要
# 它在依赖缺失时按需 `pip install` —— 打包成 exe 之后往用户环境装包是灾难。
#
# ⚠️ 这里原先写的是 `ULTRALYTICS_SKIP_UPDATE_CHECK`，但 ultralytics 源码里**根本
#    没有这个字符串**（`grep -rn SKIP_UPDATE_CHECK` 零命中），是一条从未生效过的
#    死代码。它真正读的是下面这几个；用 setdefault 以便外部按需覆盖。
os.environ.setdefault("YOLO_OFFLINE", "true")
os.environ.setdefault("YOLO_AUTOINSTALL", "false")


def _stub_unneeded_modules():
    """注入 import hook，使 ultralytics 训练模块导入 matplotlib/scipy/pandas 时不报错。

    ultralytics.models.__init__ 会导入 fastsam → yolo.semantic.train，
    后者顶层 `import matplotlib` / `import matplotlib.pyplot`。
    推理不调用这些训练函数，只需导入通过即可。
    PyInstaller 排除这些重依赖后，hook 自动生成空壳模块使导入成功。
    """

    class _Stub(types.ModuleType):
        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return _Stub(f"{self.__name__}.{name}")

        def __call__(self, *a, **kw):
            return None

    _STUB_PACKAGES = ("matplotlib", "scipy", "pandas")

    class _StubFinder:
        def find_spec(self, fullname, path=None, target=None):
            """现代 import hook API（Python 3.4+），返回 ModuleSpec 而非 loader。

            返回带 is_package=True 的 spec，使子模块导入（如 matplotlib.pyplot）
            也能被此 finder 拦截。__spec__ 非 None 避免 torch._dynamo 调用
            importlib.util.find_spec() 时抛 ValueError。
            """
            if fullname.split(".")[0] in _STUB_PACKAGES:
                return ModuleSpec(fullname, _StubLoader(_Stub), is_package=True)
            return None

    class _StubLoader:
        """配合 find_spec 的 loader，创建 stub 模块并注入 sys.modules。"""

        def __init__(self, stub_cls):
            self._stub_cls = stub_cls

        def create_module(self, spec):
            mod = self._stub_cls(spec.name)
            mod.__path__ = []
            mod.__file__ = None
            mod.__spec__ = spec
            return mod

        def exec_module(self, module):
            pass

    finder = _StubFinder()
    sys.meta_path.insert(0, finder)
    for name in _STUB_PACKAGES:
        if name not in sys.modules:
            spec = ModuleSpec(name, _StubLoader(_Stub), is_package=True)
            mod = _Stub(name)
            mod.__path__ = []
            mod.__file__ = None
            mod.__spec__ = spec
            sys.modules[name] = mod


def _silence_pruned_source_warnings() -> None:
    """静音 torch 因「源码被瘦身删掉」而逐条发出的 overload 警告。

    构建期 `build.py::prune_bloat()` 会把 ``_internal/torch/**/*.py`` 归档掉
    （它们与 PYZ 里的字节码重复，省约 48MB）。代价是 ``torch/_jit_internal.py``
    在导入时对每个 ``@torch.jit._overload`` 定义做的 ``inspect.getsource()``
    校验必然失败，于是逐条发 UserWarning —— frozen 下实测 **26 条**，会在 GUI
    日志里刷屏，而用户对这些内容完全无能为力。

    实测「失败」比「成功」**快 6 倍**（0.91ms vs 5.79ms/次；成功还要 ast.parse
    整个源文件），所以正确做法是保持瘦身、在这里提前静音，而不是把源码加回产物
    （那样又慢又大）。本项目只用 YOLO 推理、不做 ``torch.jit.script``，缺源码对
    功能没有影响。

    必须在导入 torch / ultralytics **之前**调用：这些警告发生在 import 链上。
    """
    warnings.filterwarnings(
        "ignore",
        message=r"Unable to retrieve source for @torch\.jit\._overload function",
    )


# 模块级单例：已加载的 YOLO 模型实例
_YOLO_MODEL = None
# 线程锁：保护多线程下的首次加载
_YOLO_LOCK = threading.Lock()
#: 本进程**实际执行加载**时花掉的秒数（未加载过为 0.0）。
#: 用它的调用方（常驻服务）要把这笔开销单独报出来——它必须能被单独计时，
#: 否则会落到"第一张图"的耗时里，看起来像某一张特别慢。
_LOAD_SECONDS = 0.0
#: 推理设备（load_yolo_model 里定，有 CUDA 用 GPU；见 _resolve_yolo_device）
_YOLO_DEVICE = "cpu"


def model_path() -> Path:
    """YOLO 权重文件路径（候选表只保留这一份）。

    权重路径同时被三处用到——真正加载模型、给用户打印、以及常驻 YOLO 服务的
    身份指纹（见 `functions/yolo_service.py`）。三处各写一遍候选列表迟早会
    漂移，所以统一收在这里。

    返回:
        `gujitools/weights/bookcontent.pt` 的绝对路径。

    异常:
        FileNotFoundError: 权重文件不存在（打包遗漏或安装损坏）。
    """
    project_root = Path(__file__).resolve().parents[1]
    candidate = project_root / "weights" / "bookcontent.pt"
    if not candidate.exists():
        raise FileNotFoundError(
            "未找到 YOLO 模型权重文件 bookcontent.pt。\n"
            "请将 bookcontent.pt 放置在以下位置：\n"
            f"  - {candidate}"
        )
    return candidate


def is_model_loaded() -> bool:
    """本进程是否已加载过 YOLO（常驻服务用它对外汇报，便于确认复用）。"""
    return _YOLO_MODEL is not None


def load_seconds_used() -> float:
    """本进程**实际执行**加载模型时花掉的秒数；没加载过则为 0.0。

    调用方（常驻服务）据此把这笔开销**单独报一次**，而不是算进某一张图的
    检测耗时——"第一张图要 5 秒"看起来像图的问题，其实是模型在加载。
    """
    return _LOAD_SECONDS


def _resolve_yolo_device() -> str:
    """选择 YOLO 推理设备：有可用 CUDA 就用 GPU，否则 CPU。

    - 环境变量 ``GUJI_YOLO_DEVICE`` 是用户的显式选择（auto/cpu/cuda/cuda:0…），
      直接采用、不做可用性检查——写错了自己能在日志里看到报错；
    - 自动模式探测 ``torch.cuda.is_available()``：检测是流水线里唯一的深度
      学习环节，GPU 化收益最大（CPU 推理几百 ms/张，GPU 通常快一个量级）。
      环境里装的是 CUDA 版 torch（cu121）但此前被硬编码在 CPU 上跑
      （2026-09-27 用户指出"GPU 好就吃 GPU"）；
    - 探测失败（torch 缺失/异常）一律回落 CPU，绝不因 GPU 探测把加载搞挂。
    """
    override = (os.environ.get("GUJI_YOLO_DEVICE") or "").strip().lower()
    if override:
        return override
    try:
        import torch  # noqa: PLC0415 - 调用点已在 ultralytics 导入之后

        if torch.cuda.is_available():
            return "cuda:0"
    except Exception:  # noqa: BLE001 - 探测失败就老实跑 CPU
        pass
    return "cpu"


def load_yolo_model() -> object:
    """延迟加载 YOLO 模型并返回单例实例。

    使用双重检查锁定（double-checked locking）确保线程安全：
    先无锁检查 → 再加锁检查 → 最后加载，避免每次调用都竞争锁。

    ⚠️ 单例只保证**进程内**复用。跨进程复用模型要靠常驻服务
    （`functions/yolo_service.py`）——每次点「检测」都是新的 worker 子进程，
    进程一退模型就没了，这里再单例也救不了第二次调用。

    返回:
        ultralytics.YOLO 实例（CPU 模式）。

    异常:
        FileNotFoundError: 未在候选路径找到 weights/bookcontent.pt。
    """
    global _YOLO_MODEL
    if _YOLO_MODEL is not None:
        return _YOLO_MODEL

    with _YOLO_LOCK:
        if _YOLO_MODEL is not None:
            return _YOLO_MODEL

        # 权重路径先解析（很快，不碰 torch），这样"正在加载"能**先**打出来——
        # 用户在接下来那几秒里至少知道程序在干什么。
        resolved = model_path()
        print(f"正在加载 YOLO 模型: {resolved}")

        # ⚠️ 计时必须从 import 之前开始：真正花时间的是 `import torch`
        # （frozen 下约 5 秒，291MB 的 torch_cpu.dll 加载 + 2000 多个模块），
        # 模型本身只要几十毫秒。只量 YOLO(...) 会得出"加载很快"的错误结论，
        # 上一轮排查启动慢时正是差点栽在这里。
        started = time.perf_counter()
        # 顺序要紧：两个降噪/打桩动作都必须在 import ultralytics 之前完成
        _silence_pruned_source_warnings()
        # ⚠️ stub 是**进程级**的：finder 常驻 sys.meta_path，此后进程内任何人
        # import matplotlib/scipy/pandas 拿到的都是假模块。检测跑在独立 worker
        # 子进程里时无碍；但调试脚本/同进程复用模型时如果需要真的这些库，
        # 设 `GUJI_NO_STUB=1` 即可关闭（要求环境里真装了这些包）。
        if not os.environ.get("GUJI_NO_STUB"):
            _stub_unneeded_modules()
        # 在此处导入而非模块顶层：ultralytics 导入开销大且需先执行 _stub_unneeded_modules()，
        # 保证 utils 包被导入时不会连带加载深度学习依赖。
        from ultralytics import YOLO  # noqa: PLC0415

        imported_at = time.perf_counter()
        _YOLO_MODEL = YOLO(str(resolved))
        # 设备选择：有 CUDA 就吃 GPU（用户要求"GPU 好就吃 GPU"），
        # GUJI_YOLO_DEVICE 可显式指定；挂了回落 CPU——GPU 只是加速件，
        # 绝不能让设备初始化失败把"加载模型"整个搞挂。
        global _YOLO_DEVICE
        _YOLO_DEVICE = _resolve_yolo_device()
        try:
            _YOLO_MODEL.to(_YOLO_DEVICE)
        except Exception as exc:  # noqa: BLE001 - 驱动/显存问题都走这里
            print(f"GPU 初始化失败（{_YOLO_DEVICE}）：{exc}，回落 CPU 推理")
            _YOLO_DEVICE = "cpu"
            _YOLO_MODEL.to("cpu")

        # ⚠️ 在**加载锁内、单线程**先跑一次空推理，把首次预测的惰性初始化坐实。
        #    首次 predict 会做一次性初始化，其中包括 Conv+BN 融合：`fuse()` 把 BN
        #    折进卷积后 `delattr(m, "bn")`。多线程同时触发时，先做完的线程已经把
        #    bn 删了、后做的还去取 `m.bn` → `AttributeError: bn`（实测 4~8 线程
        #    首轮偶发，上层靠重试侥幸通过，日志里表现为莫名其妙的"检测失败 -> bn"）。
        #    这里预热一次，之后并发预测就不会再撞上。
        _YOLO_MODEL.predict(np.zeros((64, 64, 3), dtype=np.uint8), verbose=False)
        elapsed = time.perf_counter() - started
        # 记下来供调用方单独报出（常驻服务把它回给客户端，见 load_seconds_used）：
        # 忘了这一句，服务就会永远报"加载 0 秒"，客户端于是以为模型早就在内存里，
        # 日志里那句"加载 YOLO 模型完成: 用时 X s"再也不会出现。
        global _LOAD_SECONDS
        _LOAD_SECONDS = elapsed
        print(
            f"加载 YOLO 模型完成: 用时 {elapsed:.1f} s"
            f"（导入 torch/ultralytics {imported_at - started:.1f} s，"
            f"加载权重并预热 {elapsed - (imported_at - started):.1f} s，"
            f"推理设备 {_YOLO_DEVICE}）"
            "；同一进程内后续检测直接复用"
        )
        return _YOLO_MODEL


#: 内容类别名。模型 `weights/bookcontent.pt` 的 `names` 就是这两个，
#: 但这里只用于**按名解析类别号**（见 :func:`_content_class_ids`），
#: 不假设它们在 `names` 里的下标顺序。
CONTENT_CLASS_HARF = "harfcontent"
CONTENT_CLASS_FULL = "fullcontent"

#: 规则1：整幅(fullcontent)框宽必须 **>** 图像宽度 × 该比例，否则视为失败检测剔除。
#: 依据：fullcontent 的语义就是「整幅内容区」——宽度不到七成的框不可能是整幅。
#: 实测：训练集里真整幅框宽 p5=88%（均值 95%），而模型误判出来的「窄整幅」
#: 只有 ~45%（一栏的宽度），70% 正好卡在两者之间。
#: 该规则与参考实现 `gujitrain/test/predict_bookcontent.py` 的
#: ``FULL_MIN_WIDTH_RATIO`` 一致。
FULL_MIN_WIDTH_RATIO = 0.70


class ContentBoxes(NamedTuple):
    """一页的内容框检测结果（**已按互斥规则消解**），按类别分流。

    属性:
        left_boxes: 半幅框中中心在中线左侧的（面积降序）。
        right_boxes: 半幅框中中心在中线右侧的（面积降序）。
        full_boxes: 整幅框（面积降序，至多一个）。
        notes: 互斥消解**实际触发**的规则说明（人读，供调用方打日志）；
            没有触发任何规则时为空元组。消解之后两类必然互斥，
            因此 left/right 与 full 不会同时非空。

    每个 box = ``(x1, y1, x2, y2, area, conf)``，坐标为整数像素值。
    """

    left_boxes: List[tuple]
    right_boxes: List[tuple]
    full_boxes: List[tuple]
    notes: Tuple[str, ...] = ()


def _content_class_ids(model: object) -> Tuple[int, int]:
    """从模型 ``names`` 里解析 ``(harfcontent_id, fullcontent_id)``。

    ⚠️ 按**类名**解析而不是写死 0/1：训练 yaml 里 `names` 的顺序将来若调整，
    这里的路由仍然正确。某个类名在 `names` 里不存在时返回 ``-1``（永不匹配），
    于是单类模型也能正确退化：只有 harfcontent 的模型不会产出整幅框，反之亦然。

    只有**拿不到任何 names 信息**时（老权重没有 names）才退回 ``(0, 1)``——
    与当前 `data/bookcontent/bookcontent.yaml` 的顺序一致。
    """
    names = getattr(model, "names", None)
    if isinstance(names, dict):
        index = {str(v): int(k) for k, v in names.items()}
    elif isinstance(names, (list, tuple)):
        index = {str(v): i for i, v in enumerate(names)}
    else:
        index = {}
    if not index:
        return 0, 1
    return index.get(CONTENT_CLASS_HARF, -1), index.get(CONTENT_CLASS_FULL, -1)


def _split_by_center(boxes: List[tuple], mid_x: float):
    """按框的水平中心把一组框分成左右两组（cx < mid_x 归左）。"""
    left, right = [], []
    for box in boxes:
        cx = (box[0] + box[2]) / 2.0
        (left if cx < mid_x else right).append(box)
    return left, right


def resolve_content_boxes(
    raw_boxes, img_w: float, harf_id: int, full_id: int
) -> Tuple[List[tuple], List[tuple], List[tuple], Tuple[str, ...]]:
    """按**互斥规则**消解 harfcontent / fullcontent，返回 (left, right, full, notes)。

    与参考实现 `gujitrain/test/predict_bookcontent.py::resolve_boxes` **同规则**
    （规则顺序即优先级）：

    1. **窄整幅剔除**：整幅框宽必须 > ``img_w × FULL_MIN_WIDTH_RATIO``（0.70），
       否则判为失败检测直接剔除；
    2. **双半幅压制整幅**：harfcontent ≥ 2 个 → 整幅框一律不存在（全删）——
       两栏都检出来了，整幅一定是错的；
    3. **单半幅与整幅比置信度**：harfcontent 恰好 1 个 → 取置信度最高的整幅框
       与它比，整幅**严格更高**才留整幅（平局留半幅）；没有 harfcontent 时
       整幅原样保留。

    参数:
        raw_boxes: 模型原始输出 ``[(cls_id, conf, x1, y1, x2, y2), …]``，未过滤。
        img_w: 图像宽度（规则1 的基准）。
        harf_id / full_id: 两类各自的类别号；``-1`` 表示该类不存在。

    返回:
        ``(left_boxes, right_boxes, full_boxes, notes)``。前三个均为面积降序的
        ``(x1,y1,x2,y2,area,conf)``；``notes`` 是消解说明（人读，只含**真的触发**
        的规则）。

    ⚠️ 「两类互斥」是就**已登记的两个类别**而言的：未知类别（将来若再添类别）
    一律按半幅处理、且**不参与**上述三条规则的计数与置信度比较——既不丢框，
    也不会让它误压制整幅框。真出现第三类时，应把它当作新的语义在
    `PageBoxes` / 槽位约定里显式建模，而不是靠这里兜底。
    """
    half, full_valid, others = [], [], []
    narrow_full = 0
    for cls, conf, x1, y1, x2, y2 in raw_boxes:
        area = (x2 - x1) * (y2 - y1)
        item = (int(x1), int(y1), int(x2), int(y2), area, float(conf))
        if cls == full_id:
            # 规则1：整幅框必须够宽，否则是"把某一栏误判成整幅"
            if (x2 - x1) / img_w > FULL_MIN_WIDTH_RATIO:
                full_valid.append(item)
            else:
                narrow_full += 1
        elif cls == harf_id:
            half.append(item)
        else:
            others.append(item)

    notes: List[str] = []
    if narrow_full:
        notes.append(
            f"剔除{narrow_full}个整幅框(宽≤{int(FULL_MIN_WIDTH_RATIO * 100)}%)"
        )

    kept_half, kept_full = half, full_valid
    if len(half) >= 2:
        # 规则2：两栏都出来了，整幅一定是错的
        kept_full = []
        if full_valid:
            notes.append(
                f"剔除{len(full_valid)}个整幅框(与{len(half)}个半幅框冲突)"
            )
    elif len(half) == 1:
        # 规则3：只剩一个半幅时，与置信度最高的整幅比置信度（整幅须**严格更高**）
        if full_valid:
            best_full = max(full_valid, key=lambda b: b[5])
            if best_full[5] > half[0][5]:
                kept_half = []
                notes.append(
                    f"剔除半幅框(置信度{half[0][5]:.2f}<整幅{best_full[5]:.2f})"
                )
            else:
                kept_full = []
                notes.append(
                    f"剔除{len(full_valid)}个整幅框"
                    f"(最高{best_full[5]:.2f}≤半幅{half[0][5]:.2f})"
                )

    # 我们的槽位只需要**一个**整幅框：多个有效整幅时取面积最大者（参考实现
    # 会把它们全留下并计入统计，本项目的下游只有一个整幅槽位）。
    if len(kept_full) > 1:
        kept_full = [max(kept_full, key=lambda b: b[4])]

    mid_x = img_w / 2.0
    left, right = _split_by_center(kept_half + others, mid_x)
    left.sort(key=lambda b: b[4], reverse=True)
    right.sort(key=lambda b: b[4], reverse=True)
    full = sorted(kept_full, key=lambda b: b[4], reverse=True)
    return left, right, full, tuple(notes)


def detect_content_boxes(image_bgr: np.ndarray, model: object) -> ContentBoxes:
    """使用 YOLO 检测页面内容框，按类别分流并按**互斥规则消解**。

    算法:
    1. 模型推理，取全部框的 ``(类别, 置信度, 坐标)``；
    2. 按类别号分流（``fullcontent`` 与其余分开）；
    3. 调用 :func:`resolve_content_boxes` 消解两类冲突（窄整幅剔除、双半幅压制
       整幅、单半幅与整幅比置信度），保证返回结果**两类互斥**；
    4. 半幅框按中线分左右，各组按面积降序（最大框排在 [0]）。

    参数:
        image_bgr: BGR 格式图像（cv2 读取的默认格式）。
        model: YOLO 模型实例。

    返回:
        :class:`ContentBoxes`（已消解；`notes` 说明触发了哪条规则）。
    """
    h, w = image_bgr.shape[:2]
    # 设备跟模型走（load 时已选定并 to() 过）。写死 "cpu" 是无 GPU 时代的
    # 兼容行为；GPU 时代它就是纯浪费（2026-09-27 用户指出"GPU 好就吃 GPU"）。
    results = model(image_bgr, verbose=False, device=_YOLO_DEVICE)
    boxes = results[0].boxes
    harf_id, full_id = _content_class_ids(model)

    raw_boxes = []
    for box in boxes:
        x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].cpu().numpy())
        raw_boxes.append(
            (
                int(box.cls[0].cpu().numpy()),
                float(box.conf[0].cpu().numpy()),
                x1,
                y1,
                x2,
                y2,
            )
        )

    left, right, full, notes = resolve_content_boxes(
        raw_boxes, w, harf_id, full_id
    )
    return ContentBoxes(left, right, full, notes)
