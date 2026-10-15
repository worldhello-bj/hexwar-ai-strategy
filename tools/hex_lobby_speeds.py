# -*- coding: utf-8 -*-
"""列出大厅各房间的倍速（看有没有 10 倍速的练习房）。"""
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
if not H.USERNAME:
    sys.exit("请设置 HEXWAR_USER / HEXWAR_PASS")
H.S = requests.Session()
H.S.headers.update({"User-Agent": H.UA, "Accept-Language": "zh-CN,zh;q=0.9"})
uid = H.login()
host = urlsplit(H.HOST).hostname
c = requests.cookies.create_cookie(name="UserID", value=str(uid or ""), domain=host, path="/")
H.S.cookies.set_cookie(c)                      # ★ 读大厅需把 UserID 挂到 path=/
# 先退出推演室，否则大厅会把我们重定向回 PortID
try:
    H.S.get(H.HOST + "/WARGAMEAI/SetUp/SetUp_Transfer/Quit.asp", timeout=30)
except Exception as e:                                     # noqa: BLE001
    print("quit err %r" % (e,))
# 清掉 PortID / UserRoom，避免大厅再重定向回原房间
for ck in list(H.S.cookies):
    if ck.name in ("PortID", "UserRoom"):
        try:
            H.S.cookies.clear(ck.domain, ck.path, ck.name)
        except Exception:                                  # noqa: BLE001
            pass
r = H.S.get(H.HOST + "/WARGAMEAI/SetUp/", timeout=30,
            headers={"Referer": H.HOST + "/WARGAMEAI/"})
txt = H.decode(r.content)
print("lobby status=%s len=%d" % (r.status_code, len(r.content)))
print("cookies: %s" % [ck.name for ck in H.S.cookies])
print("uid=%r" % (uid,))
print("body: %r" % txt[:300])
print("-" * 70)
rows = list(re.finditer(r'id="Room-(\d+)"(.*?)(?=<div id="Room-|</fieldset>)', txt, re.S))
for m in rows:
    rid, body = m.group(1), m.group(2)
    title = re.search(r'class="title">\s*([^<]*)', body)
    speed = re.search(r'<span>\s*([0-9]+)\s*倍速\s*</span>', body)
    mode = re.search(r'class="stat">\s*<p>\s*([^<]*)', body)
    prac = re.search(r'练习\s*(\d+)', body)
    red = re.search(r'红方\s*(\d+)', body)
    blue = re.search(r'蓝方\s*(\d+)', body)
    green = re.search(r'绿方\s*(\d+)', body)
    print("Room-%-3s %-10s %-6s 红%s 蓝%s 绿%s 练习%s  [%s]"
          % (rid, (title.group(1).strip() if title else "?"),
             (speed.group(1) + "倍速" if speed else "?倍速"),
             red.group(1) if red else "-", blue.group(1) if blue else "-",
             green.group(1) if green else "-", prac.group(1) if prac else "-",
             mode.group(1).strip() if mode else ""))
print("-" * 70)
speeds = sorted({(m.group(0)) for m in re.finditer(r'[0-9]+倍速', txt)})
print("出现的倍速种类：%s" % speeds)
