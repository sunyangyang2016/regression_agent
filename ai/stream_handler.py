"""
流式处理器 - 处理 AI 流式输出的异步迭代
支持多轮工具调用和实时事件分发
"""
import asyncio
import json
from typing import AsyncIterator, Optional, Callable
from openai import AsyncOpenAI
from ai.protocol import AIStreamEvent, ToolCallInfo, ModelConfig
from ai.tool_names import resolve_original_name, sanitize_tools_for_api


class StreamHandler:
    """流式处理器 - 负责处理 AI 流式响应"""
    
    def __init__(self, model_config: ModelConfig, tool_dispatcher, mcp_dispatcher=None,
                 name_resolver: Optional[Callable[[str], str]] = None):
        self.config = model_config
        self.client: Optional[AsyncOpenAI] = None
        self.tool_dispatcher = tool_dispatcher       # 内建工具调度器
        self.mcp_dispatcher = mcp_dispatcher         # MCP 工具调度器
        self.name_resolver = name_resolver           # API 名 → 原始名 还原回调
        self._tool_name_map: dict = {}               # API 名 → 原始名 映射（stream_chat 内建）
        self._client_lock = asyncio.Lock()
    
    def create_client(self):
        """创建异步客户端"""
        if not self.config.api_key:
            return None
        self.client = AsyncOpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key
        )
        return self.client
    
    async def stream_chat(
        self,
        messages: list,
        tools: Optional[list] = None,
        max_rounds: int = 30,
    ) -> AsyncIterator[AIStreamEvent]:
        """异步流式对话 - 支持多轮工具调用
        
        Args:
            messages: 消息列表（会被修改，追加新消息）
            tools: OpenAI tools 格式的工具定义
            max_rounds: 最大工具调用轮数
        
        Yields:
            AIStreamEvent 事件
        """
        if not self.client:
            yield AIStreamEvent(type="error", error="客户端未初始化")
            return
        
        round_count = 0
        current_messages = list(messages)

        # 防御性校验：确保传给 API 的工具名符合 ^[a-zA-Z0-9_-]+$（AIClient 已规范化时此步为空操作）
        if tools:
            sanitized, local_map = sanitize_tools_for_api(tools)
            if local_map:
                merged = dict(self._tool_name_map)
                for k, v in local_map.items():
                    merged.setdefault(k, v)
                self._tool_name_map = merged
            tools = sanitized
        
        while round_count < max_rounds:
            round_count += 1
            
            try:
                # 第一轮调用
                collected_content = ""
                tool_calls_buffer = {}
                usage_info = None
                
                stream = await self.client.chat.completions.create(
                    model=self.config.model,
                    messages=current_messages,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                    tools=tools if tools else None,
                    tool_choice="auto" if tools else None,
                )
                
                # 流式收集
                async for chunk in stream:
                    # 捕获 usage 信息（流式模式在最后一个 chunk 的 usage 字段中）
                    if chunk.usage:
                        usage_info = chunk.usage
                    
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    
                    if delta.content:
                        collected_content += delta.content
                        yield AIStreamEvent(type="chunk", data=delta.content)
                    
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_buffer:
                                tool_calls_buffer[idx] = {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""}
                                }
                            if tc.id:
                                tool_calls_buffer[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_buffer[idx]["function"]["name"] = tc.function.name
                                if tc.function.arguments:
                                    tool_calls_buffer[idx]["function"]["arguments"] += tc.function.arguments
                
                # 检查是否有工具调用
                if not tool_calls_buffer:
                    # 无工具调用，完成
                    current_messages.append({
                        "role": "assistant",
                        "content": collected_content
                    })
                    # 将 usage 信息附加到 complete 事件
                    complete_data = collected_content
                    if usage_info:
                        extra = {
                            "_usage": {
                                "prompt_tokens": usage_info.prompt_tokens,
                                "completion_tokens": usage_info.completion_tokens,
                                "total_tokens": usage_info.total_tokens
                            }
                        }
                        complete_data = json.dumps({"content": collected_content, **extra})
                    yield AIStreamEvent(type="complete", data=complete_data)
                    messages.clear()
                    messages.extend(current_messages)
                    return
                
                # 有工具调用 -> 添加 assistant 消息
                tool_calls_list = list(tool_calls_buffer.values())
                assistant_msg = {
                    "role": "assistant",
                    "content": collected_content or None,
                    "tool_calls": tool_calls_list
                }
                current_messages.append(assistant_msg)
                
                # ====== 第一批次预检：确定哪些工具有效调用 ======
                # 同一轮中如果同时出现有效参数和 [object Object] 无效参数，
                # 只执行有效参数那个，无效的直接跳过
                valid_tools_in_batch = set()
                for tc in tool_calls_list:
                    tool_name = tc["function"]["name"]
                    arguments_str = tc["function"]["arguments"]
                    if arguments_str not in ('[object Object]', '[object Array]', '', 'undefined', 'null'):
                        try:
                            test_args = json.loads(arguments_str)
                            args_str = json.dumps(test_args, ensure_ascii=False)
                            if '[object Object]' not in args_str and '[object Array]' not in args_str:
                                valid_tools_in_batch.add(tool_name)
                        except Exception:
                            pass
                
                # ====== 同批去重 + 参数有效性检查 ======
                executed_tools = set()  # (tool_name, arguments_json) 已执行过的
                
                for tc in tool_calls_list:
                    tool_name = tc["function"]["name"]
                    arguments_str = tc["function"]["arguments"]
                    
                    # ====== 参数有效性检查 ======
                    invalid_args = ('[object Object]', '[object Array]', '', 'undefined', 'null')
                    skip_tool = False
                    skip_reason = ""
                    
                    if arguments_str in invalid_args:
                        # 如果同一批中有该工具的有效调用，直接跳过这个无效的
                        if tool_name in valid_tools_in_batch:
                            print(f"[StreamHandler] ⚠️ 跳过工具 '{tool_name}'：同批存在有效调用，忽略无效参数 {arguments_str}")
                            current_messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": f"⏭️ 跳过重复调用：'{tool_name}' 的无效参数版本（{arguments_str}），有效版本已执行"
                            })
                            continue
                        skip_tool = True
                        skip_reason = f"参数无效（{arguments_str}）"
                    else:
                        try:
                            arguments = json.loads(arguments_str)
                            args_str = json.dumps(arguments, ensure_ascii=False)
                            if '[object Object]' in args_str or '[object Array]' in args_str:
                                skip_tool = True
                                skip_reason = "参数包含无效的 [object Object]"
                        except json.JSONDecodeError as e:
                            skip_tool = True
                            skip_reason = f"JSON 解析失败: {e}"
                    
                    # ====== 同批去重检查 ======
                    if not skip_tool:
                        tool_key = f"{tool_name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"
                        if tool_key in executed_tools:
                            print(f"[StreamHandler] ⚠️ 跳过重复工具 '{tool_name}'：同一批次中已执行过相同参数")
                            current_messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": f"⏭️ 跳过重复调用：'{tool_name}' 已在本轮执行过相同参数的调用"
                            })
                            continue
                        executed_tools.add(tool_key)
                    
                    if skip_tool:
                        print(f"[StreamHandler] ⚠️ 跳过工具 '{tool_name}'：{skip_reason}")
                        error_msg = f"❌ 工具 '{tool_name}' 调用失败：{skip_reason}，请修正参数后重试"
                        current_messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": error_msg
                        })
                        continue
                    # ====== 结束参数/去重检查 ======
                    
                    print(f"[StreamHandler] 🤖 AI 请求调用工具: {tool_name}")
                    print(f"[StreamHandler] 📤 调用参数: {json.dumps(arguments, ensure_ascii=False)}")
                    
                    tool_info = ToolCallInfo(
                        id=tc["id"],
                        name=tool_name,
                        arguments=arguments,
                        status="running"
                    )
                    yield AIStreamEvent(type="tool_call", data=tool_info)
                    
                    # 异步执行工具（统一路由）
                    print(f"[StreamHandler] ⏳ 正在执行工具 '{tool_name}'...")
                    
                    # 并发执行 + 每 2 秒 yield heartbeat 保持 UI 响应
                    tool_task = asyncio.create_task(self._execute_tool_routed(tool_name, arguments))
                    while True:
                        done, _ = await asyncio.wait([tool_task], timeout=2.0)
                        if tool_task in done:
                            result = tool_task.result()
                            break
                        # 每 2 秒发一个空 chunk 保持 UI 事件循环运转
                        yield AIStreamEvent(type="chunk", data="")
                    
                    print(f"[StreamHandler] ✅ 工具 '{tool_name}' 执行完成")
                    print(f"[StreamHandler] 📥 结果: {result[:200] if len(result) > 200 else result}")
                    
                    tool_info.status = "success"
                    tool_info.result = result
                    yield AIStreamEvent(type="tool_result", data=tool_info)
                    
                    # 添加工具结果到消息
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result
                    })
                
                # 准备下一轮
                continue
                
            except Exception as e:
                yield AIStreamEvent(type="error", error=str(e))
                return
        
        # 达到最大轮数，获取最终回复
        try:
            final = await self.client.chat.completions.create(
                model=self.config.model,
                messages=current_messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=False,
            )
            final_content = final.choices[0].message.content or ""
            current_messages.append({"role": "assistant", "content": final_content})
            yield AIStreamEvent(type="complete", data=final_content)
            messages.clear()
            messages.extend(current_messages)
        except Exception as e:
            yield AIStreamEvent(type="error", error=str(e))
    
    async def _execute_tool_routed(self, tool_name: str, arguments: dict) -> str:
        """统一工具路由：内建 → MCP Host → Builtin fallback"""
        # 0. 还原名称：模型回调的是规范化后的 API 名，先还原为原始工具名再路由
        if getattr(self, "_tool_name_map", None):
            original = resolve_original_name(self._tool_name_map, tool_name)
            if original != tool_name:
                print(f"[StreamHandler] 🔀 工具名还原: '{tool_name}' → '{original}'")
                tool_name = original
        if self.name_resolver:
            original = self.name_resolver(tool_name)
            if original != tool_name:
                print(f"[StreamHandler] 🔀 工具名还原: '{tool_name}' → '{original}'")
                tool_name = original

        # 1. 内建工具（ToolDispatcher 注册的）
        if self.tool_dispatcher.has_tool(tool_name):
            return await self.tool_dispatcher.execute(tool_name, arguments)
        # 2. MCP 工具 — 通过 MCPDispatcher 查询 MCPHost
        if self.mcp_dispatcher:
            if self.mcp_dispatcher.has_tool(tool_name):
                return await self.mcp_dispatcher.execute(tool_name, arguments)
            # MCPDispatcher 不识别但可能在 MCPHost 中未加载完？再直接查一次 MCPHost
            from tools.mcp.host import MCPHost
            host = MCPHost()
            client, tool = host.get_client_for_tool(tool_name)
            if client and tool:
                print(f"[StreamHandler] 🔀 MCPDispatcher 未找到但 MCPHost 找到工具 '{tool_name}' 在 '{client.server_id}'，直接执行")
                import asyncio
                loop = asyncio.get_event_loop()
                try:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, client.call_tool_sync, tool_name, arguments),
                        timeout=60.0
                    )
                    return str(result)
                except asyncio.TimeoutError:
                    return f"❌ 工具 '{tool_name}' 执行超时"
                except Exception as e:
                    return f"❌ 工具 '{tool_name}' 执行失败: {str(e)}"
        # 3. Fallback 到 BuiltinManager（仅限内建工具，MCP 工具不会走到这里）
        from tools.builtin.builtin_tools_manager import BuiltinManager
        bm = BuiltinManager()
        bm.get_tools_for_api()
        if bm._tool_handlers.get(tool_name):
            return bm.execute_tool(tool_name, arguments)
        # 4. 完全找不到，给明确的错误信息
        print(f"[StreamHandler] ❌ 工具 '{tool_name}' 在所有路由中均未找到")
        return f"❌ 工具 '{tool_name}' 未找到。请确认：1) 工具名称是否正确 2) 对应的 MCP 服务器是否已安装并启动 3) 内建工具是否已在工具面板中启用"

    def estimate_tokens(self, text: str) -> int:
        """估算 token 数量"""
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return chinese_chars * 2 + other_chars