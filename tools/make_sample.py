# -*- coding: utf-8 -*-
"""生成一个合成的示例想定（原创数据，非任何真实站点的数据）。

用途：让引擎与测试在**没有真实数据快照**的情况下也能跑起来，
     便于他人克隆仓库后立刻验证，也便于在 CI 上跑。

用法：
    py -3.13 tools/make_sample.py
输出：
    samples/demo/map_hexes.json
    samples/demo/units.json
    samples/demo/cities.json
"""
import os
import json
import random

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "samples", "demo")
os.makedirs(OUT, exist_ok=True)
random.seed(20260101)

BANDS = list(range(8, 16))      # 行带 8..15 → 行 16..31
COLS = list(range(0, 20))       # 列 0..19


def mapid(row, col):
    return 10000 * (row // 2) + 2 * col + (row % 2)


def hexid(row, col):
    return "%02d%02d" % (row, col)


# ---------------- 地图 ----------------
hexes = {}
for b in BANDS:
    for col in COLS:
        for parity in (0, 1):
            row = 2 * b + parity
            mid = mapid(row, col)
            # 用平滑函数造高程，保证通视判定有实际意义
            elev = 100 + int(40 * random.random()) + 5 * abs(col - 10) // 2
            # 中央一条河（cond=7 居民地，cond=6 过河，8/9 丛林）
            cond = 0
            if col == 10:
                cond = 6
            elif 3 <= col <= 5 or 14 <= col <= 16:
                cond = 8
            elif 8 <= col <= 11 and b in (9, 12):
                cond = 7
            hexes[str(mid)] = {
                "mapid": mid,
                "hexid": hexid(row, col),
                "note": "桥梁" if (col == 10 and b == 10) else "",
                "cond": cond,
                "step": 0 if (col == 10 and b != 10) else 1,
                "hex": random.choice([0, 0, 2, 7, 11, 26, 53, 60]),
                "hextype": random.choice([0, 0, 0, 2]),
                "elevation": elev,
            }

# ---------------- 城市（夺控点） ----------------
cities = [
    {"id": "C_9001", "name": "主要", "ico": "GREEN", "rot": "90", "flag": "GREEN",
     "pos": str(mapid(24, 10)), "l1": "0"},
    {"id": "C_9002", "name": "次要", "ico": "GREEN", "rot": "90", "flag": "GREEN",
     "pos": str(mapid(18, 4)), "l1": "0"},
]

# ---------------- 单位 ----------------
# data 取自 engine/equip.py 的装备库
def U(uid, data, name, army, group, color, row, col, typeid, blood, wz, extra=None):
    d = {
        "id": "Obj_%d" % uid,
        "id2": "Obj_0",
        "army": army,
        "name": name,
        "group": group,
        "user": "",
        "data": str(data),
        "typeid": str(typeid),
        "color": color,
        "uid": "0",
        "car": "Obj_0",
        "sons": "0",
        "son": "",
        "fort": "",
        "space": "0",
        "stop": "0",
        "blood": str(blood),
        "pos": str(mapid(row, col)),
        "pos2": str(mapid(row, col)),
        "home": str(mapid(row, col)),
        "step": "1",
        "ico": "DEMO",
        "icon": "ARR",
        "rot": "180",
        "aim": "0",
        "score": "10",
        "runed": "0", "pass": "0", "keep": "0", "see": "0", "ste": "0",
        "att": "0", "slope": "0", "value": "", "time": "", "radar": "",
        "res": "10", "res2": "10", "busy": "0", "sec": "0", "tg": "0",
        "a0": "0", "a1": "0", "a2": "0", "a3": "4", "a4": "0", "a5": "4",
        "b0": "0", "b1": "0", "b2": "0", "b3": "0", "b4": "0",
        "c0": "0", "c1": "0", "c3": "0",
        "d0": "0", "d1": "0", "d3": "0",
        "e0": "0", "e1": "0", "e2": "0",
        "f0": "1", "f1": "0", "f2": "0", "f3": "0",
        "s1": "10", "s2": "25", "s3": "1", "s4": "25", "s5": "0",
        "r3": "0", "r5": "0",
        "wz": wz,
        "hide": "0", "active": "0", "big": "0", "ai": "0",
        "tar": "", "task": "0", "com": "",
    }
    if extra:
        d.update(extra)
    return d


units = [
    # 红军（守方）—— 两辆坦克扼守渡口
    U(9001, 400, "坦克", "红1排", "坦克连", "RED", 18, 10, 2, 3, "43, 36"),
    U(9002, 400, "坦克", "红2排", "坦克连", "RED", 20, 10, 2, 3, "43, 36"),
    # 蓝军（攻方）—— 两辆坦克 + 一个步兵班西岸待机
    U(9101, 400, "坦克", "蓝1排", "坦克连", "BLUE", 28, 6, 2, 3, "43, 36"),
    U(9102, 393, "中型坦克", "蓝2排", "坦克连", "BLUE", 29, 7, 2, 4, "136, 37, 211"),
    U(9103, 392, "步兵班", "蓝步兵排", "步兵连", "BLUE", 30, 5, 1, 4, "29, 144"),
    U(9104, 389, "巡飞弹", "蓝无人机班", "支援连", "BLUE", 28, 8, 3, 1, "76",
      {"space": "-1", "e2": "200", "res": "0"}),
]

json.dump(hexes, open(os.path.join(OUT, "map_hexes.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=0)
json.dump(units, open(os.path.join(OUT, "units.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
json.dump(cities, open(os.path.join(OUT, "cities.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

print("sample written to", OUT)
print("  hexes=%d units=%d cities=%d" % (len(hexes), len(units), len(cities)))
