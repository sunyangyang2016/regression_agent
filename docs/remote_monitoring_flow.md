# 远程设备系统监控流程

本文档描述系统如何通过 AI + 远程 MCP 服务器实现**远程设备**的性能监控，并将数据展示在本地监控面板上。

## 一、架构总览

```
┌────────────────────────────────────────────────────────────────────┐
│  AI 层（Skill: system-monitor 指挥，有 AI 参与）                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ 1. 发现远程 MCP 服务器（提供 get_all_stats 的 HTTP 远程）     │  │
│  │ 2. 每 3 秒调用远程 get_all_stats 采集远程设备数据              │  │
│  │ 3. AI 智能判断数据异常                                        │  │
│  │ 4. AI 输出结论/告警标记 {{CONCLUSION:}} / {{ALERT:}}          │  │
│  └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ 只写共享文件
┌──────────────────────────────▼─────────────────────────────────────┐
│  监控插件（纯展示，无 AI）                                          │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ getAll()   → 读快照 → 渲染远程数据 + "远程数据源"标签          │  │
│  │ getAlerts()→ 读提醒队列 → 异常横幅 + 历史列表                 │  │
│  │ 快照缺失/过期 → 显示"远程监控源不可用"                         │  │
│  └─────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

## 二、职责边界

| 层 | 职责 | AI 参与 | 说明 |
|----|------|--------|------|
| **AI 层** | 发现远程 MCP → 采集数据 → 智能判断 → 输出结论/告警标记 | ✅ 有 | 严格按 `system-monitor` SKILL.md 指令执行 |
| **监控插件** | 只读 AI 写入的快照/提醒，纯展示 | ❌ 无 | 绝不接触 MCP、绝不显示本机数据 |

## 三、数据流

```
用户："开始系统监控"
  ↓
AI 读取 SKILL.md 指令
  ↓
① 发现：AI 探测远程 MCP（transport=http）是否提供 get_all_stats
  ↓
② 采集（每 3 秒）：AI 调用远程 get_all_stats 获取远程设备数据
  ↓
③ 智能判断：AI 分析 CPU/内存/磁盘/网络/负载/进程 识别异常
  ↓
④ 展示：MCP 完整快照 → 插件 observer 缓存到内存 _SNAPSHOT_STORE
        面板 monitor.js（每 3 秒 getAll）读取 → 渲染远程数据
  ↓
⑤ 结论/告警：AI 输出 {{CONCLUSION: ...}} / {{ALERT: ...}} 标记
        插件 observer 解析 → ai_judgment（面板右侧）/ monitor_alerts.json（异常横幅）
④ 展示：MCP 完整快照 → 插件 observer 缓存到内存 _SNAPSHOT_STORE
        面板 monitor.js（每 3 秒 getAll）读取 → 渲染远程数据
  ↓
⑤ 结论/告警：AI 输出 {{CONCLUSION: ...}} / {{ALERT: ...}} 标记
        插件 observer 解析 → ai_judgment（面板右侧）/ monitor_alerts.json（异常横幅）
