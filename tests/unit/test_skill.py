"""Skill 技能系统单元测试 — 覆盖优化后的行为"""
import asyncio
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from skills.base import BaseSkill, SkillResult, DEFAULT_SKILL_TIMEOUT
from skills.context import SkillContext
from skills.registry import SkillRegistry
from skills.executor import SkillExecutor
from skills.loader import SkillLoader
from skills.trigger_engine import TriggerEngine
from ai.skill_dispatcher import SkillDispatcher


def make_skill(name="echo", description="测试技能"):
    """动态创建测试技能实例"""
    async def execute(self, context, **kwargs):
        return SkillResult(success=True, output=kwargs.get("query", "ok"))
    return type(name, (BaseSkill,), {
        "name": name,
        "description": description,
        "execute": execute,
    })()


def make_counter_skill(name="counter", description="计数技能"):
    """创建带执行计数状态的技能，用于验证去重"""
    state = {"count": 0}
    async def execute(self, context, **kwargs):
        state["count"] += 1
        return SkillResult(success=True, output=state["count"])
    return type(name, (BaseSkill,), {
        "name": name,
        "description": description,
        "execute": execute,
        "state": state,
    })()


@pytest.fixture(autouse=True)
def clean_registry():
    """每次测试前后清空共享单例注册中心，避免测试间污染"""
    SkillRegistry().clear()
    yield
    SkillRegistry().clear()


# ---------------------------------------------------------------------------
# 1. 统一默认超时
# ---------------------------------------------------------------------------

def test_unified_timeout():
    """SkillExecutor 与 SkillDispatcher 应使用同一 DEFAULT_SKILL_TIMEOUT"""
    assert DEFAULT_SKILL_TIMEOUT == 60.0
    assert SkillExecutor().default_timeout == DEFAULT_SKILL_TIMEOUT
    assert SkillDispatcher()._default_timeout == DEFAULT_SKILL_TIMEOUT
    # 允许调用方显式覆盖
    assert SkillDispatcher(default_timeout=5.0)._default_timeout == 5.0


# ---------------------------------------------------------------------------
# 2. 注册中心统一校验入口
# ---------------------------------------------------------------------------

def test_registry_validation_rejects_invalid():
    """register() 默认走校验，名称缺失的技能应被拒绝"""
    reg = SkillRegistry()
    assert reg.register(make_skill(name="", description="x")) is False
    # 显式跳过校验时，仍要求 name 非空
    assert reg.register(make_skill(name="", description="x"), validate=False) is False


def test_registry_validation_passes_valid():
    """合法技能应注册成功"""
    reg = SkillRegistry()
    skill = make_skill(name="echo", description="回显")
    assert reg.register(skill) is True
    assert reg.get("echo") is skill


# ---------------------------------------------------------------------------
# 3. 单一数据源：Dispatcher 委托共享 Registry
# ---------------------------------------------------------------------------

def test_dispatcher_sees_dynamically_registered_skill():
    """通过 Registry 动态注册的技能，Dispatcher 无需重新同步即可感知"""
    disp = SkillDispatcher()
    skill = make_skill(name="echo", description="回显")
    assert SkillRegistry().register(skill) is True
    assert disp.get_skill("echo") is skill
    assert disp.count >= 1
    tools = disp.get_tool_descriptions()
    assert any(t["function"]["name"] == "skill_echo" for t in tools)


def test_dispatcher_register_and_unregister():
    """Dispatcher 注册/注销应同步到共享 Registry"""
    disp = SkillDispatcher()
    reg = SkillRegistry()
    skill = make_skill(name="echo", description="回显")
    assert disp.register_skill(skill) is True
    assert reg.get("echo") is skill
    assert disp.unregister_skill("echo") is True
    assert reg.get("echo") is None


