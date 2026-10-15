# -*- coding: utf-8 -*-
"""裁决规则实测套件：一个房间内跑完清单里的多项实验，逐项落盘。

模式：
  mobility  机动耗时 + 通行能力（表 4.1.2(5) / step 语义）：车辆在异质格间机动，记 (Δ高程,
            to.step/cond/hextype) → updatePos 毫秒 / 是否可走。
  combat    接近到相邻 → 重复开火（表4 采样）+ 逐距离开火（表2 攻击等级曲线）。
  timing    攻击间隔（连续裁决时间差）+ 压制时长（keep 由 1 回 0 的秒数）。
  special   间瞄 jmFire / 空中(typeid=3) / 巡飞弹(typeid=5) 的接口尝试与观测。

用法：
  $env:HEXWAR_USER=...; $env:HEXWAR_USER2=...; $env:HEXWAR_ALLOW_HTTP=1
  py -3.13 tools/hex_experiment_suite.py --room 7 --modes mobility,combat,timing,special
"""
import argparse
import io
import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"d:\兵推")
import hex_combat_round as CR                    # noqa: E402
import hex_transport_capture as H                # noqa: E402
from engine import geometry as GEO               # noqa: E402

CAP = r"d:\兵推\7527_transport_capture"
LOG = []
RES = {"mobility": [], "combat": [], "timing": {}, "special": []}


def w(x=""):
    LOG.append(str(x))
    print(x)


# ---------------- 房间准备 ----------------
def prep(room, color2="RED"):
    uA, pA = os.environ["HEXWAR_USER"], os.environ["HEXWAR_PASS"]
    uB, pB = os.environ["HEXWAR_USER2"], os.environ["HEXWAR_PASS2"]
    base7 = "%s/WARGAMEAI%d/" % (H.HOST, room)
    H.BASE7 = base7

    sessA, _ = CR.login_as(uA, pA)
    url = "%s/WARGAMEAI%d/Reset/Post.asp" % (H.HOST, room)
    m = re.search(r'<form[^>]*action="([^"]*)"[^>]*>(.*?)</form>',
                  CR.jget(sessA, "%s/WARGAMEAI%d/" % (H.HOST, room), "Reset/Post.asp",
                          scenarioId=7527, roomId=room), re.S)
    if m:
        data = {}
        for im in re.finditer(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>',
                              m.group(2), re.S):
            data[im.group(1)] = im.group(2).strip()
        sessA.post(requests.compat.urljoin(url, m.group(1)), data=data, timeout=30)
        w("- 复位房间 -> 200")

    sessA, uidA = CR.login_as(uA, pA)
    CR.quit_room(sessA, uidA)
    time.sleep(0.5)
    H.S = sessA
    H.enter(room, "NONE", uidA)
    okA, _ = CR.in_room(sessA, base7)
    w("- A(导演 %s) 在座=%s" % (uidA, okA))

    sessB, uidB = CR.login_as(uB, pB)
    CR.quit_room(sessB, uidB)
    time.sleep(0.5)
    H.S = sessB
    H.enter(room, color2, uidB)
    okB, _ = CR.in_room(sessB, base7)
    w("- B(%s %s) 在座=%s" % (color2, uidB, okB))

    started = ""
    for _ in range(6):
        txt = CR.jget(sessA, base7, "RoomStart.asp", AIStart="false", RoomSecond="0")
        if txt.strip() not in ("-1", "0", ""):
            started = txt
            break
        time.sleep(1.5)
    w("- 开局: %s" % ("成功 " + started.split(",")[0] if started else "**失败**"))
    return sessA, uidA, base7, started


def make_harvester(sess, base7, outdir):
    seen = set()

    def harvest(text):
        new = []
        for m in re.finditer(r"Caijue\((\d+)\)", text or ""):
            cid = m.group(1)
            if cid in seen:
                continue
            seen.add(cid)
            try:
                rr = sess.get(base7 + "Caijue.asp", params={"ID": cid}, timeout=30,
                              headers={"Referer": base7 + "main.html"})
            except Exception:                                     # noqa: BLE001
                continue
            if not rr.content:
                continue
            os.makedirs(outdir, exist_ok=True)
            open(os.path.join(outdir, "caijue_%s.html" % cid), "wb").write(rr.content)
            info = CR.parse_caijue(rr.content)
            info["id"] = cid
            new.append(info)
            w("    ◆ 裁决#%s 距离=%s 攻级=%s 随机数=%s 结果=%s 装甲=%s 修=%s 最终=%s | 射手=%s 目标=%s"
              % (cid, info["距离"], info["攻击等级"], info["随机数"], info["战斗结果"],
                 info["装甲级别"], info["修正结果"], info["最终战果"],
                 info["射击方状态"], info["目标状态"]))
        return new

    return harvest


