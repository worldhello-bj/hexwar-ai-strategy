# -*- coding: utf-8 -*-
"""扫描各推演室的倍速（User_Get[16]），找出 10 倍速房间。"""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"d:\兵推")
import hex_transport_capture as H                 # noqa: E402

H.USERNAME = os.environ.get("HEXWAR_USER", "")
H.PASSWORD = os.environ.get("HEXWAR_PASS", "")
H.S = requests.Session()
H.S.headers.update({"User-Agent": H.UA, "Accept-Language": "zh-CN,zh;q=0.9"})
uid = H.login()
H.S.headers["Referer"] = H.BASE + "SetUp/"

ROOMS = list(range(1, int(os.environ.get("HEXWAR_MAXROOM", "16")) + 1))
found = []
for room in ROOMS:
    db = 222 + room - 1
    base7 = "%s/WARGAMEAI%d/" % (H.HOST, room)
    try:
        r = H.S.post(H.BASE + "SetUp/SetUpSave.asp", data={
            "UserID": str(uid), "RoomID": str(db), "GameName": H.USERNAME,
            "GameColor": "NONE", "PortID": str(room), "submit": "", "UserRoom": str(db),
        }, timeout=25, allow_redirects=False)
        loc = r.headers.get("Location", "")
        if loc:
            H.S.get(requests.compat.urljoin(H.BASE + "SetUp/", loc), timeout=25)
        ru = H.S.get(base7 + "User_Get.asp", params={"userAgent": "scan"}, timeout=25,
                     headers={"Referer": base7 + "main.html"})
        parts = H.decode(ru.content).split("$")
        if len(parts) > 20:
            title = parts[14]
            rs = parts[16]
            print("推演室%-3d RoomSpeed=%-3s AllTime=%-3s KeepSec=%-3s TireSec=%-3s  %s"
                  % (room, rs, parts[19], parts[29] if len(parts) > 29 else "?",
                     parts[28] if len(parts) > 28 else "?", title))
            if rs not in ("3", ""):
                found.append((room, rs))
        else:
            print("推演室%-3d 读不到会话（len=%d）%r" % (room, len(parts), H.decode(ru.content)[:40]))
    except Exception as e:                                 # noqa: BLE001
        print("推演室%-3d ERR %r" % (room, e))
    try:
        H.S.get(H.HOST + "/WARGAMEAI7/SetUp/SetUp_Transfer/Quit.asp", timeout=20)
    except Exception:                                      # noqa: BLE001
        pass

print("-" * 60)
print("非 3 倍速的房间：%s" % (found or "无"))
