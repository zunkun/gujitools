# -*- coding: utf-8 -*-
"""desktop 单例守卫（2026-10-13 升级：激活通道从"按标题找窗口"改为
按构建身份命名的 QLocalServer 定向回报 HWND）。

覆盖：
1. 互斥体/通道名由构建身份哈希派生——同一构建稳定不变，两个构建
   （开发版 vs 正式版）互不相同，这是"开发窗口与生产窗口可同时存在"的根基。
2. 互斥体：第一次 acquire True；同身份第二次 False（ERROR_ALREADY_EXISTS）。
3. 激活通道：server listen 后客户端能连上并拿到**非零** HWND（证明
   连接→读请求→provider→回执全链路通）；第二次客户端连接依然可用
   （一次性闸门不能把服务锁死）；无服务的身份返回 False；provider
   返回 None 回 "0"、客户端安全返回 False。
"""

NAME = "single_instance"
DEPENDS: list[str] = []
TITLE = "desktop 单例守卫"


def run(ctx) -> None:
    import hashlib

    from PySide6.QtWidgets import QWidget

    import desktop.single_instance as si
    from tests.selftests._context import ok

    dev_id = r"D:\workspace\gujitools\desktop"
    prod_id = r"C:\Program Files\guji\guji\_internal\desktop"

    # ---- 1. 名字按构建身份派生 ----
    ok("互斥体名确定性（同身份同名）",
       si.mutex_name(dev_id) == si.mutex_name(dev_id))
    ok("通道名确定性（同身份同名）",
       si.channel_name(dev_id) == si.channel_name(dev_id))
    ok("互斥体与通道前缀不同（同身份也不撞名）",
       si.mutex_name(dev_id) != si.channel_name(dev_id))
    ok("开发版与正式版互斥体不同（可同时存在）",
       si.mutex_name(dev_id) != si.mutex_name(prod_id))
    ok("开发版与正式版通道不同（激活永不错靶）",
       si.channel_name(dev_id) != si.channel_name(prod_id))
    ok("名字带身份哈希", hashlib.md5(dev_id.encode()).hexdigest()[:10]
       in si.mutex_name(dev_id))

    # ---- 2. 互斥体：第一次 True、同身份第二次 False ----
    # ⚠️ 模块级 _held_mutex 有"已持有直接 True"的短路，测试前清掉；
    #    用独立测试身份，不碰真实构建身份。
    test_id = "selftest-single-instance"
    si._held_mutex = None
    ok("首次 acquire 成功", si.acquire(test_id) is True)
    si._held_mutex = None  # 只清短路标志：真实互斥体仍在（同名再拿必报已存在）
    ok("同身份第二次 acquire 被拒", si.acquire(test_id) is False)

    # ---- 3. 激活通道 ----
    # 客户端 try_activate_existing 自带嵌套 QEventLoop（信号驱动），主线程
    # 直接调用即可——嵌套 loop 会同时把服务端的事件转起来（两端同进程也通）。
    from PySide6.QtWidgets import QWidget

    window = QWidget()
    served: list = []

    def provider():
        served.append(1)
        return window

    si._server = None
    ok("server 启动成功", si.start_activation_server(test_id, provider) is True)
    ok("重复启动幂等（返回已监听状态）",
       si.start_activation_server(test_id, provider) is True)

    ok("客户端连上并拿到非零 HWND（全链路通）",
       si.try_activate_existing(test_id) is True)
    ok("provider 被调用过", bool(served))
    ok("第二次客户端连接依然可用（一次性闸门不锁死服务）",
       si.try_activate_existing(test_id) is True)

    # ⚠️ 收场必须显式 close：server→信号连接→闭包→server 是循环引用，
    #    仅把 _server 置 None 不会立刻销毁，旧监听会继续抢答。
    si._server.close()
    si._server = None

    other_id = "selftest-single-instance-other"
    ok("无 server 的身份返回 False", si.try_activate_existing(other_id) is False)

    si.start_activation_server(test_id, lambda: None)
    ok("provider 回 None → 客户端安全返回 False",
       si.try_activate_existing(test_id) is False)

    # 清场：关掉测试服务，不留监听管道
    si._server.close()
    si._server = None
