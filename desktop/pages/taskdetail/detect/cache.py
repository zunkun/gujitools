# -*- coding: utf-8 -*-
"""``detect_cache`` 的带版本号容器（从原 ``detect.py`` 拆出）。"""

from __future__ import annotations
class VersionedBoxCache(dict):
    """``detect_cache`` 的带版本号版：任何写入都自增 ``version``。

    给"整书判据"（单栏书结论 / 逐页检测框）做缓存失效用——那些判据要遍历
    全部页并读 ``boxes.json``，不能每次重算。用户在第二步改框会写这份缓存
    ⇒ 版本号自增 ⇒ 判据缓存失效，不会拿旧框去命名产物。
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.version = 0

    def __setitem__(self, key, value) -> None:  # noqa: ANN001
        super().__setitem__(key, value)
        self.version += 1

    def __delitem__(self, key) -> None:  # noqa: ANN001
        super().__delitem__(key)
        self.version += 1

    def clear(self) -> None:
        super().clear()
        self.version += 1

