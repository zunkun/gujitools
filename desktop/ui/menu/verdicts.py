# -*- coding: utf-8 -*-
"""检查更新的纯数据结论（自 ``desktop/ui/menu.py`` 拆出，不碰控件）。"""

from __future__ import annotations

from dataclasses import dataclass

from config import VERSION
from utils.data_package import effective_info, human_size

from .constants import (
    BUTTON_BROWSER,
    BUTTON_DOWNLOAD,
    BUTTON_INSTALL,
    BUTTON_LATER,
    BUTTON_OK,
    BUTTON_RETRY,
    DATA_PACKAGE_URL,
    FAILURE_REASONS,
    PROJECT_URL,
    RESULT_LATEST,
    RESULT_NEWER,
)

# ------------------------------------------------------------------ 数据（纯函数）
@dataclass(frozen=True)
class UpdateVerdict:
    """一次检查更新该呈现什么（纯数据，自测直接断言它，不碰控件）。

    - ``ok_text`` 决定**主按钮**的语义：:data:`BUTTON_DOWNLOAD` = 应用内下载、
      :data:`BUTTON_INSTALL` = 立即重启安装、:data:`BUTTON_RETRY` = 换线路重试；
      其余（``BUTTON_OK``）只关窗。
    - ``link`` 非空 ⇒ 正文里附一行**可复制的下载地址**；
    - ``browser_url`` 非空 ⇒ 次按钮「前往下载页」开浏览器（**备用**，用户自己下）。
    """

    title: str
    body: str
    ok_text: str = BUTTON_OK
    link: str = ""
    browser_url: str = ""


def update_result(
    kind: str, *, current: str, latest: dict | None = None
) -> UpdateVerdict:
    """把一次检查结果收成 :class:`UpdateVerdict`。

    ``kind`` 取 ``RESULT_LATEST`` / ``RESULT_NEWER`` / 失败分类串
    （``network`` / ``not_found`` / ``rate_limited`` / ``bad_json`` / ``http:<code>``）。

    ⚠️ 正文**不用 markdown 粗体**（``**…**``）：内容面板是普通 QLabel，星号会
    原样显示出来（与 ``_ask_overwrite`` 同款教训）。

    线路（用户 2026-10-15：「github 容易被 ban，所以可以使用代理……检测更新，下载
    更新的时候，可以选择测试选择最优方案」）：worker 已经把**四条线路（直连 + 三个
    gh-proxy 镜像）都测过速**，``latest`` 里带着 ``mirror_label`` / ``download_url`` /
    ``ranking``——这里把它们写进正文：用户看得见这次走的是哪条、多快，下载地址也是
    **拼过该线路前缀**的那个（不然给了地址还是被 ban）。
    """
    payload = latest or {}
    if kind == RESULT_NEWER:
        tag = str(payload.get("tag_name") or "")
        name = str(payload.get("name") or "").strip()
        page = str(payload.get("html_url") or "") or PROJECT_URL
        label = str(payload.get("mirror_label") or "直连")
        link = str(payload.get("download_url") or "") or page
        seconds = payload.get("seconds")
        timing = (
            f"（{float(seconds):.2f}s）" if isinstance(seconds, (int, float)) else ""
        )
        body = f"当前版本：v{current}\n最新版本：{tag}"
        if name and name != tag:
            body += f"（{name}）"
        body += f"\n\n下载线路：{label}{timing}"
        body += f"\n下载地址：{link}"
        if payload.get("prerelease"):
            body += "\n\n注意：这一版是预发布版本。"
        body += (
            f"\n\n点「{BUTTON_DOWNLOAD}」将在程序内自动下载安装包，"
            "下完提示重启安装；"
            f"点「{BUTTON_BROWSER}」打开下载页自行下载（备用）。"
        )
        return UpdateVerdict(f"发现新版本 {tag}", body, BUTTON_DOWNLOAD, link, page)
    if kind == RESULT_LATEST:
        tag = str(payload.get("tag_name") or "")
        link = str(payload.get("html_url") or "") or PROJECT_URL
        body = f"当前版本 v{current} 已是最新。"
        if tag:
            body += f"\n\n最新发布：{tag}\n{link}"
        return UpdateVerdict("已是最新版本", body)
    reason = FAILURE_REASONS.get(kind)
    if reason is None:
        if kind.startswith("http:"):
            reason = f"更新服务器返回了错误（HTTP {kind.split(':', 1)[1]}）。"
        else:
            reason = "检查更新时出了点问题。"
    return UpdateVerdict(
        "检查更新失败",
        f"{reason}\n\n直连与三个镜像都试过一遍了；稍后可以再试，"
        f"也可以到项目主页看最新版本：\n{PROJECT_URL}",
    )