def test_dispatcher_clear_only_removes_own():
    """Dispatcher.clear() 只清理自己注册的技能，不影响其他模块注册的技能"""
    reg = SkillRegistry()
    disp = SkillDispatcher()
    s1 = make_skill(name="owned_by_other", description="其他模块注册")
    s2 = make_skill(name="owned_by_disp", description="调度器注册")
    assert reg.register(s1) is True          # 由 SkillManager/其他模块注册
    assert disp.register_skill(s2) is True   # 由 Dispatcher 注册
    disp.clear()
    assert reg.get("owned_by_other") is s1   # 他人注册的保留
    assert reg.get("owned_by_disp") is None  # 自己注册的被清理


# ---------------------------------------------------------------------------
# 4. 意图触发器修复
# ---------------------------------------------------------------------------

def test_intent_trigger_matching_by_name():
    """意图名称命中时生成 intent 类型匹配（修复注册但永不触发的 bug）"""
    engine = TriggerEngine()
    engine.register_intent_trigger("summarizer", ["summarize", "总结"])
    matches = engine.evaluate("请帮我 summarize 这篇文章")
    assert any(
        m.skill_name == "summarizer" and m.trigger_type == "intent" and m.confidence == 1.0
        for m in matches
    )


def test_intent_trigger_matching_by_pattern():
    """意图正则模式优先匹配，并提取捕获组为 query 参数"""
    engine = TriggerEngine()
    engine.register_intent_trigger(
        "translator",
        ["translate"],
        patterns=[r"把\s*[「『](.+?)[」』].*?翻译"],
    )
    matches = engine.evaluate("把「你好世界」翻译成英文")
    m = next((x for x in matches if x.skill_name == "translator"), None)
    assert m is not None and m.trigger_type == "intent"
    assert m.params.get("query") == "你好世界"


def test_keyword_and_pattern_still_work():
    """原有关键词 / 正则模式匹配不受影响"""
    engine = TriggerEngine()
    engine.register_keyword_trigger("translator", ["翻译"])
    engine.register_pattern_trigger("code_assistant", [r"review\s+this\s+code"])
    assert engine.evaluate("帮我翻译")[0].trigger_type == "keyword"
    assert engine.evaluate("review this code")[0].trigger_type == "pattern"


# ---------------------------------------------------------------------------
# 5. 自动触发去重 + 上下文隔离
# ---------------------------------------------------------------------------

def test_auto_execute_dedup_by_skill():
    """同一技能被多个触发器命中时只执行一次"""
    disp = SkillDispatcher()
    skill = make_counter_skill("counter", "计数")
    disp.register_skill(skill)
    engine = TriggerEngine(disp)
    engine.register_keyword_trigger("counter", ["计数"])
    engine.register_pattern_trigger("counter", [r"计数"])
    results = asyncio.run(engine.auto_execute("帮我计数一下"))
    executed = [r for r in results if r["skill_name"] == "counter"]
    assert len(executed) == 1
    assert skill.state["count"] == 1


def test_auto_execute_returns_results():
    """auto_execute 返回结构化执行结果"""
    disp = SkillDispatcher()
    disp.register_skill(make_skill(name="echo", description="回显"))
    engine = TriggerEngine(disp)
    engine.register_keyword_trigger("echo", ["echo", "回显"])
    results = asyncio.run(engine.auto_execute("帮我回显一下"))
    assert len(results) == 1
    assert results[0]["skill_name"] == "echo"
    assert "执行成功" in results[0]["result"]


def test_context_isolation_between_executions():
    """多次执行之间 variables 不串扰：共享上下文不被 execute_skill 注入污染"""
    disp = SkillDispatcher()
    disp.register_skill(make_skill(name="iso1", description="d"))
    disp.register_skill(make_skill(name="iso2", description="d"))
    engine = TriggerEngine(disp)

    def extractor(text):
        return {"query": "抽取值"}

    engine.register_keyword_trigger("iso1", ["词A"], params_extractor=extractor)
    engine.register_keyword_trigger("iso2", ["词B"], params_extractor=extractor)

    base = SkillContext()
    base.set("shared", "yes")
    results = asyncio.run(engine.auto_execute("词A 和 词B", context=base))
    assert {r["skill_name"] for r in results} == {"iso1", "iso2"}
    # 隔离后：共享上下文 variables 保留调用方设置的值，不被注入的 query 污染
    assert base.get("shared") == "yes"
    assert "query" not in base.variables