# ---------------- E1 机动耗时 / 通行能力 ----------------
def exp_mobility(sess, base7):
    w("")
    w("## E1 机动耗时 / 通行能力")
    units = H.parse_obj_get(CR.jget(sess, base7, "Obj_Get.asp"))
    veh = [k for k, a in sorted(units.items(), key=lambda kv: int(kv[0].split("_")[1]))
           if a.get("typeid") == "2" and str(a.get("pos") or "0") not in ("0", "")]
    if not veh:
        w("- 无可用车辆，跳过")
        return
    for unit in veh[:3]:
        u = units[unit]
        cur = int(u["pos"])
        color = u.get("color") or ""
        w("- 单位 %s (%s) 起始 mapid=%d(格号%s)" % (unit, u.get("ico"), cur, GEO.hexid(cur)))
        for i in range(8):
            frm_cell = CR.cell(cur)
            nbrs = sorted(GEO.neighbors(cur))
            to = nbrs[i % len(nbrs)]
            tc = CR.cell(to)
            try:
                st = CR.move_step(sess, base7, unit, cur, to, color)
            except Exception as e:                                # noqa: BLE001
                w("    move err %r" % (e,))
                break
            time.sleep(1.0)
            got = CR.positions(sess, base7, (unit,))[unit]
            ok = (got == to)
            row = {"unit": unit, "frm": cur, "to": to,
                   "ms": st.get("update_pos"),
                   "dEle": tc.get("elevation", 0) - frm_cell.get("elevation", 0),
                   "to_step": tc.get("step"), "to_cond": tc.get("cond"),
                   "to_hextype": tc.get("hextype"), "from_cond": frm_cell.get("cond"),
                   "ok": ok}
            RES["mobility"].append(row)
            w("    %s→%s  ms=%-5s Δ高程=%-5s to(step=%s,cond=%s,hextype=%s)  %s"
              % (GEO.hexid(cur), GEO.hexid(to), st.get("update_pos"), row["dEle"],
                 row["to_step"], row["to_cond"], row["to_hextype"],
                 "可走" if ok else "**不可走**"))
            if ok:
                cur = to


# ---------------- 选一对交战 ----------------
def pick_pair(sess, base7):
    rec = CR.snapshot(sess, base7)
    units = rec["units"]
    blue = [k for k, a in units.items() if a.get("color") == "BLUE"
            and str(a.get("blood")) not in ("0", "") and str(a.get("typeid")) in ("1", "2")]
    red = [k for k, a in units.items() if a.get("color") == "RED"
           and str(a.get("blood")) not in ("0", "") and str(a.get("typeid")) in ("1", "2")]
    pairs = sorted(((GEO.distance(int(units[a]["pos"]), int(units[t]["pos"])), a, t)
                    for a in blue for t in red), key=lambda x: x[0])
    if not pairs:
        return None, None, rec
    scored = []
    for dd, a, t in pairs:
        dh = CR.elev(units[a]["pos"]) - CR.elev(units[t]["pos"])
        bw6 = CR.best_weapon(units, a, t, min(dd, 1), dh=dh)
        lvl6 = bw6[3] if bw6 and bw6[3] is not None else -99
        scored.append((-lvl6, dd, a, t))
    scored.sort()
    _, dd, a, t = scored[0]
    return a, t, rec


def approach(sess, base7, atk, tgt, units, max_steps=60, want=1):
    steps = 0
    d0 = GEO.distance(int(units[atk]["pos"]), int(units[tgt]["pos"]))
    while steps < max_steps and (d0 > want or not los_at(units, atk, tgt)):
        ps = CR.positions(sess, base7, (atk, tgt))
        for who, foe in ((atk, tgt), (tgt, atk)):
            frm, fpos = ps.get(who), ps.get(foe)
            if frm is None or fpos is None:
                continue
            if GEO.distance(frm, fpos) <= want:
                continue
            nbrs = sorted(GEO.neighbors(frm), key=lambda n: GEO.distance(n, fpos))
            col = (units.get(who) or {}).get("color") or ""
            try:
                CR.move_step(sess, base7, who, frm, nbrs[0], col)
            except Exception:                                     # noqa: BLE001
                break
            steps += 1
        ps = CR.positions(sess, base7, (atk, tgt))
        if ps.get(atk) and ps.get(tgt):
            d0 = GEO.distance(ps[atk], ps[tgt])
            units.setdefault(atk, {})["pos"] = str(ps[atk])
            units.setdefault(tgt, {})["pos"] = str(ps[tgt])
    return steps, d0


