# -*- coding: utf-8 -*-
"""1. 纯规则：解析 data.json / 2. sidecar + **生效文件解析**（权重目录换临时目录，不落仓库） / 2b. 防缓存 + \"取最新清单\"（不是\"取最快线路\"） / 3. 下载内核：落**发布名** → 校验 sha256 → 释放占用 → 切换 sidecar → 重新加载 / 3b. 在线兜底：**一份都没有**时才联网下载最新（用户 2026-10-22 第 ⑤ 条）"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import SAMPLE_DATA_JSON, _FakeResponse
    import utils.data_package as dp
    import desktop.workers.data_package_worker as dw
    import hashlib
    import json
    from tests.selftests._context import ok, pump, wait_until
    from tests.common.tmpdir import temp_dir
    import utils.download as ud
    info = dp.parse_data_json(SAMPLE_DATA_JSON)
    ok(
        "解析样例 data.json：取到 bookcontent 版本 100 与文件名/大小",
        info is not None
        and info["version"] == 100
        and info["name"] == "bookcontent-v100.pt"
        and info["size"] == 6245475,
        f"{info}",
    )
    ok(
        "解析：缺 files / 缺 bookcontent / version 非整数 一律 None（不抛异常）",
        dp.parse_data_json({}) is None
        and dp.parse_data_json({"files": {}}) is None
        and dp.parse_data_json({"files": {"bookcontent": {"name": "x"}}}) is None
        and dp.parse_data_json(None) is None,
        "",
    )
    ok(
        "地址：data.json 与资产都拼在 **gujitrain** 的 database release 下",
        dp.data_json_url()
        == "https://github.com/zunkun/gujitrain/releases/download/database/data.json"
        and dp.asset_url("bookcontent-v100.pt")
        == "https://github.com/zunkun/gujitrain/releases/download/database/"
        "bookcontent-v100.pt",
        dp.data_json_url(),
    )
    st.tmp = temp_dir("data_package_")
    real_weights_dir = dp.weights_dir
    dp.weights_dir = lambda: st.tmp  # type: ignore[assignment]
    try:
        ok(
            "空目录：没有生效权重、版本 0（于是远端 v100 必然算更新）",
            dp.resolve_weights() is None
            and dp.read_local_version() == 0
            and dp.effective_info()["source"] == "none",
            f"{dp.effective_info()}",
        )
        ok(
            "版本比较：100 > 0（有新版）、100 == 100（已最新）、0 > 100（更旧）",
            dp.has_update(100)
            and not dp.has_update(100, 100)
            and not dp.has_update(0, 100),
            "",
        )
        ok(
            "文件名解析：bookcontent-v105.pt → 105；其它形态一律 None",
            dp.parse_versioned_name("bookcontent-v105.pt") == 105
            and dp.parse_versioned_name("bookcontent.pt") is None
            and dp.parse_versioned_name("bookcontent-v105.pt.part") is None
            and dp.parse_versioned_name("detect.pt") is None,
            "",
        )

        def _touch(name: str) -> None:
            (st.tmp / name).write_bytes(b"x")

        _touch(dp.LOCAL_WEIGHTS_NAME)
        ok(
            "① 只有 bookcontent.pt → 选它（source=default，版本按 0）",
            dp.resolve_weights() == st.tmp / dp.LOCAL_WEIGHTS_NAME
            and dp.effective_info()["source"] == "default"
            and dp.read_local_version() == 0,
            f"{dp.effective_info()}",
        )
        _touch("bookcontent-v103.pt")
        ok(
            "② sidecar 不存在 → 仍读 bookcontent.pt（不是版本更大的 v103）",
            dp.resolve_weights() == st.tmp / dp.LOCAL_WEIGHTS_NAME,
            f"{dp.resolve_weights()}",
        )
        dp.record_local_version(
            {
                "version": 105,
                "name": "bookcontent-v105.pt",
                "sha256": "AB" * 32,
                "size": 6245475,
            }
        )
        ok(
            "③ sidecar 指的文件不在本地 → 退到**本地版本最大**的 v103（不是 bookcontent.pt）",
            dp.resolve_weights() == st.tmp / "bookcontent-v103.pt"
            and dp.effective_info()["source"] == "latest"
            and dp.read_local_version() == 103,
            f"{dp.effective_info()}",
        )
        _touch("bookcontent-v105.pt")
        ok(
            "④ sidecar 指的文件在本地 → 就是它（source=config、版本 105、sha 转小写）",
            dp.resolve_weights() == st.tmp / "bookcontent-v105.pt"
            and dp.effective_info()["source"] == "config"
            and dp.read_local_version() == 105
            and dp.read_local_info()["sha256"] == ("ab" * 32),
            f"{dp.effective_info()}",
        )
        ok(
            "sidecar 落点就在权重目录旁（bookcontent.version.json）",
            (st.tmp / dp.VERSION_FILE_NAME).is_file(),
            f"{dp.version_file()}",
        )
        ok(
            "目录里可同时有多份权重，versioned_weights 按版本降序",
            [v for v, _ in dp.versioned_weights()] == [105, 103],
            f"{[p.name for _, p in dp.versioned_weights()]}",
        )
        # 删掉生效的 v105：sidecar 还在，但要能退到 v103（而不是报"没有权重"）
        (st.tmp / "bookcontent-v105.pt").unlink()
        ok(
            "⑤ 生效文件被删 → 退到 v103（旧版留着就是为了这种情况）",
            dp.resolve_weights() == st.tmp / "bookcontent-v103.pt"
            and dp.read_local_version() == 103,
            f"{dp.effective_info()}",
        )
        (st.tmp / "bookcontent-v103.pt").unlink()
        ok(
            "⑥ 带版本的全没了 → 退回 bookcontent.pt（兜底）",
            dp.resolve_weights() == st.tmp / dp.LOCAL_WEIGHTS_NAME,
            f"{dp.resolve_weights()}",
        )
        (st.tmp / dp.LOCAL_WEIGHTS_NAME).unlink()
        ok(
            "⑦ 一份都没有 → None（调用方据此联网下载最新）",
            dp.resolve_weights() is None and dp.read_local_version() == 0,
            f"{dp.resolve_weights()}",
        )
        ok(
            "sidecar 还记着 v105、但文件全没了 → 版本报 0（不谎报「已是最新」）",
            dp.read_local_version() == 0,
            f"{dp.read_local_version()}",
        )
        # 迁移兼容（真实形态：旧版下载流程把 v105 改名成了 bookcontent.pt）
        (st.tmp / dp.LOCAL_WEIGHTS_NAME).write_bytes(b"x" * 40)
        dp.record_local_version(
            {"version": 105, "name": "bookcontent-v105.pt", "size": 40}
        )
        ok(
            "迁移：sidecar 记 v105、只剩同大小的 bookcontent.pt → 认定它就是 v105"
            "（不重复下载、版本不退回 0）",
            dp.resolve_weights() == st.tmp / dp.LOCAL_WEIGHTS_NAME
            and dp.effective_info()["source"] == "legacy"
            and dp.read_local_version() == 105,
            f"{dp.effective_info()}",
        )
        (st.tmp / dp.LOCAL_WEIGHTS_NAME).write_bytes(b"x" * 39)
        ok(
            "迁移判据只认**大小一致**：大小对不上就当没装过（版本 0）",
            dp.read_local_version() == 0,
            f"{dp.effective_info()}",
        )
        # 清空目录：第 3 节要从"什么权重都没有"开始，才能断言下载后**没有**
        # bookcontent.pt（不改名）。
        (st.tmp / dp.LOCAL_WEIGHTS_NAME).unlink()
    finally:
        dp.weights_dir = real_weights_dir  # type: ignore[assignment]
    ok(
        "防缓存参数：每次调用都唯一，且不破坏已有的查询串",
        dw._cache_bust("https://x/y.json") != dw._cache_bust("https://x/y.json")
        and dw._cache_bust("https://x/y.json").startswith("https://x/y.json?t=")
        and dw._cache_bust("https://x/y.json?a=1").startswith("https://x/y.json?a=1&t="),
        dw._cache_bust("https://x/y.json"),
    )

    seen_urls: list[str] = []
    real_fetch_one = dw._fetch_one

    def _spy_fetch(prefix, url, timeout):
        seen_urls.append(f"{prefix}|{url}")
        return {"prefix": prefix, "ok": False, "payload": None,
                "reason": "network", "seconds": 0.1}

    dw._fetch_one = _spy_fetch  # type: ignore[assignment]
    try:
        dw.probe_mirrors("https://x/data.json")
    finally:
        dw._fetch_one = real_fetch_one  # type: ignore[assignment]
    ok(
        "测速四条线路一律走防缓存地址（同一次检查共用同一个 t=）",
        len(seen_urls) == len(dw.MIRROR_PREFIXES)
        and all("?t=" in url for url in seen_urls)
        and len({url.split("t=")[1] for url in seen_urls}) == 1,
        f"{seen_urls}",
    )

    # 排名的**第一条**是"缓存命中的旧清单"（更快），第二条才是刚发布的 v101。
    stale_ranking = [
        {"prefix": "https://cdn.gh-proxy.org/", "label": "cdn.gh-proxy.org",
         "ok": True, "reason": "", "seconds": 0.19,
         "payload": json.loads(json.dumps(SAMPLE_DATA_JSON))},
        {"prefix": "", "label": "直连", "ok": True, "reason": "", "seconds": 1.9,
         "payload": {"files": {"bookcontent": {
             "name": "bookcontent-v101.pt", "version": 101,
             "sha256": "b" * 64, "size": 6232163}}}},
    ]
    real_probe = dw.probe_mirrors
    dw.probe_mirrors = lambda *a, **k: stale_ranking  # type: ignore[assignment]
    try:
        fetched = dw.fetch_data_json()
    finally:
        dw.probe_mirrors = real_probe  # type: ignore[assignment]
    ok(
        "清单取**版本最大**那条：旧缓存清单就算排最快也不上当（v101 胜过 v100）",
        fetched["info"]["version"] == 101
        and fetched["asset_name"] == "bookcontent-v101.pt"
        and fetched["download_url"].endswith("/bookcontent-v101.pt")
        and fetched["download_url"].startswith(
            "https://github.com/zunkun/gujitrain/releases/download/database/"),
        f"{fetched['info']} / {fetched['download_url']}",
    )
    st.data = b"0123456789" * 7000
    st.digest = hashlib.sha256(st.data).hexdigest()
    #: 目标**权重目录**（用户口径：下完仍叫 bookcontent-v100.pt，只有一份生效）
    dest = st.tmp
    recorded: list[dict] = []
    phases: list[str] = []
    real_record = dw.record_local_version
    st.real_urlopen = ud.urllib.request.urlopen
    real_release, real_reload = dw._release_model, dw._reload_model
    dw.record_local_version = (  # type: ignore[assignment]
        lambda i, d=None: recorded.append(i)
    )
    dw._release_model = lambda: phases.append("release") or True  # type: ignore[assignment]
    dw._reload_model = lambda: phases.append("reload") or True  # type: ignore[assignment]
    try:
        stages: list[str] = []
        urls: list[str] = []

        def _fake_open(request, timeout=None):
            urls.append(str(getattr(request, "full_url", request)))
            return _FakeResponse(st.data)

        ud.urllib.request.urlopen = _fake_open  # type: ignore[assignment]
        worker = dw.DataDownloadWorker(
            "https://example.invalid/x.pt",
            {
                "version": 100,
                "name": "bookcontent-v100.pt",
                "sha256": st.digest,
                "size": len(st.data),
            },
            dest=dest,
        )
        worker.stage.connect(stages.append)
        result = worker._download()
        ok(
            "下载落地**保留发布名**（bookcontent-v100.pt），不再改名成 bookcontent.pt",
            (dest / "bookcontent-v100.pt").read_bytes() == st.data
            and not (dest / "bookcontent.pt").exists()
            and not (dest / "bookcontent-v100.pt.part").exists()
            and result["path"].endswith("bookcontent-v100.pt"),
            f"{result}",
        )
        ok(
            "下载内核：sha256 校验通过后回带版本号 + 版本记录写的是**发布名**",
            result["version"] == 100
            and result["sha256"] == st.digest
            and bool(recorded)
            and recorded[-1]["version"] == 100
            and recorded[-1]["name"] == "bookcontent-v100.pt",
            f"{result} / {recorded}",
        )
        ok(
            "切换顺序：校验 → 释放占用 → 切换生效文件 → 重新加载",
            stages == ["verify", "release", "replace", "reload"]
            and phases == ["release", "reload"],
            f"stages={stages} phases={phases}",
        )
        ok(
            "下载请求也走防缓存地址（同名重传时不被缓存副本坑成 sha 不符）",
            bool(urls) and "?t=" in urls[-1],
            f"{urls[-1] if urls else None}",
        )

        # 重下同一版本：本地已有同名同 sha 的文件 ⇒ 不下载、不覆盖，直接切换生效
        before_urls = len(urls)
        again = dw.DataDownloadWorker(
            "https://example.invalid/x.pt",
            {
                "version": 100,
                "name": "bookcontent-v100.pt",
                "sha256": st.digest,
                "size": len(st.data),
            },
            dest=dest,
        )
        again_stages: list[str] = []
        again.stage.connect(again_stages.append)
        again._download()
        ok(
            "本地已有同名同 sha 的权重：**不重复下载**（也不往被占用的文件上覆盖），"
            "照样走一遍切换",
            len(urls) == before_urls
            and again_stages == ["verify", "release", "replace", "reload"],
            f"urls={len(urls)-before_urls} stages={again_stages}",
        )

        # sha 不符：删掉下好的文件、**不启用**（不写版本记录）
        before = len(recorded)
        ud.urllib.request.urlopen = (  # type: ignore[assignment]
            lambda request, timeout=None: _FakeResponse(b"tampered"))
        bad = dw.DataDownloadWorker(
            "https://example.invalid/x.pt",
            {
                "version": 101,
                "name": "bookcontent-v101.pt",
                "sha256": st.digest,
                "size": 8,
            },
            dest=dest,
        )
        raised = False
        try:
            bad._download()
        except ValueError:
            raised = True
        ok(
            "校验不符：抛错、旧的 v100 **不受影响**、下坏的 v101 删掉、不写版本记录",
            raised
            and (dest / "bookcontent-v100.pt").read_bytes() == st.data
            and not (dest / "bookcontent-v101.pt").exists()
            and len(recorded) == before,
            f"raised={raised} recorded={recorded}",
        )

        # 取消：写出临时文件后中断（不落任何最终文件）
        ud.urllib.request.urlopen = (  # type: ignore[assignment]
            lambda request, timeout=None: _FakeResponse(st.data))
        cancelled = dw.DataDownloadWorker(
            "https://example.invalid/x.pt",
            {
                "version": 102,
                "name": "bookcontent-v102.pt",
                "sha256": st.digest,
                "size": len(st.data),
            },
            dest=dest,
        )
        cancelled.cancel()
        stopped = False
        try:
            cancelled._download()
        except dw._Cancelled:
            stopped = True
        ok(
            "取消下载：抛 _Cancelled 且不留任何文件（已生效的 v100 保持原样）",
            stopped
            and (dest / "bookcontent-v100.pt").read_bytes() == st.data
            and not (dest / "bookcontent-v102.pt").exists()
            and not (dest / "bookcontent-v102.pt.part").exists(),
            f"stopped={stopped}",
        )
    finally:
        dw.record_local_version = real_record  # type: ignore[assignment]
        ud.urllib.request.urlopen = st.real_urlopen  # type: ignore[assignment]
        dw._release_model = real_release  # type: ignore[assignment]
        dw._reload_model = real_reload  # type: ignore[assignment]
    online = temp_dir("data_package_online_")
    real_dir = dp.weights_dir
    real_fetch_latest = dp.fetch_latest_info
    dp.weights_dir = lambda: online  # type: ignore[assignment]
    try:
        picked: list[int] = []

        def _fake_latest(*_a, **_k):
            picked.append(1)
            return {
                "info": {"version": 105, "name": "bookcontent-v105.pt",
                         "sha256": st.digest, "size": len(st.data), "date": ""},
                "asset_name": "bookcontent-v105.pt",
                "mirror_prefix": "https://v6.gh-proxy.org/",
                "mirror_label": "v6.gh-proxy.org",
            }

        dp.fetch_latest_info = _fake_latest  # type: ignore[assignment]
        ud.urllib.request.urlopen = (  # type: ignore[assignment]
            lambda request, timeout=None: _FakeResponse(st.data))
        (online / dp.LOCAL_WEIGHTS_NAME).write_bytes(b"x")
        ok(
            "本地还有权重时 ensure_weights_online **不联网**（直接返回本地那份）",
            dp.ensure_weights_online() == online / dp.LOCAL_WEIGHTS_NAME
            and picked == [],
            f"{picked}",
        )
        (online / dp.LOCAL_WEIGHTS_NAME).unlink()
        path = dp.ensure_weights_online()
        ok(
            "一份都没有时：联网取最新 → 下到**发布名** → 写 sidecar（版本 105）",
            path == online / "bookcontent-v105.pt"
            and path.read_bytes() == st.data
            and dp.read_local_version() == 105
            and dp.effective_info()["source"] == "config"
            and bool(picked),
            f"{dp.effective_info()}",
        )
    finally:
        dp.weights_dir = real_dir  # type: ignore[assignment]
        dp.fetch_latest_info = real_fetch_latest  # type: ignore[assignment]
        ud.urllib.request.urlopen = st.real_urlopen  # type: ignore[assignment]

