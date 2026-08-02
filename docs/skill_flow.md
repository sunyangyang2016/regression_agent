# Skill 技能系统 — 业务流程文档

> 本文档基于 `skills/` 模块、`ai/skill_dispatcher.py`、`controller/app_controller.py`、`bridge/skill_bridge.py` 的实际实现编写，覆盖技能系统的**初始化、加载注册、触发执行、AI 工具调用、技能管理**等核心业务流程。

---

## 目录

- [1. 系统整体业务流程](#1-系统整体业务流程)
- [2. 技能系统初始化流程](#2-技能系统初始化流程)
- [3. 技能加载与注册流程](#3-技能加载与注册流程)
- [4. 技能执行核心流程](#4-技能执行核心流程)
- [5. 自动触发流程（TriggerEngine）](#5-自动触发流程triggerengine)
- [6. AI 工具调用执行流程](#6-ai-工具调用执行流程)
- [7. MD 技能管理流程](#7-md-技能管理流程)
- [8. 技能执行时序](#8-技能执行时序)
- [9. 异常处理与错误码](#9-异常处理与错误码)
- [10. 技能状态流转](#10-技能状态流转)

---

## 1. 系统整体业务流程

展示用户输入 → 触发/调用 → 执行 → 返回结果的**完整业务闭环**。

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 UI 层                             │
│   用户输入消息          技能管理面板          对话面板          │
└─────────┬───────────────────┬───────────────────▲──────────┘
          │                   │                   │
          ▼                   ▼                   │
┌─────────────────────────────────────────────────────────────┐
│                     核心控制层                                │
│   AppController ──► ChatController ──► SkillManager          │
│                                    └──── SkillBridge         │
└─────────┬───────────────────┬───────────────────────────────┘
          │                   │
          ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                     技能引擎层                                │
│   SkillLoader ──► SkillRegistry(单例) ◄── SkillDispatcher    │
│   TriggerEngine ──► SkillValidator ──► SkillExecutor         │
└─────────┬───────────────────┬───────────────────────────────┘
          │                   │
          ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                         AI 层                                │
│   AIClient / StreamHandler ──► ToolDispatcher ──► LLM        │
└─────────────────────────────────────────────────────────────┘
```

**执行路径说明：**

| 路径 | 入口 | 调用链 | 适用场景 |
|------|------|--------|----------|
| ① 自动触发 | `ChatController` | `TriggerEngine.auto_execute()` → `SkillDispatcher.execute_skill()` | 用户输入命中关键词/意图/正则模式 |
| ② AI 工具调用 | `AIClient` | LLM 生成 `tool_call` → `ToolDispatcher` → `SkillDispatcher.execute_skill()` | LLM 自主决策调用技能 |
| ③ 直接执行 | 任意代码 | `SkillManager.execute()` → `SkillExecutor.execute()` | 程序化调用（测试/插件） |

---

## 2. 技能系统初始化流程

对应实现：`AppController._init_skill_system()`（`controller/app_controller.py:220`）

```
应用启动 AppController.initialize()
    │
    ▼
① SkillManager.initialize()  加载 Python 技能类
    ├─ Loader.load_builtin_skills()   扫描 skills/builtin/*.py
    └─ Loader.load_custom_skills()    扫描 skills/custom/**/*.py
                │
                ▼
② SkillDispatcher.register_from_registry()  批量注册已启用技能
    └─ 遍历 registry，enabled=True 的技能注册到 dispatcher
                │
                ▼
②1 MD 技能注册为可执行适配器（enable_md_skill_tools 开关，默认开启）
    └─ Loader.load_md_skill_adapters() → 每个适配器 register_skill()
                │
                ▼
③ TriggerEngine 初始化
    ├─ set_skill_dispatcher()           注入调度器引用
    ├─ register_default_triggers()      注册内置默认触发器
    └─ register_skills_triggers()       注册技能声明式触发器（BaseSkill.triggers）
                │
                ▼
④ 注入 TriggerEngine 到 ChatController
                │
                ▼
⑤ 注入 SkillDispatcher 到 AIClient + 注册 skill 工具描述到 ToolDispatcher
                │
                ▼
⑥ _sync_skills_to_frontend()  推送技能数据到前端（立即 + 延迟 1.5s 双推送）
                │
                ▼
⑦ skill_manager.registry.set_event_sink(EventBus.emit)
   技能注册/注销/切换事件 → EventBus 可观测性通道
```

> **核心要点**：
> - `SkillManager`、`SkillDispatcher`、`SkillExecutor` 共享**同一个单例 `SkillRegistry`**，执行时无需额外同步。
> - MD 技能在启用开关开启时注册为 `MdSkill` 适配器，可被 AI 以工具形式调用。
> - 技能数据通过 `_sync_skills_to_frontend()` 直接注入 `appState.skills`，绕过桥接调用。

---

## 3. 技能加载与注册流程

对应实现：`SkillLoader._load_from_module()`（`skills/loader.py`）、`SkillRegistry.register()`（`skills/registry.py`）

```
SkillLoader.load_builtin_skills() / load_custom_skills()
    │
    ▼
importlib.import_module(module)
    │
    ▼
inspect.getmembers(mod) 遍历模块内所有对象
    │
    ▼
是否 class 且是 BaseSkill 子类？ ──否──► 跳过
    │是
    ▼
是否抽象类或就是 BaseSkill？ ──是──► 跳过
    │否
    ▼
实例化 obj() → SkillRegistry.register(instance)
    │
    ▼
SkillValidator.validate_skill() 校验（name/description/validate()）
    │
    ├─ 通过 → registry._skills[name] = instance，加载计数 +1
    └─ 失败 → 拒绝注册并打印错误
```

**加载来源：**

| 来源 | 目录 | 说明 |
|------|------|------|
| 内建技能（Python） | `skills/builtin/*.py` | 内置技能：翻译、总结、代码助手、文档写作、邮件、会议纪要、头脑风暴、问题求解、数据导出、数据分析、网页抓取 |
| 自定义技能（Python） | `skills/custom/**/*.py` | 递归扫描子目录，支持分层模块 |
| MD 技能（目录化） | `skills/md/<name>/SKILL.md` | 目录化技能包：SKILL.md 为必需核心指令，可选 scripts/references/assets 子目录 |

---

## 4. 技能执行核心流程

对应实现：`SkillDispatcher.execute_skill()`（`ai/skill_dispatcher.py`）

```
execute_skill(skill_name, arguments, context, timeout)
    │
    ▼
技能已注册？ ──否──► 返回: ⚠️ 技能 '{name}' 未注册
    │是
    ▼
技能已启用？ ──否──► 返回: ⚠️ 技能 '{name}' 已禁用
    │是
    ▼
外部传入 context？ ──否──► 创建新 SkillContext()
                   ──是──► 复用传入 context，注入 skill_dispatcher 引用
    │                        （允许技能内部嵌套调用其他技能）
    ▼
注入参数: context.params = arguments, context.set(key, value)
    │
    ▼
确定超时时间: timeout 或默认 60s
    │
    ▼
asyncio.wait_for(skill.execute(context, **arguments))
    │
    ├─ 超时 TimeoutError ──► 返回: ⚠️ 技能 '{name}' 执行超时 (>Ns)
    ├─ 异常 Exception   ──► 打印堆栈，返回: ⚠️ 技能 '{name}' 执行失败: {error}
    └─ 正常返回 SkillResult
             │
             ▼
    记录耗时 duration_ms + 执行计数 _execution_count
             │
             ▼
    result.success?
        ├─ 是 → 返回: ✅ 技能 '{name}' 执行成功: + output
        └─ 否 → 返回: ❌ 技能 '{name}' 执行失败: + result.error
```

> **核心设计**：
> - 执行使用 `asyncio.wait_for` 包裹，保证**超时可控**（`SkillExecutor` / `SkillDispatcher` 统一默认 60 秒，共享常量 `DEFAULT_SKILL_TIMEOUT`）。
> - `SkillContext` 中注入 `skill_dispatcher` 引用，使技能可以**嵌套调用其他技能**。
> - 执行历史记录（`execution_history`）：成功/失败/超时/未注册均记录，可观测。
> - 参数会同时注入 `context.params` 与 `context.variables`，技能通过 `kwargs` 或 `context.get()` 两种方式读取。

---

## 5. 自动触发流程（TriggerEngine）

对应实现：`TriggerEngine.evaluate()` 与 `TriggerEngine.auto_execute()`（`skills/trigger_engine.py`）

```
用户输入 user_input
    │
    ▼
引擎已启用且输入非空？ ──否──► 返回空列表，不触发
    │是
    ▼
① 关键词匹配   keyword_triggers     → confidence 0.7~0.8
② 意图匹配     intent_triggers      → confidence 1.0
③ 正则匹配     pattern_triggers     → confidence 0.9（捕获组 → query 参数）
④ 上下文匹配   context_triggers     → 根据 context_data 判断
⑤ 时间匹配     time_triggers        → 根据 current_time 判断
⑥ 事件匹配     event_triggers       → 根据 event_name 判断
    │
    ▼
所有匹配按 confidence 降序排序
    │
    ▼
筛选 confidence ≥ 0.7 且最多取前 3 个
    │
    ├─ 无匹配 → 返回空列表
    └─ 有匹配 → 遍历 high_confidence，调用 SkillDispatcher.execute_skill()
                │
                ├─ 成功 → 收集 {skill_name, trigger_type, confidence, result}
                └─ 异常 → 收集 ⚠️ 自动执行失败: {error}
                │
                ▼
        返回执行结果列表 → 注入对话上下文
```

**默认触发器配置**（`register_default_triggers`）：

| 技能 | 触发关键词示例 | 正则模式 |
|------|---------------|---------|
| translator 翻译 | 翻译 / translate / 英译中 / 翻一下 | `把「...」翻译成 \w+` |
| summarizer 总结 | 总结 / 摘要 / 概括 / 提炼 | — |
| code_assistant 代码助手 | 代码审查 / debug / 重构 | `帮我审查这段代码` |
| web_scraper 网页抓取 | 抓取网页 / 爬取 / scrape | — |
| email_composer 写邮件 | 写邮件 / 起草邮件 | — |
| meeting_minutes 会议纪要 | 会议纪要 / 会议记录 | — |
| brainstorming 头脑风暴 | 头脑风暴 / 想点子 | — |
| problem_solver 问题求解 | 解决问题 / 根因分析 | — |
| document_writer 写文档 | 写文档 / 技术文档 | — |

> **声明式触发器**：技能类可通过 `BaseSkill.triggers` 声明自身触发器元数据，加载时由 `register_skills_triggers()` 自动注册，新增技能无需修改 `AppController`。

---

## 6. AI 工具调用执行流程

对应实现：`AppController._register_skill_tools()`、`AIClient._get_skill_tools()`（`ai/client.py`）

```
LLM 收到对话消息（已注入系统提示 + 技能 Tool 描述）
    │
    ▼
LLM 决定调用工具？
    ├─ 否 → 直接生成文本回复 → 对话输出
    └─ 是 → 生成 tool_call (function: skill_xxx)
               │
               ▼
        StreamHandler 解析 tool_call
               │
               ▼
        ToolDispatcher 查找 handler（skill_xxx → 异步 handler）
               │
               ├─ 不存在 → 返回工具不存在错误
               └─ 存在 → handler(args) → SkillDispatcher.execute_skill(raw_name, args)
                           │
                           ▼
                   执行技能核心流程（见第 4 节）
                           │
                           ▼
                   返回结果字符串 → 作为 tool_message 回传 LLM
                           │
                           ▼
                   LLM 综合结果生成最终回复 → 对话输出
```

> **实现要点**：
> - 每个 skill 生成的 Tool 名称为 `skill_<name>`，注册到 `ToolDispatcher` 时提取原始名称 `raw_name` 作为 `execute_skill` 的第一个参数。
> - 工具描述符合 OpenAI/MCP 兼容的 function-call 格式（`type: function`），`input_schema` 由技能类显式定义，未定义时使用默认 `{query: string}`。
> - 系统提示词通过 `loader.get_combined_prompt()` 将启用的 **MD 技能** 合并为 `## 技能指令` 段落注入。

---

## 7. MD 技能管理流程

对应实现：`SkillBridge`（`bridge/skill_bridge.py`）+ `SkillManager` MD 相关方法（`skills/manager.py`）

```
┌────────────┐   ┌──────────────────┐   ┌──────────────────┐   ┌────────────────────────────┐
│ 前端技能面板 │ → │ SkillBridge       │ → │ SkillManager      │ → │ 文件系统 skills/md/<name>/ │
│            │ ← │ (QWebChannel)     │ ← │                  │ ← │                            │
└────────────┘   └──────────────────┘   └──────────────────┘   └────────────────────────────┘
 getSkills              getSkills()          get_skills_for_js()     解析 <name>/SKILL.md
 on_upload_skill_dir    on_upload_skill_dir() add_md_skill(name, files) 创建 <name>/ 目录
 on_remove_skill        on_remove_skill()    remove_md_skill()       删除 <name>/ 目录
 on_toggle_skill        on_toggle_skill()    toggle_md_skill()       修改 SKILL.md enabled
```

**运行时注册到 AI**：上传 / 删除 / 启用切换后，`SkillBridge` 会调用 `AppController._resync_md_skill_tools()`：先把当前已注册的 MD 适配器注销，再将磁盘上已启用的 MD 技能重新注册为可执行适配器（`SkillManager.sync_md_skills_to_registry()`），并同步 `skill_<name>` 工具处理器到 `ai_client.tool_dispatcher`，使 AI 能即时感知新增 / 禁用 / 删除的技能（无需重启应用）。

**MD 技能目录结构（Claude Skill 风格）：**

```
skills/md/
  <skill-name>/
    SKILL.md          # 必需：核心指令与元数据（YAML Frontmatter）
    scripts/          # 可选：可执行的脚本（.py, .sh）
    references/       # 可选：供 AI 参考的详细文档
    assets/           # 可选：模板、图片等静态资源
```

**SKILL.md 文件格式：**

```markdown
---
name: code-review
enabled: true
description: 代码审查技能提示词
---

（技能提示词正文，将被注入系统提示词）
```

**资源文件说明：**

| 子目录 | 说明 | 加载行为 |
|--------|------|---------|
| `scripts/` | 可执行脚本 | 文件名列表注入提示词，由 AI 决定是否读取/执行 |
| `references/` | 参考文档 | 文件名列表注入提示词，由 AI 决定是否读取 |
| `assets/` | 附加资源 | 文件名列表注入提示词 |

**目录上传：** 支持通过前端"上传技能目录"功能上传完整技能包（使用 `webkitdirectory` 选择目录，前端递归读取全部文件后通过 `on_upload_skill_dir` 桥接上传）。

**管理操作与前端消息反馈：**

| 操作 | 方法 | 说明 |
|------|------|------|
| 上传技能目录 | `on_upload_skill_dir(name, files_json)` | 上传完整技能包（必须含 SKILL.md），后端创建 `<name>/` 目录 |
| 添加简单技能 | `on_add_skill(name)` | 仅创建含 SKILL.md 的最小技能目录 |
| 删除 | `on_remove_skill(name)` | 递归删除 `<name>/` 目录 |
| 切换 | `on_toggle_skill(name)` | 修改 SKILL.md 的 `enabled` 字段 |

---

## 8. 技能执行时序

以 TriggerEngine 自动触发为例：触发 → 执行 → 返回

```
用户 ──输入消息（如"帮我翻译这段文字"）──► ChatController
    ChatController ──auto_execute(user_input)──► TriggerEngine
        TriggerEngine ──evaluate()──► 关键词/意图/正则/上下文/时间/事件 匹配
        TriggerEngine ◄── 返回 TriggerMatch 列表（置信度排序）──
    
    alt 匹配成功且 confidence ≥ 0.7
        TriggerEngine ──execute_skill(name, params, context)──► SkillDispatcher
            SkillDispatcher ──校验存在 & enabled──► 自身
            SkillDispatcher ──注入 skill_dispatcher + 参数──► SkillContext
            SkillDispatcher ──asyncio.wait_for(skill.execute(context, **args), 60s)──► BaseSkill
            BaseSkill ──返回 SkillResult(success, output/error)──► SkillDispatcher
                SkillDispatcher ──记录 duration_ms / _execution_count──► 自身
                SkillDispatcher ──结果字符串──► TriggerEngine
            TriggerEngine ──[{skill_name, confidence, result}]──► ChatController
        ChatController ──注入执行结果到对话──► 用户
    
    alt AI 自主调用（第二条路径）
        用户 ──输入消息──► ChatController
            ChatController ──send(messages, tools=[skill_xxx...])──► LLM
            LLM ──tool_call(function: skill_xxx, args)──► ChatController
            ChatController ──ToolDispatcher → execute_skill(raw_name, args)──► SkillDispatcher
            SkillDispatcher ──结果作为 tool_message──► LLM
            LLM ──基于工具结果生成最终回复──► 用户
```

---

## 9. 异常处理与错误码

对应实现：`SkillDispatcher.execute_skill()` 的异常分支与 `SkillExecutor.execute()`

| 异常场景 | 检测点 | 返回值 | 代码位置 |
|---------|--------|--------|---------|
| 技能未注册 | `execute_skill` 入口 | `⚠️ 技能 'x' 未注册` | `ai/skill_dispatcher.py` |
| 技能已禁用 | `execute_skill` 入口 | `⚠️ 技能 'x' 已禁用` | `ai/skill_dispatcher.py` |
| 执行超时 | `asyncio.wait_for` | `⚠️ 技能 'x' 执行超时 (>{N}s)` | `ai/skill_dispatcher.py` |
| 执行异常 | 捕获 `Exception` | `⚠️ 技能 'x' 执行失败: {error}` | `ai/skill_dispatcher.py` |
| 技能不合法 | `SkillValidator.validate_skill` | 拒绝注册 + 错误列表 | `skills/validator.py` |
| 名称非法 | `SkillValidator.validate_name` | 仅允许字母/数字/下划线/连字符 | `skills/validator.py` |

**兜底保障**：

| 保障机制 | 说明 |
|---------|------|
| `asyncio.wait_for` 超时保护 | 统一默认 60s（`DEFAULT_SKILL_TIMEOUT`） |
| `traceback.print_exc()` | 保留堆栈便于排查 |
| try/except 包裹 | 异常不向上传播 |
| 结果统一为字符串 | AI 可直接理解 |

---

## 10. 技能状态流转

```
[*] → 未注册: 编写技能类/MD 文件
未注册 → 已注册: SkillRegistry.register()
已注册 → 未注册: unregister()
已注册 → 已启用: enabled = True
已注册 → 已禁用: enabled = False（toggle_md_skill）
已禁用 → 已启用: toggle_md_skill() / 重新加载
已启用 → 执行中: SkillDispatcher.execute_skill()
执行中 → 已启用: 执行完成（成功/失败/超时均返回）
已启用 → 未注册: 卸载/删除
已启用 → [*]: 系统退出
```

**状态说明：**

| 状态 | 含义 | 判断条件 |
|------|------|---------|
| 未注册 | 尚未进入 Registry | `registry.get(name) is None` |
| 已注册 | 已注册但禁用 | 注册成功，`enabled = False` |
| 已启用 | 可被触发/调用 | `enabled = True` 且已注册 |
| 执行中 | 正在异步执行 | `asyncio.wait_for` 包裹期间 |
| 已禁用 | 拒绝执行 | `execute_skill` 直接返回禁用提示 |

---

## 附：核心类与职责速查

| 类 | 所在文件 | 职责 |
|----|---------|------|
| `BaseSkill` | `skills/base.py` | 技能抽象基类，子类实现 `execute()`，声明 `name/description/input_schema/triggers` |
| `SkillResult` | `skills/base.py` | 执行结果数据类（success/output/error/duration_ms/metadata） |
| `SkillContext` | `skills/context.py` | 执行上下文（用户输入、会话、参数、变量、调度器引用） |
| `SkillRegistry` | `skills/registry.py` | 单例注册中心，技能按名称注册/查找/分类，生命周期钩子 + EventBus 事件 |
| `SkillLoader` | `skills/loader.py` | 加载 Python 技能类 + 解析 MD 技能目录（mtime 缓存） |
| `SkillExecutor` | `skills/executor.py` | 技能执行器（批量/分类并发执行，超时保护） |
| `SkillValidator` | `skills/validator.py` | 技能配置与执行参数校验 |
| `SkillManager` | `skills/manager.py` | 统一门面：加载/注册/执行/MD 管理/前端桥接 |
| `SkillDispatcher` | `ai/skill_dispatcher.py` | AI 工具化调度：Tool 描述生成 + 异步执行 + 执行历史 |
| `TriggerEngine` | `skills/trigger_engine.py` | 触发评估引擎：6 类触发器（关键词/意图/正则/上下文/时间/事件）+ 自动执行 |
| `MdSkill` | `skills/md_skill.py` | MD 技能适配器：将技能目录（SKILL.md + 资源）包装为可执行 BaseSkill |
| `SkillBridge` | `bridge/skill_bridge.py` | QWebChannel 桥接，前端技能管理接口 |

---

*文档生成日期：2026-08-01 · 基于当前代码库实现编写。若模块逻辑变更，请同步更新本文档。*