# -*- coding: utf-8 -*-
"""表4 列号实测扫描：把射手依次拉到不同距离开火，覆盖尽量多的**攻击等级**。

为什么需要：手册表4 的 PDF 网格是斜的，`engine/tables.json` 的 `table4_columns`
（攻级 → 列号）只能靠单调性择优，实测已证明「攻级10」映射错了（实测列 16/17，映射写 13）。
每种攻级要有**多条不同随机数1** 的样本，反解出的列号集合才会收敛成唯一值。

流程：近距离（攻级最高）→ 逐步拉远 → 每个距离打 2 发并收裁决明细。

用法：HEXWAR_USER/USER2/ALLOW_HTTP；py -3.13 tools\\hex_table4_sweep.py --room 7 --minutes 30
"""
import argparse
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"d:\兵推")
import hex_combat_round as CR                    # noqa: E402
import hex_transport_capture as H                # noqa: E402
import hex_experiment_suite as SUITE             # noqa: E402
from engine import equip as EQ                   # noqa: E402

CAP = r"d:\兵推\7527_transport_capture"
DISTANCES = [1, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18]


def armored_targets(units):
    """红方**有装甲**的车辆（typeid=2 且装甲 ≠ 无装甲）。

    UGV（无人察打车）也是 typeid=2、但装甲就是「无装甲」，会把表4 样本污染成
    「像人员一样的低结果」，必须排除。
    """
    out = []
    for k, a in units.items():
        if a.get("color") != "RED" or str(a.get("typeid")) != "2":
            continue
        if str(a.get("blood")) in ("0", ""):
            continue
        eq = EQ.equipment(a.get("data"))
        if eq and eq[2] != "无装甲":
            out.append(k)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", type=int, default=7)
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--shots", type=int, default=2)
    ap.add_argument("--prefer-weapon", default="重型坦克炮")
    ap.add_argument("--distances", default="",
                    help="逗号分隔的距离序列（默认 1,1,2,3,4,5,6,7,8,10,12,14,16,18）")
    args = ap.parse_args()

    outdir = os.path.join(CAP, "table4_sweep_%s" % time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(outdir, exist_ok=True)
    LOG = []

    def w(x=""):
        LOG.append(str(x))
        print(x)
        with io.open(os.path.join(outdir, "report.md"), "w", encoding="utf-8") as fh:
            fh.write("# 表4 列号扫描 %s\n\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            fh.write("\n".join(LOG) + "\n")

    sess, uid, base7, _ = SUITE.prep(args.room)
    SUITE.w = w          # 让采集器（make_harvester）的日志也写进本报告
    harvest = SUITE.make_harvester(sess, base7, os.path.join(outdir, "caijue"))
    deadline = time.time() + args.minutes * 60
    w("## 距离扫描（目标：车辆，覆盖攻级 1–10）")

    rec = CR.snapshot(sess, base7)
    units = rec["units"]
    # 目标：红方**有装甲**车辆（typeid=2、装甲 ≠ 无装甲）、未被压制
    reds = armored_targets(units)
    chosen = None
    fallback = None
    for tgt in reds:
        for a in units:
            if units[a].get("color") != "BLUE" or str(units[a].get("blood")) == "0":
                continue
            pick = CR.best_weapon(units, a, tgt, 1)
            if pick and pick[3] is not None:
                if pick[2][0] == args.prefer_weapon:
                    chosen = (tgt, a, pick)
                    break
                if fallback is None:
                    fallback = (tgt, a, pick)
        if chosen:
            break
    chosen = chosen or fallback
    if not chosen:
        w("!! 找不到（车辆目标 + 射手）组合")
        return
    tgt, atk, pick = chosen
    eq0 = EQ.equipment((units.get(tgt) or {}).get("data")) or ("?", "?", "?")
    w("- 目标 %s(ico=%s typeid=%s 装甲=%s) ← 射手 %s 武器 %s（射程 %s，近距预估攻级 %s）"
      % (tgt, units[tgt].get("ico"), units[tgt].get("typeid"), eq0[2], atk,
         pick[2][0], pick[2][1], pick[3]))

    got = []
    for want in DISTANCES:
        if time.time() > deadline:
            w("- 超时，停止")
            break
        rec = CR.snapshot(sess, base7)
        units = rec["units"]
        if str(units.get(tgt, {}).get("blood")) in ("0", ""):
            w("- 目标已歼灭，换一个")
            reds = armored_targets(units)
            if not reds:
                break
            tgt = reds[0]
            eq = EQ.equipment((units.get(tgt) or {}).get("data")) or ("?", "?", "?")
            w("- 目标 %s(ico=%s typeid=%s 装甲=%s) ← 射手 %s 武器 %s"
              % (tgt, (units.get(tgt) or {}).get("ico"),
                 (units.get(tgt) or {}).get("typeid"), eq[2], atk, pick[2][0]))
        steps, d = 0, SUITE.move_to_distance(sess, base7, atk, tgt, want, units,
                                             max_steps=60)
        lvl = CR.expected_level(units, atk, tgt, pick[2][0], d)
        w("\n- 目标距离 %d 格（走 %d 步），武器 %s 预估攻级 %s"
          % (d, steps, pick[2][0], lvl))
        for _ in range(args.shots):
            if time.time() > deadline:
                break
            r = SUITE.fire_once(sess, base7, atk, tgt, harvest, timeout_s=45)
            if not r:
                w("  开火失败（无战报）")
                continue
            for c in (r.get("caijue") or []):
                got.append({"dist": r.get("dist"), "atk": c.get("攻击等级"),
                            "roll1": c.get("随机数"), "battle": c.get("战斗结果"),
                            "fix": c.get("修正结果"), "final": c.get("最终战果"),
                            "armor": c.get("装甲级别"), "id": c.get("id")})
            if r.get("dead"):
                w("  （目标已歼灭）")
                break

    w("\n## 汇总（攻级 → 观察到的战斗结果）")
    per = {}
    for g in got:
        per.setdefault(g["atk"], []).append((g["roll1"], g["battle"], g["fix"],
                                             g["final"], g["dist"]))
    for a in sorted(per, key=lambda x: int(x or 0)):
        w("- 攻级 %s（%d 条）：%s" % (a, len(per[a]), per[a]))
    io.open(os.path.join(outdir, "results.json"), "w", encoding="utf-8").write(
        json.dumps(got, ensure_ascii=False, indent=1))
    print("ok ->", outdir)


if __name__ == "__main__":
    main()