def data_package_result(
    kind: str, *, current: int, latest: dict | None = None
) -> UpdateVerdict:
    """把一次「去底色数据包检查」结果收成 :class:`UpdateVerdict`（纯数据）。

    ``kind`` 取 ``RESULT_LATEST`` / ``RESULT_NEWER`` / 失败分类串。与
    :func:`update_result` 的关键区别：**没有外链备用按钮**——有新版时主按钮是
    :data:`BUTTON_DOWNLOAD`（「下载」），点了由控制器**在程序内**下载并替换，
    而不是开浏览器（用户 2026-10-16：「不要让用户自己去下载」）。

    ``current`` 是**本机已安装版本**（整数）；``latest`` 是检查结果
    （``data_package_worker.fetch_data_json`` 的返回，含 ``info`` 与线路信息）。
    """
    payload = latest or {}
    info = payload.get("info") or {}
    remote = int(info.get("version") or 0)
    if kind == RESULT_NEWER:
        name = str(info.get("name") or "")
        size = human_size(info.get("size"))
        label = str(payload.get("mirror_label") or "直连")
        seconds = payload.get("seconds")
        timing = (
            f"（{float(seconds):.2f}s）" if isinstance(seconds, (int, float)) else ""
        )
        # current = 0 表示本机**一份权重都没有**（没装过 / 被删了 / 安装损坏），
        # 说成"当前版本 v0"会让人以为有个 0 版模型。
        body = "本机尚未安装数据包（权重文件缺失）" if current <= 0 else (
            f"当前数据包版本：v{current}"
        )
        body += f"\n最新数据包版本：v{remote}"
        if name:
            body += f"（{name}）"
        if size:
            body += f"\n文件大小：{size}"
        body += (
            f"\n\n点「{BUTTON_DOWNLOAD}」将经最快线路（{label}{timing}）"
            "自动下载并在本机启用。\n"
            "下载后文件名保留版本号（如 bookcontent-v105.pt），旧模型不会删除；"
            "\n由 bookcontent.version.json 指定当前生效的那一份，下次检测即用新版。"
        )
        return UpdateVerdict("发现新版本数据包", body, BUTTON_DOWNLOAD)
    if kind == RESULT_LATEST:
        body = f"当前数据包版本 v{current} 已是最新。"
        local = effective_info().get("name")
        if local:
            body += f"\n\n本机生效文件：{local}"
        return UpdateVerdict("数据包已是最新", body)
    reason = FAILURE_REASONS.get(kind)
    if reason is None:
        if kind.startswith("http:"):
            reason = f"更新服务器返回了错误（HTTP {kind.split(':', 1)[1]}）。"
        else:
            reason = "检查数据包时出了点问题。"
    return UpdateVerdict(
        "检查数据包失败",
        f"{reason}\n\n直连与三个镜像都试过一遍了；稍后可以再试，"
        f"也可以到发布页看看：\n{DATA_PACKAGE_URL}",
    )


def _ready_verdict(tag: str) -> UpdateVerdict:
    """「安装包已就绪」结论（用户 2026-10-16）：主按钮「立即重启安装」，次按钮「稍后」。

    点「立即重启安装」由控制器启动安装器并退出本程序（``_install_and_restart``）；
    「稍后」则把安装包留在用户目录，下次点「检查更新」时可直接安装（免重下）。
    """
    body = (
        f"安装包已下载完成（{tag or '新版本'}）。\n\n"
        f"点「{BUTTON_INSTALL}」将关闭本程序并启动安装程序完成更新；\n"
        f"点「{BUTTON_LATER}」稍后再说——安装包会留着，"
        "下次点「检查更新」可直接安装，无需重新下载。"
    )
    return UpdateVerdict("更新已就绪", body, BUTTON_INSTALL)


def _download_failed_verdict(kind: str, browser_url: str) -> UpdateVerdict:
    """下载失败的结论：主按钮「换条线路重试」，次按钮「前往下载页」（**备用**）。"""
    reason = FAILURE_REASONS.get(kind)
    if reason is None:
        if "sha256" in kind or "ValueError" in kind:
            reason = "下载的安装包校验不通过（可能被网络中间层改写）。"
        else:
            reason = f"下载失败（{kind}）。"
    body = (
        f"{reason}\n\n可以点「{BUTTON_RETRY}」换一条线路重试；"
        f"也可以点「{BUTTON_BROWSER}」自行下载。"
    )
    return UpdateVerdict("更新下载失败", body, BUTTON_RETRY, "", browser_url)


def about_rows(window=None) -> list[tuple[str, str]]:
    """「关于」弹窗的行（``(键, 值)``）。纯数据，自测直接断言。

    版本取 ``config.VERSION``（**唯一来源**）；程序名取窗口标题（不 import
    ``desktop.app``——那会与本模块形成循环导入）；数据目录取 ``window.store.root``
    （没有 store 时省略该行）。
    """
    name = str(window.windowTitle() or "") if window is not None else ""
    rows = [("程序名称", name or "古籍重製"), ("版本", f"v{VERSION}")]
    store = getattr(window, "store", None)
    root = getattr(store, "root", None)
    if root:
        rows.append(("数据目录", str(root)))
    rows.append(("项目地址", PROJECT_URL))
    return rows
