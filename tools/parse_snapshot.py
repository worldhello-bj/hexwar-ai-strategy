# -*- coding: utf-8 -*-
"""解析抓取到的地图/单位/城市数据，输出结构化 JSON + 统计报告。"""
import os
import re
import json
from bs4 import BeautifulSoup

RAW = r"d:\兵推\snapshot\raw"
OUT = r"d:\兵推\snapshot\parsed"
os.makedirs(OUT, exist_ok=True)
REP = r"d:\兵推\analysis\parse.md"

rep = []
def w(x=""):
    rep.append(x)

def read(name):
    p = os.path.join(RAW, name)
    if not os.path.exists(p):
        return None
    b = open(p, "rb").read()
    for enc in ("utf-8", "gb18030"):
        try:
            return b.decode(enc)
        except Exception:
            pass
    return b.decode("utf-8", errors="replace")

w("# 数据解析报告")
w()

# ---------- 1. 地图 ----------
w("## 1. 地图数据 Map_Get.asp")
w()
mj = read("Map_Get.asp.json") or ""
w("- 原始长度: %d 字符" % len(mj))
# 宽松解析：{key:{...},...}
pat = re.compile(r'(\d+):\{"mapid":"(\d+)","hexid":"([^"]*)","note":"([^"]*)","cond":"?(\d+)"?,"step":"?(\d+)"?,"hex":"?(\d+)"?,"hextype":"?(\d+)"?,"elevation":(\d+)\}')
items = pat.findall(mj)
w("- 匹配到格子数: %d" % len(items))
if not items:
    w()
    w("### 原始前 600 字符")
    w()
    w("```")
    w(mj[:600])
    w("```")
    w()

hexes = {}
for k, mapid, hexid, note, cond, step, hexv, hextype, elev in items:
    hexes[k] = {
        "mapid": int(mapid), "hexid": hexid.strip(),
        "note": note, "cond": int(cond), "step": int(step),
        "hex": int(hexv), "hextype": int(hextype), "elevation": int(elev),
    }
