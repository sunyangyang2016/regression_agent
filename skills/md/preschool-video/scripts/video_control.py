"""
video_control.py — 控制视频播放器（独立进程）

通过 HTTP POST 命令到 video_plugin（主进程内 PluginBus 事件通道），
video_plugin 控制前端 HTML5 播放器。

用法：
    python video_control.py --action play --video-id <ID>
    python video_control.py --action pause
    python video_control.py --action stop
    python video_control.py --action seek --seconds 30
    python video_control.py --action seek --seconds -10
    python video_control.py --action volume --value 0.8
    python video_control.py --action fullscreen
    python video_control.py --action get_state --video-id <ID>
"""
import argparse
import sys

from common import project_root, send_command

# 确保项目根目录可导入（storage.repositories 等）
_ROOT = project_root()
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main():
    parser = argparse.ArgumentParser(description="控制视频播放器")
    parser.add_argument("--action", required=True,
                        choices=["play", "pause", "stop", "seek", "volume",
                                 "fullscreen", "get_state"],
                        help="控制动作")
    parser.add_argument("--video-id", help="视频 ID（play/get_state 时必填）")
    parser.add_argument("--seconds", type=int, help="快进/快退秒数（seek 时必填）")
    parser.add_argument("--value", type=float, help="音量 0-1（volume 时必填）")
    args = parser.parse_args()

    # ===== 构造 payload =====
    payload = {
        "type": "video_control",
        "action": args.action,
        "video_id": args.video_id,
        "seconds": args.seconds,
        "volume": args.value,
    }

    # ===== play：查询视频信息 =====
    if args.action == "play":
        if not args.video_id:
            print("❌ 播放需要提供 --video-id")
            sys.exit(1)
        from storage.repositories.video_repo import VideoRepository
        repo = VideoRepository()
        video = repo.get_by_id(args.video_id)
        if not video:
            print(f"❌ 视频不存在（ID: {args.video_id}）")
            sys.exit(1)
        payload["title"] = video.get("title")
        payload["url"] = video.get("localPath") or video.get("playUrl")
        payload["lastPosition"] = video.get("lastPosition") or 0
        if not payload["url"]:
            print("❌ 该视频没有可用的播放地址")
            sys.exit(1)
        print(f"▶️ 播放: {video.get('title')}")

    # ===== get_state：直接查库 =====
    elif args.action == "get_state":
        if not args.video_id:
            print("❌ 查询播放状态需要提供 --video-id")
            sys.exit(1)
        from storage.repositories.video_repo import VideoRepository
        repo = VideoRepository()
        state = repo.get_playback_state(args.video_id)
        if not state:
            print(f"❌ 视频不存在（ID: {args.video_id}）")
            sys.exit(1)
        # 格式化输出
        pos_m = state.get("position", 0) // 60
        pos_s = state.get("position", 0) % 60
        dur_m = state.get("duration", 0) // 60
        dur_s = state.get("duration", 0) % 60
        print("📊 播放状态：")
        print(f"  标题：{state.get('title', '')}")
        print(f"  播放位置：{pos_m:02d}:{pos_s:02d} / {dur_m:02d}:{dur_s:02d}")
        print(f"  播放次数：{state.get('play_count', 0)}")
        print(f"  最近播放：{state.get('last_played_at', '从未播放')}")
        sys.exit(0)

    # ===== seek：校验 seconds =====
    elif args.action == "seek":
        if args.seconds is None:
            print("❌ 快进/快退需要提供 --seconds（正=快进，负=快退）")
            sys.exit(1)
        print(f"⏩ 快进/快退: {args.seconds} 秒")

    # ===== volume：校验 value =====
    elif args.action == "volume":
        if args.value is None:
            print("❌ 音量需要提供 --value（0-1）")
            sys.exit(1)
        if not (0 <= args.value <= 1):
            print("❌ 音量必须在 0-1 之间")
            sys.exit(1)
        print(f"🔊 音量: {int(args.value * 100)}%")

    # ===== 其他动作 =====
    else:
        print(f"✅ 已发送指令: {args.action}")

    # 发送命令到 video_plugin（HTTP → PluginBus 事件）
    if send_command(payload):
        print("📨 指令已发送到视频播放器")
    else:
        print("❌ 指令未送达（请确认应用已启动、video_plugin 已加载）")
        sys.exit(1)


if __name__ == "__main__":
    main()
