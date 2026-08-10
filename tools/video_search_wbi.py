# -*- coding: utf-8 -*-
"""
B站搜索 - wbi 签名 + 浏览器指纹（可复用模块）

调用 B站 wbi/search/type 接口搜索视频，绕过 412 风控（voucher 验证）。
供 video_search.py（Skill 脚本）和 video_bridge.py（插件 searchOnline）复用。

用法：
    from tools.video_search_wbi import bili_search
    videos = bili_search("幼儿园大班 数学", limit=10)
    # 返回 [{"title", "page_url", "play_url", "thumbnail", "duration", ...}]
"""
import json
import time
import urllib.request
import urllib.parse
import http.cookiejar
from functools import reduce

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]


def _get_mixin_key(orig: str) -> str:
    return reduce(lambda s, i: s + orig[i], MIXIN_KEY_ENC_TAB[:32], "")[:32]


def _get_wbi_keys(session_cj) -> tuple:
    """从 nav 接口获取 img_key/sub_key"""
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(session_cj))
    opener.addheaders = [
        ("User-Agent", UA),
        ("Referer", "https://www.bilibili.com"),
    ]
    raw = opener.open(
        "https://api.bilibili.com/x/web-interface/nav", timeout=15
    ).read().decode()
    data = json.loads(raw)["data"]
    img_url = data["wbi_img"]["img_url"]
    sub_url = data["wbi_img"]["sub_url"]
    img_key = img_url.rsplit("/", 1)[1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]
    return img_key, sub_key


def _enc_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    """给参数添加 wts 和 w_rid 签名"""
    import hashlib
    mixin_key = _get_mixin_key(img_key + sub_key)
    params["wts"] = int(time.time())
    params = dict(sorted(params.items()))
    query = urllib.parse.urlencode(params)
    query += mixin_key
    params["w_rid"] = hashlib.md5(query.encode()).hexdigest()
    return params


def _build_opener(cj):
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [
        ("User-Agent", UA),
        ("Referer", "https://www.bilibili.com"),
        ("Accept", "application/json, text/plain, */*"),
        ("Accept-Language", "zh-CN,zh;q=0.9"),
        ("sec-ch-ua",
         '"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"'),
        ("sec-ch-ua-mobile", "?0"),
        ("sec-ch-ua-platform", '"Windows"'),
        ("sec-fetch-dest", "empty"),
        ("sec-fetch-mode", "cors"),
        ("sec-fetch-site", "same-site"),
    ]
    return opener


def _strip_html(text: str) -> str:
    """去除搜索结果标题中的 <em class=...> 高亮标签"""
    import re
    text = re.sub(r"<[^>]+>", "", text) if text else text
    return text


def bili_search(keyword: str, limit: int = 10) -> list:
    """使用 wbi 签名搜索 B站视频，返回视频信息列表

    返回：
        [{
            "title", "page_url", "play_url", "thumbnail",
            "duration", "width", "height", "resolution", "fps",
            "source", "description"
        }, ...]
    失败返回 []。
    """
    limit = int(limit or 10)
    cj = http.cookiejar.CookieJar()
    opener = _build_opener(cj)

    # 1. 获取 buvid3/buvid4/b_nut 指纹
    try:
        spi = json.loads(
            opener.open(
                "https://api.bilibili.com/x/frontend/finger/spi", timeout=15
            ).read().decode()
        )["data"]
    except Exception as e:
        print(f"[BiliSearch] 获取指纹失败: {e}")
        return []
    exp = int(time.time()) + 63072000
    cj.set_cookie(http.cookiejar.Cookie(
        0, "buvid3", spi["b_3"], None, False, ".bilibili.com", True,
        False, "/", True, False, exp, False, None, None, {}))
    cj.set_cookie(http.cookiejar.Cookie(
        0, "buvid4", spi["b_4"], None, False, ".bilibili.com", True,
        False, "/", True, False, exp, False, None, None, {}))
    cj.set_cookie(http.cookiejar.Cookie(
        0, "b_nut", str(int(time.time())), None, False, ".bilibili.com", True,
        False, "/", True, False, exp, False, None, None, {}))

    # 2. 获取 wbi 密钥
    try:
        img_key, sub_key = _get_wbi_keys(cj)
    except Exception as e:
        print(f"[BiliSearch] 获取 wbi 密钥失败: {e}")
        return []

    # 3. 发起 wbi 签名搜索（多轮 voucher 凭证链兜底）
    params = {
        "search_type": "video",
        "keyword": keyword,
        "page": 1,
        "page_size": limit,
        "order": "totalrank",
        "platform": "pc",
        "web_location": "1550101",
    }

    def do_request(extra: dict) -> dict:
        p = dict(params)
        p.update(extra)
        p = _enc_wbi(p, img_key, sub_key)
        u = ("https://api.bilibili.com/x/web-interface/wbi/search/type?" +
             urllib.parse.urlencode(p))
        r = opener.open(u, timeout=20)
        return json.loads(r.read().decode("utf-8"))

    data = do_request({})
    d = data.get("data", {})

    # voucher 凭证链：最多 5 轮
    for i in range(5):
        if isinstance(d, dict) and d.get("result"):
            break
        v = d.get("v_voucher") if isinstance(d, dict) else None
        if not v:
            break
        time.sleep(1)
        data = do_request({"v_voucher": v})
        d = data.get("data", {})

    if not isinstance(d, dict) or not d.get("result"):
        print(f"[BiliSearch] 搜索失败: code={data.get('code')} msg={data.get('message')}")
        return []

    # 4. 解析结果
    videos = []
    for item in d["result"]:
        bvid = item.get("bvid", "")
        title = _strip_html(item.get("title", ""))
        page_url = f"https://www.bilibili.com/video/{bvid}" if bvid else item.get("arcurl", "")
        # 搜索结果不含 play_url/thumbnail/duration（需打开单视频解析）；
        # 先存基础信息，播放时由 video_bridge 用 yt-dlp 解析真实地址。
        a_duration = item.get("duration", "")
        duration_sec = 0
        # duration 形如 "12:34" 或 "1:02:34"
        try:
            parts = [int(x) for x in a_duration.split(":")]
            duration_sec = sum(parts[i] * (60 ** (len(parts) - 1 - i)) for i in range(len(parts)))
        except (ValueError, AttributeError):
            pass
        videos.append({
            "title": title,
            "page_url": page_url,
            "play_url": page_url,  # 占位，播放时用 yt-dlp 解析
            "thumbnail": item.get("pic", ""),
            "duration": duration_sec,
            "width": item.get("width"),
            "height": item.get("height"),
            "resolution": None,
            "fps": None,
            "source": "bilibili",
            "description": item.get("description", "")[:500],
        })
    return videos[:limit]


def bili_search_flat(keyword: str, limit: int = 10) -> list:
    """平铺接口（供 video_search.py 直接使用，返回字典列表）"""
    return bili_search(keyword, limit)