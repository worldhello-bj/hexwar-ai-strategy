# -*- coding: utf-8 -*-
"""下载离线渲染所需的全部资源（地形贴图 / 单位图标 / 城市旗帜）。"""
import os
import json
import time
import requests

BASE7 = "http://www.hexwar.cn/WARGAMEAI7/"
CDN = "http://cdn1.hexwar.cn/"
SNAP = r"d:\兵推\snapshot"
ASSETS = os.path.join(SNAP, "assets")
PARSED = os.path.join(SNAP, "parsed")
REP = r"d:\兵推\analysis\assets.md"

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": BASE7 + "main.html",
})

log = []
def w(x=""):
    log.append(x)

def dl(url, relpath):
    p = os.path.join(ASSETS, relpath.replace("/", os.sep))
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return "cached", os.path.getsize(p)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    try:
        r = s.get(url, timeout=30)
    except Exception as e:
        return "ERR %r" % (e,), 0
    if r.status_code != 200 or not r.content:
        return "status=%s" % r.status_code, 0
    with open(p, "wb") as f:
        f.write(r.content)
    return "ok", len(r.content)

hexes = json.load(open(os.path.join(PARSED, "map_hexes.json"), encoding="utf-8"))
units = json.load(open(os.path.join(PARSED, "units.json"), encoding="utf-8"))
cities = json.load(open(os.path.join(PARSED, "cities.json"), encoding="utf-8"))

w("# 离线资源下载")
w()

# ---- 1. 地形贴图 ----
w("## 1. 地形贴图 Hex1/")
w()
tasks = []
for h in hexes.values():
    if h["hex"] > 0:
        tasks.append(("Hex1/%d.png" % h["hex"], BASE7 + "Hex1/%d.png" % h["hex"]))
    c = h["cond"]
    if c > 0:
        name = "%d.png" % c if c > 25 else "cond%d.png" % c
        tasks.append(("Hex1/" + name, BASE7 + "Hex1/" + name))
uniq = {}
for rel, url in tasks:
    uniq[rel] = url
w("- 需要 %d 个贴图" % len(uniq))
w()
w("| 文件 | 结果 | 字节 |")
w("|---|---|---|")
ok = fail = 0
for rel, url in sorted(uniq.items()):
    st, n = dl(url, rel)
    if st in ("ok", "cached"):
        ok += 1
    else:
        fail += 1
        w("| `%s` | %s | %d |" % (rel, st, n))
w("| （其余 %d 个） | ok | - |" % ok)
w()
w("- 成功 %d / 失败 %d" % (ok, fail))
w()

# ---- 2. 单位图标 ----
w("## 2. 单位图标 ico/<ico>/<rot>.png")
w()
u_uniq = {}
for u in units:
    ico = u.get("ico") or ""
    rot = u.get("rot") or "0"
    if ico and ico != "0":
        try:
            f = "%05d" % int(rot)
        except Exception:
            f = "00000"
        u_uniq["ico/%s/%s.png" % (ico, f)] = CDN + "ico/%s/%s.png" % (ico, f)
    ic = u.get("icon") or ""
    col = u.get("color") or ""
    if ic:
        u_uniq["icon/%s-%s-0.png" % (ic, col)] = CDN + "icon/%s-%s-0.png" % (ic, col)
    son = u.get("son") or ""
    for sk in [x for x in son.split(",") if x]:
        u_uniq["ico/%s/00270.png" % sk] = CDN + "ico/%s/00270.png" % sk
w("- 需要 %d 个图标" % len(u_uniq))
w()
ok = fail = 0
fails = []
for rel, url in sorted(u_uniq.items()):
    st, n = dl(url, rel)
    if st in ("ok", "cached"):
        ok += 1
    else:
        fail += 1
        fails.append((rel, st))
w("- 成功 %d / 失败 %d" % (ok, fail))
if fails:
    w()
    w("| 失败文件 | 原因 |")
    w("|---|---|")
    for rel, st in fails:
        w("| `%s` | %s |" % (rel, st))
w()

# ---- 3. 城市旗帜 + 样式 ----
w("## 3. 城市旗帜与样式")
w()
misc = {}
for c in cities:
    fl = c.get("flag") or "GREEN"
    for col in ("RED", "BLUE", "GREEN", "NONE"):
        misc["skin/FLAG-%s-%s.png" % (fl, col)] = BASE7 + "skin/FLAG-%s-%s.png" % (fl, col)
for f in ("Hex1/cond6.png", "Hex1/cond7.png", "Hex1/cond8.png", "Hex1/cond9.png"):
    misc[f] = BASE7 + f
for m in ("main.html", "war.min.css", "user.css", "observe.css", "common.css"):
    misc[m] = BASE7 + m
misc["hexcolor/20.css"] = BASE7 + "hexcolor/20.css"
misc["SetUp.js"] = BASE7 + "SetUp.js"
misc["war.min.js"] = BASE7 + "war.min.js"
misc["lib/jquery-1.8.3.min.js"] = BASE7 + "lib/jquery-1.8.3.min.js"
misc["lib/iscroll/iscroll-zoom.js"] = BASE7 + "lib/iscroll/iscroll-zoom.js"
misc["lib/paint/paint.js"] = BASE7 + "lib/paint/paint.js"
misc["lib/move.js"] = BASE7 + "lib/move.js"
misc["lib/jAlert/js/jquery.alerts.js"] = BASE7 + "lib/jAlert/js/jquery.alerts.js"
misc["lib/jAlert/css/jquery.alerts.css"] = BASE7 + "lib/jAlert/css/jquery.alerts.css"
misc["skin/Grid.png"] = BASE7 + "skin/Grid.png"
misc["skin/arrow_up.png"] = BASE7 + "skin/arrow_up.png"
misc["skin/weather/icon-day-0.png"] = BASE7 + "skin/weather/icon-day-0.png"
misc["skin/weather/icon-weather-0.png"] = BASE7 + "skin/weather/icon-weather-0.png"
misc["BD/SetUp.js"] = BASE7 + "SetUp.js"
w("| 文件 | 结果 | 字节 |")
w("|---|---|---|")
ok = fail = 0
for rel, url in sorted(misc.items()):
    st, n = dl(url, rel)
    if st in ("ok", "cached"):
        ok += 1
    else:
        fail += 1
        w("| `%s` | %s | %d |" % (rel, st, n))
w("| （其余 %d 个） | ok | - |" % ok)
w()
w("- 成功 %d / 失败 %d" % (ok, fail))
w()

# ---- 4. 汇总 ----
total = 0
cnt = 0
for root, dirs, files in os.walk(ASSETS):
    for fn in files:
        total += os.path.getsize(os.path.join(root, fn))
        cnt += 1
w("## 4. 汇总")
w()
w("- 资源文件数: %d" % cnt)
w("- 总字节: %d (%.2f MB)" % (total, total / 1048576))

with open(REP, "w", encoding="utf-8") as f:
    f.write("\n".join(log))
print("assets done:", cnt, "files", total, "bytes")
