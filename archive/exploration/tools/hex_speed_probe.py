# -*- coding: utf-8 -*-
"""探测：进房时能否用参数改推演倍速（User_Get[16] RoomSpeed）。"""
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

ROOM = 7
ROOM_DB = 222 + ROOM - 1
BASE7 = "%s/WARGAMEAI%d/" % (H.HOST, ROOM)


def room_speed(sess):
    r = sess.get(BASE7 + "User_Get.asp", params={"userAgent": "sp"}, timeout=30,
                 headers={"Referer": BASE7 + "main.html"})
    parts = H.decode(r.content).split("$")
    if len(parts) <= 17:
        return "? (len=%d) %r" % (len(parts), H.decode(r.content)[:60])
    return "%s  (AllTime=%s TireSec=%s KeepSec=%s)" % (
        parts[16], parts[19] if len(parts) > 19 else "?",
        parts[28] if len(parts) > 28 else "?", parts[29] if len(parts) > 29 else "?")


CANDS = [
    ("baseline", {}),
    ("RoomSpeed=10", {"RoomSpeed": "10"}),
    ("Speed=10", {"Speed": "10"}),
    ("RoomSpeed=10,SecDiff=10", {"RoomSpeed": "10", "SecDiff": "10"}),
    ("GameSpeed=10", {"GameSpeed": "10"}),
]
H.S.headers["Referer"] = H.BASE + "SetUp/"
for name, extra in CANDS:
    data = {"UserID": str(uid), "RoomID": str(ROOM_DB), "GameName": H.USERNAME,
            "GameColor": "NONE", "PortID": str(ROOM), "submit": "", "UserRoom": str(ROOM_DB)}
    data.update(extra)
    try:
        r = H.S.post(H.BASE + "SetUp/SetUpSave.asp", data=data, timeout=30, allow_redirects=False)
        loc = r.headers.get("Location", "")
        if loc:
            H.S.get(requests.compat.urljoin(H.BASE + "SetUp/", loc), timeout=30)
        print("%-26s post=%s loc=%s" % (name, r.status_code, (loc or "")[-40:]))
        print("    RoomSpeed -> %s" % room_speed(H.S))
    except Exception as e:                                 # noqa: BLE001
        print("%-26s ERR %r" % (name, e))
    # 退出房间，避免互相干扰
    try:
        H.S.get(H.HOST + "/WARGAMEAI7/SetUp/SetUp_Transfer/Quit.asp", timeout=20)
    except Exception:                                      # noqa: BLE001
        pass
