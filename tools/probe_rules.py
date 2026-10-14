# -*- coding: utf-8 -*-
"""探测服务器上的裁决/想定/规则类文本接口，用于交叉验证重建的裁决表。"""
import os
import sys
import re
import json
import requests

BASE = "http://www.hexwar.cn/WARGAMEAI/"
B7 = "http://www.hexwar.cn/WARGAMEAI7/"
RAW = r"d:\兵推\snapshot\raw3"
os.makedirs(RAW, exist_ok=True)
LOG = r"d:\兵推\analysis\rule_probe.md"

USERNAME = os.environ.get("HEXWAR_USER", "")
PASSWORD = os.environ.get("HEXWAR_PASS", "")
if not USERNAME or not PASSWORD:
    sys.exit("请先设置环境变量 HEXWAR_USER / HEXWAR_PASS（不要写进代码）")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": B7 + "main.html",
})
s.get(BASE, timeout=30)
s.post(BASE + "login/", data={"UserName": USERNAME, "UserPassword": PASSWORD},
       timeout=30, allow_redirects=True)
s.headers["Referer"] = BASE + "SetUp/"
r0 = s.post(BASE + "SetUp/SetUpSave.asp", data={
    "UserID": "1243", "RoomID": "228", "GameName": USERNAME, "GameColor": "NONE",
    "PortID": "7", "submit": "", "UserRoom": "228"}, timeout=30, allow_redirects=False)
loc = r0.headers.get("Location", "")
if loc:
    s.get(requests.compat.urljoin(BASE + "SetUp/", loc), timeout=30, allow_redirects=True)
s.get(B7 + "Login/Login_Transfer/?PortID=7", timeout=30)
s.get(B7 + "main.html", timeout=30)
s.get(B7 + "User_Get.asp?userAgent=x", timeout=30)

lines = []
def w(x=""):
    lines.append(str(x))

def get(path, params=None, fname=None):
    try:
        rr = s.get(B7 + path, params=params, timeout=30)
    except Exception as e:
        return None, "ERR %r" % (e,), 0
    if fname:
        open(os.path.join(RAW, fname), "wb").write(rr.content)
    return rr.content.decode("gb18030", errors="replace"), "status=%s" % rr.status_code, len(rr.content)

w("# 规则/裁决类接口探测")
w()

targets = [
    ("loadInfo.asp", None, "loadInfo.html"),
    ("Caijue.asp", {"ID": "7527"}, "Caijue_7527.html"),
    ("Caijue.asp", {"ID": "1"}, "Caijue_1.html"),
    ("Caijue.asp", {"ID": "0"}, "Caijue_0.html"),
    ("Report_All.asp", {"RecordID": "", "GameOverStat": ""}, "Report_All.html"),
    ("ArmyList.asp", {"RoomID": "228"}, "ArmyList.html"),
    ("readme.txt", None, "readme.txt"),
    ("SystemArmy.asp", None, "SystemArmy.html"),
    ("MeterGrid.asp", {"Ditu": "199"}, "MeterGrid.html"),
    ("jmDataList.asp", {"ObjID": "Obj_100139"}, "jmDataList_139.html"),
    ("TgList.asp", {"ObjID": "Obj_100139", "ObjPos": "120037", "ObjColor": "RED"},
     "TgList_139.html"),
    ("com/ObjTask.asp", {"ObjID": "Obj_100139"}, "ObjTask_139.html"),
]
for path, params, fn in targets:
    txt, st, n = get(path, params, fn)
    w("## `%s` %s -> %s (%d 字节)" % (path, params or "", st, n))
    w()
    if txt:
        t = re.sub(r"\n{2,}", "\n", txt.strip())
        w("```")
        w(t[:2500])
        w("```")
    w()

# 装备表（从 ObjInfo 抓取全部单位的武器装备行）
w("## 各装备的 ObjInfo 装备行（用于校验参数）")
w()
r = s.get(B7 + "Obj_Get.asp", timeout=60)
open(os.path.join(RAW, "Obj_Get.html"), "wb").write(r.content)
html = r.content.decode("gb18030", errors="replace")
ids = re.findall(r'id="(Obj_\d+)"[^>]*name="([^"]*)"', html)
seen = {}
for oid, nm in ids:
    txt, st, n = get("ObjInfo.asp", {"ObjID": oid})
    if not txt:
        continue
    key = (nm, oid.split("_")[0])
    row = re.sub(r"<[^>]+>", " ", txt)
    row = re.sub(r"\s+", " ", row).strip()
    seen[nm] = row
    w("- **%s** (%s): %s" % (nm, oid, row[:400]))
    w()
    if len(seen) >= 20:
        break

json.dump(seen, open(os.path.join(RAW, "objinfo.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
open(LOG, "w", encoding="utf-8").write("\n".join(lines))
print("rule probe done; objinfo:", len(seen))
