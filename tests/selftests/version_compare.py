# -*- coding: utf-8 -*-
"""版本号解析/比较（``utils/version.py``）的纯函数护栏。

为什么单列一个模块：这套规则**只在"检查更新"里用**，却是那一整条链上唯一
"判错了用户就得不出有用结论"的地方——判成"有新版本"会骗人去下载、
判成"已是最新"会让用户错过更新。规则本身与 Qt / 网络无关，用纯函数逐条钉死
比在弹窗里断言便宜得多。

覆盖四类边界（与 ``utils/version.py`` 模块头的四条约定一一对应）：
数值比较（不是字典序）、缺位补 0、预发布更旧、构建元数据忽略；
外加"**任何垃圾输入都不许抛异常**、且不可比时一律不说有新版本"。
"""

from tests.selftests._context import ok

NAME = "version_compare"
TITLE = "版本号解析与比较"
DEPENDS: list[str] = []


def run(ctx) -> None:
    from utils.version import compare, is_newer, is_prerelease, parse_version

    # ---- 1. 解析：剥 v 前缀、点分段、垃圾输入退化成 () ----
    ok("解析：v2.0.4 与 2.0.4 同值（v/V 前缀剥掉）",
       parse_version("v2.0.4") == (2, 0, 4)
       and parse_version("V2.0.4") == (2, 0, 4)
       and parse_version("2.0.4") == (2, 0, 4),
       f"{parse_version('v2.0.4')} / {parse_version('2.0.4')}")
    ok("解析：只吃数字核（2.0.4+b57 / 2.1.0-rc1 都停在 2.0.4 / 2.1.0）",
       parse_version("2.0.4+b57") == (2, 0, 4)
       and parse_version("2.1.0-rc1") == (2, 1, 0),
       f"{parse_version('2.0.4+b57')} / {parse_version('2.1.0-rc1')}")
    ok("解析：非版本串返回 ()，且不抛异常（含 None / 空串 / 纯文字）",
       parse_version("release") == ()
       and parse_version("") == ()
       and parse_version(None) == ()
       and parse_version("合订本") == (),
       f"{parse_version('release')} / {parse_version(None)}")

    # ---- 2. 比较：数值序、缺位补 0、不可比为 0 ----
    ok("比较：2.10.0 大于 2.9.0（数值比较，不是字典序）",
       compare("2.10.0", "2.9.0") == 1 and compare("2.9.0", "2.10.0") == -1,
       f"{compare('2.10.0', '2.9.0')}")
    ok("比较：2.0 == 2.0.0，而 2.0.1 大于 2.0（缺位补 0）",
       compare("2.0", "2.0.0") == 0 and compare("2.0.1", "2.0") == 1,
       f"{compare('2.0', '2.0.0')} / {compare('2.0.1', '2.0')}")
    ok("比较：任一侧不可比都返回 0（不抛异常、也不假装谁大）",
       compare("2.0.4", "release") == 0 and compare("release", "2.0.4") == 0,
       f"{compare('2.0.4', 'release')}")

    # ---- 3. is_newer：主用途（该不该提示"有新版本"）----
    ok("更新判定：同版本不算新、更高的算新、更低的算旧",
       not is_newer("2.0.4", "2.0.4")
       and is_newer("2.0.5", "2.0.4")
       and not is_newer("2.0.3", "2.0.4"),
       f"{is_newer('2.0.5', '2.0.4')} / {is_newer('2.0.3', '2.0.4')}")
    ok("更新判定：2.10.0 比 2.9.0 新（数值序在 is_newer 里也成立）",
       is_newer("2.10.0", "2.9.0"), f"{is_newer('2.10.0', '2.9.0')}")
    ok("更新判定：同核的预发布更旧（2.1.0-rc1 → 2.1.0 算更新）",
       is_newer("2.1.0", "2.1.0-rc1") and not is_newer("2.1.0-rc1", "2.1.0"),
       f"{is_newer('2.1.0', '2.1.0-rc1')} / {is_newer('2.1.0-rc1', '2.1.0')}")
    ok("更新判定：最新版 tag 解析不出来时不说有新版本（宁可不报）",
       not is_newer("release", "2.0.4") and not is_newer(None, "2.0.4")
       and not is_newer("", "2.0.4"),
       f"{is_newer('release', '2.0.4')}")

    # ---- 4. 预发布判定：构建元数据不算预发布 ----
    ok("预发布判定：rc/beta 算预发布，纯版本号与 +build 都不算",
       is_prerelease("2.1.0-rc1")
       and is_prerelease("2.0.4-beta2")
       and not is_prerelease("2.0.4")
       and not is_prerelease("v2.0.4")
       and not is_prerelease("2.0.4+b57")
       and not is_prerelease("release"),
       f"rc1={is_prerelease('2.1.0-rc1')} b57={is_prerelease('2.0.4+b57')}")
    ok("预发布判定：纯数字附加段（2.0.4-1）不算预发布",
       not is_prerelease("2.0.4-1"), f"{is_prerelease('2.0.4-1')}")
