# -*- coding: utf-8 -*-
"""诊断 B站 wbi 搜索完整响应"""
import sys, json, urllib.request, urllib.parse, http.cookiejar, time, traceback
sys.path.insert(0, r"E:\workplace\regression-agent\regression_agent")
from tools.video_search_wbi import _build_opener, _get_wbi_keys, _enc_wbi

cj = http.cookiejar.CookieJar()
opener = _build_opener(cj)
try:
    spi = json.loads(opener.open("https://api.bilibili.com/x/frontend/finger/spi", timeout=15).read().decode())["data"]
    exp = int(time.time()) + 63072000
    for name, val in [("buvid3", spi["b_3"]), ("buvid4", spi["b_4"]), ("b_nut", str(int(time.time())))]:
        cj.set_cookie(http.cookiejar.Cookie(0, name, val, None, False, ".bilibili.com", True, False, "/", True, False, exp, False, None, None, {}))
    img_key, sub_key = _get_wbi_keys(cj)
    print("wbi keys ok:", img_key[:8], sub_key[:8])
    params = {
        "search_type": "video",
        "keyword": "幼儿园大班 教学视频",
        "page": 1,
        "page_size": 5,
        "order": "totalrank",
        "platform": "pc",
        "web_location": "1550101",
    }
    p = _enc_wbi(params, img_key, sub_key)
    u = "https://api.bilibili.com/x/web-interface/wbi/search/type?" + urllib.parse.urlencode(p)
    r = opener.open(u, timeout=20)
    data = json.loads(r.read().decode("utf-8"))
    print("code:", data.get("code"), "msg:", data.get("message"))
    d = data.get("data") or {}
    print("data keys:", list(d.keys())[:20])
    print("result len:", len(d.get("result") or []))
    print("v_voucher:", str(d.get("v_voucher"))[:200])
except Exception:
    traceback.print_exc()
