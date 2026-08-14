---
name: preschool-video
enabled: true
description: 学前班教学视频 - AI 负责搜索教学视频、控制播放、下载、查询播放进度
---

# Preschool Video Skill

当用户需要学前班/幼儿园教学视频时，按本技能执行。

## 解析用户意图

用户需求 → 提取三要素：
- **年级**：学前班 / 大班 / 中班 / 小班
- **科目**：数学 / 语文 / 英语 / 科学 / 艺术 / 健康
- **关键词**：`年级 + 科目 + 教学视频` 组合，如 `大班 数学 教学视频`

### ⚠️ 先问再搜（提升搜索准确度，必读）

**年级或科目有任一缺失/含糊时，必须先追问补齐再执行搜索，不要凭猜测直接搜**：

1. **判断缺什么，只问缺的**：
   - "搜学前班的教学视频" → 年级=学前班 已知，**科目缺失** → 只问科目
   - "找数学视频" → 科目=数学 已知，**年级缺失** → 只问年级
   - "搜教学视频" / "找点视频" → 都缺 → 科目、年级都问
   - "找大班数学启蒙视频" → 都有 → 不问，直接搜
2. **追问带选项清单**（用户可直接选）：
   - 科目：数学 / 语文 / 英语 / 科学 / 艺术 / 健康
   - 年级：学前班 / 大班 / 中班 / 小班
   - 例："好的，学前班。请问要哪个科目？数学 / 语文 / 英语 / 科学 / 艺术 / 健康？"
3. **用户确认后**，把 `年级 + 科目 + 教学视频` 拼成关键词再搜（保持顺序：年级在前、科目在后）：
   - `学前班 数学 教学视频` → `--keyword "学前班 数学 教学视频"`
   - `大班 语文 教学视频` → `--keyword "大班 语文 教学视频"`
   - 结构化关键词既提升搜索结果相关性，也让入库视频自动打上准确的 科目/年级 标签（guess_metadata）
4. **用户说"随便/都行/你定"** → 用默认 `学前班 数学 教学视频` 并说明："按 学前班+数学 搜索，如需其他科目/年级可告诉我"。不要反复追问。

### ⚠️ 立即执行协议（防停滞，必读）

1. **年级+科目一旦确定（或用户说"随便" → 用默认 `学前班 数学 教学视频`），必须立即执行搜索**——不要再追问、不要重复调用本技能、不要先输出大段解释。
2. 正确动作 = 直接调用 `execute_system_command` 执行，**必须传 `timeout: 300`**：
   ```json
   {"command": "python skills/md/preschool-video/scripts/video_search.py --keyword \"学前班 数学 教学视频\" --limit 50", "timeout": 300}
   ```
3. **一条用户消息只执行一次搜索**；搜索脚本已返回结果后，把摘要总结给用户即可，不得再次搜索。

## 搜索视频

用户说"帮我找xxx视频" → 执行：

```bash
python scripts/video_search.py --keyword "关键词" [--source 自动] [--limit 50]
```

示例（关键词 = 年级 + 科目 + 教学视频）：

```bash
python scripts/video_search.py --keyword "大班 数学 教学视频" --source bilibili --limit 50
python scripts/video_search.py --keyword "学前班 语文 教学视频" --source 智慧教育平台 --limit 50
python scripts/video_search.py --keyword "中班 英语 教学视频" --source 优酷 --limit 50
```

> 若结构化关键词结果少，可加「幼儿园」前缀重试，如 `幼儿园 大班 数学 教学视频`。

`--source` 可选：`自动`（默认）/ `bilibili` / `智慧教育平台` / `优酷`。
各源为**尽力而为**：B站稳定可靠；智慧教育平台、优酷受平台反爬限制，目标源抓不到数据时脚本会打 ⚠️ 日志并**自动回退 B站**，不会报错或无结果。

脚本执行后会返回搜索摘要，并将视频信息写入视频库（video_library 表）。
搜索结果会出现在视频中心，前端自动刷新。

