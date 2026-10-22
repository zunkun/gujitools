# -*- coding: utf-8 -*-
"""去底色预览：单视图显示，去底色结果优先，顶部用分段开关切换原图。

左侧缩略图条按"输出条目"组织：
- 每个文本框一条（标签 <页>-l / <页>-r），右侧显示该框 + border 区域；
- 整幅页一条（标签就是页名），显示该整幅框 + border 区域。

区域合成在 worker 线程完成，不生成文件；通过请求令牌避免快速切换串台。
"""


from __future__ import annotations

from .core import RembgPreviewWidget

__all__ = ["RembgPreviewWidget"]
