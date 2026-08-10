"""
video_search.py — 搜索学前教学视频并写入 video_library 表（独立进程）

通过 yt-dlp 搜索视频元数据，写入 MySQLite 数据库（VideoRepository），
并通过命令文件通知 video_plugin 前端刷新视频列表。

用法：
    python video_search.py --keyword "幼儿园大班 数学" [--source 自动] [--limit 10]
"""
import argparse
import json
import os
import subprocess
import sys

# 确保项目根目录可导入（scripts → preschool-video → md → skills → 根目录，共 5 级）
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 引入 wbi 搜索模块（B站风控破解，必须在设置 ROOT 之后导入）
try:
    from tools.video_search_wbi import bili_search as _wbi_search
    WBI_AVAILABLE = True
except Exception as e:
    print(f"⚠️ wbi 搜索模块不可用: {e}")
    WBI_AVAILABLE = False

# 命令文件路径（video_plugin 监听）
COMMANDS_FILE = os.path.join(ROOT, "storage", "video_commands.json")


# ==========================================
# 辅助函数
# ==========================================

def classify_source(source: str) -> str:
    """将来源名称规范化"""
    if not source:
        return "未知"
    if "智慧" in source:
        return "智慧教育平台"
    if "bili" in source.lower() or "b站" in source:
        return "bilibili"
    if "优酷" in source:
        return "优酷"
    return source


def guess_subject(keyword: str) -> str:
    """从关键词猜测科目"""
    subjects = {
        "数学": "数学", "算术": "数学", "数字": "数学", "计算": "数学",
        "语文": "语文", "拼音": "语文", "识字": "语文", "汉字": "语文",
        "英语": "英语", "字母": "英语", "abc": "英语",
        "科学": "科学", "实验": "科学", "自然": "科学",
        "艺术": "艺术", "画画": "艺术", "美术": "艺术", "音乐": "艺术",
        "健康": "健康", "体育": "健康", "安全": "健康",
    }
    kw_lower = keyword.lower()
    for k, v in subjects.items():
        if k in kw_lower:
            return v
    return None


def guess_grade(keyword: str) -> str:
    """从关键词猜测年级"""
    grades = {
        "学前班": "学前班", "幼小衔接": "学前班", "幼儿园": "学前班",
        "大班": "大班", "中班": "中班", "小班": "小班",
    }
    for k, v in grades.items():
        if k in keyword:
            return v
    return None


def _apply_guess(video: dict, keyword: str, source: str) -> dict:
    """为视频补全科目/年级/来源推断"""
    video["source"] = classify_source(source)
    if not video.get("subject"):
        video["subject"] = guess_subject(keyword)
    if not video.get("grade"):
        video["grade"] = guess_grade(keyword)
    return video


def search_ytdlp(keyword: str, source: str, limit: int) -> list:
    """使用 yt-dlp 搜索视频（兜底），返回视频信息列表"""
    videos = []
    try:
        cmd = [
            "yt-dlp",
            f"bilisearch{limit}:{keyword}",
            "--flat-playlist",
            "--dump-json",
            "--no-warnings",
            "--no-playlist",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            print(f"⚠️ yt-dlp 搜索失败: {result.stderr[:200]}")
            return []

        for line in result.stdout.strip().splitlines():
            try:
                info = json.loads(line)
                width = info.get("width")
                height = info.get("height")
                videos.append(_apply_guess({
                    "title": info.get("title", ""),
                    "page_url": info.get("webpage_url", ""),
                    "play_url": info.get("url", ""),
                    "thumbnail": info.get("thumbnail", ""),
                    "duration": info.get("duration") or 0,
                    "width": width,
                    "height": height,
                    "resolution": f"{width}x{height}" if width and height else None,
                    "fps": info.get("fps"),
                    "description": (info.get("description") or "")[:500],
                }, keyword, source))
            except (ValueError, KeyError):
                continue
    except subprocess.TimeoutExpired:
        print("⏱️ yt-dlp 搜索超时（60 秒）")
    except Exception as e:
        print(f"❌ 搜索异常: {e}")
    return videos[:limit]


def search_combined(keyword: str, source: str, limit: int) -> list:
    """优先 wbi 搜索（破解 B站风控），失败兜底 yt-dlp"""
    if WBI_AVAILABLE:
        try:
            wbi_videos = _wbi_search(keyword, limit=limit)
            if wbi_videos:
                # 补全科目/年级/来源
                for v in wbi_videos:
                    _apply_guess(v, keyword, source if source != "自动" else "bilibili")
                print(f"✅ wbi 搜索成功，返回 {len(wbi_videos)} 个视频")
                return wbi_videos
        except Exception as e:
            print(f"⚠️ wbi 搜索失败: {e}，尝试 yt-dlp 兜底")
    return search_ytdlp(keyword, source, limit)


def notify_frontend(payload: dict):
    """写入命令文件通知 video_plugin 刷新前端"""
    try:
        os.makedirs(os.path.dirname(COMMANDS_FILE), exist_ok=True)
        commands = []
        if os.path.exists(COMMANDS_FILE):
            try:
                with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
                    commands = json.load(f)
            except (ValueError, OSError):
                commands = []
        commands.append(payload)
        with open(COMMANDS_FILE, "w", encoding="utf-8") as f:
            json.dump(commands, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 通知前端失败: {e}")


# ==========================================
# 主入口
# ==========================================

def main():
    parser = argparse.ArgumentParser(description="搜索学前教学视频并写入视频库")
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument("--source", default="自动", help="内容来源（自动/智慧教育平台/bilibili/优酷）")
    parser.add_argument("--limit", type=int, default=10, help="返回数量（默认 10）")
    args = parser.parse_args()

    if not args.keyword:
        print("❌ 请提供搜索关键词")
        sys.exit(1)

    # 1. 搜索（优先 wbi 签名，兜底 yt-dlp）
    videos = search_combined(args.keyword, args.source, args.limit)
    if not videos:
        print(f"❌ 未搜索到相关视频（关键词: {args.keyword}）")
        sys.exit(1)

    # 2. 写入数据库
    from storage.repositories.video_repo import VideoRepository
    repo = VideoRepository()
    added = repo.add_many(videos)

    # 3. 通知前端刷新
    notify_frontend({
        "type": "video_updated",
        "added": added,
        "total": len(videos),
        "keyword": args.keyword,
    })

    # 4. 输出摘要
    print(f"✅ 搜索到 {len(videos)} 个视频，新增 {added} 个到视频库")
    for i, v in enumerate(videos[:5]):
        print(f"  {i+1}. {v['title']}")
        if v.get("id"):
            print(f"     ID: {v['id']} | {v.get('subject', '未知')} | {v.get('grade', '未知')}")


if __name__ == "__main__":
    main()