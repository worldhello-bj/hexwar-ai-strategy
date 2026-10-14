# -*- coding: utf-8 -*-
"""从真实快照反推装备参数：按 name 聚合单位属性，找出武器/弹药/装甲相关字段。"""
import os
import json
import collections

PARSED = r"d:\兵推\snapshot\parsed"
OUT = r"d:\兵推\analysis\equipment_probe.md"

units = json.load(open(os.path.join(PARSED, "units.json"), encoding="utf-8"))

KEYS = ["data", "typeid", "name", "ico", "icon", "blood", "space", "step", "score", "wz",
        "res", "res2", "s1", "s2", "s3", "s4", "s5", "a0", "a1", "a2", "a3", "a4", "a5",
        "b0", "b1", "b2", "b3", "b4", "c0", "c1", "c3", "d0", "d1", "d3", "e0", "e1", "e2",
        "f0", "f1", "f2", "f3", "r3", "r5", "slope", "sons", "son", "fort"]

lines = []
def w(x=""):
    lines.append(str(x))

w("# 单位属性反推")
w()

by_name = collections.defaultdict(list)
for u in units:
    by_name[(u.get("name"), u.get("data"), u.get("typeid"))].append(u)

w("## 按 (装备名, data, typeid) 分组，逐字段取值集合")
w()
for key in sorted(by_name, key=lambda k: (k[2] or "", k[1] or "")):
    us = by_name[key]
    w("### %s   data=%s  typeid=%s   数量 %d" % (key[0], key[1], key[2], len(us)))
    w()
    w("| 字段 | 取值 |")
    w("|---|---|")
    for k in KEYS:
        vals = sorted({str(u.get(k)) for u in us})
        # 去掉纯 0 噪声但仍显示
        w("| %s | %s |" % (k, ", ".join(vals[:8]) + ("…" if len(vals) > 8 else "")))
    w()
    # 代表性样本
    w("样本 army=%s pos=%s blood=%s" % (us[0].get("army"), us[0].get("pos"), us[0].get("blood")))
    w()

# 全量字段取值分布
w("## 关键字段全局分布")
w()
for k in ("blood", "space", "step", "score", "res", "wz", "typeid", "slope", "c0", "e2", "s1", "s2", "s3", "s4", "s5", "a3", "a4", "f0", "f1", "f2"):
    c = collections.Counter(str(u.get(k)) for u in units)
    w("- `%s`: %s" % (k, dict(c)))
w()

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("written", OUT, len(lines), "lines")