# ---------------------------------------------------------------------------
# 6. SkillDispatcher 执行核心
# ---------------------------------------------------------------------------

def test_execute_unregistered_and_disabled():
    """未注册 / 已禁用技能返回明确错误提示"""
    disp = SkillDispatcher()
    assert "未注册" in asyncio.run(disp.execute_skill("nope", {}))

    skill = make_skill(name="disabled", description="禁用技能")
    skill.enabled = False
    assert disp.register_skill(skill) is False  # 禁用技能无法注册
    assert disp.get_skill("disabled") is None


def test_execute_success_and_result_format():
    """正常执行返回 ✅ 成功格式"""
    disp = SkillDispatcher()
    disp.register_skill(make_skill(name="echo", description="回显"))
    result = asyncio.run(disp.execute_skill("echo", {"query": "hello"}))
    assert "执行成功" in result
    assert "hello" in result


# ---------------------------------------------------------------------------
# 7. MD 技能 mtime 缓存
# ---------------------------------------------------------------------------

def test_md_cache_and_invalidation(tmp_path):
    """SKILL.md 未变更时命中缓存，变更后自动失效"""
    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    md_path = skill_dir / "SKILL.md"
    md_path.write_text("---\nname: demo\nenabled: true\n---\n内容A", encoding="utf-8")

    loader = SkillLoader(md_dir=str(tmp_path))
    skills = loader.get_all_md_skills()
    assert skills and skills[0]["name"] == "demo"
    assert "内容A" in skills[0]["content"]

    # 修改文件 → mtime 变化 → 缓存失效
    time.sleep(0.01)
    md_path.write_text("---\nname: demo\nenabled: true\n---\n内容B", encoding="utf-8")
    new_time = time.time() + 5
    os.utime(str(md_path), (new_time, new_time))

    skills2 = loader.get_all_md_skills()
    assert "内容B" in skills2[0]["content"]


def test_md_skills_load_from_actual_dir():
    """能加载真实 skills/md 目录下的技能"""
    repo_md = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "skills", "md",
    )
    if not os.path.isdir(repo_md):
        pytest.skip("skills/md 目录不存在")
    loader = SkillLoader(md_dir=repo_md)
    skills = loader.get_all_md_skills()
    assert any(s["name"] == "code-review" for s in skills)



# ---------------------------------------------------------------------------
# 8. execute_all 并发执行
# ---------------------------------------------------------------------------

def test_execute_all_concurrent():
    """execute_all 应返回所有已启用技能的结果"""
    reg = SkillRegistry()
    exe = SkillExecutor()
    for name in ("echo", "echo2", "echo3"):
        reg.register(make_skill(name=name, description="d"))
    results = asyncio.run(exe.execute_all(query="hello"))
    assert set(results.keys()) == {"echo", "echo2", "echo3"}
    assert all(r.success for r in results.values())


def test_execute_by_category_concurrent():
    """execute_by_category 只执行指定类别的已启用技能"""
    reg = SkillRegistry()
    exe = SkillExecutor()

    async def execute(self, context, **kwargs):
        return SkillResult(success=True, output="ok")

    for name, cat in (("a1", "utility"), ("a2", "utility"), ("b1", "general")):
        skill = type(name, (BaseSkill,), {
            "name": name, "description": "d", "category": cat, "execute": execute,
        })()
        reg.register(skill)

    results = asyncio.run(exe.execute_by_category("utility"))
    assert set(results.keys()) == {"a1", "a2"}


# ---------------------------------------------------------------------------
# 9. 技能生命周期钩子
# ---------------------------------------------------------------------------

