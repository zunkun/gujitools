# -*- coding: utf-8 -*-
"""逐图坐标/旋转覆盖的键归一与位图旋转。"""

from __future__ import annotations

from PIL import Image

from utils.page_layout import normalize_page_rotation


def _normalize_page_rects(raw) -> dict:
    """把逐图坐标覆盖的页号键归一为 int。

    ⚠️ 这条归一不能省：GUI 把 ``{1: [x,y,w,h]}`` 写进运行配置，而运行配置
    要落盘成 JSON（``write_json``）——**JSON 对象的键只能是字符串**——
    子进程读回来就成了 ``{"1": [...]}``。若仍用 int 查表（``get(i + 1)``）
    永远查不到，坐标覆盖静默失效，PDF 依旧按 page_margins 自动排版：
    表现为「预览里拖好了位置和大小，生成的 PDF 却还是原来那样」。

    同时兼容 CLI/模板里写成字符串键（``page_rects: {"1": [...]}``）的用法。
    解析不了的键直接丢弃（对应页回退自动排版）。
    """
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        try:
            out[int(key)] = value
        except (TypeError, ValueError):
            continue
    return out


def _normalize_page_rotations(raw) -> dict:
    """把逐图旋转角的页号键归一为 int，值归一为 **(-180, 180] 的浮点角度**。

    与 :func:`_normalize_page_rects` 同一套原因：运行配置要过 JSON，键会变成
    字符串；直接用 int 查表会让「版面编辑器里转好的方向」在 PDF 里失效。
    角度可以是任意值（画布旋转钮可拖任意角度），口径统一走
    ``utils.page_layout.normalize_page_rotation``。
    0° 不写进结果表（没有旋转就是没有覆盖，省得调用方到处判空）。
    """
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        try:
            page = int(key)
        except (TypeError, ValueError):
            continue
        rotate = normalize_page_rotation(value)
        if rotate:
            out[page] = rotate
    return out


def _rotate_pil(img: Image.Image, degrees) -> Image.Image:
    """按顺时针 ``degrees`` 旋转 PIL 位图（任意角度，绕中心按外接框扩图）。

    角度口径与预览/版面编辑器一致（``utils.page_layout.normalize_page_rotation``）。
    直角（±90/180）仍走**无损转置**，老任务输出逐像素不变；其它角度用
    ``rotate(-angle, expand=True)``——PIL 的 ``rotate`` 正角是逆时针，所以
    顺时针角度要取负。⚠️ PIL 的 ``ROTATE_270`` 是**逆时针 270° = 顺时针 90°**。
    """
    angle = normalize_page_rotation(degrees)
    if angle == 0:
        return img
    if angle == 90:
        return img.transpose(Image.Transpose.ROTATE_270)
    if angle == 180:
        return img.transpose(Image.Transpose.ROTATE_180)
    if angle == -90:
        return img.transpose(Image.Transpose.ROTATE_90)
    return img.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
