# -*- coding: utf-8 -*-
"""抓取单条战斗的裁决明细页 Caijue.asp?ID=<id>。

战报（Report_Attack.asp）里形如 `<a href="javascript:Caijue(128241)">…(无效)</a>`，
其中的数字就是裁决 ID。本工具登录后逐条抓取并保存原文。

用法：
    $env:HEXWAR_USER=...; $env:HEXWAR_PASS=...; $env:HEXWAR_ALLOW_HTTP=1
    py -3.13 tools/hex_fetch_caijue.py 128241 128242
"""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"d:\兵推")
import hex_transport_capture as H                 # noqa: E402

OUT = r"d:\兵推\7527_transport_capture\caijue"
os.makedirs(OUT, exist_ok=True)

H.USERNAME = os.environ.get("HEXWAR_USER", "")
H.PASSWORD = os.environ.get("HEXWAR_PASS", "")
if not H.USERNAME:
    sys.exit("请设置 HEXWAR_USER / HEXWAR_PASS")
H.S = requests.Session()
H.S.headers.update({"User-Agent": H.UA, "Accept-Language": "zh-CN,zh;q=0.9"})
H.login()

base7 = H.HOST + "/WARGAMEAI7/"
ids = sys.argv[1:]
if not ids:
    sys.exit("用法：hex_fetch_caijue.py <ID> [ID...]")

for cid in ids:
    r = H.S.get(base7 + "Caijue.asp", params={"ID": cid}, timeout=30,
                headers={"Referer": base7 + "main.html"})
    # ★ Caijue.asp 是纯 GB2312（不要用 utf-8 优先的 H.decode，会半乱码）
    txt = r.content.decode("gb18030", errors="replace")
    p = os.path.join(OUT, "caijue_%s.html" % cid)
    open(p, "wb").write(r.content)
    print("=" * 90)
    print("ID=%s  status=%s  bytes=%d  -> %s" % (cid, r.status_code, len(r.content), p))
    print(txt)