def test_lifecycle_hooks_on_register_and_unregister():
    """register 触发 on_load，unregister 触发 on_unload"""
    calls = []

    async def execute(self, context, **kwargs):
        return SkillResult(success=True, output="ok")

    skill = type("lifecycle", (BaseSkill,), {
        "name": "lifecycle", "description": "d", "execute": execute,
        "on_load": lambda self: calls.append("load"),
        "on_unload": lambda self: calls.append("unload"),
    })()
    reg = SkillRegistry()
    assert reg.register(skill) is True
    assert calls == ["load"]
    assert reg.unregister("lifecycle") is True
    assert calls == ["load", "unload"]


def test_set_enabled_triggers_enable_disable_hooks():
    """set_enabled 切换状态时触发 on_enable / on_disable"""
    events = []

    async def execute(self, context, **kwargs):
        return SkillResult(success=True, output="ok")

    skill = type("toggle", (BaseSkill,), {
        "name": "toggle", "description": "d", "execute": execute,
        "on_enable": lambda self: events.append("enable"),
        "on_disable": lambda self: events.append("disable"),
    })()
    skill.set_enabled(False)  # True -> False
    assert events == ["disable"]
    skill.set_enabled(True)   # False -> True
    assert events == ["disable", "enable"]
    skill.set_enabled(True)   # 无变化，不触发
    assert events == ["disable", "enable"]


def test_registry_toggle_enabled():
    """SkillRegistry.toggle_enabled 切换状态并更新注册中心"""
    reg = SkillRegistry()
    skill = make_skill(name="toggle", description="d")
    reg.register(skill)
    assert reg.toggle_enabled("toggle") is True
    assert skill.enabled is False
    assert reg.toggle_enabled("toggle") is True
    assert skill.enabled is True
    assert reg.toggle_enabled("missing") is False


# ---------------------------------------------------------------------------
# 10. 声明式触发器
# ---------------------------------------------------------------------------

def test_register_skill_triggers_from_metadata():
    """技能声明的 triggers 元数据可自动注册为触发器"""
    async def execute(self, context, **kwargs):
        return SkillResult(success=True, output="ok")

    skill = type("declarative", (BaseSkill,), {
        "name": "declarative", "description": "d", "execute": execute,
        "triggers": [
            {"type": "keyword", "keywords": ["声明式", "declarative"]},
            {"type": "pattern", "patterns": [r"触发\s*声明"]},
        ],
    })()
    engine = TriggerEngine()
    count = engine.register_skill_triggers(skill)
    assert count == 2
    matches = engine.evaluate("使用声明式配置")
    assert any(m.skill_name == "declarative" and m.trigger_type == "keyword" for m in matches)
    assert engine.evaluate("触发 声明一下")[0].trigger_type == "pattern"


def test_register_skills_triggers_batch():
    """批量注册多个技能的声明式触发器"""
    async def execute(self, context, **kwargs):
        return SkillResult(success=True, output="ok")

    s1 = type("s1", (BaseSkill,), {
        "name": "s1", "description": "d", "execute": execute,
        "triggers": [{"type": "keyword", "keywords": ["技能一"]}],
    })()
    s2 = type("s2", (BaseSkill,), {
        "name": "s2", "description": "d", "execute": execute,
        "triggers": [{"type": "keyword", "keywords": ["技能二"]}],
    })()
    engine = TriggerEngine()
    assert engine.register_skills_triggers([s1, s2]) == 2
    assert engine.evaluate("测试技能二")[0].skill_name == "s2"


# ---------------------------------------------------------------------------
# 11. 技能事件通道（可观测性）
# ---------------------------------------------------------------------------

def test_registry_event_sink():
    """注册/注销/切换技能时通过事件通道发送事件"""
    reg = SkillRegistry()
    events = []

    def sink(event, data):
        events.append((event, data))

    reg.set_event_sink(sink)
    skill = make_skill(name="eventful", description="d")
    assert reg.register(skill) is True
    assert reg.toggle_enabled("eventful") is True
    assert reg.unregister("eventful") is True

    names = [e for e, _ in events]
    assert names == ["skill:registered", "skill:toggle", "skill:unregistered"]
    assert events[0][1]["name"] == "eventful"


