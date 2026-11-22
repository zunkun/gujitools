# -*- coding: utf-8 -*-
"""本包共享的常量、夹具与检查函数（由原大模块拆出）。"""

from __future__ import annotations

# -*- coding: utf-8 -*-

from __future__ import annotations

import time
from pathlib import Path

NAME = "steps_components"
DEPENDS: list[str] = ["tasklist"]
TITLE = "共用步骤组件层"




__all__ = ["NAME", "DEPENDS", "TITLE", "run"]


#: 仓库根（分片比原模块深一层，深两层，不能用 parents[2]/[3]）
import pathlib as _pathlib
ROOT = _pathlib.Path(__file__).resolve().parents[4]
