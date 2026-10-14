# -*- coding: utf-8 -*-
"""补充缺失贴图 + 生成离线态势查看器（纯静态，可 file:// 直接打开）。"""
import os
import json
import re
import shutil
import requests

BASE7 = "http://www.hexwar.cn/WARGAMEAI7/"
SNAP = r"d:\兵推\snapshot"
ASSETS = os.path.join(SNAP, "assets")
PARSED = os.path.join(SNAP, "parsed")
RAW = os.path.join(SNAP, "raw")
OUT = r"d:\兵推\offline"
os.makedirs(OUT, exist_ok=True)
LOG = r"d:\兵推\analysis\build.md"

rep = []
def w(x=""):
    rep.append(x)

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": BASE7 + "main.html",
})

# ---------- 1. 补充贴图 ----------
w("# 离线包构建")
w()
w("## 1. 补充缺失贴图")
w()
extra = ["Hex1/52.png", "Hex/25.png", "Hex/cond6.png", "Hex/cond7.png",
         "Hex/cond1.png", "Hex/cond2.png", "Hex/cond3.png", "Hex/cond4.png",
         "Hex/cond5.png", "Hex/cond8.png", "Hex/cond9.png", "Hex/cond16.png"]
w("| 文件 | 结果 |")
w("|---|---|")
for rel in extra:
    p = os.path.join(ASSETS, rel.replace("/", os.sep))
    if os.path.exists(p) and os.path.getsize(p) > 0:
        w("| `%s` | cached |" % rel)
        continue
    try:
        r = s.get(BASE7 + rel, timeout=30)
    except Exception as e:
        w("| `%s` | ERR %r |" % (rel, e))
        continue
    if r.status_code == 200 and r.content:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(r.content)
        w("| `%s` | ok %d |" % (rel, len(r.content)))
    else:
        w("| `%s` | status=%s |" % (rel, r.status_code))
w()

# ---------- 2. 数据 ----------
hexes = json.load(open(os.path.join(PARSED, "map_hexes.json"), encoding="utf-8"))
units = json.load(open(os.path.join(PARSED, "units.json"), encoding="utf-8"))
cities = json.load(open(os.path.join(PARSED, "cities.json"), encoding="utf-8"))

# ObjAjax 动态状态（宽松解析）
ajax_state = {}
try:
    t = open(os.path.join(RAW, "ObjAjax.asp.json"), "rb").read()
    for enc in ("utf-8", "gb18030"):
        try:
            t = t.decode(enc)
            break
        except Exception:
            pass
    else:
        t = t.decode("utf-8", errors="replace")
    t = t.strip().rstrip(",")
    if not t.startswith("{"):
        t = "{" + t + "}"
    t = re.sub(r",(\s*})", r"\1", t)
    ajax_state = json.loads(t)
except Exception as e:
    w("- ObjAjax 解析失败: %r" % (e,))
w("- 动态状态条目: %d" % len(ajax_state))
w()

# User_Get 配置
cfg = {}
try:
    raw = open(os.path.join(RAW, "User_Get.asp.txt"), "rb").read().decode("utf-8", errors="replace")
    parts = raw.split("$")
    keys = ["CenterID", "GridDiff", "Moban", "StartTime", "UserID", "RoomID", "HexCols",
            "HexRows", "OnTime", "ProMode", "GameColor", "WarDateTime", "GridMeter",
            "RecordID", "RoomTitle", "UserStart", "RoomSpeed", "FirstColor", "Ditu",
            "AllTime", "RoomSecond", "TeamName", "MapWidth", "MapHeight", "GmapType",
            "EleLow", "EleDiv", "EleCss", "TireSec", "KeepSec", "GmapZoom", "WmapZoom",
            "HexWidth", "ServerTime", "Time1", "Client", "StageArr"]
    for i, k in enumerate(keys):
        cfg[k] = parts[i] if i < len(parts) else ""
except Exception as e:
    w("- User_Get 解析失败: %r" % (e,))

HexCols = int(cfg.get("HexCols") or 100)
HexRows = int(cfg.get("HexRows") or 18)
CenterID = int(cfg.get("CenterID") or 160066)
HexWidth = int(cfg.get("HexWidth") or 52)
HexHalfWidth = HexWidth / 2
HexRowHeight = round(1.73 * HexWidth)
HexHalfRowHeight = round(HexRowHeight / 2)
GridMeter = int(cfg.get("GridMeter") or 200)

