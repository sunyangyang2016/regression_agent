"""
MCP 工具调度器 - 异步执行 MCP 工具调用
代理到 MCPHost 进行路由，MCPHost 负责找到正确的 MCPClient
"""
import asyncio
import json
from typing import Dict, Callable, Awaitable


class MCPDispatcher:
    """MCP 工具调度器 - 负责将 MCP 工具调用路由到正确的 MCPHost"""

    def __init__(self):
        self._handlers: Dict[str, Callable[[dict], Awaitable[str]]] = {}
        self._timeout: float = 60.0

    def register(self, name: str, handler: Callable[[dict], Awaitable[str]]):
        self._handlers[name] = handler

    def register_sync(self, name: str, handler: Callable[[dict], str]):
        async def wrapper(args: dict) -> str:
            return handler(args)
        self._handlers[name] = wrapper

    def unregister(self, name: str):
        self._handlers.pop(name, None)

    def has_tool(self, tool_name: str) -> bool:
        """检查工具是否可用 - 先查内部处理器，再查 MCPHost"""
        if tool_name in self._handlers:
            return True
        # 查询 MCPHost 中已连接的客户端
        try:
            from tools.mcp.host import MCPHost
            host = MCPHost()
            client, tool = host.get_client_for_tool(tool_name)
            if client and tool:
                return True
        except Exception:
            pass
        return False

    async def execute(self, tool_name: str, arguments: dict) -> str:
        """
        执行 MCP 工具
        
        路由策略：
        1. 优先使用注册的处理器（异步包装）
        2. 回退到 MCPHost 查找对应的 MCPClient
        """
        # ====== 工具权限校验（安全插件 hook 广播，MCP 作为独立业务方） ======
        # MCP 不纳入插件框架生命周期管理，仅在工具执行前广播权限校验事件。
        try:
            from plugins.hook_registry import HookRegistry
            results = await HookRegistry().atrigger("tool:before_execute", json.dumps(
                {"tool_name": tool_name, "arguments": arguments, "source": "mcp"}, ensure_ascii=False))
            for r in HookRegistry.parse_results(results):
                if not r.get("allowed", True):
                    print(f"[MCPDispatcher] 🛡️ MCP 工具 '{tool_name}' 被安全策略拦截")
                    return r.get("deny_message", f"❌ MCP 工具 '{tool_name}' 已被安全策略禁止")
        except Exception as e:
            print(f"[MCPDispatcher] ⚠️ 工具权限校验失败: {e}")

        handler = self._handlers.get(tool_name)
        if handler:
            print(f"[MCPDispatcher] ⏳ 通过注册处理器执行 '{tool_name}'...")
            try:
                result = await asyncio.wait_for(handler(arguments), timeout=self._timeout)
                print(f"[MCPDispatcher] ✅ '{tool_name}' 执行成功")
                return str(result)
            except asyncio.TimeoutError:
                print(f"[MCPDispatcher] ❌ '{tool_name}' 超时")
                return f"❌ MCP 工具 '{tool_name}' 执行超时"
            except Exception as e:
                print(f"[MCPDispatcher] ❌ '{tool_name}' 失败: {e}")
                return f"❌ MCP 工具 '{tool_name}' 执行失败: {str(e)}"

        # 回退到 MCPHost 路由
        print(f"[MCPDispatcher] 🔀 通过 MCPHost 路由 '{tool_name}'...")
        try:
            from tools.mcp.host import MCPHost
            host = MCPHost()
            client, tool = host.get_client_for_tool(tool_name)
            if client and tool:
                print(f"[MCPDispatcher] 🔀 找到客户端 '{client.server_id}'，正在执行...")
                # 检查客户端是否运行中
                if not client.is_running():
                    print(f"[MCPDispatcher] ❌ 客户端 '{client.server_id}' 未运行")
                    return f"❌ MCP 工具 '{tool_name}' 调用失败：服务器 '{client.server_id}' 未运行，请先启动该 MCP 服务器"
                try:
                    # 统一使用 call_tool_sync 通过线程池执行
                    # MCPLocalClient 的子进程绑定在独立事件循环中，必须在独立线程中执行
                    # MCPHTTPClient 的 call_tool_sync 是同步包装
                    print(f"[MCPDispatcher] 🔀 通过线程池执行 tool 调用...")
                    result = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, client.call_tool_sync, tool_name, arguments
                        ),
                        timeout=self._timeout
                    )
                    print(f"[MCPDispatcher] ✅ '{tool_name}' 通过 MCPHost 执行成功")
                    return str(result)
                except AttributeError as e:
                    print(f"[MCPDispatcher] ❌ 客户端 '{type(client).__name__}' 缺少方法: {e}")
                    # 降级：尝试直接通过 host.execute_tool
                    try:
                        result = await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(
                                None, host.execute_tool, tool_name, arguments
                            ),
                            timeout=self._timeout
                        )
                        return str(result)
                    except Exception as e2:
                        return f"❌ MCP 工具 '{tool_name}' 调用失败: {str(e2)}"
                except asyncio.TimeoutError:
                    return f"❌ MCP 工具 '{tool_name}' 执行超时"
                except Exception as e:
                    return f"❌ MCP 工具 '{tool_name}' 调用失败: {str(e)}"
            
            # 找不到该工具，尝试直接让 MCPHost 执行（兼容旧路由）
            try:
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, host.execute_tool, tool_name, arguments
                    ),
                    timeout=self._timeout
                )
                return str(result)
            except asyncio.TimeoutError:
                return f"❌ MCP 工具 '{tool_name}' 执行超时"
            except Exception as e:
                return f"❌ MCP 工具 '{tool_name}' 执行失败: {str(e)}"
        except asyncio.TimeoutError:
            return f"❌ MCP 工具 '{tool_name}' 执行超时"
        except Exception as e:
            return f"❌ MCP 工具 '{tool_name}' 执行失败: {str(e)}"

    def clear(self):
        self._handlers.clear()