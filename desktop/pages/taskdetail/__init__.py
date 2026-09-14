"""任务详情页：一个页面骨架 + 按职责拆分的控制器 Mixin。

- page.py       TaskDetailPage 骨架（任务切换/阶段切换/状态刷新），组合下列 Mixin
- view.py       视图组装（头部/步骤条/预览区/控制列/日志）
- manifest.py   页面清单、缩略图、页面增删
- history.py    历史执行配置回填
- submit.py     rembg 提交控制器与按钮状态
- print_list.py 第四步待打印列表
- runner.py     阶段执行（worker 子进程编排）
- detect.py     detect 检测控制
"""

from desktop.pages.taskdetail.page import TaskDetailPage

__all__ = ["TaskDetailPage"]
