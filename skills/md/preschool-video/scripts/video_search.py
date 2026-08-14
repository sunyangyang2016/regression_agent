"""
video_search.py — 搜索学前教学视频并写入 video_library 表（独立进程）

通过多源搜索（B站 / 智慧教育平台 / 优酷，目标源失败自动回退 B站）获取视频元数据，
写入 MySQLite 数据库（VideoRepository），并通知 video_plugin 前端刷新（HTTP → PluginBus 事件）。

用法：
    python video_search.py --keyword "幼儿园大班 数学" [--source 自动] [--limit 10]
"""
import argparse
import sys

from common import project_root, send_command

# 确保项目根目录可导入（storage.repositories 等）
_ROOT = project_root()
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from video_catcher_runner import search_videos, guess_metadata


def search_combined(keyword: str, source: str, limit: int) -> list:
    """多源搜索：目标源失败由 search_videos 自动回退 B站"""
    videos = search_videos(keyword, limit=limit, source=source)
    for v in videos:
        guess_metadata(v, keyword, source)
    return videos[:limit]


def main():
    parser = argparse.ArgumentParser(description="搜索学前教学视频并写入视频库")
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument("--source", default="自动",
                        help="内容来源（自动/bilibili/智慧教育平台/优酷，目标源失败自动回退 B站）")
    parser.add_argument("--limit", type=int, default=10, help="返回数量（默认 10）")
    args = parser.parse_args()

    if not args.keyword:
        print("❌ 请提供搜索关键词")
        sys.exit(1)

    # 多源搜索（B站/智慧教育平台/优酷，失败自动回退 B站）
    videos = search_combined(args.keyword, args.source, args.limit)
    if not videos:
        print(f"❌ 未搜索到相关视频（关键词: {args.keyword}）")
        sys.exit(1)

    # 写入数据库
    from storage.repositories.video_repo import VideoRepository
    repo = VideoRepository()
    added = repo.add_many(videos)

    # 通知前端刷新（HTTP → PluginBus 事件）
    send_command({
        "type": "video_updated",
        "added": added,
        "total": len(videos),
        "keyword": args.keyword,
    })

    # 输出摘要
    print(f"✅ 搜索到 {len(videos)} 个视频，新增 {added} 个到视频库")
    for i, v in enumerate(videos[:5]):
        print(f"  {i+1}. {v['title']}")
        if v.get("id"):
            print(f"     ID: {v['id']} | {v.get('subject', '未知')} | {v.get('grade', '未知')}")


if __name__ == "__main__":
    main()
