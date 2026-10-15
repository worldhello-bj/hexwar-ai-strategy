# -*- coding: utf-8 -*-
"""诊断：① 推演时钟是否推进；② 为何连续开火失败；③ 压制为何不解除。

复用 hex_experiment_suite 的房间准备与 hex_combat_round 的协议实现。

用法：
    $env:HEXWAR_USER=...; $env:HEXWAR_USER2=...; $env:HEXWAR_ALLOW_HTTP=1
    py -3.13 tools/hex_clock_probe.py --room 7
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
import hex_experiment_suite as S                 # noqa: E402
import hex_transport_capture as H                # noqa: E402
from engine import geometry as GEO               # noqa: E402


def user_get(sess, base7):
    return CR.jget(sess, base7, "User_Get.asp", userAgent="probe").split("$")


def rs(parts):
    return parts[20] if len(parts) > 20 else "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", type=int, default=7)
    ap.add_argument("--watch", type=float, default=30.0, help="观测时钟的秒数")
    args = ap.parse_args()

    H.guard()
    base7 = "%s/WARGAMEAI%d/" % (H.HOST, args.room)
    H.BASE7 = base7
    sessA, uidA, base7, started = S.prep(args.room)
    d = os.path.join(S.CAP, "clock_probe_%s" % time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(d, exist_ok=True)
    out = []

    def w(x=""):
        out.append(str(x))
        print(x)

    def finish():
        io.open(os.path.join(d, "report.md"), "w", encoding="utf-8").write("\n".join(out))
        print("ok ->", d)

    w("# 时钟/连射诊断 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    if not started:
        w("!!! 开局失败")
        finish()
        return

    # ---- ① 时钟是否推进（同时每秒调用 ObjAjax，模拟客户端轮询）----
    w("")
    w("## ① 时钟推进（每秒一次 ObjAjax + 读 RoomSecond）")
    p0 = user_get(sessA, base7)
    w("  StartTime=%s WarDateTime=%s RoomSecond=%s Time1=%s"
      % (p0[3] if len(p0) > 3 else "", p0[11] if len(p0) > 11 else "",
         rs(p0), p0[34] if len(p0) > 34 else ""))
    t0 = time.time()
    samples = []
    while time.time() - t0 < args.watch:
        CR.jget(sessA, base7, "ObjAjax.asp")          # 模拟客户端轮询
        p = user_get(sessA, base7)
        samples.append((round(time.time() - t0), rs(p)))
        time.sleep(1.0)
    w("  RoomSecond 序列：%s" % samples)
    vals = [s[1] for s in samples]
    w("  → %s" % ("**时钟在推进**" if len(set(vals)) > 1 else "**时钟不推进（停在 %s）**" % vals[0]))

    # ---- ② 逼近一对并连续开火，观察返回与 Attack 相关接口 ----
    w("")
    w("## ② 连续开火")
    atk, tgt, rec = S.pick_pair(sessA, base7)
    if not atk:
        w("- 无可用交战对")
        finish()
        return
    units = rec["units"]
    w("- 交战对 %s(%s) ↔ %s(%s)" % (atk, (units[atk] or {}).get("ico"),
                                  tgt, (units[tgt] or {}).get("ico")))
    steps, dd = S.approach(sessA, base7, atk, tgt, units)
    w("- 逼近 %d 步后距离 %d 格" % (steps, dd))

    harvest = S.make_harvester(sessA, base7, os.path.join(d, "caijue"))
    for k in range(6):
        p = user_get(sessA, base7)
        rec = CR.snapshot(sessA, base7)
        units = rec["units"]
        if atk not in units or str(units[atk].get("blood")) == "0":
            w("- 射手不在表或已歼，停止")
            break
        if tgt in units and str(units[tgt].get("blood")) == "0":
            w("- 目标已歼灭，停止")
            break
        dnow = GEO.distance(int(units[atk]["pos"]), int(units[tgt]["pos"]))
        dyn = rec["dynamic"].get(units and tgt, {}) or {}
        keep = (rec["dynamic"].get(tgt) or {}).get("keep")
        da = rec["dynamic"].get(atk) or {}
        dh = CR.elev(units[atk]["pos"]) - CR.elev(units[tgt]["pos"])
        bw = CR.best_weapon(units, atk, tgt, dnow, dh=dh)
        if not bw:
            w("- 无武器")
            break
        idx, wid, info, lvl = bw
        f = CR.fire(sessA, base7, atk, tgt, wid, units[atk].get("color") or "", rec)
        w("- 第%d发 RoomSecond=%s 距离=%d 武器=%s 返回=%r  射手[a1=%s a2=%s att=%s d0=%s] 目标keep=%s"
          % (k + 1, rs(p), dnow, info[0], f.get("attack_resp"),
             da.get("a1"), da.get("a2"), da.get("att"), da.get("d0"), keep))
        # 观察 15s 内战报
        got = []
        t1 = time.time()
        while time.time() - t1 < 15:
            time.sleep(3)
            r2 = CR.snapshot(sessA, base7)
            got += harvest(r2["report_attack"])
            if got:
                break
        if got:
            w("    → 收工该发")
        else:
            # 试客户端的"武器就绪"收尾
            try:
                rr = CR.jget(sessA, base7, "com/ObjWeaponReady.asp", ObjID=atk)
                w("    ObjWeaponReady -> %r" % str(rr)[:80])
            except Exception as e:                            # noqa: BLE001
                w("    ObjWeaponReady err %r" % (e,))
        time.sleep(3)

    finish()


if __name__ == "__main__":
    main()
