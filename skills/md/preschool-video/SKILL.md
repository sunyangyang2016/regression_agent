---
name: preschool-video
enabled: true
description: 学前班教学视频 - AI 负责搜索教学视频、控制播放、下载、查询播放进度
---

# Preschool Video Skill

当用户需要学前班/幼儿园教学视频时，按本技能执行。

## 解析用户意图

用户需求 → 提取：
- **科目**：数学 / 语文 / 英语 / 科学 / 艺术 / 健康
- **年级**：学前班 / 大班 / 中班 / 小班
- **关键词**：组合如 "幼儿园大班 数学 教学视频"

## 搜索视频

用户说"帮我找xxx视频" → 执行：

```bash
python scripts/video_search.py --keyword "关键词" [--source 自动] [--limit 10]
```

示例：

```bash
python scripts/video_search.py --keyword "幼儿园大班 数学 教学视频" --source bilibili --limit 10
```

脚本执行后会返回搜索摘要，并将视频信息写入视频库（video_library 表）。
搜索结果会出现在视频中心，前端自动刷新。

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
# 使用 video-catcher 下载（URL 来自搜索结果）
python ../video-catcher/scripts/video_catcher.py download "<视频URL>"

# 查看可下载清晰度
python ../video-catcher/scripts/video_catcher.py formats "<视频URL>"

# 指定画质下载
python ../video-catcher/scripts/video_catcher.py download "<视频URL>" --quality 720p --quality-mode exact
```


## 视频 ID 查找

用户要求播放/下载具体视频时，先执行搜索或查询视频库列表：

```bash
python scripts/video_search.py --keyword "关键词" --limit 10
```

脚本输出会包含每个视频的 ID，用该 ID 执行播放/下载命令。

## 内容源优先级

1. 国家智慧教育平台（basic.smartedu.cn）— 首选（内容权威合规）
2. B站（bilibili）
3. 其他公开免费源

## 合规要求

- 仅搜索公开免费、有访问权限的视频
- 不绕过 DRM、付费墙或会员权限
- 下载仅用于个人学习和教学用途

## 可参考文档

- `references/sources.md` — 内容源详细说明