if hexes:
    keys = sorted(int(k) for k in hexes)
    elevs = [h["elevation"] for h in hexes.values()]
    conds = {}
    for h in hexes.values():
        conds[h["cond"]] = conds.get(h["cond"], 0) + 1
    types = {}
    for h in hexes.values():
        types[h["hextype"]] = types.get(h["hextype"], 0) + 1
    heximgs = {}
    for h in hexes.values():
        if h["hex"]:
            heximgs[h["hex"]] = heximgs.get(h["hex"], 0) + 1
    rows = sorted({int(h["hexid"][:2]) if h["hexid"][:2].isdigit() else -1 for h in hexes.values()})
    cols = sorted({int(h["hexid"][2:]) if h["hexid"][2:].isdigit() else -1 for h in hexes.values()})
    w("- mapid 范围: %d .. %d" % (keys[0], keys[-1]))
    w("- hexid 行号范围: %s .. %s (%d 行)" % (rows[0], rows[-1], len(rows)))
    w("- hexid 列号范围: %s .. %s (%d 列)" % (cols[0], cols[-1], len(cols)))
    w("- 高程 elevation: %d .. %d" % (min(elevs), max(elevs)))
    w("- cond 分布: %s" % json.dumps(conds, ensure_ascii=False))
    w("- hextype 分布: %s" % json.dumps(types, ensure_ascii=False))
    w("- 有地形贴图(hex>0) 的格子数: %d, 不同贴图 %d 种" % (sum(heximgs.values()), len(heximgs)))
    w("- 贴图编号(前 30): %s" % sorted(heximgs)[:30])
    json.dump(hexes, open(os.path.join(OUT, "map_hexes.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    w("- 已写出 `parsed/map_hexes.json`")
    # 一条样例
    w()
    w("### 样例（前 3 格）")
    w()
    w("```json")
    w(json.dumps([hexes[k] for k in list(hexes)[:3]], ensure_ascii=False, indent=2))
    w("```")
w()

# ---------- 2. 城市 ----------
w("## 2. 城市数据 City_Get.asp")
w()
cj = read("City_Get.asp.html") or ""
csoup = BeautifulSoup(cj, "lxml")
cities = []
for d in csoup.find_all("div"):
    cities.append({k: d.get(k) for k in ("id", "name", "ico", "rot", "flag", "pos", "l1")})
w("- 城市数: %d" % len(cities))
w()
w("| id | name | ico | flag | pos |")
w("|---|---|---|---|---|")
for c in cities:
    w("| %s | %s | %s | %s | %s |" % (c["id"], c["name"], c["ico"], c["flag"], c["pos"]))
w()
json.dump(cities, open(os.path.join(OUT, "cities.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# ---------- 3. 单位 ----------
w("## 3. 单位数据 Obj_Get.asp")
w()
oj = read("Obj_Get.asp.html") or ""
osoup = BeautifulSoup(oj, "lxml")
divs = osoup.find_all("div")
units = []
for d in divs:
    if not d.get("id", "").startswith("Obj_"):
        continue
    a = {k: d.get(k) for k in d.attrs if k not in ("id",)}
    a["id"] = d.get("id")
    a.pop("class", None)
    units.append(a)
w("- 单位数量: %d" % len(units))
if units:
    w("- 属性键（并集）: %s" % sorted({k for u in units for k in u}))
    w()
    byname = {}
    for u in units:
        byname[u.get("name")] = byname.get(u.get("name"), 0) + 1
    w("### 装备/单位类型统计")
    w()
    w("| name | 数量 |")
    w("|---|---|")
    for k, v in sorted(byname.items(), key=lambda kv: -kv[1]):
        w("| %s | %d |" % (k, v))
    w()
    bycolor = {}
    for u in units:
        bycolor[u.get("color")] = bycolor.get(u.get("color"), 0) + 1
    w("- 阵营分布: %s" % json.dumps(bycolor, ensure_ascii=False))
    bytypeid = {}
    for u in units:
        bytypeid[u.get("typeid")] = bytypeid.get(u.get("typeid"), 0) + 1
    w("- typeid 分布: %s" % json.dumps(bytypeid, ensure_ascii=False))
    w()
    json.dump(units, open(os.path.join(OUT, "units.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    w("- 已写出 `parsed/units.json`")
    w()
    w("### 样例单位")
    w()
    w("```json")
    w(json.dumps(units[0], ensure_ascii=False, indent=2))
    w("```")
w()

# ---------- 4. ObjAjax ----------
w("## 4. 动态状态 ObjAjax.asp")
w()
aj = read("ObjAjax.asp.json") or ""
try:
    fixed = re.sub(r"^\s*", "", aj)
    obj = json.loads("{" + fixed.strip().rstrip(",") + "}") if not fixed.strip().startswith("{") else json.loads(fixed)
except Exception as e:
    obj = None
    w("- 严格 JSON 解析失败(%r)，改用宽松提取" % (e,))
if obj:
    w("- 条目数: %d" % len(obj))
    k0 = list(obj)[0]
    w("- 字段: %s" % sorted(obj[k0].keys()))
    w()
    w("```json")
    w(json.dumps({k0: obj[k0]}, ensure_ascii=False, indent=2))
    w("```")
    json.dump(obj, open(os.path.join(OUT, "obj_ajax_state.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    w("- 已写出 `parsed/obj_ajax_state.json`")
w()

# ---------- 5. offlinemapdata ----------
w("## 5. 瓦片清单 offlinemapdata.asp")
w()
om = read("offlinemapdata.asp.txt") or ""
tiles = [t for t in om.strip().split(",") if t.strip()]
w("- 瓦片名数量: %d" % len(tiles))
w("- 前 20: %s" % tiles[:20])
w("- 后 10: %s" % tiles[-10:])
w()

with open(REP, "w", encoding="utf-8") as f:
    f.write("\n".join(rep))
print("parse done; hexes=%d units=%d cities=%d" % (len(hexes), len(units), len(cities)))
