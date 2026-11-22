# -*- coding: utf-8 -*-
"""任务详情页模块级常量。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


#: 聚合任务汇集期间，起点清单的重刷间隔（分批显示：文件落一批显示一批）。
#: 逐文件复制几百张扫描件要几十秒，1.2s 一次的重刷只是 readdir + 差量装条目，
#: 不解码原图，不构成负担。
INPUT_NODE_POLL_MS = 1200

