#!/usr/bin/env python
"""发布新版本：把 ``dist/`` 里的发布资产与线上 Release 比对，必要时发布。

流程（脚本自己判断该不该发）：

1. 从 ``config.py`` 读当前版本号，在 ``dist/`` 里找**同版本**的发布资产
   （Windows：安装包 + 绿色免安装 zip；Linux：绿色免安装 tar.gz）；
2. 用 ``gh`` 查线上最新 Release 的 tag，按 ``utils.version`` 的规则比大小；
3. 线上已不比本地旧 → 直接退出，不重复发布；
4. 本地较新 → 自动提交版本号、推送分支、打 tag，
   再用 ``gh release create`` 把**全部资产**一起上传并设为 latest。

用法::

    python tools/release.py                          # 发布 config.py 当前版本
    python tools/release.py --title "自定义流程优化"   # Release 标题后缀
    python tools/release.py --notes "本次更新：..."    # 手写发布说明
    python tools/release.py --build                  # 先跑 python build.py 再发布
    python tools/release.py --dry-run                # 只打印计划，不改任何东西
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 复用运行时的版本比较规则（纯规则模块，不拉进 cv2/torch）
sys.path.insert(0, str(ROOT))

from utils.version import compare, parse_version

CONFIG = ROOT / "config.py"
DIST = ROOT / "dist"

#: ``dist/`` 里可上传的发布资产：``<名称>_<版本>_<平台>.<后缀>``，不含时间戳。
#: - Windows：安装包 ``gujitools_setup_*.exe`` + 绿色免安装 ``gujitools_portable_*.zip``；
#: - Linux：绿色免安装 ``gujitools_portable_*.tar.gz``（Linux 没有安装包）。
#: ⚠️ 绿色版命名与 ``build.py`` 的 ``PORTABLE_TEMPLATE`` 同源，
#: 守卫见 ``tests/selftests/release_assets.py``。
_ASSET_PATTERNS = (
    re.compile(r"^gujitools_setup_(?P<version>.+)_(?:windows|linux)-[\w.-]+\.exe$"),
    re.compile(
        r"^gujitools_portable_(?P<version>.+)_(?:windows|linux)-[\w.-]+\.(?:zip|tar\.gz)$"
    ),
)


class ReleaseError(Exception):
    """可预期的失败：打印中文原因后以非零退出码结束。"""


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """执行外部命令；失败时抛出带 stdout/stderr 的 ReleaseError。"""
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ReleaseError(f"命令失败（退出码 {result.returncode}）：{' '.join(cmd)}\n{detail}")
    return result


def _git(*args: str, check: bool = True) -> str:
    return _run(["git", *args], check=check).stdout.strip()


def _gh(*args: str, check: bool = True) -> str:
    return _run(["gh", *args], check=check).stdout.strip()


def _config_version() -> str:
    """从 config.py 读 VERSION（不 import，避免受 tools/ 下 sys.path 影响）。"""
    match = re.search(
        r"""^VERSION\s*=\s*["']([^"']+)["']""",
        CONFIG.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if match is None:
        raise ReleaseError(f"未能在 {CONFIG} 中找到 VERSION 定义")
    return match.group(1)


def _parse_asset(name: str) -> str | None:
    """从发布资产的文件名解析版本号；不是资产则返回 None。"""
    for pattern in _ASSET_PATTERNS:
        match = pattern.match(name)
        if match is not None:
            return match.group("version")
    return None


def _find_assets(version: str) -> list[Path]:
    """在 dist/ 里找指定版本的**全部**发布资产；找不到时列出 dist 里现有版本。

    产物名不含时间戳，同一版本重打会覆盖同名文件，因此这里按版本号全收：
    Windows 通常得到安装包 + 绿色版 zip 两个，Linux 只有绿色版 tar.gz。
    """
    if not DIST.is_dir():
        raise ReleaseError("没有 dist/ 目录，请先执行 python build.py 打包")

    assets = sorted(
        path
        for path in DIST.iterdir()
        if path.is_file() and _parse_asset(path.name) == version
    )
    if not assets:
        available = sorted(
            {
                found
                for path in DIST.iterdir()
                if path.is_file()
                if (found := _parse_asset(path.name)) is not None
            }
        )
        hint = (
            f"dist/ 里现有版本：{', '.join(available)}"
            if available
            else "dist/ 里没有发布资产"
        )
        raise ReleaseError(
            f"dist/ 里没有版本 {version} 的发布资产（{hint}）。"
            "请先执行 python build.py，或加 --build 让脚本自动打包"
        )
    return assets


def _latest_online_tag() -> str:
    """线上最新 Release 的 tag；一个 Release 都没有时返回空串。"""
    output = _gh(
        "release", "list", "--limit", "1", "--json", "tagName", "--jq", ".[0].tagName"
    )
    return "" if output in ("", "null") else output


def _release_exists(tag: str) -> bool:
    result = _run(["gh", "release", "view", tag, "--json", "tagName"], check=False)
    return result.returncode == 0


def _repo_slug() -> str:
    return _gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner")


def _remote_tag_exists(repo: str, tag: str) -> bool:
    """用 gh API 查远端 tag（比 git ls-remote 更稳，且与 gh 共用同一套凭据）。"""
    result = _run(["gh", "api", f"repos/{repo}/git/ref/tags/{tag}"], check=False)
    return result.returncode == 0


def _check_auth() -> None:
    result = _run(["gh", "auth", "status"], check=False)
    if result.returncode != 0:
        raise ReleaseError("gh 尚未登录，请先执行 gh auth login")


def _prepare_worktree(version: str, dry_run: bool) -> None:
    """工作区只允许有「config.py 版本号」这一处未提交改动，并自动提交它。"""
    # ⚠️ 不能用 _git（它会 strip 整个输出）：porcelain 的第一行以状态空格开头，
    #    整段 strip 会把首个路径吃掉一个字符（" M config.py" → "onfig.py"）。
    status = _run(["git", "status", "--porcelain"]).stdout
    dirty = [line for line in status.splitlines() if line.strip()]
    dirty_paths = [line[3:].strip() for line in dirty]

    others = [path for path in dirty_paths if path != "config.py"]
    if others:
        raise ReleaseError(
            "工作区还有未提交的改动，发布脚本不会替你一并提交：\n  "
            + "\n  ".join(others)
            + "\n请先自行提交或清理后再发布"
        )

    if "config.py" not in dirty_paths:
        return

    # config.py 只改版本号才自动提交；混了别的改动就拒绝
    diff = _git("diff", "--", "config.py")
    changed = [
        line
        for line in diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    if not changed or any("VERSION" not in line for line in changed):
        raise ReleaseError("config.py 的未提交改动不只是版本号，请先自行处理")

    if dry_run:
        print(f"  [dry-run] 将提交 config.py（版本号 → {version}）")
        return
    _git("add", "config.py")
    _git("commit", "-m", "update: version")
    print("✅ 已提交版本号变更：update: version")


def _push_branch(dry_run: bool) -> None:
    """把当前分支推到远端（落后远端时拒绝发布，避免带着旧代码打 tag）。"""
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    upstream = _run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        check=False,
    )
    if upstream.returncode != 0:
        if dry_run:
            print(f"  [dry-run] 将推送分支 {branch}（首次推送并设置 upstream）")
            return
        _git("push", "-u", "origin", branch)
        print(f"✅ 已推送分支 {branch}")
        return

    behind, ahead = (int(part) for part in _git(
        "rev-list", "--left-right", "--count", "@{upstream}...HEAD"
    ).split())
    if behind > 0:
        raise ReleaseError(
            f"本地分支比远端落后 {behind} 个提交，请先同步（git pull）后再发布"
        )
    if ahead == 0:
        print(f"   分支 {branch} 已与远端同步")
        return
    if dry_run:
        print(f"  [dry-run] 将推送分支 {branch}（{ahead} 个提交）")
        return
    _git("push", "origin", branch)
    print(f"✅ 已推送分支 {branch}（{ahead} 个提交）")


def _create_tag(version: str, dry_run: bool) -> str:
    """在 HEAD 上打轻量 tag（与仓库现有 v2.0.x 形式一致）。"""
    tag = f"v{version}"
    local = _run(["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"], check=False)
    if local.returncode == 0:
        tag_commit = _git("rev-parse", f"{tag}^{{commit}}")
        head = _git("rev-parse", "HEAD")
        if tag_commit != head:
            raise ReleaseError(f"tag {tag} 已存在且不在当前 HEAD 上，请先处理该 tag")
        print(f"   复用已存在的 tag {tag}")
    else:
        if dry_run:
            print(f"  [dry-run] 将在 HEAD 创建 tag {tag}")
        else:
            _git("tag", tag)
            print(f"✅ 已创建 tag {tag}")

    if dry_run:
        print(f"  [dry-run] 将推送 tag {tag}")
        return tag
    if _remote_tag_exists(_repo_slug(), tag):
        print(f"   远端已有 tag {tag}")
    else:
        _git("push", "origin", tag)
        print(f"✅ 已推送 tag {tag}")
    return tag


def _asset_notes(assets: list[Path]) -> str:
    """按实际上传的资产生成固定的「安装包说明」，免得用户分不清 setup / portable。"""
    lines: list[str] = []
    if any(asset.name.startswith("gujitools_setup_") for asset in assets):
        lines.append("- `gujitools_setup_*.exe`：Windows 安装版（带安装向导）")
    if any(
        asset.name.startswith("gujitools_portable_") and asset.name.endswith(".zip")
        for asset in assets
    ):
        lines.append("- `gujitools_portable_*.zip`：绿色免安装版（解压即用，无需安装）")
    if any(
        asset.name.startswith("gujitools_portable_") and asset.name.endswith(".tar.gz")
        for asset in assets
    ):
        lines.append("- `gujitools_portable_*.tar.gz`：绿色免安装版（解压即用，无需安装）")
    if not lines:
        return ""
    return "安装包说明：\n" + "\n".join(lines)


def _release_notes(previous_tag: str) -> str:
    """从上一版以来的提交生成发布说明（跳过版本号提交与合并提交）。"""
    git_range = f"{previous_tag}..HEAD" if parse_version(previous_tag) else "--max-count=20 HEAD"
    subjects = _git("log", git_range, "--no-merges", "--format=%s").splitlines()
    bullets = [
        subject.strip()
        for subject in subjects
        if subject.strip()
        and not subject.strip().lower().startswith("update: version")
        and not subject.strip().lower().startswith("merge ")
    ]
    if not bullets:
        bullets = ["版本更新"]
    return "本次更新：\n" + "\n".join(f"- {subject}" for subject in bullets)


def _arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="比对 dist/ 安装包与线上版本并发布")
    parser.add_argument("--title", default="", help="Release 标题后缀（默认只有 v<版本>）")
    parser.add_argument("--notes", default="", help="手写发布说明（默认按提交记录生成）")
    parser.add_argument("--build", action="store_true", help="发布前先执行 python build.py")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不提交、不推送、不发布")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _arg_parser().parse_args(argv)

    try:
        _check_auth()

        version = _config_version()
        print(f"本地版本: {version}")

        if args.build:
            print("▶ 执行 python build.py ...")
            result = subprocess.run([sys.executable, "build.py"], cwd=ROOT)
            if result.returncode != 0:
                raise ReleaseError("打包失败，已中止发布")

        assets = _find_assets(version)
        for asset in assets:
            size_mb = asset.stat().st_size / 1024 / 1024
            print(f"发布资产: {asset.relative_to(ROOT)}（{size_mb:.0f} MB）")

        online_tag = _latest_online_tag()
        print(f"线上最新: {online_tag or '（尚无 Release）'}")

        if online_tag and compare(version, online_tag) <= 0:
            print(f"✅ 线上 {online_tag} 已不比本地 {version} 旧，无需发布")
            return 0

        _prepare_worktree(version, args.dry_run)
        _push_branch(args.dry_run)
        tag = _create_tag(version, args.dry_run)

        if _release_exists(tag):
            raise ReleaseError(f"Release {tag} 已存在，不能重复发布")

        notes = args.notes.strip() or _release_notes(online_tag)
        asset_notes = _asset_notes(assets)
        if asset_notes:
            notes = f"{notes}\n\n{asset_notes}"
        title = f"v{version} {args.title}".strip()

        print(f"\n▶ 发布 {tag}：《{title}》")
        print(notes)
        if args.dry_run:
            print(
                "[dry-run] 将上传 "
                f"{', '.join(asset.name for asset in assets)} 并设为 latest"
            )
            return 0

        url = _gh(
            "release",
            "create",
            tag,
            *[str(asset) for asset in assets],
            "--title",
            title,
            "--notes",
            notes,
            "--latest",
        )
        print(f"✅ 发布完成: {url}")
        return 0
    except ReleaseError as exc:
        print(f"\n❌ {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