def los_at(units, a, b):
    try:
        return CR.GAME.los(int(units[a]["pos"]), int(units[b]["pos"]))[0]
    except Exception:                                             # noqa: BLE001
        return True


def fire_once(sess, base7, atk, tgt, harvest, timeout_s=45):
    rec = CR.snapshot(sess, base7)
    units = rec["units"]
    if atk not in units or tgt not in units:
        return None
    if str((units.get(tgt) or {}).get("blood")) == "0":
        w("    (目标已歼灭)")
        return {"dead": True}
    d = GEO.distance(int(units[atk]["pos"]), int(units[tgt]["pos"]))
    dh = CR.elev(units[atk]["pos"]) - CR.elev(units[tgt]["pos"])
    bw = CR.best_weapon(units, atk, tgt, d, dh=dh)
    if not bw:
        w("    (无可用武器)")
        return None
    idx, wid, info, lvl = bw
    b0 = str((rec["dynamic"].get(tgt) or {}).get("keep", 0))
    f = CR.fire(sess, base7, atk, tgt, wid, units[atk].get("color") or "", rec)
    w("    开火 %s→%s 武器=%s(射程%d,预估等级%s) 返回=%r"
      % (atk, tgt, info[0], info[2], lvl, f.get("attack_resp")))
    t0 = time.time()
    samples = []
    while time.time() - t0 < timeout_s:
        rep = CR.jget(sess, base7, "Report_Attack.asp")
        samples += harvest(rep)
        if samples:
            break
        CR.jget(sess, base7, "ObjAjax.asp")       # 保持服务端时钟推进
        time.sleep(1)
    # ★ 开火后必须让武器"就绪"（客户端 com/ObjWeaponReady.asp），
    #   否则下一发 com/Attack.asp 返回空串（= 射击失败）。实测：成功→失败→就绪→成功。
    for _ in range(15):
        d2 = H.parse_obj_ajax(CR.jget(sess, base7, "ObjAjax.asp"))
        if str((d2.get(atk) or {}).get("att", "0")) in ("0", "", "None"):
            break
        try:
            CR.jget(sess, base7, "com/ObjWeaponReady.asp", ObjID=atk)
        except Exception:                                     # noqa: BLE001
            pass
        time.sleep(1)
    return {"dist": d, "weapon": info[0], "resp": f.get("attack_resp"),
            "dt": round(time.time() - t0, 1), "caijue": samples}


# ---------------- E2/E3 combat ----------------
def exp_combat(sess, base7, harvest, shots=8, minutes=12):
    w("")
    w("## E2/E3 攻击等级曲线(表2) + 表4 重复采样")
    deadline = time.time() + minutes * 60
    atk, tgt, rec = pick_pair(sess, base7)
    if not atk:
        w("- 无可用敌我对，跳过")
        return None
    units = rec["units"]
    w("- 交战对 %s(%s) ↔ %s(%s)" % (atk, (units[atk] or {}).get("ico"),
                                  tgt, (units[tgt] or {}).get("ico")))
    steps, d0 = approach(sess, base7, atk, tgt, units)
    w("- 逼近 %d 步后距离 %d 格" % (steps, d0))

    results = []
    # E3：同一距离重复开火
    for k in range(shots):
        if time.time() > deadline:
            break
        r = fire_once(sess, base7, atk, tgt, harvest)
        if not r or r.get("dead"):
            break
        r["phase"] = "repeat@%s" % r.get("dist")
        results.append(r)
    # E2：拉开距离再开火，取不同攻击等级
    for back in (1, 2, 3):
        if time.time() > deadline:
            break
        ps = CR.positions(sess, base7, (atk,))
        frm = ps.get(atk)
        if frm is None:
            break
        nbrs = sorted(GEO.neighbors(frm), key=lambda n: -GEO.distance(n, int(
            CR.positions(sess, base7, (tgt,))[tgt] or frm)))
        CR.move_step(sess, base7, atk, frm, nbrs[0],
                     (units.get(atk) or {}).get("color") or "")
        time.sleep(1)
        r = fire_once(sess, base7, atk, tgt, harvest)
        if r:
            r["phase"] = "distance-sweep"
            results.append(r)
    RES["combat"] = results
    return atk, tgt


