# -*- coding: utf-8 -*-
"""应用级偏好设置：配置项（``config``）与设置页（``page``）。

- :mod:`desktop.settings.config` —— 基于 qfluentwidgets ``QConfig`` 的配置项，
  落盘在数据根目录的 ``config.json``（不作为、也不 import 任何界面控件）；
- :mod:`desktop.settings.page` —— 左侧栏底部「设置」进的那一页，用
  qfluentwidgets 的 ``SettingCard`` 摆开关。

读开关一律走 ``config`` 里的取值函数（``developer_mode()`` /
``yolo_annotation()``），**不要在各页面里直接摸 ``qconfig``** —— 那样
"配置项叫什么、默认值是多少"就会散成好几份。
"""

from __future__ import annotations

__all__: list[str] = []
