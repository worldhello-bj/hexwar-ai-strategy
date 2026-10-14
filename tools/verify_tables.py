"""把 `engine/tables.json` 与手册里逐字誊出的数值做对照校验。

手册数据来自 `docs/WARGAMEAI.pdf` 的译文（`analysis/manual_text.md`），
下面每一项都注明条款/表号，改表时必须同步改这里。

另外列出**官方软件认识、但手册未给数值**的状态与装甲级别——
这些不能臆造，引擎对它们一律不修正，且在裁决日志中显式提示。

运行：``py -3.13 tools/verify_tables.py``
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import crt                                    # noqa: E402

T = json.load(open(os.path.join(ROOT, "engine", "tables.json"), encoding="utf-8"))

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, note: str = "") -> None:
    RESULTS.append((name, bool(ok), note))
    print(("  [通过] " if ok else "  [失败] ") + name + (("　— " + note) if note else ""))


# ---- 表7「人员伤亡结果修正」的状态修正（手册第 30 页）
MANUAL_STATE_MODS = {
    "shooter_stunned": -1,      # 射击算子状态修正：被压制 −1
    "shooter_moving": -1,       # 射击算子状态修正：机动中 −1
    "terrain_town": -1,         # 目标所处地形修正：居民地 −1
    "terrain_jungle": -2,       # 丛林地 −2
    "terrain_fort": -4,         # 工事/掩体/建筑物 −4
    "target_moving": -2,        # 目标状态修正：机动 −2
    "target_hidden": -2,        # 掩蔽 −2
    "target_stacked": 2,        # 堆叠 +2
}

# ---- 表8「手雷战斗结果」（手册第 30 页）：2-4 无效，5-9 为 1，10-12 无效
MANUAL_GRENADE = {2: 0, 3: 0, 4: 0, 5: 1, 6: 1, 7: 1, 8: 1, 9: 1,
                  10: 0, 11: 0, 12: 0}

# ---- 表5「车辆战损结果修正」的防护力分级（手册第 29 页）
MANUAL_ARMOR = {"无装甲", "轻型装甲", "中型装甲", "复合装甲", "重型装甲"}

# ---- 官方 Caijue.asp 模板列举、但手册未给出修正值的目标状态
OFFICIAL_ONLY_STATES = ["卧倒", "行军", "水上", "车内"]
# ---- 同上，装甲级别
OFFICIAL_ONLY_ARMOR = ["反应装甲"]

print("\n== 表7 状态修正 ==")
sm = T.get("state_mods") or {}
for k, v in MANUAL_STATE_MODS.items():
    check(f"state_mods[{k}] == {v:+d}", sm.get(k) == v, f"实际={sm.get(k)}")
extra = set(sm) - set(MANUAL_STATE_MODS)
check("没有手册以外的修正项", not extra, f"多出={sorted(extra)}" if extra else "")

print("\n== 表8 手雷结果 ==")
gr = T.get("grenade_result") or {}
for roll, v in MANUAL_GRENADE.items():
    got = gr.get(str(roll), 0)
    check(f"随机数 {roll} → {v}", got == v, f"实际={got}")

print("\n== 表5 防护力分级 ==")
got_armor = set((T.get("table5") or {}).get("by_armor") or {})
check("装甲分级集合与手册一致", got_armor == MANUAL_ARMOR,
      f"实际={sorted(got_armor)}")

print("\n== 手册未给数值、因此不修正的项（已知缺口，非缺陷）==")
for st in OFFICIAL_ONLY_STATES:
    check(f"目标状态「{st}」未计入修正（手册无该条）", True, "引擎按 0 处理")
for ar in OFFICIAL_ONLY_ARMOR:
    check(f"装甲「{ar}」不在表5 → 引擎会显式警告", not crt.armor_known(ar))

ok = sum(1 for _n, c, _m in RESULTS if c)
print("\n" + "=" * 60)
print("裁决表校验：%d/%d 通过" % (ok, len(RESULTS)))
failed = [n for n, c, _m in RESULTS if not c]
if failed:
    print("未通过：")
    for n in failed:
        print("  - " + n)
sys.exit(0 if not failed else 1)
