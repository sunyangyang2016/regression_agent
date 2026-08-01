"""测试新模块化架构的功能"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_imports():
    """测试导入"""
    from core.event_bus import EventBus
    from core.plugin_base import UIPlugin, BusinessPlugin
    from ai.protocol import Message, ModelConfig, AIStreamEvent
    from ai.tool_dispatcher import ToolDispatcher
    from ai.stream_handler import StreamHandler
    from ai.ai_client import AIClient
    from tools.builtin.data import BUILTIN_TOOLS, BUILTIN_SERVICE_IDS
    from tools.builtin.registry import BuiltinToolRegistry
    from mcp.host import MCPHost, MCPTool
    from mcp.market.installer import MarketInstaller
    from mcp.mcp_manager import MCPManager
    from skills.skill_loader import SkillLoader, parse_skill_md
    from skills.skill_manager import SkillManager
    
    from ui.bridge import MainBridge, PluginBridge
    print("✅ 所有模块导入成功")


def test_skill_loader():
    """测试 Skill MD 文件解析"""
    from skills.skill_loader import SkillLoader, parse_skill_md
    
    md_path = os.path.join("skills", "md", "code-review.md")
    skill = parse_skill_md(md_path)
    assert skill is not None, "解析失败"
    assert skill["name"] == "code-review", f"名称错误: {skill['name']}"
    assert skill["enabled"] == True, "启用状态错误"
    print(f"✅ 技能 '{skill['name']}' 解析成功")
    print(f"   description: {skill['description']}")
    print(f"   content: {skill['content'][:60]}...")
    
    # 测试加载器
    loader = SkillLoader()
    all_skills = loader.get_all_skills()
    assert len(all_skills) >= 1, f"Should have at least 1 skill, got {len(all_skills)}"
    print(f"✅ 加载了 {len(all_skills)} 个技能")
    
    # 测试合并提示词
    combined = loader.get_combined_prompt()
    assert len(combined) > 0, "合并提示词不应为空"
    print(f"✅ 合并提示词长度: {len(combined)} 字符")
    print(f"   预览: {combined[:100]}...")
    
    # 测试新增和删除
    loader.add_skill("test-skill", "测试用", "这是测试内容")
    assert loader.get_skill("test-skill") is not None, "新增失败"
    print("✅ 技能新增成功")
    
    loader.remove_skill("test-skill")
    assert loader.get_skill("test-skill") is None, "删除失败"
    print("✅ 技能删除成功")


def test_tool_dispatcher():
    """测试工具调度器"""
    from ai.tool_dispatcher import ToolDispatcher
    import asyncio
    
    dispatcher = ToolDispatcher()
    
    # 注册同步处理器
    def greet(args):
        return f"Hello, {args.get('name', 'world')}!"
    
    dispatcher.register_sync("greet", greet)
    assert dispatcher.has_tool("greet"), "注册失败"
    print("✅ 工具注册成功")
    
    # 异步执行
    async def test_exec():
        result = await dispatcher.execute("greet", {"name": "Test"})
        assert result == "Hello, Test!", f"执行结果错误: {result}"
        print(f"✅ 工具执行成功: {result}")
        
        # 测试未知工具
        result2 = await dispatcher.execute("unknown", {})
        assert "未注册" in result2
        print(f"✅ 未知工具提示正确: {result2}")
    
    asyncio.run(test_exec())
    
    dispatcher.clear()
    assert not dispatcher.has_tool("greet"), "清理失败"
    print("✅ 工具清理成功")


def test_theme_manager():
    """测试主题管理器"""
    
    
    theme = ThemeManager()
    assert theme.theme_name == "default", f"默认主题名错误: {theme.theme_name}"
    assert theme.get_color("accent") == "#2b7aff", "默认主题颜色错误"
    print(f"✅ 默认主题已加载: {theme.theme_name}")
    
    css_vars = theme.get_all_css_vars()
    assert ":root {" in css_vars, "CSS 变量格式错误"
    assert "--accent: #2b7aff;" in css_vars, f"CSS 变量内容错误: {css_vars[:200]}"
    print(f"✅ CSS 变量生成成功 ({len(css_vars)} 字符)")


def test_event_bus():
    """测试事件总线"""
    from core.event_bus import EventBus
    
    bus = EventBus()
    results = []
    
    def handler(data):
        results.append(data)
    
    bus.on("test:event", handler)
    bus.emit("test:event", "hello")
    
    # 信号是异步的，需要等一小段时间
    import time
    time.sleep(0.1)
    
    assert len(results) == 1, f"应该收到1个事件, 实际{len(results)}"
    assert results[0] == "hello", f"事件数据错误: {results[0]}"
    print("✅ 事件总线工作正常")
    
    bus.clear()
    print("✅ 事件总线清理成功")


if __name__ == "__main__":
    print("=" * 50)
    print("  新模块化架构测试")
    print("=" * 50)
    
    tests = [
        ("导入测试", test_imports),
        ("事件总线", test_event_bus),
        ("主题管理器", test_theme_manager),
        ("工具调度器", test_tool_dispatcher),
        ("Skill 加载器", test_skill_loader),
    ]
    
    passed = 0
    for name, func in tests:
        print(f"\n▶ {name}")
        try:
            func()
            passed += 1
            print(f"  ✅ {name} 通过")
        except Exception as e:
            import traceback
            print(f"  ❌ {name} 失败: {e}")
            traceback.print_exc()
    
    print(f"\n{'=' * 50}")
    print(f"  结果: {passed}/{len(tests)} 通过")
    print(f"{'=' * 50}")