def test_registry_event_sink_failure_is_isolated():
    """事件通道抛异常不应影响技能注册主流程"""
    reg = SkillRegistry()

    def bad_sink(event, data):
        raise RuntimeError("sink failed")

    reg.set_event_sink(bad_sink)
    skill = make_skill(name="robust", description="d")
    assert reg.register(skill) is True   # 事件失败但注册成功
    assert reg.get("robust") is skill



# ---------------------------------------------------------------------------
# 12. 时间 / 上下文 / 事件触发器
# ---------------------------------------------------------------------------

def test_time_trigger_registration_and_evaluation():
    """时间触发器注册与评估（间隔触发）"""
    from datetime import datetime, timedelta
    engine = TriggerEngine()
    engine.register_time_trigger("reporter", interval_minutes=1)
    t0 = datetime.now()
    assert engine.evaluate_time(t0)  # 首次触发
    assert not engine.evaluate_time(t0 + timedelta(seconds=5))  # 间隔未到
    assert engine.evaluate_time(t0 + timedelta(minutes=2))      # 间隔已到


def test_context_trigger_registration_and_evaluation():
    """上下文触发器按条件匹配"""
    engine = TriggerEngine()
    engine.register_context_trigger("summarizer", lambda ctx: len(ctx.get("messages", [])) >= 5)
    assert engine.evaluate_context({"messages": list(range(5))})
    assert not engine.evaluate_context({"messages": list(range(2))})
    # 条件抛异常时安全返回 False
    assert not engine.evaluate_context({})


def test_event_trigger_registration_and_evaluation():
    """事件触发器按事件名匹配"""
    engine = TriggerEngine()
    engine.register_event_trigger("notifier", ["skill:updated", "skill:registered"])
    assert engine.evaluate_event("skill:updated")
    assert engine.evaluate_event("skill:registered")
    assert not engine.evaluate_event("unknown:event")


def test_auto_execute_time_uses_dispatcher():
    """auto_execute_time 会执行时间触发器命中的技能"""
    disp = SkillDispatcher()
    disp.register_skill(make_skill(name="reporter", description="d"))
    engine = TriggerEngine(disp)
    engine.register_time_trigger("reporter", interval_minutes=1)
    results = asyncio.run(engine.auto_execute_time())
    assert len(results) == 1
    assert results[0]["skill_name"] == "reporter"
    # 间隔未到，第二次不触发
    from datetime import datetime, timedelta
    later = datetime.now() + timedelta(seconds=5)
    assert asyncio.run(engine.auto_execute_time(later)) == []


# ---------------------------------------------------------------------------
# 13. 执行历史记录
# ---------------------------------------------------------------------------

def test_execution_history_records_success_and_failure():
    """execute_skill 记录成功与失败的执行历史"""
    disp = SkillDispatcher()
    disp.register_skill(make_skill(name="echo", description="d"))
    asyncio.run(disp.execute_skill("echo", {"query": "hi"}))
    asyncio.run(disp.execute_skill("missing_skill", {}))
    hist = disp.get_execution_history()
    assert len(hist) == 2
    assert hist[0]["skill_name"] == "echo" and hist[0]["success"] is True
    assert hist[1]["skill_name"] == "missing_skill" and hist[1]["success"] is False
    assert "timestamp" in hist[0] and "duration_ms" in hist[0]


def test_execution_history_limit():
    """get_execution_history(limit) 只返回最近 N 条"""
    disp = SkillDispatcher()
    disp.register_skill(make_skill(name="echo", description="d"))
    for _ in range(5):
        asyncio.run(disp.execute_skill("echo", {"query": "hi"}))
    assert len(disp.get_execution_history()) == 5
    assert len(disp.get_execution_history(limit=2)) == 2
    assert disp.get_status()["execution_history_count"] == 5


# ---------------------------------------------------------------------------
# 14. MD 技能适配器（统一技能模型）
# ---------------------------------------------------------------------------