```

## 四、组件说明

### 1. Skill：`skills/md/system-monitor/`
| 文件 | 作用 |
|------|------|
| `SKILL.md` | AI 指令书：定义发现/采集/判断/结论/告警标记的完整动作 |
| `references/thresholds.md` | 异常判断参考阈值（AI 综合判断，非机械执行） |
| ~~`scripts/collect_stats.py`~~ | ❌ 已删除（不再通过脚本写快照，由插件 observer 处理内存快照） |
| ~~`scripts/push_alert.py`~~ | ❌ 已删除（异常提醒改由 AI 输出 `{{ALERT:}}` 标记，插件解析） |

### 2. 监控插件：`plugins/builtin/monitor_plugin/`
| 文件 | 作用 |
|------|------|
| `bridge/monitor_bridge.py` | 只读快照 + 提醒队列；仅返回 `data_source=remote` 数据 |
| `view/js/monitor.js` | 只渲染远程数据；不可用显示空状态；移除 mock 分支 |
| `view/js/index.html` | 数据源标签 + 不可用覆盖层 |
| `view/css/monitor.css` | 数据源标记 + 不可用空状态样式 |

### 3. 共享文件
| 文件 | 写入方 | 读取方 |
|------|--------|--------|
| `storage/remote_monitor_data.json` | AI（collect_stats.py） | MonitorBridge.getAll |
| `storage/monitor_alerts.json` | AI（push_alert.py） | MonitorBridge.getAlerts |

## 五、远程 MCP 工具契约

远程设备上部署的 MCP 服务器需提供：

| 工具名 | 用途 |
|--------|------|
| `get_all_stats` | 返回远程设备完整监控数据（见下方数据结构） |
| `get_alerts` | 返回远程设备异常提醒列表（可选） |

`get_all_stats` 返回结构（数据结构契约）：
```json
{
    "hostname": "remote-device",
    "cpu": {"percent": 32.4, "freq": "2.4 GHz", "cores": 8},
    "memory": {"total": 10737418240, "used": 7340032000, "percent": 68.2},
    "disk_io": {"read_mb": 18.2, "write_mb": 14.5, "total_mb": 32.7,
                "readable": "18.2 MB/s", "writable": "14.5 MB/s"},
    "network": {"rx_mbps": 842.1, "tx_mbps": 356.4, "rx": "105.3 MB/s",
                "tx": "44.6 MB/s", "conns": 1284},
    "load": [0.82, 0.63, 0.41],
    "uptime": "12d 4h",
    "processes": [{"pid": 9201, "name": "postgres", "cpu_percent": 8.7,
                   "mem_percent": 4.8, "rss": 341835776, "vsz": 1287651328, "threads": 8}],
    "disks": [{"mount": "/", "device": "/dev/sda1", "total": 37044092928,
               "used": 30534533120, "percent": 82.4}],
    "summary": {"cpu_total": 56.3, "mem_total": 45.2, "rss_total": 2147483648,
                "rss_total_str": "2.0G", "threads_total": 128}
}
```

## 六、快照文件结构（AI 写入）

```json
{
    "timestamp": "2026-08-05T01:35:00",
    "data_source": "remote",
    "remote_server": "remote-device-monitor",
    "cpu": {...}, "memory": {...}, "disk_io": {...},
    "network": {...}, "load": [...], "uptime": "...",
    "processes": [...], "disks": [...], "summary": {...},
    "alerts": [{"level": "warning", "title": "...", "message": "...", "metric": "disk"}]
}
```

## 七、异常提醒规则

AI 对采集数据**智能判断**异常（参考阈值但非机械执行）：

| 维度 | 参考阈值 | 提醒级别 |
|------|---------|---------|
| CPU 使用率 | > 85% 警告 / > 95% 严重 | warning / critical |
| 内存使用率 | > 85% 警告 / > 95% 严重 | warning / critical |
| 磁盘占用 | > 85% 警告 / > 95% 严重 | warning / critical |
| 负载 | load > 核心数 | warning |
| 网络连接 | 异常激增 | warning |
| 进程 | 异常高占用 | warning |

## 八、配置与使用

### 1. 配置远程 MCP 服务器（用户操作）
在 `user_config/user/mcp_servers.json` 添加（或通过 UI "MCP → 远程服务器"）：
```json
"remote-device-monitor": {
    "transport": "http",
    "url": "http://<远程设备IP>:<端口>/mcp",
    "enabled": true,
    "description": "远程设备系统监控"
}
```

### 2. 启动监控（用户对话触发）
用户说"开始系统监控" → AI 按 SKILL.md 执行完整监控循环。

### 3. 停止监控
用户说"停止监控" → AI 停止循环并汇报总结。

## 九、验证方式

| 场景 | 预期表现 |
|------|---------|
| 无快照文件 | 面板显示"远程监控源不可用"空状态 |
| AI 写入快照 | 面板渲染远程数据 + "远程数据源"标签 |
| 快照过期（>3秒未更新） | 面板显示"远程监控源不可用" |
| AI 写入异常提醒 | 面板显示异常横幅 + 历史列表 |