# 复刻 GetCenterID
CenterDiff = 10000 * (HexRows // 2) + (HexCols // 2) - 10000
if CenterDiff % 2 == 0:
    CenterDiff += 1
CenterDiffX = HexCols // 2
if CenterDiffX % 2 == 0:
    CenterDiffX += 1
a = CenterID
cid = CenterDiff if a < CenterDiff else a
b = 10000 * (CenterDiff // 10000)
c = a - CenterDiff
c = c - 10000 * (c // 10000)
if c < 0:
    cid = CenterDiff + (10000 + c)
    if 10000 <= cid - b:
        cid = CenterDiff
if 5000 < c:
    cid = 10000 * (a // 10000) + CenterDiffX
if cid % 2:
    cid += 1
FirstID = cid - CenterDiff
if FirstID % 2:
    FirstID -= 1
LastID = (cid + CenterDiff - 1) + 10000

# 复刻 LoadCurrentCity 布局
layout = {}
GroundID = FirstID
pos1 = pos2 = 0
ii = 0
total = HexCols * HexRows
for n in range(total):
    layout[str(GroundID)] = (pos1, pos2)
    pos1 += HexHalfWidth
    GroundID += 1
    ii += 1
    pos2 += -HexHalfRowHeight if GroundID % 2 == 0 else HexHalfRowHeight
    if ii % HexCols == 0:
        band = ii // HexCols
        pos1 = 0
        pos2 = HexRowHeight * band
        GroundID = FirstID + 10000 * band

def hexid(mid):
    b = mid // 10000
    c = mid % 2
    d = "%02d" % ((2 * b) if c == 0 else (2 * b + 1))
    a2 = round((mid - 10000 * b) / 2)
    if c == 1:
        a2 -= 1
    return d + "%02d" % a2

# 只保留布局内的格子
grid = {}
for k, h in hexes.items():
    kk = str(int(k))
    if kk in layout:
        grid[kk] = h
w("## 2. 布局")
w()
w("- 网格 %d×%d = %d 格；布局覆盖地图 id %d..%d" % (HexCols, HexRows, total, FirstID, FirstID + 10000 * (HexRows - 1) + HexCols - 1))
w("- 布局内命中格子: %d / 服务端返回 %d" % (len(grid), len(hexes)))
xs = [v[0] for v in layout.values()]
ys = [v[1] for v in layout.values()]
w("- 画布范围: x %.0f..%.0f  y %.0f..%.0f  (HexWidth=%d, HexRowHeight=%d)" % (
    min(xs), max(xs), min(ys), max(ys), HexWidth, HexRowHeight))
w()

# 单位：把 pos 映射成 x,y
placed = 0
missing = 0
for u in units:
    key = str(u.get("pos"))
    if key in layout:
        u["_x"], u["_y"] = layout[key]
        placed += 1
    else:
        u["_x"] = u["_y"] = None
        missing += 1
w("- 单位落在网格内: %d，落在网格外: %d" % (placed, missing))
w()
for u in units:
    if u["_x"] is None:
        w("  - `%s` %s pos=%s" % (u["id"], u.get("name"), u.get("pos")))
w()

for c in cities:
    key = str(c.get("pos"))
    if key in layout:
        c["_x"], c["_y"] = layout[key]
    else:
        c["_x"] = c["_y"] = None
w("- 城市落在网格内: %d / %d" % (sum(1 for c in cities if c["_x"] is not None), len(cities)))
w()

# ---------- 3. 生成 data.js ----------
data = {
    "config": cfg,
    "geom": {
        "HexCols": HexCols, "HexRows": HexRows, "HexWidth": HexWidth,
        "HexRowHeight": HexRowHeight, "HexHalfWidth": HexHalfWidth,
        "HexHalfRowHeight": HexHalfRowHeight, "FirstID": FirstID, "LastID": LastID,
        "CenterID": CenterID, "GridMeter": GridMeter,
        "RoomHex": "Hex" + (cfg.get("FirstColor", "").split("|")[2] if cfg.get("FirstColor") else ""),
    },
    "layout": {k: list(v) for k, v in layout.items()},
    "hexes": grid,
    "units": units,
    "cities": cities,
    "ajaxState": ajax_state,
    "hexidSample": {k: hexid(int(k)) for k in list(layout)[:5]},
}

with open(os.path.join(OUT, "data.js"), "w", encoding="utf-8") as f:
    f.write("// 自动生成：Hexwar 离线练习数据快照\n")
    f.write("// 来源：http://www.hexwar.cn/WARGAMEAI7/  (推演室7 / 想定 7527)\n")
    f.write("window.HEXWAR_DATA = ")
    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";\n")
w("## 3. 生成 data.js")
w()
w("- 大小: %.1f KB" % (os.path.getsize(os.path.join(OUT, "data.js")) / 1024))
w()

# ---------- 4. 拷贝资源 ----------
dst_assets = os.path.join(OUT, "assets")
if os.path.exists(dst_assets):
    shutil.rmtree(dst_assets)
shutil.copytree(ASSETS, dst_assets)
n = sum(len(fs) for _, _, fs in os.walk(dst_assets))
w("## 4. 资源拷贝")
w()
w("- 已拷贝 %d 个资源文件到 `offline/assets/`" % n)
w()

with open(LOG, "w", encoding="utf-8") as f:
    f.write("\n".join(rep))
print("build data ok: first=%d last=%d grid=%d units=%d" % (FirstID, LastID, len(grid), len(units)))
