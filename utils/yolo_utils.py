"""YOLO 检测封装：模型加载与左右文本框分割。

此模块封装了 YOLO 目标检测模型的使用，提供两个核心功能：

1. **模型加载** (`load_yolo_model`)
   延迟加载 + 模块级单例 + 双重检查锁，确保多线程下模型只加载一次。
   权重文件查找路径: `gujitools/weights/detect.pt`。

2. **左右文本框检测** (`detect_left_right_boxes`)
   对古籍扫描图（通常左页 + 右页双栏排版）执行检测后，按检测框水平中心点
   与图像中线的关系分为 left / right 两组，供 crop / cropremove 使用。

左右分割算法:
    以图像宽度一半为分界线，检测框中心 cx < w/2 归入 left，否则归入 right。
    每组按面积降序排序，调用方取 [0] 即可获得最大候选框。
"""

import os
import sys
import types
import threading
from pathlib import Path
from importlib.machinery import ModuleSpec
import numpy as np
import cv2
from typing import List, Tuple

# 跳过 ultralytics 启动时的版本检查提示，减少日志噪音
os.environ["ULTRALYTICS_SKIP_UPDATE_CHECK"] = "1"


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


# 模块级单例：已加载的 YOLO 模型实例
_YOLO_MODEL = None
# 线程锁：保护多线程下的首次加载
_YOLO_LOCK = threading.Lock()


def load_yolo_model() -> object:
    """延迟加载 YOLO 模型并返回单例实例。

    使用双重检查锁定（double-checked locking）确保线程安全：
    先无锁检查 → 再加锁检查 → 最后加载，避免每次调用都竞争锁。

    返回:
        ultralytics.YOLO 实例（CPU 模式）。

    异常:
        FileNotFoundError: 未在候选路径找到 weights/detect.pt。
    """
    global _YOLO_MODEL
    if _YOLO_MODEL is not None:
        return _YOLO_MODEL

    with _YOLO_LOCK:
        if _YOLO_MODEL is not None:
            return _YOLO_MODEL

        _stub_unneeded_modules()
        from ultralytics import YOLO

        # 权重文件候选路径（按优先级排列）
        current_dir = Path(__file__).resolve()  # gujitools/utils/yolo_utils.py
        project_root = current_dir.parents[1]  # gujitools 根目录

        candidates = [
            project_root / "weights" / "detect.pt",  # gujitools/weights/detect.pt
        ]

        model_path = None
        for p in candidates:
            if p.exists():
                model_path = p
                break

        if model_path is None:
            raise FileNotFoundError(
                "未找到 YOLO 模型权重文件 detect.pt。\n"
                "请将 detect.pt 放置在以下任一位置：\n"
                + "\n".join(f"  - {p}" for p in candidates)
            )

        print(f"加载 YOLO 模型: {model_path}")
        _YOLO_MODEL = YOLO(str(model_path))
        _YOLO_MODEL.to("cpu")  # 强制 CPU 模式，兼容无 GPU 环境
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