def test_md_skill_adapter_execute():
    """MdSkill 将 MD 技能 dict 包装为可执行技能"""
    from skills.md_skill import MdSkill
    skill = MdSkill({
        "name": "code-review",
        "description": "代码审查技能",
        "content": "代码审查规范：逐行检查并给出修改建议",
    })
    assert skill.name == "code-review"
    assert skill.category == "md"
    result = asyncio.run(skill.execute(SkillContext()))
    assert result.success
    assert "代码审查" in result.output
    assert result.metadata["source"] == "markdown"


def test_loader_load_md_skill_adapters(tmp_path):
    """SkillLoader.load_md_skill_adapters 加载临时 MD 技能目录为适配器"""
    skill_dir = tmp_path / "review"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: review\nenabled: true\n---\n审查内容", encoding="utf-8"
    )
    loader = SkillLoader(md_dir=str(tmp_path))
    adapters = loader.load_md_skill_adapters()
    assert len(adapters) == 1
    assert adapters[0].name == "review"
    assert adapters[0].enabled is True


def test_md_skill_adapter_registrable_to_dispatcher():
    """MD 技能适配器可注册到 SkillDispatcher 并被 tool-call 执行"""
    from skills.md_skill import MdSkill
    disp = SkillDispatcher()
    skill = MdSkill({"name": "code-review", "description": "审查", "content": "审查规则"})
    assert disp.register_skill(skill) is True
    tools = disp.get_tool_descriptions()
    assert any(t["function"]["name"] == "skill_code-review" for t in tools)
    result = asyncio.run(disp.execute_skill("code-review", {}))
    assert "执行成功" in result



# ---------------------------------------------------------------------------
# 15. 前端数据源统一
# ---------------------------------------------------------------------------

def test_manager_get_skills_for_js_aggregates_python_and_md(tmp_path):
    """SkillManager.get_skills_for_js 聚合 Python 技能与 MD 技能（统一数据源）"""
    from skills.manager import SkillManager
    # 注册一个 Python 技能
    SkillRegistry().register(make_skill(name="py_skill", description="d"))
    # 创建带 MD 技能的 manager
    md_dir = tmp_path / "md"
    review_dir = md_dir / "review"
    review_dir.mkdir(parents=True)
    (review_dir / "SKILL.md").write_text(
        "---\nname: review\nenabled: true\n---\n审查内容", encoding="utf-8"
    )
    mgr = SkillManager(md_dir=str(md_dir))
    data = mgr.get_skills_for_js()
    by_name = {s["name"]: s for s in data}
    assert "py_skill" in by_name and by_name["py_skill"]["source"] == "python"
    assert "review" in by_name and by_name["review"]["source"] == "markdown"
    assert by_name["review"]["category"] == "md"


def test_get_skills_for_js_dedups_md_adapter_in_registry(tmp_path):
    """MD 技能注册为 MdSkill 适配器后，get_skills_for_js 不应重复显示（回归：UI 显示两条）"""
    from skills.manager import SkillManager
    from skills.md_skill import MdSkill
    reg = SkillRegistry()
    reg.unregister("review_dup")
    md_dir = tmp_path / "md"
    dup_dir = md_dir / "review_dup"
    dup_dir.mkdir(parents=True)
    (dup_dir / "SKILL.md").write_text(
        "---\nname: review_dup\nenabled: true\n---\n审查内容", encoding="utf-8"
    )
    # 模拟真实运行状态：MD 技能已作为适配器注册进 SkillRegistry（供 AI 工具调用）
    reg.register(MdSkill({"name": "review_dup", "description": "审查", "content": "审查内容"}))
    try:
        mgr = SkillManager(md_dir=str(md_dir))
        data = mgr.get_skills_for_js()
        names = [s["name"] for s in data]
        assert names.count("review_dup") == 1, f"MD 技能重复显示: {names}"
        item = next(s for s in data if s["name"] == "review_dup")
        assert item["source"] == "markdown" and item["category"] == "md"
    finally:
        reg.unregister("review_dup")