### ⚠️ 搜索耗时与超时（必读）

搜索是**长耗时操作**（每个候选要解析元数据，数秒到数十秒；候选越多越久）：

1. **执行 `execute_system_command` 时必须传 `timeout: 300`**（该工具默认 60 秒超时会**中断搜索**，导致只返回很少的结果）。命令示例：
   ```json
   {"command": "python skills/md/preschool-video/scripts/video_search.py --keyword \"幼儿园大班 数学\" --limit 50", "timeout": 300}
   ```
2. `--limit` 是**候选数**（默认 50，多P视频自动展开整套入库），不是返回条数；单次搜索最多入库 100 条（受脚本 `MAX_SEARCH_TOTAL` 约束）。若用户要更多，可把 `--limit` 调大到 100。
3. 搜索量大时返回 30~50+ 条属正常；部分候选可能因平台反爬失败被跳过，脚本不会报错。

## 播放控制

用户说"播放xxx" → 执行：

```bash
python scripts/video_control.py --action play --video-id <ID>
```

| 用户指令 | 脚本命令 |
|---------|---------|
| "播放xxx" | `python scripts/video_control.py --action play --video-id <ID>` |
| "暂停" | `python scripts/video_control.py --action pause` |
| "停止" | `python scripts/video_control.py --action stop` |
| "快进 30 秒" | `python scripts/video_control.py --action seek --seconds 30` |
| "后退 10 秒" | `python scripts/video_control.py --action seek --seconds -10` |
| "音量调到 80%" | `python scripts/video_control.py --action volume --value 0.8` |
| "全屏" | `python scripts/video_control.py --action fullscreen` |
| "播放到哪了" | `python scripts/video_control.py --action get_state --video-id <ID>` |

## 下载视频

用户说"下载xxx" → **使用 video-catcher skill**（负责所有下载任务，支持 B站/YouTube/抖音等，自动嗅探/断点续传）：

```bash
# 使用 video-catcher 下载（URL 来自搜索结果）— 统一输出到项目共享目录
python ../video-catcher/scripts/video_catcher.py download "<视频URL>" --out-root user_config/media/videos

# 查看可下载清晰度
python ../video-catcher/scripts/video_catcher.py formats "<视频URL>" --out-root user_config/media/videos

# 指定画质下载（--quality-mode at-most=不超过该高度，默认；exact=精确匹配）
python ../video-catcher/scripts/video_catcher.py download "<视频URL>" --quality 720p --quality-mode at-most --out-root user_config/media/videos
```

下载输出目录：`user_config/media/videos/YYYY-MM-DD-主题/`。视频播放器按
`user_config/media/videos/<video_id>/` 固定子目录配对本地文件，若手动下载到别处，
可改用视频中心前端的下载按钮（它会自动用固定子目录保存）。


## 视频 ID 查找

用户要求播放/下载具体视频时，先执行搜索或查询视频库列表：

```bash
python scripts/video_search.py --keyword "关键词" --limit 50
```

脚本输出会包含每个视频的 ID，用该 ID 执行播放/下载命令。

## 内容源优先级

| 优先级 | 来源 | 可用性 |
|--------|------|--------|
| 1 | B站（bilibili） | ✅ 稳定，yt-dlp 搜索直连，默认源 |
| 2 | 国家智慧教育平台 | ⚠️ 尽力而为，受反爬限制常返回空，失败自动回退 B站 |
| 3 | 优酷 | ⚠️ 尽力而为，JS 渲染 SPA 难抓取，失败自动回退 B站 |

> 实际搜索以 B站为主（内容权威合规度以智慧教育平台为理想目标，但抓取不稳定）。

## 合规要求

- 仅搜索公开免费、有访问权限的视频
- 不绕过 DRM、付费墙或会员权限
- 下载仅用于个人学习和教学用途

## 可参考文档

- `references/sources.md` — 内容源详细说明