# -*- coding: utf-8 -*-
"""姿态变体矩阵：在**同一个红方人员单位**上逐个试不同发法，看哪个真能改状态。

变体（每个都打印执行前后 keep/ste/e2/stat，以及 ObjAjax 里该单位的原始字段）：
  V1 导演 A → com/ObjHeight.asp?ObjID&Flag=104（潜伏）
  V2 红方 B → com/ObjHeight.asp?ObjID&Flag=104
  V3 导演 A → com/ObjHeight.asp?ObjID&Flag=3（keep 语义码，验证 Flag 是不是 take keep 值）
  V4 导演 A → ComPost{"keep":3} + ComAjax + ComFlag
  V5 红方 B → ComPost{"keep":3} + ComAjax + ComFlag
  V6 导演 A → ComPost{"stat":2}（掩蔽） + ComAjax + ObjHeight(Flag=2) + ComFlag

用法：HEXWAR_USER/USER2/ALLOW_HTTP 环境变量；py -3.13 tools\\hex_pose_probe2.py --room 7
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

CAP = r"d:\兵推\7527_transport_capture"
KEYS = ("keep", "ste", "e2", "stat", "att", "d0", "pass", "blood", "typeid", "task")


def dump(sess, base7, uid):
    dyn = H.parse_obj_ajax(CR.jget(sess, base7, "ObjAjax.asp"))
    d = dyn.get(uid) or {}
    return {k: d.get(k) for k in KEYS}


def post_cmd(sess, base7, uid, cmd, name):
    rec = CR.snapshot(sess, base7)
    u = rec["units"].get(uid) or {}
    r = CR.jget(sess, base7, "com/ComPost.asp", ObjID=uid,
                Command=json.dumps(cmd, ensure_ascii=False),
                ObjColor=u.get("color") or "", TaskName=name,
                ObjPos=str(u.get("pos") or ""), MapID="")
    ajax = str(CR.jget(sess, base7, "com/ComAjax.asp"))
    want = json.dumps(cmd, ensure_ascii=False).replace(" ", "")
    comid = None
    for part in ajax.split("&"):
        f = part.split("|")
        if len(f) >= 3 and f[2].replace(" ", "") == want:
            comid = f[0]
            break
    return repr(r)[:20], comid, ajax[-90:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", type=int, default=7)
    args = ap.parse_args()
    outdir = os.path.join(CAP, "pose_probe2_%s" % time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(outdir, exist_ok=True)
    LOG = []

    def w(x=""):
        LOG.append(str(x))
        print(x)

    sessA, uidA, base7, _ = SUITE.prep(args.room)
    uB, pB = os.environ["HEXWAR_USER2"], os.environ["HEXWAR_PASS2"]
    sessB, uidB = CR.login_as(uB, pB)
    w("- 房间就绪；A(导演 %s) B(红方 %s)" % (uidA, uidB))

    rec = CR.snapshot(sessA, base7)
    units = rec["units"]
    red = [k for k, a in units.items()
           if a.get("color") == "RED" and str(a.get("typeid")) == "1"
           and str(a.get("blood")) not in ("0", "")]
    if not red:
        w("!! 没有红方人员单位")
        return
    uid = red[0]
    w("- 目标 %s(%s)" % (uid, units[uid].get("name")))
    w("- 初始 %s" % json.dumps(dump(sessA, base7, uid), ensure_ascii=False))

    def variant(tag, fn):
        before = dump(sessA, base7, uid)
        info = fn()
        time.sleep(1.5)
        after = dump(sessA, base7, uid)
        changed = {k: (before.get(k), after.get(k))
                   for k in KEYS if before.get(k) != after.get(k)}
        w("\n### %s" % tag)
        w("  执行: %s" % json.dumps(info, ensure_ascii=False))
        w("  变化: %s" % (json.dumps(changed, ensure_ascii=False) if changed else "**无变化**"))
        return changed

    variant("V1 导演 ObjHeight Flag=104", lambda: {
        "resp": repr(CR.jget(sessA, base7, "com/ObjHeight.asp", ObjID=uid, Flag=104))[:40]})
    variant("V2 红方 ObjHeight Flag=104", lambda: {
        "resp": repr(CR.jget(sessB, base7, "com/ObjHeight.asp", ObjID=uid, Flag=104))[:40]})
    variant("V3 导演 ObjHeight Flag=3", lambda: {
        "resp": repr(CR.jget(sessA, base7, "com/ObjHeight.asp", ObjID=uid, Flag=3))[:40]})

    def v4():
        post, comid, tail = post_cmd(sessA, base7, uid, {uid: {"keep": 3}}, "卧倒")
        oh = repr(CR.jget(sessA, base7, "com/ObjHeight.asp", ObjID=uid, Flag=103))[:40]
        cf = repr(CR.jget(sessA, base7, "com/ComFlag.asp", ComID=comid or 0,
                           Flag=1, ErrorStr=""))[:40]
        return {"com_post": post, "comid": comid, "tail": tail, "obj_height": oh,
                "com_flag": cf}
    variant("V4 导演 ComPost{keep:3} + ObjHeight103 + ComFlag", v4)

    def v5():
        post, comid, tail = post_cmd(sessB, base7, uid, {uid: {"keep": 3}}, "卧倒")
        oh = repr(CR.jget(sessB, base7, "com/ObjHeight.asp", ObjID=uid, Flag=103))[:40]
        return {"com_post": post, "comid": comid, "tail": tail, "obj_height": oh}
    variant("V5 红方 ComPost{keep:3} + ObjHeight103", v5)

    def v6():
        post, comid, tail = post_cmd(sessA, base7, uid, {uid: {"stat": 2}}, "掩蔽")
        oh = repr(CR.jget(sessA, base7, "com/ObjHeight.asp", ObjID=uid, Flag=2))[:40]
        cf = repr(CR.jget(sessA, base7, "com/ComFlag.asp", ComID=comid or 0,
                           Flag=1, ErrorStr=""))[:40]
        return {"com_post": post, "comid": comid, "tail": tail, "obj_height": oh,
                "com_flag": cf}
    variant("V6 导演 ComPost{stat:2} + ObjHeight2", v6)

    io.open(os.path.join(outdir, "report.md"), "w", encoding="utf-8").write(
        "# 姿态变体矩阵 %s\n\n" % time.strftime("%Y-%m-%d %H:%M:%S") + "\n".join(LOG) + "\n")
    print("ok ->", outdir)


if __name__ == "__main__":
    main()
