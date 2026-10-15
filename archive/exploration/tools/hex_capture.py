# -*- coding: utf-8 -*-
"""登录 -> 以导演身份进入推演室 -> 抓取完整对局数据（地图/单位/城市/会话）。

说明：只做「进入推演室 + 读取数据」，不下达任何作战指令，不修改服务器状态。
"""
import os
import sys
import re
import json
import math
import requests
from urllib.parse import urlsplit

# 主机可用 HEXWAR_BASE 覆盖，以便指向比赛服（默认练习服）
_HOST = os.environ.get("HEXWAR_BASE", "http://www.hexwar.cn")
if urlsplit(_HOST).scheme.lower() != "https":
    sys.exit("Refusing to send credentials over HTTP. Configure a verified HTTPS endpoint; if unavailable, do not use this login script.")
BASE = _HOST + "/WARGAMEAI/"
BASE7 = _HOST + "/WARGAMEAI7/"
SNAP = r"d:\兵推\snapshot"
RAW = os.path.join(SNAP, "raw")
os.makedirs(RAW, exist_ok=True)
LOG = r"d:\兵推\analysis\capture.md"

USERNAME = os.environ.get("HEXWAR_USER", "")
PASSWORD = os.environ.get("HEXWAR_PASS", "")
if not USERNAME or not PASSWORD:
    sys.exit("请先设置环境变量 HEXWAR_USER / HEXWAR_PASS（不要写进代码）")
ROOM_DB_ID = 228      # 推演室7 的内部 RoomID
PORT_ID = 7           # 推演室序号
COLOR = "NONE"        # 导演（官方单人控双方的练习模式）

log = []
def w(x=""):
    log.append(x)

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
})

def save(name, r):
    p = os.path.join(RAW, name)
    with open(p, "wb") as f:
        f.write(r.content)
    return p, len(r.content)

def text(r):
    for enc in ("utf-8", "gb18030"):
        try:
            return r.content.decode(enc)
        except Exception:
            continue
    return r.content.decode("utf-8", errors="replace")

w("# 对局数据抓取")
w()

# ---------- 1. 登录 ----------
s.get(BASE, timeout=30)
login_response = s.post(BASE + "login/", data={"UserName": USERNAME, "UserPassword": PASSWORD},
       timeout=30, allow_redirects=False)
if 300 <= login_response.status_code < 400:
    sys.exit("Login redirect stopped. Verify the destination manually before continuing.")
w("## 1. 登录")
w("- cookies: %s" % "[REDACTED]")
w()

# ---------- 2. 进入推演室 ----------
s.headers["Referer"] = BASE + "SetUp/"
r = s.post(BASE + "SetUp/SetUpSave.asp", data={
    "UserID": "1243", "RoomID": str(ROOM_DB_ID), "GameName": USERNAME,
    "GameColor": COLOR, "PortID": str(PORT_ID), "submit": "", "UserRoom": str(ROOM_DB_ID),
}, timeout=30, allow_redirects=False)
w("## 2. 进入推演室")
w("- POST SetUp/SetUpSave.asp -> status=%s  Location=%s" % (r.status_code, r.headers.get("Location")))
loc = r.headers.get("Location", "")
w("- cookies: %s" % "[REDACTED]")
w()
if loc:
    r2 = s.get(requests.compat.urljoin(BASE + "SetUp/", loc), timeout=30, allow_redirects=True)
    w("- 跟随 Location -> status=%s  url=%s  len=%d" % (r2.status_code, r2.url, len(r2.content)))
    save("redirect_follow.html", r2)
    w()

# 若未直接落到 WARGAMEAI7，试一次 Login_Transfer
w("## 3. 会话与客户端资源")
w()

def get7(name, path, note=""):
    url = BASE7 + path
    try:
        rr = s.get(url, timeout=60, headers={"Referer": BASE7 + "main.html"})
    except Exception as e:
        w("- %s 失败: %r" % (path, e))
        return None
    p, n = save(name, rr)
    w("- `%s` -> status=%s  %d 字节  -> %s  %s" % (path, rr.status_code, n, name, note))
    return rr

# Login_Transfer（客户端入口）
get7("login_transfer.html", "Login/Login_Transfer/?PortID=%d" % PORT_ID)
get7("main.html", "main.html")
get7("SetUp.js", "SetUp.js")
get7("war.min.js", "war.min.js")

