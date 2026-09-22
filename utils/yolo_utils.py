"""YOLO 检测封装：模型加载与左右文本框分割。

此模块封装了 YOLO 目标检测模型的使用，提供两个核心功能：

1. **模型加载** (`load_yolo_model`)
   延迟加载 + 模块级单例 + 双重检查锁，确保多线程下模型只加载一次。
   权重文件查找路径: `gujitools/weights/bookcontent.pt`。

2. **左右文本框检测** (`detect_left_right_boxes`)
   对古籍扫描图（通常左页 + 右页双栏排版）执行检测后，按检测框水平中心点
   与图像中线的关系分为 left / right 两组，供 crop / cropremove 使用。

左右分割算法:
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
import numpy as np
from typing import List, Tuple

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
        _stub_unneeded_modules()
        # 在此处导入而非模块顶层：ultralytics 导入开销大且需先执行 _stub_unneeded_modules()，
        # 保证 utils 包被导入时不会连带加载深度学习依赖。
        from ultralytics import YOLO  # noqa: PLC0415

        imported_at = time.perf_counter()
        _YOLO_MODEL = YOLO(str(resolved))
        _YOLO_MODEL.to("cpu")  # 强制 CPU 模式，兼容无 GPU 环境

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
            f"加载权重并预热 {elapsed - (imported_at - started):.1f} s）"
            "；同一进程内后续检测直接复用"
        )
        return _YOLO_MODEL


def detect_left_right_boxes(
    image_bgr: np.ndarray, model: object
) -> Tuple[List[tuple], List[tuple]]:
    """使用 YOLO 检测文本框并按水平中心分为左右两组。

    算法:
    1. 取图像宽度的一半 mid_x = w / 2 作为左右分界线；
    2. 遍历所有检测框，计算中心 cx = (x1 + x2) / 2；
    3. cx < mid_x → left_boxes，否则 → right_boxes；
    4. 每组按面积降序排序（最大框排在 [0]）。

    参数:
        image_bgr: BGR 格式图像（cv2 读取的默认格式）。
        model: YOLO 模型实例。

    返回:
        (left_boxes, right_boxes)：
        - 每个 box = (x1, y1, x2, y2, area)，坐标为整数像素值；
        - 面积降序排列，取 [0] 即可得最大候选框；
        - 若某侧无检测框，对应列表为空。
    """
    h, w = image_bgr.shape[:2]
    mid_x = w / 2.0  # 图像中线，用于区分左右页

    results = model(image_bgr, verbose=False, device="cpu")
    boxes = results[0].boxes
    left_boxes, right_boxes = [], []

    for box in boxes:
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        cx = (x1 + x2) / 2.0  # 检测框水平中心
        area = (x2 - x1) * (y2 - y1)
        bbox = (int(x1), int(y1), int(x2), int(y2), area)
        if cx < mid_x:
            left_boxes.append(bbox)
        else:
            right_boxes.append(bbox)

    # 按面积降序排序，调用方取 [0] 即可获得最大候选框
    left_boxes.sort(key=lambda b: b[4], reverse=True)
    right_boxes.sort(key=lambda b: b[4], reverse=True)
    return left_boxes, right_boxes
