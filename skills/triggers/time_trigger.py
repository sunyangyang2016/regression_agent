"""
时间触发器 - 基于时间条件触发技能（定时任务）
"""
from datetime import datetime, time, timedelta
from typing import Optional, Callable


class TimeTrigger:
    """时间触发器 - 根据时间条件触发技能"""

    def __init__(
        self,
        skill_name: str,
        trigger_time: Optional[time] = None,
        interval_minutes: Optional[int] = None,
        weekdays: Optional[list] = None,
    ):
        self.skill_name = skill_name
        self.trigger_time = trigger_time
        self.interval_minutes = interval_minutes
        self.weekdays = weekdays
        self._last_triggered: Optional[datetime] = None

    def check(self, current_time: Optional[datetime] = None) -> bool:
        """检查是否满足时间触发条件"""
        if current_time is None:
            current_time = datetime.now()

        # 星期过滤
        if self.weekdays is not None:
            if current_time.weekday() not in self.weekdays:
                return False

        # 固定时间触发
        if self.trigger_time is not None:
            if (current_time.hour == self.trigger_time.hour
                    and current_time.minute == self.trigger_time.minute
                    and (self._last_triggered is None
                         or current_time.date() > self._last_triggered.date())):
                self._last_triggered = current_time
                return True

        # 间隔触发
        if self.interval_minutes is not None:
            if (self._last_triggered is None
                    or (current_time - self._last_triggered).total_seconds()
                    >= self.interval_minutes * 60):
                self._last_triggered = current_time
                return True

        return False

    def get_match_info(self, current_time: Optional[datetime] = None) -> Optional[dict]:
        """获取匹配信息"""
        if self.check(current_time):
            now = current_time or datetime.now()
            return {
                "trigger_type": "time",
                "skill_name": self.skill_name,
                "triggered_at": now.isoformat(),
            }
        return None