# ---------- 4. 会话数据 ----------
ua = requests.utils.quote(s.headers["User-Agent"], safe="")
ru = get7("User_Get.asp.txt", "User_Get.asp?userAgent=" + ua)
user_fields = None
if ru is not None and ru.status_code == 200:
    raw = text(ru)
    w()
    w("### User_Get.asp 原始响应")
    w()
    w("```")
    w(raw)
    w("```")
    w()
    parts = raw.split("$")
    names = ["CenterID", "GridDiff", "Moban", "StartTime", "UserID", "RoomID", "HexCols",
             "HexRows", "OnTime", "ProMode", "GameColor", "WarDateTime", "GridMeter",
             "RecordID", "RoomTitle", "UserStart", "RoomSpeed", "FirstColor", "Ditu",
             "AllTime(分)", "RoomSecond", "TeamName", "MapWidth", "MapHeight", "GmapType",
             "EleLow", "EleDiv", "EleCss", "TireSec", "KeepSec"]
    w("### User_Get 字段解析")
    w()
    w("| # | 字段 | 值 |")
    w("|---|---|---|")
    for i, nm in enumerate(names):
        w("| %d | %s | `%s` |" % (i, nm, parts[i] if i < len(parts) else ""))
    if len(parts) > 30:
        for i in range(30, min(len(parts), 80)):
            v = parts[i]
            if len(v) > 80:
                v = v[:80] + "…(%d)" % len(v)
            w("| %d | a[%d] | `%s` |" % (i, i, v))
    w()
    user_fields = parts

    # 计算 FirstID / LastID（复刻客户端 GetCenterID）
    HexCols = int(parts[6]); HexRows = int(parts[7]); CenterID0 = int(parts[0])
    CenterDiff = 10000 * (HexRows // 2) + (HexCols // 2) - 10000
    if CenterDiff % 2 == 0:
        CenterDiff += 1
    CenterDiffX = HexCols // 2
    if CenterDiffX % 2 == 0:
        CenterDiffX += 1
    a = CenterID0
    CenterID = CenterDiff if a < CenterDiff else a
    b = 10000 * (CenterDiff // 10000)
    c = a - CenterDiff
    d = c // 10000
    c = c - 10000 * d
    if c < 0:
        CenterID = CenterDiff + (10000 + c)
        if 10000 <= CenterID - b:
            CenterID = CenterDiff
    if 5000 < c:
        CenterID = 10000 * (a // 10000) + CenterDiffX
    if CenterID % 2 != 0:
        CenterID += 1
    FirstID = CenterID - CenterDiff
    if FirstID % 2 != 0:
        FirstID -= 1
    LastID = (CenterID + CenterDiff - 1) + 10000
    w("### 地图窗口计算")
    w()
    w("- HexCols=%d HexRows=%d CenterID=%d" % (HexCols, HexRows, CenterID0))
    w("- CenterDiff=%d CenterDiffX=%d" % (CenterDiff, CenterDiffX))
    w("- **FirstID=%d  LastID=%d**  （格数 %d）" % (FirstID, LastID, (LastID - FirstID)))
    w()
else:
    FirstID, LastID = 80014, 250116
    w("- 未能取得 User_Get，使用 HAR 观测值 FirstID=%d LastID=%d" % (FirstID, LastID))
    w()

# ---------- 5. 地图与单位数据 ----------
w("## 4. 地图与单位数据")
w()
get7("offlinemapdata.asp.txt", "offlinemapdata.asp")
get7("Map_Get.asp.json", "Map_Get.asp?FirstID=%d&LastID=%d" % (FirstID, LastID))
get7("Map_Get_Under.asp.json", "Map_Get_Under.asp?FirstID=%d&LastID=%d" % (FirstID, LastID))
get7("City_Get.asp.html", "City_Get.asp")
get7("Obj_Get.asp.html", "Obj_Get.asp")
get7("AIUser.asp.txt", "AIUser.asp")
get7("UserTeamShow.asp.txt", "UserTeamShow.asp")
get7("RoomStat.asp.txt", "RoomStat.asp?RoomID=%d" % ROOM_DB_ID)
get7("ObjAjax.asp.json", "ObjAjax.asp")
w()

with open(LOG, "w", encoding="utf-8") as f:
    f.write("\n".join(log))
print("capture done")
