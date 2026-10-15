# -*- coding: utf-8 -*-
"""姿态探针：**走完整官方执行链**（ComPost → ComAjax 取 ComID → ObjHeight → ComFlag）
给目标设「卧倒 / 潜伏 / 掩蔽 / 机动」，再看裁决明细的「目标状态」是否随之改变。

为什么要 ComFlag：官方前端收到 ComAjax 里的指令后，是**客户端**去执行
（`CommandHeight(ComID, ObjID, height)` → `com/ObjHeight.asp?ObjID=&Flag=`），
执行成功再 `ComFlag(ComID,1,"")` → `com/ComFlag.asp` 销掉队列里的这条指令。
只发 ComPost 不执行/不销账，姿态永远不生效（本探针就是为验证这一点而写）。

目标选**人员单位**（typeid=1）：卧倒/潜伏对车辆无意义（上一轮错误地用坦克当目标）。

用法：
  $env:HEXWAR_USER=...; $env:HEXWAR_USER2=...; $env:HEXWAR_ALLOW_HTTP=1
  py -3.13 tools/hex_pose_probe.py --room 7 --minutes 25
"""
import argparse
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"d:\兵推")
import hex_combat_round as CR                    # noqa: E402
import hex_transport_capture as H                # noqa: E402
import hex_experiment_suite as SUITE             # noqa: E402

CAP = r"d:\兵推\7527_transport_capture"
POSES = [("机动(基线)", 101, "机动"), ("卧倒", 103, "卧倒"),
         ("潜伏", 104, "潜伏"), ("掩蔽", 2, "掩蔽")]


def send_pose(sess, base7, uid, code, name):
    """完整链路：ComPost → ComAjax(取 ComID) → ObjHeight → ComFlag。"""
    rec = CR.snapshot(sess, base7)
    u = rec["units"].get(uid) or {}
    kind, val = ("stat", 2) if code == 2 else ("height", code)
    cmd = {uid: {kind: val}}
    out = {"code": code, "cmd": cmd, "before": dict(
        (k, u.get(k)) for k in ("keep", "ste", "att", "d0", "pass", "blood", "typeid"))}
    out["com_post"] = repr(CR.jget(
        sess, base7, "com/ComPost.asp", ObjID=uid,
        Command=json.dumps(cmd, ensure_ascii=False),
        ObjColor=u.get("color") or "", TaskName=name,
        ObjPos=str(u.get("pos") or ""), MapID=""))[:40]
    # 从 ComAjax 回放里找**我们这条**指令的 ComID
    ajax = str(CR.jget(sess, base7, "com/ComAjax.asp"))
    want = json.dumps(cmd, ensure_ascii=False).replace(" ", "")
    comid = None
    for part in ajax.split("&"):
        f = part.split("|")
        if len(f) >= 3 and f[2].replace(" ", "") == want:
            comid = f[0]
            break
    out["comid"] = comid
    out["comajax_tail"] = ajax[-160:]
    if comid is None:
        out["error"] = "ComAjax 里没找到该指令（可能被平台拒了）"
        return out
    out["obj_height"] = repr(CR.jget(sess, base7, "com/ObjHeight.asp",
                                     ObjID=uid, Flag=code))[:40]
    out["com_flag"] = repr(CR.jget(sess, base7, "com/ComFlag.asp",
                                   ComID=comid, Flag=1, ErrorStr=""))[:40]
    time.sleep(1.5)
    dyn = H.parse_obj_ajax(CR.jget(sess, base7, "ObjAjax.asp"))
    d = dyn.get(uid) or {}
    out["after"] = dict((k, d.get(k)) for k in ("keep", "ste", "att", "d0", "pass"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", type=int, default=7)
    ap.add_argument("--minutes", type=float, default=25)
    ap.add_argument("--shots", type=int, default=3)
    args = ap.parse_args()

    outdir = os.path.join(CAP, "pose_probe_%s" % time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(outdir, exist_ok=True)
    LOG = []

    def w(x=""):
        LOG.append(str(x))
        print(x)
        with io.open(os.path.join(outdir, "report.md"), "w", encoding="utf-8") as fh:
            fh.write("# 姿态探针 %s\n\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            fh.write("\n".join(LOG) + "\n")

    sess, uid, base7, started = SUITE.prep(args.room)
    w("## 姿态执行链 + 裁决目标状态")
    harvest = SUITE.make_harvester(sess, base7, os.path.join(outdir, "caijue"))
    deadline = time.time() + args.minutes * 60
    results = []
    used = set()

    for label, code, name in POSES:
        if time.time() > deadline:
            w("- 超时，跳过 %s" % label)
            continue
        rec = CR.snapshot(sess, base7)
        units = rec["units"]
        # 目标：红方**人员**（typeid=1），未被压制、没被用过
        reds = [k for k, a in units.items()
                if a.get("color") == "RED" and str(a.get("typeid")) == "1"
                and str(a.get("blood")) not in ("0", "") and k not in used
                and str(a.get("keep", "0")) in ("0", "")]
        chosen = None
        for tgt in reds:
            for a in units:
                if units[a].get("color") != "BLUE" or str(units[a].get("blood")) == "0":
                    continue
                pick = CR.best_weapon(units, a, tgt, 1)
                if pick and pick[3] is not None:
                    chosen = (tgt, a, pick)
                    break
            if chosen:
                break
        if not chosen:
            w("- 没有可用的（人员目标 + 射手）组合，跳过 %s" % label)
            continue
        tgt, atk, pick = chosen
        used.add(tgt)
        w("\n- 【%s】目标 %s(typeid=%s ico=%s) ← 射手 %s 武器 %s"
          % (label, tgt, units[tgt].get("typeid"), units[tgt].get("ico"),
             atk, pick[2][0]))
        st = send_pose(sess, base7, tgt, code, name)
        w("  ComPost=%s ComID=%s → ObjHeight=%s → ComFlag=%s"
          % (st["com_post"], st.get("comid"), st.get("obj_height"),
             st.get("com_flag")))
        w("  设姿态前 %s" % json.dumps(st["before"], ensure_ascii=False))
        w("  设姿态后 %s" % json.dumps(st.get("after"), ensure_ascii=False))
        if st.get("error"):
            w("  !! %s" % st["error"])
        steps, d = SUITE.approach(sess, base7, atk, tgt, units)
        w("  逼近 %d 步后距 %d 格" % (steps, d))
        got = []
        for _ in range(args.shots):
            if time.time() > deadline:
                break
            r = SUITE.fire_once(sess, base7, atk, tgt, harvest, timeout_s=45)
            if not r or r.get("dead"):
                break
            for c in (r.get("caijue") or []):
                got.append({"id": c.get("id"), "目标状态": c.get("目标状态"),
                            "射击方状态": c.get("射击方状态"),
                            "修正前": c.get("修正前"), "修正结果": c.get("修正结果")})
        w("  样本 %d：%s" % (len(got), json.dumps(got, ensure_ascii=False)))
        results.append({"pose": label, "code": code, "state": st, "samples": got})

    io.open(os.path.join(outdir, "results.json"), "w", encoding="utf-8").write(
        json.dumps(results, ensure_ascii=False, indent=1))
    w("\n## 汇总")
    for r in results:
        seen = sorted(set(s["目标状态"] for s in r["samples"]))
        w("- %-10s 执行后 keep=%s ste=%s；裁决目标状态=%s"
          % (r["pose"], (r["state"].get("after") or {}).get("keep"),
             (r["state"].get("after") or {}).get("ste"), seen or "（无样本）"))
    print("ok ->", outdir)


if __name__ == "__main__":
    main()
