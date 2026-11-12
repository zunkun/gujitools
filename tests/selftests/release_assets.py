# -*- coding: utf-8 -*-
"""发布资产守卫：安装包 + 绿色免安装版同名同规则、一起上传。

背景（2026-11-03）：``publish_release.py`` 原先只认安装包，绿色版只能手工传。
现在 Windows 构建同时产出 ``gujitools_setup_<版本>_<平台>.exe`` 与
``gujitools_portable_<版本>_<平台>.zip``（**不带时间戳**），发布时一起上传。

本模块钉死三件事：

1. ``build.py`` 的 ``PORTABLE_TEMPLATE`` 产出的名字能被 ``publish_release.py`` 的
   资产规则识别（改一处忘改另一处 ⇒ 绿色版被静默漏发）；
2. 同一版本的多份资产（安装包 + 绿色版）能一起找到，其它版本/无关文件不混入；
3. 客户端「检查更新」（``update_worker.pick_asset``）仍然只认 ``.exe``，
   绿色版 zip 不能把安装包挤掉。
"""

NAME = "release_assets"
DEPENDS: list[str] = []
TITLE = "发布资产：安装包与绿色免安装版同名规则、一起上传"


def run(ctx) -> None:
    from pathlib import Path

    from tests.selftests._context import ok
    from tests.tmpdir import temp_dir

    import build
    import publish_release as release

    version = "2.0.99"
    platform = "windows-x86_64" if build.IS_WINDOWS else "linux-x86_64"
    name = build.PORTABLE_TEMPLATE.format(version=version, platform=platform)

    # ---- 1. 绿色版命名：build.py 产出 ⇄ publish_release.py 识别同源，且不含时间戳 ----
    ok(f"build.py 的绿色版产物名（{name}）能被 publish_release.py 识别",
       release._parse_asset(name) == version, str(release._parse_asset(name)))
    ok("产物名只含「版本 + 平台」，不含构建时间戳",
       f"_{version}_{platform}" in name and "2026" not in name, name)
    ok("绿色版文件名的平台后缀正确（Windows 为 zip，Linux 为 tar.gz）",
       name.endswith(".zip") if build.IS_WINDOWS else name.endswith(".tar.gz"),
       name)

    # ---- 2. 同版本资产全收：安装包 + 绿色版；其它版本/无关文件不混入 ----
    tmp = Path(temp_dir("release_assets_"))
    installer = tmp / f"gujitools_setup_{version}_{platform}.exe"
    portable = tmp / name
    other_version = tmp / "gujitools_setup_1.0.0_windows-x86_64.exe"
    unrelated = tmp / "unrelated.txt"
    for path in (installer, portable, other_version):
        path.write_bytes(b"x")
    unrelated.write_text("x", encoding="utf-8")

    real_dist = release.DIST
    release.DIST = tmp
    try:
        assets = release._find_assets(version)
        ok("同版本资产全收：安装包 + 绿色版（且不混入其它版本/无关文件）",
           set(assets) == {installer, portable},
           str([path.name for path in assets]))
        ok("资产按文件名排序（顺序稳定）",
           assets == sorted(assets),
           str([path.name for path in assets]))

        try:
            release._find_assets("9.9.9")
        except release.ReleaseError as exc:
            message = str(exc)
            ok("找不到版本时，报错里带出 dist/ 现有版本",
               "9.9.9" in message and version in message, message)
        else:
            raise AssertionError("[FAIL] 版本缺失时没有报错")
    finally:
        release.DIST = real_dist

    # ---- 3. 检查更新只认 .exe ----
    from desktop.workers.update_worker import pick_asset

    payload = {
        "assets": [
            {"name": portable.name,
             "browser_download_url": "https://example.test/portable.zip"},
            {"name": installer.name,
             "browser_download_url": "https://example.test/setup.exe"},
        ]
    }
    chosen = pick_asset(payload)
    ok("检查更新仍挑 .exe 资产（绿色版 zip 不会挤掉安装包）",
       chosen.get("name", "").endswith(".exe"), str(chosen.get("name")))