def test_app_controller_get_skills_data_dedups_md(tmp_path):
    """AppController._get_skills_data 不重复显示已注册为适配器的 MD 技能（回归：UI 显示两条）"""
    ctrl = _make_app_controller(tmp_path)
    assert ctrl.skill_manager.add_md_skill("review-dup", {"SKILL.md": "---\nname: review-dup\nenabled: true\n---\n内容"}) is True
    # 模拟 _init_skill_system：将 MD 技能注册为可执行适配器（进入共享 SkillRegistry）
    for adapter in ctrl.skill_manager.loader.load_md_skill_adapters():
        assert ctrl.skill_dispatcher.register_skill(adapter) is True

    data = ctrl._get_skills_data()
    names = [s["name"] for s in data]
    assert names.count("review-dup") == 1, f"MD 技能重复显示: {names}"
    item = next(s for s in data if s["name"] == "review-dup")
    assert item["source"] == "markdown" and item["category"] == "md"



def test_md_skill_adapter_end_to_end(tmp_path):
    """MD 技能 -> 适配器 -> Dispatcher 全链路（供 AI 工具调用）"""
    skill_dir = tmp_path / "review"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: review\nenabled: true\n---\n审查内容", encoding="utf-8"
    )
    loader = SkillLoader(md_dir=str(tmp_path))
    disp = SkillDispatcher()
    for adapter in loader.load_md_skill_adapters():
        assert disp.register_skill(adapter) is True
    assert disp.get_skill("review") is not None
    tools = disp.get_tool_descriptions()
    assert any(t["function"]["name"] == "skill_review" for t in tools)
    result = asyncio.run(disp.execute_skill("review", {}))
    assert "执行成功" in result



# ---------------------------------------------------------------------------
# 16. MD 技能上传持久化
# ---------------------------------------------------------------------------

def test_add_md_skill_persists_file(tmp_path):
    """SkillManager.add_md_skill 持久化 MD 技能目录并可重新解析"""
    from skills.manager import SkillManager
    mgr = SkillManager(md_dir=str(tmp_path))
    files = {"SKILL.md": "---\nname: my-skill\nenabled: true\n---\n技能内容"}
    assert mgr.add_md_skill("my-skill", files) is True
    # 重复添加失败
    assert mgr.add_md_skill("my-skill", files) is False

    fpath = tmp_path / "my-skill" / "SKILL.md"
    assert fpath.exists()
    content = fpath.read_text(encoding="utf-8")
    assert "name: my-skill" in content
    assert "enabled: true" in content
    assert "技能内容" in content

    # 可被 loader 解析回来
    parsed = mgr.loader.parse_md_file(str(fpath))
    assert parsed["name"] == "my-skill"
    assert parsed["content"] == "技能内容"



# ---------------------------------------------------------------------------
# 17. MD skill uploaded at runtime -> registered to AI (SkillRegistry + ToolDispatcher)
# ---------------------------------------------------------------------------

def _make_app_controller(tmp_path):
    """Build a minimal AppController to verify runtime MD skill sync to AI"""
    from PyQt5.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    from controller.app_controller import AppController
    from ai.tool_dispatcher import ToolDispatcher
    from skills.manager import SkillManager
    from ai.skill_dispatcher import SkillDispatcher

    class StubAI:
        def __init__(self):
            self.tool_dispatcher = ToolDispatcher()

        def connect(self):
            return True, "ok"

    class StubModelConfig(dict):
        def get(self, key, default=None):
            if key == "chat":
                return {"system_prompt": "test"}
            return dict.get(self, key, default)

    ctrl = AppController(StubModelConfig(), StubAI())
    # Use temp dir as the MD skill dir to avoid touching real skills/md
    ctrl.skill_manager = SkillManager(md_dir=str(tmp_path))
    ctrl.skill_dispatcher = SkillDispatcher()
    ctrl.ai_client.skill_dispatcher = ctrl.skill_dispatcher
    return ctrl