# ---------------- E10 CRT 采样（距离扫描） ----------------
def move_to_distance(sess, base7, atk, tgt, want, units, max_steps=40):
    """只移动射手，让它到目标的距离尽量等于 want（用于制造不同攻击等级）。"""
    for _ in range(max_steps):
        ps = CR.positions(sess, base7, (atk, tgt))
        f, t = ps.get(atk), ps.get(tgt)
        if f is None or t is None:
            return None
        d = GEO.distance(f, t)
        if d == want:
            return d
        far = [n for n in GEO.neighbors(f) if GEO.distance(n, t) != d]
        if not far:
            return d
        nxt = min(far, key=lambda n: (abs(GEO.distance(n, t) - want), GEO.distance(n, t)))
        CR.move_step(sess, base7, atk, f, nxt, (units.get(atk) or {}).get("color") or "")
        time.sleep(0.5)
    return GEO.distance(*[CR.positions(sess, base7, (atk, tgt))[k] for k in (atk, tgt)])


def exp_crt(sess, base7, harvest, per_dist=4, minutes=18):
    """换目标 + 逐次加距离：覆盖不同攻击等级 × 多随机数（表4/表6 采样）。"""
    w("")
    w("## E10 CRT 采样（多目标 × 距离阶梯 → 攻级 × 随机数）")
    deadline = time.time() + minutes * 60
    # ★ 射手必须"对地面目标有攻击等级"——不能按射程最长挑（会挑到只带防空导弹的车，
    #   对地攻级为 None，服务端一律拒收、返回空串）。直接用与交战同款的评分选。
    atk, tgt0, rec = pick_pair(sess, base7)
    if not atk:
        w("- 无可用交战对，跳过")
        return
    units = rec["units"]
    reds = [tgt0] + [k for k, a in units.items()
                     if k != tgt0 and a.get("color") == "RED"
                     and str(a.get("blood")) not in ("0", "")
                     and str(a.get("typeid")) in ("1", "2")]
    w("- 射手 %s(%s)（按对地攻击等级选出）；候选目标 %d 个"
      % (atk, (units[atk] or {}).get("ico"), len(reds)))

    want = 1
    for tgt in reds:
        if time.time() > deadline:
            break
        chk = CR.snapshot(sess, base7)
        if atk not in chk["units"] or str(chk["units"][atk].get("blood")) == "0":
            w("- 射手已不在场，结束")
            break
        if tgt not in chk["units"] or str(chk["units"][tgt].get("blood")) == "0":
            continue
        d = move_to_distance(sess, base7, atk, tgt, want, units)
        if d is None:
            continue
        w("\n- 目标 %s(%s) 就位距离 %s 格（期望 %d）"
          % (tgt, (units[tgt] or {}).get("ico"), d, want))
        for _ in range(per_dist):
            if time.time() > deadline:
                break
            r = fire_once(sess, base7, atk, tgt, harvest, timeout_s=30)
            if not r or r.get("dead"):
                break
        want += 1
    RES["crt"] = "done"


# ---------------- E4/E5 timing ----------------
def exp_timing(sess, base7, atk, tgt, harvest, minutes=8):
    w("")
    w("## E4 压制解除时长 / E5 攻击间隔")
    if not atk:
        w("- 无交战对，跳过")
        return
    rec = CR.snapshot(sess, base7)
    units = rec["units"]
    if str((units.get(tgt) or {}).get("keep", "0"))[:1] not in ("1", "2", "3"):
        r = fire_once(sess, base7, atk, tgt, harvest, timeout_s=40)
        if r:
            RES.setdefault("timing", {})["first_shot"] = r
    # 轮询 keep 直到解除
    t0 = time.time()
    last = None
    while time.time() - t0 < minutes * 60:
        dyn = H.parse_obj_ajax(CR.jget(sess, base7, "ObjAjax.asp"))
        kv = (dyn.get(tgt) or {}).get("keep")
        if str(kv) != str(last):
            w("    t=%.0fs  %s keep=%s" % (time.time() - t0, tgt, kv))
            last = kv
        if str(kv) in ("0", "None", ""):
            break
        time.sleep(1)
    RES["timing"]["suppress_seconds"] = round(time.time() - t0, 1)
    w("- 压制观察耗时 %.0f 秒（keep 当前=%s）" % (time.time() - t0, last))


