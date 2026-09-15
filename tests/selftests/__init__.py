# -*- coding: utf-8 -*-
"""GUI 自测用例包：一个功能一个模块，由 tests/gui_selftest.py 动态发现。

模块约定：

- ``NAME``：模块标识（--only/--skip 用这个名字）；
- ``DEPENDS``：依赖的其他模块名列表（运行器自动补跑依赖、拓扑排序）；
- ``TITLE``：输出里显示的中文章节名；
- ``run(ctx)``：执行用例，ctx 见 ``_context.Context``。

新增用例 = 在本目录新增一个 .py 文件；删除用例 = 删文件或运行时 --skip。
下划线开头的文件（如 _context.py）是内部设施，不当作用例。
"""
