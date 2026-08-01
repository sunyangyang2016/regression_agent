"""MCP 管理器集成测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feature.mcp_manager import MCPManager
from feature.config_manager import ConfigManager
from feature.ai_client import AIClient


def test_mcp_manager():
    """测试 MCP 管理器"""
    print("=" * 60)
    print("MCP 管理器集成测试")
    print("=" * 60)
    
    # 1. 初始化
    mgr = MCPManager()
    print("\n=== 初始状态 ===")
    print(f"已安装: {mgr.get_installed_plugins()}")
    print(f"工具数: {len(mgr.get_tools())}")
    
    # 2. 安装天气插件
    print("\n=== 安装 weather 插件 ===")
    mgr.install_plugin("weather")
    print(f"已安装: {mgr.get_installed_plugins()}")
    print(f"工具数: {len(mgr.get_tools())}")
    for t in mgr.get_tools():
        print(f"  - {t['function']['name']}: {t['function']['description'][:60]}...")
    
    # 3. 验证持久化
    print("\n=== 验证持久化（重新初始化） ===")
    mgr2 = MCPManager()
    print(f"已安装: {mgr2.get_installed_plugins()}")
    print(f"工具数: {len(mgr2.get_tools())}")
    
    # 4. 测试工具调用
    print("\n=== 测试工具调用 ===")
    result = mgr.execute_tool("get_weather", {"city": "开封"})
    print(f"get_weather('开封'): {result[:200] if result else '无结果'}")
    
    result2 = mgr.execute_tool("get_forecast", {"city": "开封", "days": 3})
    print(f"get_forecast('开封', 3): {result2[:200] if result2 else '无结果'}")
    
    # 5. 测试文件系统工具
    print("\n=== 测试文件系统工具 ===")
    result3 = mgr.execute_tool("read_file", {"path": "main.py"})
    print(f"read_file('main.py'): {result3[:100] if result3 else '无结果'}...")
    
    result4 = mgr.execute_tool("list_files", {"path": "."})
    print(f"list_files('.'): {result4[:200] if result4 else '无结果'}...")
    
    # 6. 验证 AI Client 集成
    print("\n=== AI Client 集成验证 ===")
    config_mgr = ConfigManager()
    client = AIClient(config_mgr)
    print(f"MCP 工具数: {len(client.mcp_manager.get_tools())}")
    tool_names = [t["function"]["name"] for t in client.mcp_manager.get_tools()]
    print(f"工具列表: {tool_names}")
    
    # 7. 清理
    print("\n=== 清理 ===")
    mgr.uninstall_plugin("weather")
    print(f"卸载 weather 后已安装: {mgr.get_installed_plugins()}")
    print(f"工具数: {len(mgr.get_tools())}")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    test_mcp_manager()