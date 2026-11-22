# -*- coding: utf-8 -*-
"""本包共享的常量、夹具与检查函数（由原大模块拆出）。"""

from __future__ import annotations

# -*- coding: utf-8 -*-

NAME = "book_layout"
DEPENDS: list[str] = []
TITLE = "全书级页形态（单栏书 / 整幅书可疑半幅）"

W = 1000
#: 单宽框：2 槽、单框、宽 85%
WIDE = [[75, 100, 925, 1300], None]
#: 窄单框：2 槽、单框、宽仅 45%（单栏书里的漏网之鱼）
NARROW = [[80, 100, 530, 1300], None]
#: 真双栏
DOUBLE = [[0, 100, 450, 1300], [520, 100, 1000, 1300]]
#: 整幅：1 槽
FULL = [[100, 100, 900, 1300]]


#: 仓库根（分片比原模块深一层，深两层，不能用 parents[2]/[3]）
import pathlib as _pathlib
ROOT = _pathlib.Path(__file__).resolve().parents[4]
