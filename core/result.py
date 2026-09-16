"""
File: core/result.py
统一的阶段结果与状态语义。

背景：同一件事在两侧各有表述——
- cli 侧用进程退出码：0 / 1 / 130；
- desktop 侧用状态字符串：pending / running / success / failed / cancelled，
  并在 runner.py 与 store 中各自维护一份映射。

本模块把二者收敛为单一枚举 + 双向转换，任一入口都从这里取值。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class StageStatus(str, Enum):
    """阶段状态。继承 str 以便直接与 JSON / 数据库中的字符串比较。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def from_exit_code(cls, code: int) -> "StageStatus":
        """退出码 → 状态：0 成功；130 中断（Ctrl+C）；其余失败。"""
        if code == 0:
            return cls.SUCCESS
        if code == 130:
            return cls.CANCELLED
        return cls.FAILED

    def to_exit_code(self) -> int:
        """状态 → 退出码（CLI 进程退出用）。"""
        return {
            StageStatus.SUCCESS: 0,
            StageStatus.CANCELLED: 130,
            StageStatus.FAILED: 1,
        }.get(self, 1)


# 状态 → 中文标签（原 runner.STATUS_LABELS，两侧共用）
STAGE_STATUS_LABELS: Dict[str, str] = {
    StageStatus.PENDING.value: "未执行",
    StageStatus.RUNNING.value: "执行中",
    StageStatus.SUCCESS.value: "成功",
    StageStatus.FAILED.value: "失败",
    StageStatus.CANCELLED.value: "已中断",
}

# 是否终态
TERMINAL_STATUSES = frozenset(
    {StageStatus.SUCCESS.value, StageStatus.FAILED.value, StageStatus.CANCELLED.value}
)


def exit_code_for(status: str) -> int:
    """字符串状态 → 退出码；未知状态按失败处理。"""
    try:
        return StageStatus(status).to_exit_code()
    except ValueError:
        return 1


def status_for_exit_code(code: int) -> str:
    """退出码 → 字符串状态。"""
    return StageStatus.from_exit_code(code).value


@dataclass
class StageResult:
    """功能/阶段执行的统一结果。

    取代原先「cli 只看退出码、desktop 只看 result dict」的碎片化传递：
    两侧都拿到同一个结构，各自取所需字段渲染。

    属性:
        status: 标准化状态。
        exit_code: 对应退出码，供 CLI 直接使用。
        output: 输出目录（若有）。
        processed: 已处理数量。
        status_counts: 各处理状态计数（success/skipped/error…）。
        message: 失败原因或补充说明。
        raw: 功能模块原始返回字典（保留供桥接期使用）。
    """

    status: str
    exit_code: int = 0
    output: Optional[str] = None
    processed: int = 0
    status_counts: Dict[str, int] = field(default_factory=dict)
    message: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    @classmethod
    def from_function_result(
        cls,
        result: Optional[Dict[str, Any]],
        status: str = StageStatus.SUCCESS.value,
        message: Optional[str] = None,
    ) -> "StageResult":
        """由 FunctionBase.execute() 的返回字典构造。"""
        result = result or {}
        counts = {
            k: v
            for k, v in result.items()
            if k not in ("processed", "output") and isinstance(v, int)
        }
        return cls(
            status=status,
            exit_code=exit_code_for(status),
            output=result.get("output"),
            processed=int(result.get("processed", 0) or 0),
            status_counts=counts,
            message=message,
            raw=result,
        )

    def to_dict(self) -> Dict[str, Any]:
        """转为可 JSON 序列化的字典。"""
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "output": self.output,
            "processed": self.processed,
            "status_counts": dict(self.status_counts),
            "message": self.message,
        }
