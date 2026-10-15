# -*- coding: utf-8 -*-
"""探测：登录后从哪个入口能读到大厅房间列表（绕过 PortID 重定向）。"""
import os
import re
import sys
from urllib.parse import urlsplit

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"d:\兵推")
import hex_transport_capture as H                 # noqa: E402

H.USERNAME = os.environ.get("HEXWAR_USER", "")
H.PASSWORD = os.environ.get("HEXWAR_PASS", "")
H.S = requests.Session()
H.S.headers.update({"User-Agent": H.UA, "Accept-Language": "zh-CN,zh;q=0.9"})
uid = H.login()
host = urlsplit(H.HOST).hostname
H.S.cookies.set_cookie(requests.cookies.create_cookie(
    name="UserID", value=str(uid or ""), domain=host, path="/"))

QUITS = [
    H.HOST + "/WARGAMEAI/SetUp/SetUp_Transfer/Quit.asp",
    H.HOST + "/WARGAMEAI7/Quit.asp",
    H.HOST + "/WARGAMEAI7/SetUp/SetUp_Transfer/Quit.asp",
    H.HOST + "/WARGAMEAI7/SetUp/SetUp_Transfer/Quit.asp?PortID=",
]
for q in QUITS:
    try:
        rr = H.S.get(q, timeout=20, allow_redirects=False)
        print("QUIT %-70s -> %s len=%d" % (q, rr.status_code, len(rr.content)))
    except Exception as e:                                 # noqa: BLE001
        print("QUIT %-70s ERR %r" % (q, e))

URLS = [
    H.HOST + "/WARGAMEAI/",
    H.HOST + "/WARGAMEAI/SetUp/",
    H.HOST + "/WARGAMEAI/SetUp/SetUp_Transfer/",
    H.HOST + "/WARGAMEAI/login/Login_Transfer/",
    H.HOST + "/WARGAMEAI/SetUp/SetUp_List.asp",
]
for u in URLS:
    try:
        rr = H.S.get(u, timeout=20)
    except Exception as e:                                 # noqa: BLE001
        print("GET  %-70s ERR %r" % (u, e))
        continue
    t = H.decode(rr.content)
    speeds = sorted(set(re.findall(r'[0-9]+倍速', t)))
    nroom = len(re.findall(r'id="Room-', t))
    print("GET  %-70s -> %s len=%-6d rooms=%-3d speeds=%s  head=%r"
          % (u, rr.status_code, len(rr.content), nroom, speeds, t[:80].replace("\n", " ")))
