"""
TriggerEngine - 技能触发引擎
在用户输入 / 时间 / 上下文 / 事件满足条件后自动评估触发器，决定是否自动执行技能
"""
import asyncio
from typing import Any, Dict, List, Optional, Callable

from skills.base import SkillResult
from skills.context import SkillContext
from skills.triggers.keyword_trigger import KeywordTrigger
from skills.triggers.intent_trigger import IntentTrigger
from skills.triggers.pattern_trigger import PatternTrigger
from skills.triggers.context_trigger import ContextTrigger
from skills.triggers.time_trigger import TimeTrigger
from skills.triggers.event_trigger import EventTrigger


class TriggerMatch:
    """触发器匹配结果"""
    def __init__(self, skill_name: str, trigger_type: str, confidence: float = 1.0,
                 matched_info: Optional[Dict] = None, params: Optional[Dict] = None):
        self.skill_name = skill_name
        self.trigger_type = trigger_type
        self.confidence = confidence
        self.matched_info = matched_info or {}
        self.params = params or {}

    def __repr__(self):
        return f"TriggerMatch(skill={self.skill_name}, type={self.trigger_type}, confidence={self.confidence})"


class TriggerEngine:
    """
    技能触发引擎

    职责：
    1. 管理触发器注册（关键词、意图、正则、上下文、时间、事件）
    2. 评估用户输入/上下文/时间/事件，匹配合适的触发器
    3. 调用 SkillDispatcher 自动执行匹配的技能（按技能名去重）
    4. 将执行结果注入到对话上下文
    """

    def __init__(self, skill_dispatcher=None):
        self.skill_dispatcher = skill_dispatcher
        self._keyword_triggers: List[Dict] = []  # {keywords, skill_name, params_extractor}
        self._intent_triggers: List[Dict] = []
        self._pattern_triggers: List[Dict] = []
        self._context_triggers: List[Dict] = []  # {skill_name, condition}
        self._time_triggers: List[Dict] = []     # {skill_name, trigger: TimeTrigger}
        self._event_triggers: List[Dict] = []    # {skill_name, event_names}
        self._enabled = True

    # ---- 触发器注册 ----

    def register_keyword_trigger(self, skill_name: str, keywords: List[str],
                                  params_extractor: Optional[Callable] = None):
        """注册关键词触发器"""
        self._keyword_triggers.append({
            "skill_name": skill_name,
            "keywords": [k.lower() for k in keywords],
            "extractor": params_extractor,
        })

    def register_intent_trigger(self, skill_name: str, intent_names: List[str],
                                params_extractor: Optional[Callable] = None,
                                patterns: Optional[List[str]] = None):
        """注册意图触发器

        Args:
            skill_name: 技能名称
            intent_names: 意图名称（作为关键词兜底匹配，如 'translate'）
            params_extractor: 参数提取函数
            patterns: 意图正则模式列表（优先使用，捕获组可作为 query 参数）
        """
        import re
        self._intent_triggers.append({
            "skill_name": skill_name,
            "intents": intent_names,
            "patterns": [re.compile(p) for p in patterns] if patterns else [],
            "extractor": params_extractor,
        })

    def register_pattern_trigger(self, skill_name: str, patterns: List[str],
                                  params_extractor: Optional[Callable] = None):
        """注册正则模式触发器"""
        import re
        self._pattern_triggers.append({
            "skill_name": skill_name,
            "patterns": [re.compile(p) for p in patterns],
            "extractor": params_extractor,
        })

    def register_context_trigger(self, skill_name: str,
                                 condition: Callable[[Dict[str, Any]], bool]):
        """注册上下文触发器（基于对话上下文状态触发，如历史长度、会话状态）"""
        self._context_triggers.append({
            "skill_name": skill_name,
            "condition": condition,
        })

    def register_time_trigger(self, skill_name: str,
                              trigger_time: Optional[object] = None,
                              interval_minutes: Optional[int] = None,
                              weekdays: Optional[list] = None):
        """注册时间触发器（定时 / 间隔 / 星期过滤，可用于定时任务）"""
        self._time_triggers.append({
            "skill_name": skill_name,
            "trigger": TimeTrigger(
                skill_name,
                trigger_time=trigger_time,
                interval_minutes=interval_minutes,
                weekdays=weekdays,
            ),
        })

    def register_event_trigger(self, skill_name: str, event_names: List[str]):
        """注册事件触发器（系统事件发生时触发，如 EventBus 事件）"""
        self._event_triggers.append({
            "skill_name": skill_name,
            "event_names": list(event_names),
        })

    # ---- 声明式触发器注册（从技能元数据自动注册） ----

    def register_skill_triggers(self, skill) -> int:
        """从技能声明的 triggers 元数据自动注册触发器（新增技能无需修改本引擎代码）

        skill.triggers 格式示例：
        [
            {"type": "keyword", "keywords": ["翻译", "translate"]},
            {"type": "pattern", "patterns": [r"把\\s*(.+?)\\s*翻译"]},
            {"type": "intent", "intents": ["translate"], "patterns": [...]},
            {"type": "context", "condition": callable},   # 可选
            {"type": "time", "trigger_time": datetime.time(h=9), "interval_minutes": 60},
            {"type": "event", "event_names": ["skill:updated"]},
        ]
        """
        declarations = getattr(skill, "triggers", None)
        if not declarations:
            return 0
        count = 0
        for trig in declarations:
            trig_type = trig.get("type", "keyword")
            try:
                if trig_type == "keyword":
                    self.register_keyword_trigger(skill.name, trig.get("keywords", []))
                elif trig_type == "pattern":
                    self.register_pattern_trigger(skill.name, trig.get("patterns", []))
                elif trig_type == "intent":
                    self.register_intent_trigger(
                        skill.name,
                        trig.get("intents", []),
                        patterns=trig.get("patterns"),
                    )
                elif trig_type == "context":
                    self.register_context_trigger(skill.name, trig.get("condition"))
                elif trig_type == "time":
                    self.register_time_trigger(
                        skill.name,
                        trigger_time=trig.get("trigger_time"),
                        interval_minutes=trig.get("interval_minutes"),
                        weekdays=trig.get("weekdays"),
                    )
                elif trig_type == "event":
                    self.register_event_trigger(skill.name, trig.get("event_names", []))
                else:
                    continue
                count += 1
            except Exception as e:
                print(f"[TriggerEngine] ⚠️ 技能 '{skill.name}' 触发器注册失败: {e}")
        return count

    def register_skills_triggers(self, skills) -> int:
        """批量注册多个技能的声明式触发器"""
        total = 0
        for skill in skills:
            total += self.register_skill_triggers(skill)
        return total

    # ---- 默认触发器配置 ----

    def register_default_triggers(self):
        """注册内置技能的默认触发器"""
        # 关键词触发器
        self.register_keyword_trigger("translator", ["翻译", "translate", "translation",
                                                       "英译中", "中译英", "翻一下"])
        self.register_keyword_trigger("summarizer", ["总结", "摘要", "概括", "summarize",
                                                       "提炼", "要点", "归纳"])
        self.register_keyword_trigger("code_assistant", ["代码审查", "优化代码", "debug",
                                                          "改bug", "重构", "review code"])
        self.register_keyword_trigger("translator", ["翻译成", "用英文说", "用中文说"])
        self.register_keyword_trigger("web_scraper", ["抓取网页", "爬取", "网页抓取",
                                                       "scrape", "获取网页内容"])
        self.register_keyword_trigger("email_composer", ["写邮件", "邮件模板", "起草邮件",
                                                          "compose email"])
        self.register_keyword_trigger("meeting_minutes", ["会议纪要", "会议记录", "整理会议",
                                                           "meeting notes", "minutes"])
        self.register_keyword_trigger("brainstorming", ["头脑风暴", "创意", "想点子",
                                                         "brainstorm", "发散思维"])
        self.register_keyword_trigger("problem_solver", ["解决问题", "根因分析", "问题分析",
                                                          "swot", "problem solving"])
        self.register_keyword_trigger("document_writer", ["写文档", "撰写文档", "技术文档",
                                                            "写报告", "documentation"])

        # 正则模式触发器
        self.register_pattern_trigger("translator", [
            r"把\s*[「『\"](.+?)[」』\"].*?翻译成\s*\w+",
            r"翻[译一下]\s*[：:]\s*(.+)",
        ])
        self.register_pattern_trigger("code_assistant", [
            r"帮我\s*(审查|优化|调试|重构)\s*(一下\s*)?这段代码",
            r"review\s+this\s+code",
        ])


    # ---- 触发评估（用户输入） ----

    def evaluate(self, user_input: str) -> List[TriggerMatch]:
        """评估用户输入，返回所有匹配的触发器结果（按置信度排序）"""
        if not self._enabled or not user_input:
            return []

        matches = []
        text_lower = user_input.lower()

        # 1. 关键词匹配
        for trigger in self._keyword_triggers:
            for kw in trigger["keywords"]:
                if kw in text_lower:
                    params = {}
                    if trigger.get("extractor"):
                        try:
                            params = trigger["extractor"](user_input) or {}
                        except Exception:
                            params = {}
                    matches.append(TriggerMatch(
                        skill_name=trigger["skill_name"],
                        trigger_type="keyword",
                        confidence=0.7 if len(kw) <= 2 else 0.8,
                        matched_info={"keyword": kw},
                        params=params,
                    ))
                    break  # 一个触发器只匹配一次

        # 2. 意图匹配（优先正则模式，其次意图名称兜底）
        for trigger in self._intent_triggers:
            params = {}
            if trigger.get("extractor"):
                try:
                    params = trigger["extractor"](user_input) or {}
                except Exception:
                    params = {}
            matched_intent = None
            for pat in trigger.get("patterns", []):
                match = pat.search(user_input)
                if match:
                    matched_intent = pat.pattern
                    if match.groups():
                        params.setdefault("query", match.group(1))
                    break
            if matched_intent is None:
                for intent in trigger["intents"]:
                    if intent in text_lower:
                        matched_intent = intent
                        break
            if matched_intent is not None:
                matches.append(TriggerMatch(
                    skill_name=trigger["skill_name"],
                    trigger_type="intent",
                    confidence=1.0,
                    matched_info={"intent": matched_intent},
                    params=params,
                ))

        # 3. 正则模式匹配
        import re
        for trigger in self._pattern_triggers:
            for pattern in trigger["patterns"]:
                match = pattern.search(user_input)
                if match:
                    params = {}
                    if trigger.get("extractor"):
                        try:
                            params = trigger["extractor"](user_input) or {}
                        except Exception:
                            params = {}
                    # 提取捕获组作为参数
                    if match.groups():
                        params.setdefault("query", match.group(1))
                    matches.append(TriggerMatch(
                        skill_name=trigger["skill_name"],
                        trigger_type="pattern",
                        confidence=0.9,
                        matched_info={"pattern": pattern.pattern},
                        params=params,
                    ))
                    break  # 一个触发器只匹配一次

        # 按置信度降序排序
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches

    # ---- 触发评估（时间 / 上下文 / 事件） ----

    def evaluate_time(self, current_time: Optional[Any] = None) -> List[TriggerMatch]:
        """评估时间触发器（定时 / 间隔 / 星期），可由定时任务周期性调用"""
        if not self._enabled:
            return []
        matches = []
        for trig in self._time_triggers:
            info = trig["trigger"].get_match_info(current_time)
            if info:
                matches.append(TriggerMatch(
                    skill_name=trig["skill_name"],
                    trigger_type="time",
                    confidence=1.0,
                    matched_info=info,
                ))
        return matches

    def evaluate_context(self, context_data: Dict[str, Any]) -> List[TriggerMatch]:
        """评估上下文触发器（基于对话历史/会话状态）"""
        if not self._enabled or not context_data:
            return []
        matches = []
        for trig in self._context_triggers:
            try:
                ok = bool(trig["condition"](context_data))
            except Exception:
                ok = False
            if ok:
                matches.append(TriggerMatch(
                    skill_name=trig["skill_name"],
                    trigger_type="context",
                    confidence=1.0,
                    matched_info={"context_keys": list(context_data.keys())},
                ))
        return matches

    def evaluate_event(self, event_name: str,
                       event_data: Optional[Dict[str, Any]] = None) -> List[TriggerMatch]:
        """评估事件触发器（系统事件发生时触发，如 EventBus 事件）"""
        if not self._enabled or not event_name:
            return []
        matches = []
        for trig in self._event_triggers:
            if event_name in trig["event_names"]:
                matches.append(TriggerMatch(
                    skill_name=trig["skill_name"],
                    trigger_type="event",
                    confidence=1.0,
                    matched_info={"event_name": event_name, "event_data": event_data},
                ))
        return matches


    # ---- 自动执行 ----

    async def auto_execute(self, user_input: str,
                            context: Optional[SkillContext] = None,
                            confidence_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """自动评估并执行用户输入命中的技能（按技能名去重，最多前 3 个）"""
        if not self.skill_dispatcher:
            return []
        return await self._execute_matches(
            self.evaluate(user_input), context, confidence_threshold
        )

    async def auto_execute_time(self, current_time: Optional[Any] = None,
                                context: Optional[SkillContext] = None,
                                confidence_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """评估并执行时间触发器命中的技能（可由定时任务周期调用）"""
        if not self.skill_dispatcher:
            return []
        return await self._execute_matches(
            self.evaluate_time(current_time), context, confidence_threshold
        )

    async def auto_execute_context(self, context_data: Dict[str, Any],
                                   context: Optional[SkillContext] = None,
                                   confidence_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """评估并执行上下文触发器命中的技能"""
        if not self.skill_dispatcher:
            return []
        return await self._execute_matches(
            self.evaluate_context(context_data), context, confidence_threshold
        )

    async def auto_execute_event(self, event_name: str,
                                 event_data: Optional[Dict[str, Any]] = None,
                                 context: Optional[SkillContext] = None,
                                 confidence_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """评估并执行事件触发器命中的技能"""
        if not self.skill_dispatcher:
            return []
        return await self._execute_matches(
            self.evaluate_event(event_name, event_data), context, confidence_threshold
        )

    async def _execute_matches(self, matches: List[TriggerMatch],
                               context: Optional[SkillContext],
                               confidence_threshold: float) -> List[Dict[str, Any]]:
        """共享执行逻辑：过滤置信度、按技能名去重、逐个执行（独立上下文）"""
        if not matches:
            return []

        seen = set()
        high_confidence = []
        for m in matches:
            if m.confidence >= confidence_threshold and m.skill_name not in seen:
                high_confidence.append(m)
                seen.add(m.skill_name)
                if len(high_confidence) >= 3:
                    break
        if not high_confidence:
            return []

        results = []
        for match in high_confidence:
            try:
                # 每个匹配使用独立上下文，避免 variables/params 在不同技能间串扰
                exec_context = self._isolate_context(context)
                result_str = await self.skill_dispatcher.execute_skill(
                    skill_name=match.skill_name,
                    arguments=match.params,
                    context=exec_context,
                )
                results.append({
                    "skill_name": match.skill_name,
                    "trigger_type": match.trigger_type,
                    "confidence": match.confidence,
                    "result": result_str,
                })
            except Exception as e:
                results.append({
                    "skill_name": match.skill_name,
                    "trigger_type": match.trigger_type,
                    "confidence": match.confidence,
                    "result": f"⚠️ 自动执行失败: {e}",
                })

        return results

    @staticmethod
    def _isolate_context(context: Optional[SkillContext]) -> SkillContext:
        """为每次执行创建独立上下文，隔离 variables/params，避免串扰"""
        if context is None:
            return SkillContext()
        import dataclasses
        return dataclasses.replace(
            context,
            variables={},
            params={},
        )

    def set_skill_dispatcher(self, dispatcher):
        """设置 SkillDispatcher 引用"""
        self.skill_dispatcher = dispatcher

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    def get_status(self) -> Dict[str, Any]:
        """获取触发引擎状态"""
        return {
            "enabled": self._enabled,
            "keyword_triggers": len(self._keyword_triggers),
            "intent_triggers": len(self._intent_triggers),
            "pattern_triggers": len(self._pattern_triggers),
            "context_triggers": len(self._context_triggers),
            "time_triggers": len(self._time_triggers),
            "event_triggers": len(self._event_triggers),
        }

