# -*- coding: utf-8 -*-
"""本包共享的常量、夹具与检查函数（由原大模块拆出）。"""

from __future__ import annotations

# -*- coding: utf-8 -*-

from __future__ import annotations

from tests.selftests._context import ok, pump, wait_until

NAME = "data_package"
TITLE = "去底色数据包检查与下载"
DEPENDS: list[str] = []

#: 用户给的样例 data.json（真源形态；bookcontent 版本 100）。
SAMPLE_DATA_JSON = {
    "generated_at": "2026-10-16T09:22:21+08:00",
    "release": "database",
    "files": {
        "bookcontent": {
            "name": "bookcontent-v100.pt",
            "version": 100,
            "sha256": "8a70a890c3132edc9da82f27e51113bf054dd82ab7fad2c7bb8d71dd66d2fa5d",
            "size": 6245475,
            "date": "2026-09-28T18:52:07+08:00",
        },
        "gujiline": {
            "name": "gujiline-v100.pt",
            "version": 100,
            "sha256": "89dca4b2b0541d078500a383a29ce514e7ceb57107dff095e9d343440a92940d",
            "size": 6252707,
            "date": "2026-09-23T01:14:32+08:00",
        },
    },
}


class _FakeDialog:
    """假弹窗实体：exec/show/adjustSize 空实现，close 记一笔。"""

    def __init__(self) -> None:
        self.closed = False

    def exec(self) -> int:
        return 1

    def show(self) -> None:
        return None

    def adjustSize(self) -> None:
        return None

    def done(self, _result: int = 0) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _DialogRecorder:
    """假弹窗外壳：替 ``menu.shell_dialog``，记下每次调用的标题/正文/按钮/回调。

    正文照真货口径从内容面板的 ``BodyLabel`` 读——断言的是"用户真会看到什么"。
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.dialogs: list[_FakeDialog] = []

    def __call__(self, title, panel, parent=None, **kwargs) -> _FakeDialog:
        from qfluentwidgets import BodyLabel

        labels = panel.findChildren(BodyLabel)
        self.calls.append(
            {
                "title": title,
                "body": "\n".join(label.text() for label in labels),
                "ok_text": kwargs.get("ok_text"),
                "cancel_text": kwargs.get("cancel_text"),
                "show_cancel": kwargs.get("show_cancel"),
                "on_ok": kwargs.get("on_ok"),
                "on_cancel": kwargs.get("on_cancel"),
            }
        )
        dialog = _FakeDialog()
        self.dialogs.append(dialog)
        return dialog


class _FakeResponse:
    """内存假响应：够 ``urlopen`` 那条读链路用（headers + 流式 read）。"""

    def __init__(self, data: bytes, with_length: bool = True) -> None:
        self._data = data
        self._pos = 0
        self.headers = {"Content-Length": str(len(data))} if with_length else {}

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            chunk = self._data[self._pos :]
            self._pos = len(self._data)
            return chunk
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False


def _payload(
    version: int = 100, name: str = "bookcontent-v100.pt", size: int = 6245475
) -> dict:
    """``fetch_data_json`` 的返回形态（控制器测试用）。"""
    return {
        "info": {
            "name": name,
            "version": version,
            "sha256": "a" * 64,
            "size": size,
            "date": "",
        },
        "asset_name": name,
        "download_url": "https://v6.gh-proxy.org/https://example.invalid/x.pt",
        "mirror_prefix": "https://v6.gh-proxy.org/",
        "mirror_label": "v6.gh-proxy.org",
        "seconds": 0.38,
        "ranking": [
            {
                "prefix": "https://v6.gh-proxy.org/",
                "label": "v6.gh-proxy.org",
                "ok": True,
                "seconds": 0.38,
            },
            {"prefix": "", "label": "直连", "ok": True, "seconds": 2.42},
        ],
    }


def _menu_of(window, title: str):
    for action in window.menu_bar.actions():
        if action.text() == title:
            menu = action.menu()
            assert menu is not None, f"菜单 {title} 没有实体"
            return menu
    raise AssertionError(f"没有找到顶级菜单：{title}")


def _action_of(menu, text: str):
    for action in menu.actions():
        if not action.isSeparator() and action.text() == text:
            return action
    raise AssertionError(f"菜单里没有动作：{text}")


#: 仓库根（分片比原模块深一层，深两层，不能用 parents[2]/[3]）
import pathlib as _pathlib
ROOT = _pathlib.Path(__file__).resolve().parents[4]
