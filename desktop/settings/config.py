# -*- coding: utf-8 -*-
"""应用级偏好设置：qfluentwidgets 的 ``QConfig`` + 本程序自己的配置项。

用户 2026-10-16 指名的做法（qfluentwidgets 的 Config 文档）：配置项声明成
``ConfigItem``，读写交给库自带的全局 ``qconfig``，界面侧用 ``SettingCard``
直接绑配置项（见 :mod:`desktop.settings.page`）。

**与项目约定的接口只有一个**：配置文件的位置。qconfig 默认写
``config/config.json``——那是**相对当前工作目录**的路径，开发期会把文件写进
仓库根、打包后可能落到安装目录（只读）。所以这里用 ``qconfig.load(file, cfg)``
把它指到数据根目录（``~/Documents/guji/config.json``，与 ``tasks/`` 同级），
与其它状态文件放在一起。

⚠️ **``qconfig.load`` 全程序只调一次**：它把全局 ``qconfig`` 的存取/落盘
整体转交给传进去的实例，重复调用等于把内存里的改动丢掉重读磁盘。
"""

from __future__ import annotations

from pathlib import Path

from qfluentwidgets import ConfigItem, QConfig, qconfig
from qfluentwidgets.common.config import BoolValidator

from desktop.utils.files import guji_data_dir

#: 配置文件名（落在数据根目录下，见模块 docstring）。
CONFIG_FILENAME = "config.json"


class AppConfig(QConfig):
    """本程序的应用级配置项。

    ⚠️ **必须是 ``QConfig`` 的子类、且配置项写成类属性**：``qconfig.load``
    与 ``save`` 都靠 ``dir(cls)`` 把 ``ConfigItem`` 找回来落盘。写成实例属性
    的话存得进去、读不回来。

    新增一个开关 = 在这里加一个 ``ConfigItem`` + 在设置页摆一张
    ``SwitchSettingCard``（绑上它即可，读写/落盘全免）。
    """

    #: 开发者模式：打开后设置页才显示开发/训练相关的选项。
    developerMode = ConfigItem(
        "Developer", "DeveloperMode", False, BoolValidator()
    )
    #: YOLO 标注：「检测文本框」右栏底部露出「导出YOLO标注」按钮。
    yoloAnnotation = ConfigItem(
        "Developer", "YoloAnnotation", False, BoolValidator()
    )


#: 已载入的配置实例（见 :func:`app_config`）。
_app_config: AppConfig | None = None


def config_path() -> Path:
    """配置文件路径：数据根目录下的 ``config.json``。"""
    return guji_data_dir() / CONFIG_FILENAME


def app_config() -> AppConfig:
    """取应用配置（首次调用时从磁盘载入；重复调用返回同一个实例）。

    ⚠️ 不能写成"模块导入时载入"：本模块会被**未建窗口**的路径碰到（自测、
    将来可能的批处理入口），导入期读写文件是不该有的副作用。
    """
    global _app_config
    if _app_config is None:
        cfg = AppConfig()
        # qconfig.load 自带 @exceptionHandler，配置坏了/读不动会回落默认值
        qconfig.load(config_path(), cfg)
        _app_config = cfg
    return _app_config


def developer_mode() -> bool:
    """开发者模式是否打开。"""
    return bool(app_config().developerMode.value)


def yolo_annotation() -> bool:
    """是否启用 YOLO 标注（「导出YOLO标注」按钮的显示条件之一）。"""
    return bool(app_config().yoloAnnotation.value)


__all__ = [
    "AppConfig",
    "CONFIG_FILENAME",
    "app_config",
    "config_path",
    "developer_mode",
    "yolo_annotation",
]