# ---------------- E8/E9 special ----------------
def exp_special(sess, base7):
    w("")
    w("## E8/E9 间瞄 / 空中 / 巡飞弹")
    rec = CR.snapshot(sess, base7)
    units = rec["units"]
    by_type = {}
    for k, a in units.items():
        by_type.setdefault(str(a.get("typeid")), []).append(k)
    w("- 单位类型分布：%s" % {t: len(v) for t, v in sorted(by_type.items())})
    for t in ("3", "4", "5"):
        if t in by_type:
            k = by_type[t][0]
            u = units[k]
            w("   typeid=%s 例：%s ico=%s color=%s pos=%s" % (t, k, u.get("ico"),
                                                            u.get("color"), u.get("pos")))
    # 间瞄：客户端 CommandJm → jmFire.asp（参数未知，做几种尝试并记录响应）
    jm_unit = by_type.get("2", [None])[0]
    if jm_unit:
        for params in ({"ObjID": jm_unit, "TarPos": units[jm_unit].get("pos")},
                       {"ObjID": jm_unit, "TarPos": units[jm_unit].get("pos"),
                        "WeaponID": 72},
                       {"ObjID": jm_unit}):
            try:
                resp = CR.jget(sess, base7, "com/jmFire.asp", **params)
            except Exception as e:                                # noqa: BLE001
                resp = "ERR %r" % (e,)
            w("   jmFire.asp %s -> %r" % (params, str(resp)[:120]))
            RES["special"].append({"probe": "jmFire", "params": params, "resp": str(resp)[:200]})
    for ep in ("com/TgList.asp", "loadInfo.asp", "Caijue.asp"):
        try:
            resp = CR.jget(sess, base7, ep)
        except Exception as e:                                    # noqa: BLE001
            resp = "ERR %r" % (e,)
        w("   GET %s -> %r" % (ep, str(resp)[:100]))


# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", type=int, default=7)
    ap.add_argument("--modes", default="mobility,combat,timing,special")
    ap.add_argument("--shots", type=int, default=8)
    ap.add_argument("--minutes", type=float, default=12)
    args = ap.parse_args()

    H.guard()
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    d = os.path.join(CAP, "experiment_%s" % time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(d, exist_ok=True)
    w("# 裁决规则实测套件 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    w("模式：%s" % ",".join(modes))

    sessA, uidA, base7, started = prep(args.room)
    if not started:
        w("!!! 开局失败，终止")
        io.open(os.path.join(d, "report.md"), "w", encoding="utf-8").write("\n".join(LOG))
        return
    harvest = make_harvester(sessA, base7, os.path.join(d, "caijue"))

    atk = tgt = None
    try:
        if "mobility" in modes:
            exp_mobility(sessA, base7)
    except Exception as e:                                        # noqa: BLE001
        w("!! mobility 异常：%r" % (e,))
    try:
        if "combat" in modes:
            r = exp_combat(sessA, base7, harvest, args.shots, args.minutes)
            if r:
                atk, tgt = r
    except Exception as e:                                        # noqa: BLE001
        w("!! combat 异常：%r" % (e,))
    try:
        if "crt" in modes:
            exp_crt(sessA, base7, harvest, per_dist=4, minutes=max(8, args.minutes))
    except Exception as e:                                        # noqa: BLE001
        w("!! crt 异常：%r" % (e,))
    try:
        if "timing" in modes:
            exp_timing(sessA, base7, atk, tgt, harvest, 6)
    except Exception as e:                                        # noqa: BLE001
        w("!! timing 异常：%r" % (e,))
    try:
        if "special" in modes:
            exp_special(sessA, base7)
    except Exception as e:                                        # noqa: BLE001
        w("!! special 异常：%r" % (e,))

    # ---- 汇总 ----
    w("")
    w("## 汇总")
    mob = RES["mobility"]
    if mob:
        ok = [r for r in mob if r["ok"]]
        w("- 机动样本 %d 条（可走 %d）：" % (len(mob), len(ok)))
        from collections import Counter
        c = Counter((r["to_step"], r["to_cond"], r["to_hextype"]) for r in ok)
        w("  可走格 (step,cond,hextype) 分布：%s" % dict(c))
        blocked = [r for r in mob if not r["ok"]]
        if blocked:
            w("  **不可走**样本：%s" % [(r["to_step"], r["to_cond"], r["dEle"]) for r in blocked])
        ms = [(r["ms"], r["dEle"], r["to_cond"]) for r in ok if str(r["ms"]).isdigit()]
        if ms:
            w("  毫秒范围 %s .. %s" % (min(int(x[0]) for x in ms), max(int(x[0]) for x in ms)))
    w("- 战斗样本 %d 条" % len(RES["combat"]))
    w("- 特殊接口探测 %d 条" % len(RES["special"]))

    io.open(os.path.join(d, "results.json"), "w", encoding="utf-8").write(
        json.dumps(RES, ensure_ascii=False, indent=1))
    io.open(os.path.join(d, "report.md"), "w", encoding="utf-8").write("\n".join(LOG))
    print("ok ->", d)


if __name__ == "__main__":
    main()
