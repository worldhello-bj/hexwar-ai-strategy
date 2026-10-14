# -*- coding: utf-8 -*-
"""登录进房后，取各单位的武器/指令面板，建立 data ID → 武器名称 映射。"""
import os
import sys
import re
import json
import requests
from bs4 import BeautifulSoup

_HOST = os.environ.get("HEXWAR_BASE", "http://www.hexwar.cn")
BASE = _HOST + "/WARGAMEAI/"
B7 = _HOST + "/WARGAMEAI7/"
RAW = r"d:\兵推\snapshot\raw2"
os.makedirs(RAW, exist_ok=True)
LOG = r"d:\兵推\analysis\weapon_probe.md"

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
    "UserID": "1243", "RoomID": "228", "GameName": USERNAME,
    "GameColor": "NONE", "PortID": "7", "submit": "", "UserRoom": "228",
}, timeout=30, allow_redirects=False)
loc = r0.headers.get("Location", "")
if loc:
    s.get(requests.compat.urljoin(BASE + "SetUp/", loc), timeout=30, allow_redirects=True)
s.get(B7 + "Login/Login_Transfer/?PortID=7", timeout=30)
s.get(B7 + "main.html", timeout=30)
s.get(B7 + "User_Get.asp?userAgent=x", timeout=30)

# 重新取一次单位，拿到最新 id 列表
r = s.get(B7 + "Obj_Get.asp", timeout=60)
obj_html = r.content.decode("gb18030", errors="replace")
open(os.path.join(RAW, "Obj_Get.asp.html"), "wb").write(r.content)

units = []
soup = BeautifulSoup(obj_html, "lxml")
for d in soup.find_all("div"):
    if str(d.get("id", "")).startswith("Obj_"):
        units.append({"id": d.get("id"), "name": d.get("name"), "data": d.get("data"),
                      "typeid": d.get("typeid"), "ico": d.get("ico"), "wz": d.get("wz")})

# 每种 (name,data) 取一个代表
seen = {}
for u in units:
    seen.setdefault((u["name"], u["data"]), u)

lines = []
def w(x=""):
    lines.append(str(x))

w("# 武器面板探测")
w()
w("- 单位总数 %d，装备种类 %d" % (len(units), len(seen)))
w()

def fetch(path, fname, params=None):
    url = B7 + path
    try:
        rr = s.get(url, params=params, timeout=30)
    except Exception as e:
        return None, "ERR %r" % (e,)
    open(os.path.join(RAW, fname), "wb").write(rr.content)
    return rr.content.decode("gb18030", errors="replace"), "ok %d" % len(rr.content)

for (nm, data), u in sorted(seen.items(), key=lambda kv: str(kv[0][1])):
    oid = u["id"]
    w("## %s  data=%s typeid=%s ico=%s wz=%s  (%s)" % (nm, data, u["typeid"], u["ico"], u["wz"], oid))
    w()
    for path, fname, params in (
        ("com/CommandObj.asp", "CommandObj_%s.html" % oid, {"ObjID": oid}),
        ("Obj_Weapon.asp", "ObjWeapon_%s.html" % oid, {"ObjID": oid, "value": "0"}),
        ("ObjInfo.asp", "ObjInfo_%s.html" % oid, {"ObjID": oid}),
        ("com/ObjTask.asp", "ObjTask_%s.html" % oid, {"ObjID": oid}),
    ):
        txt, st = fetch(path, fname, params)
        w("### `%s` -> %s" % (path + "?" + "&".join("%s=%s" % kv for kv in (params or {}).items()), st))
        w()
        if txt:
            w("```html")
            w(re.sub(r"\n{2,}", "\n", txt.strip())[:2500])
            w("```")
        w()

open(LOG, "w", encoding="utf-8").write("\n".join(lines))
print("probe done:", len(seen), "equipment kinds")
