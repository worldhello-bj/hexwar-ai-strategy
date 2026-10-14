# -*- coding: utf-8 -*-
"""补齐 hexcolor 高程分层图与血条/状态图标。"""
import os
import re
import requests

BASE7 = "http://www.hexwar.cn/WARGAMEAI7/"
ASSETS = r"d:\兵推\snapshot\assets"
REP = r"d:\兵推\analysis\assets2.md"

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": BASE7 + "main.html",
})

def dl(rel):
    p = os.path.join(ASSETS, rel.replace("/", os.sep))
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return "cached", os.path.getsize(p)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    try:
        r = s.get(BASE7 + rel, timeout=30)
    except Exception as e:
        return "ERR %r" % (e,), 0
    if r.status_code == 200 and r.content:
        open(p, "wb").write(r.content)
        return "ok", len(r.content)
    return "status=%s" % r.status_code, 0

log = []
def w(x=""):
    log.append(x)

w("# 补充资源（第二批）")
w()

# 1. hexcolor/02/*.png —— 从 20.css 与请求日志推断
w("## 1. hexcolor 高程分层")
w()
levels = list(range(60, 520, 20)) + [0, 20, 40]
targets = []
for n in levels:
    targets.append("hexcolor/02/%d.png" % n)
for f in ("hexcolor/02/0.png", "hexcolor/02.css", "hexcolor/01.css", "hexcolor/03.css",
          "hexcolor/00.css", "hexcolor/20.css"):
    targets.append(f)
w("| 文件 | 结果 | 字节 |")
w("|---|---|---|")
bad = []
for rel in targets:
    st, n = dl(rel)
    if st not in ("ok", "cached"):
        bad.append((rel, st))
w("| 共 %d 个 | 失败 %d | - |" % (len(targets), len(bad)))
for rel, st in bad:
    w("| `%s` | %s | - |" % (rel, st))
w()

# 2. 血条 / 状态图标
w("## 2. 血条与状态图标")
w()
skins = []
for col in ("RED", "BLUE", "GREEN"):
    for b in range(0, 12):
        skins.append("skin/%s-blood-%d.png" % (col, b))
for n in ("Grid0.png", "Grid-Few.png", "Died-RED.png", "Died-BLUE.png", "Grid.png",
          "Grid-14.png", "Grid-200.png", "Grid-260.png"):
    skins.append("skin/" + n)
bad2 = []
for rel in skins:
    st, n = dl(rel)
    if st not in ("ok", "cached"):
        bad2.append((rel, st))
w("- 尝试 %d 个，失败 %d 个" % (len(skins), len(bad2)))
for rel, st in bad2:
    w("  - `%s` : %s" % (rel, st))
w()

# 3. Hex1 全量（cond > 25 的分层）
w("## 3. Hex1 分层图（cond>25）")
w()
conds = [26, 28, 37, 53, 55, 83, 84, 161, 162, 173, 184, 185]
bad3 = []
for c in conds:
    rel = "Hex1/%d.png" % c
    st, n = dl(rel)
    if st not in ("ok", "cached"):
        bad3.append((rel, st))
    rel = "Hex/%d.png" % c
    st, n = dl(rel)
    if st not in ("ok", "cached"):
        bad3.append((rel, st))
w("- 失败: %s" % (bad3 if bad3 else "无"))
w()

# 汇总
tot = cnt = 0
for root, dirs, files in os.walk(ASSETS):
    for fn in files:
        tot += os.path.getsize(os.path.join(root, fn))
        cnt += 1
w("## 4. 汇总")
w()
w("- 资源文件数: %d，总字节: %d (%.2f MB)" % (cnt, tot, tot / 1048576))

open(REP, "w", encoding="utf-8").write("\n".join(log))
print("supplement done:", cnt, "files")
