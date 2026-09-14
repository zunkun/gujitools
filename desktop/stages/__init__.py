# -*- coding: utf-8 -*-
"""worker 子进程的阶段执行器（subprocess 侧，不含 GUI）。

按职责分文件：
- events        ：JSON Lines 事件输出 + print 拦截/进度解析
- detect_stage  ：detect 阶段（YOLO 文本框检测）
- generic_stage ：通用 CLI 阶段 + extract 渲染阶段
- print_stage   ：print 阶段（效果图合成 + 生成 PDF）
- rembg_stage   ：rembg_submit 阶段（最终图片合成）
"""

from desktop.stages.events import ProgressStream, emit
from desktop.stages.detect_stage import run_detect, run_detect_stage
from desktop.stages.generic_stage import run_extract_stage, run_stage
from desktop.stages.print_stage import run_print_stage
from desktop.stages.rembg_stage import run_rembg_submit_stage

__all__ = [
    "ProgressStream",
    "emit",
    "run_detect",
    "run_detect_stage",
    "run_extract_stage",
    "run_stage",
    "run_print_stage",
    "run_rembg_submit_stage",
]
