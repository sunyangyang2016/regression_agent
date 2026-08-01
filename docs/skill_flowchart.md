# Skill 技能系统 — 业务流程图

> 本文档基于 `skills/` 模块、`ai/skill_dispatcher.py`、`controller/app_controller.py`、`bridge/skill_bridge.py` 的实际实现绘制，覆盖技能系统的**初始化、加载注册、触发执行、AI 工具调用、技能管理**等核心业务流程。
>
> 图例：`flowchart` 为业务流程图，`sequenceDiagram` 为时序图，`stateDiagram` 为状态流转图。文中标注的类名/方法名均与代码一一对应，可用于快速定位实现。

---

## 目录

- [1. 系统整体业务流程图](#1-系统整体业务流程图)
- [2. 技能系统初始化流程](#2-技能系统初始化流程)
- [3. 技能加载与注册流程](#3-技能加载与注册流程)
- [4. 技能执行核心流程](#4-技能执行核心流程)
- [5. 自动触发流程（TriggerEngine）](#5-自动触发流程triggerengine)
- [6. AI 工具调用执行流程](#6-ai-工具调用执行流程)
- [7. MD 技能管理流程](#7-md-技能管理流程)
- [8. 技能执行时序图](#8-技能执行时序图)
- [9. 异常处理与错误码](#9-异常处理与错误码)
- [10. 技能状态流转](#10-技能状态流转)

---

## 1. 系统整体业务流程图

展示用户输入 → 触发/调用 → 执行 → 返回结果的**完整业务闭环**。

```mermaid
flowchart TD
    subgraph UI["前端 UI 层"]
        A1["用户输入消息"]
        A2["技能管理面板"]
        A3["对话面板"]
    end

    subgraph CORE["核心控制层"]
        B1["AppController<br/>（主控制器）"]
        B2["ChatController<br/>（对话控制器）"]
        B3["SkillManager<br/>（技能门面 Facade）"]
        B4["SkillBridge<br/>（前后端桥接）"]
    end

    subgraph SKILL["技能引擎层"]
        C1["SkillLoader<br/>（加载器）"]
        C2["SkillRegistry<br/>（注册中心·单例）"]
        C3["SkillDispatcher<br/>（调度器）"]
        C4["TriggerEngine<br/>（触发引擎）"]
        C5["SkillValidator<br/>（验证器）"]
    end

    subgraph AI["AI 层"]
        D1["AIClient / StreamHandler"]
        D2["ToolDispatcher<br/>（内建工具调度器）"]
        D3["LLM 大模型"]
    end

    A1 -->|"① 自动触发"| C4
    A1 -->|"② 发送对话"| D1
    D1 --> D3
    D3 -->|"③ 返回 tool_call (skill_xxx)"| D2
    C4 -->|"触发匹配"| C3
    D2 -->|"③ 调用执行"| C3
    C3 -->|"执行技能"| C1
    C3 -.->|"读取"| C2
    C1 -->|"加载并注册"| C2
    B1 -->|"初始化/注入依赖"| C3
    B1 -->|"初始化/注入依赖"| C4
    A2 -->|"技能 CRUD"| B4
    B4 --> B3
    B3 -->|"读写 MD 技能"| C1
    B3 -->|"执行/注册"| C2
    C3 -->|"返回结果字符串"| D2
    D2 --> D1
    D1 -->|"④ 结果注入对话"| A3
    C3 -->|"返回执行结果"| C4
    C4 -->|"结果注入对话上下文"| A3
    B4 -->|"技能状态 JSON"| A2
```

**执行路径说明：**

| 路径 | 入口 | 调用链 | 适用场景 |
|------|------|--------|----------|
| ① 自动触发 | `ChatController` | `TriggerEngine.auto_execute()` → `SkillDispatcher.execute_skill()` | 用户输入命中关键词/意图/正则模式 |
| ② AI 工具调用 | `AIClient` | LLM 生成 `tool_call` → `ToolDispatcher` → `SkillDispatcher.execute_skill()` | LLM 自主决策调用技能 |
| ③ 直接执行 | 任意代码 | `SkillManager.execute()` → `SkillExecutor.execute()` | 程序化调用（测试/插件） |

---

## 2. 技能系统初始化流程

对应实现：`AppController._init_skill_system()`（`controller/app_controller.py:203`）

```mermaid
flowchart TD
    START(["应用启动<br/>AppController.initialize()"]) --> INIT["初始化技能系统<br/>_init_skill_system()"]
    INIT --> S1["Step 1: SkillManager.initialize()<br/>加载 Python 技能类"]
    S1 --> S1a["Loader.load_builtin_skills()<br/>扫描 skills/builtin/*.py"]
    S1 --> S1b["Loader.load_custom_skills()<br/>扫描 skills/custom/**/*.py"]
    S1a --> REG["注册到 SkillRegistry"]
    S1b --> REG

    REG --> S2["Step 2: SkillDispatcher.register_from_registry()<br/>批量注册已启用技能"]
    S2 --> CHK{"技能已注册<br/>且 enabled=True?"}
    CHK -->|"是"| S2a["dispatcher.registry.register(skill)<br/>（共享 SkillRegistry 单例）"]
    CHK -->|"否"| S2x["跳过该技能"]
    S2a --> S3["Step 3: TriggerEngine 初始化<br/>set_skill_dispatcher() + register_default_triggers()"]
    S2x --> S3

    S3 --> S4["Step 4: 注入 TriggerEngine<br/>chat_controller.trigger_engine = engine"]
    S4 --> S5["Step 5: 注入 SkillDispatcher 到 AIClient<br/>ai_client.skill_dispatcher = dispatcher"]
    S5 --> S6["_register_skill_tools()<br/>skill → Tool 描述 → ToolDispatcher"]
    S6 --> S7["Step 6: _sync_skills_to_frontend()<br/>推送技能数据到前端"]
    S7 --> DONE(["✅ 技能系统初始化完成"])

    DONE -.->|"记录日志"| LOG["[AppController] 🎯 SkillDispatcher 已注册 N 个技能"]
```

> **注意**：`SkillManager`、`SkillDispatcher`、`SkillExecutor` 共享**同一个单例 `SkillRegistry`**，因此技能在执行时无需额外同步。

---

## 3. 技能加载与注册流程

对应实现：`SkillLoader._load_from_module()`（`skills/loader.py:64`）、`SkillRegistry.register()`（`skills/registry.py:19`）

```mermaid
flowchart TD
    A["SkillLoader.load_builtin_skills()<br/>或 load_custom_skills()"] --> B["importlib.import_module(module)"]
    B --> C["inspect.getmembers(mod)<br/>遍历模块内所有对象"]

    C --> D{"是 class 且<br/>是 BaseSkill 子类?"}
    D -->|"否"| C
    D -->|"是"| E{"是抽象类<br/>或就是 BaseSkill?"}
    E -->|"是"| C
    E -->|"否"| F["实例化 obj()"]
    F --> G["SkillRegistry.register(instance)"]
    G --> H{"name 非空?"}
    H -->|"否"| F
    H -->|"是"| I["registry._skills[name] = instance"]
    I --> J[("加载计数 +1")]

    K["SkillValidator.validate_skill()<br/>（可选，由 SkillManager.register 调用）"] -.-> G
    L{"name 为空?<br/>description 缺失?<br/>validate() 失败?"} -.->|"任一失败"| M["拒绝注册并打印错误"]
```

**加载来源：**

| 来源 | 目录 | 说明 |
|------|------|------|
| 内建技能（Python） | `skills/builtin/*.py` | 11 个内置技能：翻译、总结、代码助手、文档写作、邮件、会议纪要、头脑风暴、问题求解、数据导出、数据分析、网页抓取 |
| 自定义技能（Python） | `skills/custom/**/*.py` | 递归扫描子目录，支持分层模块 |
| MD 技能（提示词） | `skills/md/*.md` | 通过 YAML Frontmatter（`name/enabled/description`）声明，正文为提示词 |

---

## 4. 技能执行核心流程

对应实现：`SkillDispatcher.execute_skill()`（`ai/skill_dispatcher.py:127`）

```mermaid
flowchart TD
    CALL(["execute_skill(skill_name, arguments, context, timeout)"]) --> F1{"技能已注册?<br/>dispatcher._skills.get()"}

    F1 -->|"否"| E1["返回: ⚠️ 技能 '{name}' 未注册"]
    F1 -->|"是"| F2{"技能已启用?<br/>skill.enabled"}

    F2 -->|"否"| E2["返回: ⚠️ 技能 '{name}' 已禁用"]
    F2 -->|"是"| F3{"外部传入 context?"}
    F3 -->|"否"| F3a["创建新 SkillContext()"]
    F3 -->|"是"| F3b["复用传入 context<br/>context.skill_dispatcher = self<br/>（允许技能内部调用其他技能）"]
    F3a --> F4
    F3b --> F4

    F4["注入参数<br/>context.params = arguments<br/>context.set(key, value) 写入 variables"]
    F4 --> F5["确定超时时间<br/>timeout 或默认 60s"]

    F5 --> F6["asyncio.wait_for<br/>skill.execute(context, **arguments)"]
    F6 --> F7{"执行结果?"}

    F7 -->|"超时 TimeoutError"| E3["返回: ⚠️ 技能 '{name}' 执行超时 (>Ns)"]
    F7 -->|"异常 Exception"| E4["打印堆栈<br/>返回: ⚠️ 技能 '{name}' 执行失败: {error}"]
    F7 -->|"正常返回 SkillResult"| F8["记录耗时<br/>result.duration_ms = 实际毫秒<br/>skill._execution_count += 1"]

    F8 --> F9{"result.success?"}
    F9 -->|"是"| R1["返回: ✅ 技能 '{name}' 执行成功:<br/>+ output"]
    F9 -->|"否"| R2["返回: ❌ 技能 '{name}' 执行失败:<br/>+ result.error"]
    E1 --> RETURN["返回结果字符串（给 AI/调用方）"]
    E2 --> RETURN
    E3 --> RETURN
    E4 --> RETURN
    R1 --> RETURN
    R2 --> RETURN
```

> **核心设计**：
> - 执行使用 `asyncio.wait_for` 包裹，保证**超时可控**（`SkillExecutor` / `SkillDispatcher` 统一默认 60 秒，共享常量 `DEFAULT_SKILL_TIMEOUT`）。
> - `SkillContext` 中注入 `skill_dispatcher` 引用，使技能可以**嵌套调用其他技能**。
> - 参数会同时注入 `context.params` 与 `context.variables`，技能通过 `kwargs` 或 `context.get()` 两种方式读取。

---

## 5. 自动触发流程（TriggerEngine）

对应实现：`TriggerEngine.evaluate()` 与 `TriggerEngine.auto_execute()`（`skills/trigger_engine.py:114/171`）

```mermaid
flowchart TD
    U(["用户输入 user_input"]) --> G1{"引擎已启用?<br/>_enabled && 输入非空"}
    G1 -->|"否"| G0["返回空列表，不触发"]
    G1 -->|"是"| G2["① 关键词匹配<br/>遍历 keyword_triggers<br/>keyword ∈ 输入（小写）"]
    G2 --> G3["② 意图匹配<br/>遍历 intent_triggers<br/>意图模式命中"]
    G3 --> G4["③ 正则模式匹配<br/>遍历 pattern_triggers<br/>pattern.search(输入)"]

    G2 --> G5["生成 TriggerMatch<br/>confidence = 0.7 / 0.8"]
    G3 --> G6["生成 TriggerMatch<br/>confidence = 1.0"]
    G4 --> G7["生成 TriggerMatch<br/>confidence = 0.9<br/>捕获组 → query 参数"]

    G5 --> SORT["所有匹配按 confidence 降序排序"]
    G6 --> SORT
    G7 --> SORT

    SORT --> FILTER["筛选 confidence ≥ 0.7<br/>且最多取前 3 个"]
    FILTER -->|"无匹配"| G0
    FILTER -->|"有匹配"| EXEC["遍历 high_confidence<br/>调用 SkillDispatcher.execute_skill(name, params, context)"]
    EXEC --> E1{"执行成功?"}
    E1 -->|"是"| R1["收集结果 {skill_name, trigger_type, confidence, result}"]
    E1 -->|"异常"| R2["收集结果 ⚠️ 自动执行失败: {error}"]
    R1 --> R["返回执行结果列表<br/>注入对话上下文"]
    R2 --> R
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

---

## 6. AI 工具调用执行流程

对应实现：`AppController._register_skill_tools()`（`controller/app_controller.py:299`）、`AIClient._get_skill_tools()`（`ai/client.py:336`）

```mermaid
flowchart TD
    A["LLM 收到对话消息<br/>（已注入系统提示 + 技能 Tool 描述）"] --> B{"LLM 决定调用工具?"}
    B -->|"否"| N1["直接生成文本回复"]
    B -->|"是"| C["生成 tool_call<br/>function: skill_xxx"]
    C --> D["StreamHandler 解析 tool_call"]
    D --> E["ToolDispatcher 查找 handler<br/>（skill_xxx → 异步 handler）"]
    E --> F{"handler 存在?"}
    F -->|"否"| E1["返回工具不存在错误"]
    F -->|"是"| G["handler(args_dict)<br/>→ SkillDispatcher.execute_skill(raw_name, args)"]
    G --> H["执行技能核心流程<br/>（见第 4 节）"]
    H --> I["返回结果字符串"]
    I --> J["结果作为 tool_message 回传 LLM"]
    J --> K["LLM 综合结果生成最终回复"]
    N1 --> OUT["对话输出"]
    K --> OUT
```

> **实现要点**：
> - 每个 skill 生成的 Tool 名称为 `skill_<name>`，注册到 `ToolDispatcher` 时提取原始名称 `raw_name` 作为 `execute_skill` 的第一个参数。
> - 工具描述符合 OpenAI/MCP 兼容的 function-call 格式（`type: function`），`input_schema` 由技能类显式定义，未定义时使用默认 `{query: string}`。
> - 系统提示词通过 `loader.get_combined_prompt()` 将启用的 **MD 技能** 合并为 `## 技能指令` 段落注入。

---

## 7. MD 技能管理流程

对应实现：`SkillBridge`（`bridge/skill_bridge.py`）+ `SkillManager` MD 相关方法（`skills/manager.py`）

```mermaid
flowchart TD
    subgraph FE["前端技能面板"]
        L["getSkills<br/>技能列表"]
        A1["on_add_skill<br/>添加技能"]
        R1["on_remove_skill<br/>删除技能"]
        T1["on_toggle_skill<br/>启用/禁用"]
        S1["getSkillStatus<br/>系统状态"]
    end

    subgraph BRIDGE["SkillBridge（QWebChannel @pyqtSlot）"]
        B1["getSkills()"]
        B2["on_add_skill(name)"]
        B3["on_remove_skill(name)"]
        B4["on_toggle_skill(name)"]
        B5["getSkillStatus()"]
    end

    subgraph MGR["SkillManager"]
        M1["get_skills_for_js()<br/>registry + loader.md_dir 合并"]
        M2["add_md_skill(name, desc, content)"]
        M3["remove_md_skill(name)"]
        M4["toggle_md_skill(name)"]
        M5["get_status()"]
    end

    subgraph FS["文件系统 / skills/md/*.md"]
        F1["创建 xxx.md<br/>--- name/enabled/description ---"]
        F2["删除 xxx.md"]
        F3["修改 enabled: true ↔ false"]
    end

    L --> B1
    A1 --> B2
    R1 --> B3
    T1 --> B4
    S1 --> B5

    B1 --> M1
    B2 --> M2
    B3 --> M3
    B4 --> M4
    B5 --> M5

    M2 --> C1{"文件已存在?"}
    C1 -->|"是"| E1["返回 False，提示已存在"]
    C1 -->|"否"| F1
    M3 --> F2
    M4 --> P1["parse_md_file 读取 frontmatter"]
    P1 --> F3

    M1 -.->|"解析"| P2["Loader.parse_md_file()<br/>正则解析 --- YAML 块 ---"]
    M1 --> J1["返回 [{name, enabled, description}] JSON"]
    J1 --> L
```

**运行时注册到 AI：** 上传 / 删除 / 启用切换后，`SkillBridge` 会调用 `AppController._resync_md_skill_tools()`：先把当前已注册的 MD 适配器注销，再将磁盘上已启用的 MD 技能重新注册为可执行适配器（`SkillManager.sync_md_skills_to_registry()`），并同步 `skill_<name>` 工具处理器到 `ai_client.tool_dispatcher`，使 AI 能即时感知新增 / 禁用 / 删除的技能（无需重启应用）。

**MD 技能文件格式：**

```markdown
---
name: code-review
enabled: true
description: 代码审查技能提示词
---

（技能提示词正文，将被注入系统提示词）
```

**管理操作与前端消息反馈：**

| 操作 | 方法 | 成功反馈 | 失败反馈 |
|------|------|---------|---------|
| 添加 | `on_add_skill` | `✅ 技能 "x" 已添加。` | `⚠️ 技能 "x" 已存在或名称无效。` |
| 删除 | `on_remove_skill` | `🗑️ 技能 "x" 已删除。` | — |
| 切换 | `on_toggle_skill` | `🔄 技能 "x" 已启用/禁用。` | — |

---

## 8. 技能执行时序图

展示一次完整的**触发 → 执行 → 返回**时序（以 TriggerEngine 自动触发为例）：

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户
    participant CC as ChatController
    participant TE as TriggerEngine
    participant SD as SkillDispatcher
    participant CTX as SkillContext
    participant SK as BaseSkill
    participant LLM as LLM（可选路径）

    User->>CC: 输入消息（如"帮我翻译这段文字"）
    CC->>TE: auto_execute(user_input)
    TE->>TE: evaluate()：关键词/意图/正则匹配
    TE-->>CC: 返回 TriggerMatch 列表（置信度排序）

    alt 匹配成功且 confidence ≥ 0.7
        TE->>SD: execute_skill(name, params, context)
        SD->>SD: 校验技能存在 & enabled
        SD->>CTX: 注入 skill_dispatcher 引用 + 参数
        SD->>SK: asyncio.wait_for(skill.execute(context, **args), 60s)
        SK-->>SD: SkillResult(success, output/error)
        SD->>SD: 记录 duration_ms / _execution_count
        SD-->>TE: 结果字符串（✅ 成功 / ❌ 失败）
        TE-->>CC: [{skill_name, confidence, result}]
        CC-->>User: 注入执行结果到对话
    end

    alt AI 自主调用（第二条路径）
        User->>CC: 输入消息
        CC->>LLM: send(messages, tools=[skill_xxx...])
        LLM-->>CC: tool_call(function: skill_xxx, args)
        CC->>SD: ToolDispatcher → execute_skill(raw_name, args)
        SD-->>LLM: 结果作为 tool_message
        LLM-->>User: 基于工具结果生成最终回复
    end
```

---

## 9. 异常处理与错误码

对应实现：`SkillDispatcher.execute_skill()` 的异常分支与 `SkillExecutor.execute()`

```mermaid
flowchart LR
    subgraph 错误分类
        E1["未注册<br/>⚠️ 技能 '{name}' 未注册"]
        E2["已禁用<br/>⚠️ 技能 '{name}' 已禁用"]
        E3["超时<br/>⚠️ 技能 '{name}' 执行超时 (>{N}s)"]
        E4["业务失败<br/>❌ 技能 '{name}' 执行失败: {error}"]
        E5["验证失败<br/>SkillValidator 拒绝注册"]
    end

    subgraph 兜底保障
        S1["asyncio.wait_for 超时保护<br/>统一默认 60s（DEFAULT_SKILL_TIMEOUT）"]
        S2["traceback.print_exc()<br/>保留堆栈便于排查"]
        S3["try/except 包裹<br/>异常不向上传播"]
        S4["结果统一为字符串<br/>AI 可直接理解"]
    end
```

| 异常场景 | 检测点 | 返回值 | 代码位置 |
|---------|--------|--------|---------|
| 技能未注册 | `execute_skill` 入口 | `⚠️ 技能 'x' 未注册` | `ai/skill_dispatcher.py:147` |
| 技能已禁用 | `execute_skill` 入口 | `⚠️ 技能 'x' 已禁用` | `ai/skill_dispatcher.py:149` |
| 执行超时 | `asyncio.wait_for` | `⚠️ 技能 'x' 执行超时 (>{N}s)` | `ai/skill_dispatcher.py:178` |
| 执行异常 | 捕获 `Exception` | `⚠️ 技能 'x' 执行失败: {error}` | `ai/skill_dispatcher.py:180` |
| 技能不合法 | `SkillValidator.validate_skill` | 拒绝注册 + 错误列表 | `skills/validator.py:12` |
| 名称非法 | `SkillValidator.validate_name` | 仅允许字母/数字/下划线/连字符 | `skills/validator.py:43` |

---

## 10. 技能状态流转

```mermaid
stateDiagram-v2
    [*] --> 未注册: 编写技能类/MD 文件
    未注册 --> 已注册: SkillRegistry.register()
    已注册 --> 未注册: unregister()
    已注册 --> 已启用: enabled = True
    已注册 --> 已禁用: enabled = False（toggle_md_skill）
    已禁用 --> 已启用: toggle_md_skill() / 重新加载
    已启用 --> 执行中: SkillDispatcher.execute_skill()
    执行中 --> 已启用: 执行完成（成功/失败/超时均返回）
    已启用 --> 未注册: 卸载/删除
    已启用 --> [*]: 系统退出
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
| `BaseSkill` | `skills/base.py` | 技能抽象基类，子类实现 `execute()`，声明 `name/description/input_schema` |
| `SkillResult` | `skills/base.py` | 执行结果数据类（success/output/error/duration_ms/metadata） |
| `SkillContext` | `skills/context.py` | 执行上下文（用户输入、会话、参数、变量、调度器引用） |
| `SkillRegistry` | `skills/registry.py` | 单例注册中心，技能按名称注册/查找/分类 |
| `SkillLoader` | `skills/loader.py` | 加载 Python 技能类 + 解析 MD 技能文件 |
| `SkillExecutor` | `skills/executor.py` | 技能执行器（批量/分类执行，超时保护） |
| `SkillValidator` | `skills/validator.py` | 技能配置与执行参数校验 |
| `SkillManager` | `skills/manager.py` | 统一门面：加载/注册/执行/MD 管理/前端桥接 |
| `SkillDispatcher` | `ai/skill_dispatcher.py` | AI 工具化调度：Tool 描述生成 + 异步执行 |
| `TriggerEngine` | `skills/trigger_engine.py` | 触发评估引擎：关键词/意图/正则/上下文/时间/事件匹配 + 自动执行 |
| `MdSkill` | `skills/md_skill.py` | MD 技能适配器：将 Markdown 技能包装为可执行 BaseSkill |
| `SkillBridge` | `bridge/skill_bridge.py` | QWebChannel 桥接，前端技能管理接口 |

---

## 附：优化记录

基于代码审查实施的优化项（与流程图中的实现保持一致）：

| 阶段 | 优化项 | 涉及文件 |
|------|--------|---------|
| 第 1 轮 | ① 修复意图触发器"注册但永不触发"的 bug | `skills/trigger_engine.py` |
| 第 1 轮 | ② 统一 `SkillExecutor` / `SkillDispatcher` 默认超时（`DEFAULT_SKILL_TIMEOUT = 60s`） | `skills/base.py`、`skills/executor.py` |
| 第 1 轮 | ③ `SkillDispatcher` 委托单例 `SkillRegistry`，消除双注册中心 | `ai/skill_dispatcher.py` |
| 第 1 轮 | ④ `SkillRegistry.register()` 统一校验入口 | `skills/registry.py` |
| 第 1 轮 | ⑤ 自动触发按技能名去重 + 每次执行独立上下文 | `skills/trigger_engine.py` |
| 第 1 轮 | ⑥ MD 技能文件 mtime 缓存 | `skills/loader.py` |
| 第 2 轮 | ⑦ `execute_all` / `execute_by_category` 并发执行（`asyncio.gather`） | `skills/executor.py` |
| 第 2 轮 | ⑧ 技能生命周期钩子 `on_load / on_unload / on_enable / on_disable` + `set_enabled` / `toggle_enabled` | `skills/base.py`、`skills/registry.py` |
| 第 2 轮 | ⑨ 声明式触发器元数据 `BaseSkill.triggers`，加载时自动注册 | `skills/base.py`、`skills/trigger_engine.py`、`controller/app_controller.py` |
| 第 2 轮 | ⑩ 技能生命周期事件接入 EventBus（`skill:registered / unregistered / toggle`） | `skills/registry.py`、`controller/app_controller.py` |
| 第 3 轮 | ⑪ TriggerEngine 集成全部 6 类触发器（关键词/意图/正则/上下文/时间/事件），消除死代码 | `skills/trigger_engine.py` |
| 第 3 轮 | ⑫ `SkillDispatcher` 执行历史记录（`execution_history`，成功/失败/超时/未注册均记录） | `ai/skill_dispatcher.py` |
| 第 3 轮 | ⑬ MD 技能适配器 `MdSkill`（将 Markdown 技能包装为可执行 BaseSkill，统一技能模型） | `skills/md_skill.py`、`skills/loader.py` |
| 第 4 轮 | ⑭ 前端数据源统一：`get_skills_for_js` 聚合 Python+MD、`_sync_to_js` 指向 `appState`、SkillBridge 变异后统一刷新 | `skills/manager.py`、`bridge/skill_bridge.py` |
| 第 4 轮 | ⑮ MD 技能注册为 AI 工具（`enable_md_skill_tools` 开关，默认开启） | `controller/app_controller.py`、`skills/md_skill.py` |


---

*文档生成日期：2026-07-31 · 基于当前代码库实现绘制。若模块逻辑变更，请同步更新本图。*