def test_manager_sync_md_skills_to_registry(tmp_path):
    """add_md_skill persists the directory; sync_md_skills_to_registry registers enabled MD adapters"""
    from skills.manager import SkillManager
    mgr = SkillManager(md_dir=str(tmp_path))
    files = {"SKILL.md": "---\nname: code-review\nenabled: true\n---\nReview line by line"}
    assert mgr.add_md_skill("code-review", files) is True
    # Persisting the file alone must NOT register the adapter
    assert mgr.registry.get("code-review") is None

    assert mgr.sync_md_skills_to_registry() == 1
    skill = mgr.registry.get("code-review")
    assert skill is not None and skill.category == "md"

    # Disabling then syncing unregisters it
    assert mgr.toggle_md_skill("code-review") is True
    assert mgr.sync_md_skills_to_registry() == 0
    assert mgr.registry.get("code-review") is None

    # Re-enabling then syncing registers it again
    assert mgr.toggle_md_skill("code-review") is True
    assert mgr.sync_md_skills_to_registry() == 1
    assert mgr.registry.get("code-review") is not None


def test_app_controller_resync_md_skill_tools(tmp_path):
    """_resync_md_skill_tools registers uploaded MD skill as an AI-callable tool; remove/disable drops it"""
    ctrl = _make_app_controller(tmp_path)
    files = {"SKILL.md": "---\nname: code-review\nenabled: true\n---\nReview rules"}
    assert ctrl.skill_manager.add_md_skill("code-review", files) is True

    # Before sync: invisible to AI
    assert ctrl.skill_dispatcher.get_skill("code-review") is None
    assert not ctrl.ai_client.tool_dispatcher.has_tool("skill_code-review")

    # After sync: visible to AI and executable through the tool dispatcher
    assert ctrl._resync_md_skill_tools() == 1
    assert ctrl.skill_dispatcher.get_skill("code-review") is not None
    assert ctrl.ai_client.tool_dispatcher.has_tool("skill_code-review")
    tools = ctrl.skill_dispatcher.get_tool_descriptions()
    assert any(t["function"]["name"] == "skill_code-review" for t in tools)
    result = asyncio.run(ctrl.ai_client.tool_dispatcher.execute("skill_code-review", {"query": "hi"}))
    assert "执行成功" in result

    # Remove the file and resync: no longer visible to AI
    assert ctrl.skill_manager.remove_md_skill("code-review") is True
    assert ctrl._resync_md_skill_tools() == 0
    assert ctrl.skill_dispatcher.get_skill("code-review") is None
    assert not ctrl.ai_client.tool_dispatcher.has_tool("skill_code-review")


def test_skill_bridge_upload_registers_to_ai(tmp_path):
    """SkillBridge.on_upload_skill_dir registers the MD skill with SkillDispatcher and the AI ToolDispatcher"""
    import json
    from bridge.skill_bridge import SkillBridge
    ctrl = _make_app_controller(tmp_path)
    bridge = SkillBridge(ctrl)
    files = {"SKILL.md": "---\nname: code-review\nenabled: true\n---\nReview content"}

    assert bridge.on_upload_skill_dir("code-review", json.dumps(files)) is True
    assert ctrl.skill_dispatcher.get_skill("code-review") is not None
    assert ctrl.ai_client.tool_dispatcher.has_tool("skill_code-review")

    # Remove and resync through the bridge
    bridge.on_remove_skill("code-review")
    assert ctrl.skill_dispatcher.get_skill("code-review") is None
    assert not ctrl.ai_client.tool_dispatcher.has_tool("skill_code-review")

    # Upload again, then toggle off -> AI invisible; toggle on -> AI visible
    assert bridge.on_upload_skill_dir("code-review", json.dumps(files)) is True
    assert ctrl.ai_client.tool_dispatcher.has_tool("skill_code-review")
    bridge.on_toggle_skill("code-review")
    assert ctrl.skill_dispatcher.get_skill("code-review") is None
    assert not ctrl.ai_client.tool_dispatcher.has_tool("skill_code-review")
    bridge.on_toggle_skill("code-review")
    assert ctrl.skill_dispatcher.get_skill("code-review") is not None
    assert ctrl.ai_client.tool_dispatcher.has_tool("skill_code-review")
