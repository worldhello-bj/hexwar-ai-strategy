# -*- coding: utf-8 -*-
"""实测：把乘员**真正装进**载具（ObjInto）后，载具被歼时乘员还在不在、分是否被扣。

为什么必须单独做：想定**开局时乘员与载具同格**（都是上阵单位），所以"打掉载具"
并不会碰到乘员 —— 这解释不了"车内乘员"的行为。要先把乘员装上车再打。

流程（同一次 run）：
    A) 复位房间 → 导演 + 红方进房 → 开局
    B) 记录开局：单位表 + 计分页（预期 红 354 / 蓝 234）
    C) 把红方同格的乘员装进 ZBD100（ComPost {"<乘员>":{"inside":"<车>"}} + ObjInto.asp）
       确认它变成 pos=0 / blood=0 / color=''，并存一次计分页
    D) 蓝方坦克机动到相邻格，连续开火打到该车 blood=0
    E) 逐 tick 采计分页；车死后：
       - 再看乘员记录（还在不在、字段怎么变）
       - 试一次 Obj2_Out，看乘员还能不能被放出来

判读：
    * RED 只掉车体的 40 ⇒ 车内乘员**不随车被歼扣分**（与现行 v4 口径一致）
    * RED 掉 40 + 乘员分 ⇒ 乘员随车被歼（手册 4.6.3(3) / 旧口径）

产物：`7527_transport_capture/loadkill_<时间戳>/`（report.md / timeline.jsonl / actions.jsonl）

用法：
    $env:HEXWAR_USER='...'; $env:HEXWAR_PASS='...'; $env:HEXWAR_USER2='...'; $env:HEXWAR_PASS2='...'
    $env:HEXWAR_ALLOW_HTTP='1'
    py -3.13 tools/hex_load_kill_probe.py --room 7 --minutes 18
"""
import argparse
import io
import json
import os
import re
import sys
import time
from urllib.parse import urlsplit

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"d:\兵推")
import hex_transport_capture as H            # noqa: E402
import hex_play_round as P                   # noqa: E402
import hex_combat_round as C                 # noqa: E402
import hex_score_probe as S                  # noqa: E402
from engine import geometry as GEO           # noqa: E402

CAP = r"d:\兵推\7527_transport_capture"
PRACTICE_HOSTS = ("www.hexwar.cn",)
CAR_ICO = "ZBD100"          # 红方火力支援车（score 10 / blood 4）


def com_post(sess, base7, objid, color, command, task, pos_hex):
    """ComPost 受理 + ComAjax 取回 ComID（两段式的第一段）。"""
    params = {"ObjID": objid, "Command": json.dumps(command, ensure_ascii=False),
              "ObjColor": color, "TaskName": task, "ObjPos": pos_hex, "MapID": ""}
    r = sess.get(base7 + "com/ComPost.asp", params=params, timeout=30,
                 headers={"Referer": base7 + "main.html"})
    body = H.decode(r.content)
    ra = sess.get(base7 + "com/ComAjax.asp", timeout=30,
                  headers={"Referer": base7 + "main.html"})
    echo = H.decode(ra.content)
    m = re.search(r"(\d+)\|[^|]*\|", echo)
    return body, echo, (m.group(1) if m else "")


def pick_shooter(units, target):
    """选一辆能对 `target` 打出战果的蓝方车辆（按贴到相邻格时的预期攻级最高）。"""
    best = None
    for k, a in units.items():
        if a.get("color") != "BLUE" or str(a.get("blood")) in ("0", ""):
            continue
        if str(a.get("typeid")) not in ("1", "2"):
            continue
        pick = C.best_weapon(units, k, target, 1)
        if not pick or pick[3] is None:
            continue
        key = -pick[3]
        if best is None or key < best[0]:
            best = (key, k, pick)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", type=int, default=7)
    ap.add_argument("--minutes", type=float, default=18.0)
    ap.add_argument("--tick", type=float, default=1.0)
    ap.add_argument("--max-move", type=int, default=140)
    ap.add_argument("--max-shots", type=int, default=20)
    args = ap.parse_args()

    if urlsplit(H.HOST).hostname not in PRACTICE_HOSTS:
        sys.exit("只允许练习服 %s" % (PRACTICE_HOSTS,))
    H.guard()
    uA, pA = os.environ.get("HEXWAR_USER", ""), os.environ.get("HEXWAR_PASS", "")
    uB, pB = os.environ.get("HEXWAR_USER2", ""), os.environ.get("HEXWAR_PASS2", "")
    if not uB or not pB:
        sys.exit("请设置 HEXWAR_USER2 / HEXWAR_PASS2")

    base7 = "%s/WARGAMEAI%d/" % (H.HOST, args.room)
    H.BASE7 = base7
    stamp = time.strftime("%Y%m%d-%H%M%S")
    d = os.path.join(CAP, "loadkill_%s" % stamp)
    os.makedirs(d, exist_ok=True)
    timeline = io.open(os.path.join(d, "timeline.jsonl"), "w", encoding="utf-8")
    actions = io.open(os.path.join(d, "actions.jsonl"), "w", encoding="utf-8")
    log = []

    def w(x=""):
        log.append(str(x))
        print(x)

    def log_action(o):
        actions.write(json.dumps(o, ensure_ascii=False) + "\n")
        actions.flush()

    w("# 车内乘员 vs 载具被歼  实测  %s" % stamp)
    # ---------- 复位 / 进房 / 开局（同 hex_flip_probe）----------
    sessA, _ = P.login_as(uA, pA)
    url = "%s/WARGAMEAI%d/Reset/Post.asp" % (H.HOST, args.room)
    r = P.get(sessA, url, params={"scenarioId": "7527", "roomId": str(args.room)})
    m = re.search(r'<form[^>]*action="([^"]*)"[^>]*>(.*?)</form>', H.decode(r.content), re.S)
    if m:
        data = {}
        for im in re.finditer(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>',
                              m.group(2), re.S):
            data[im.group(1)] = im.group(2).strip()
        post = sessA.post(requests.compat.urljoin(url, m.group(1)), data=data, timeout=30)
        w("- 复位房间 -> %s" % post.status_code)
    sessA, uidA = P.login_as(uA, pA)
    okA, _ = P.join(sessA, uidA, "NONE", args.room, base7)
    w("- A(导演 %s) 进房: %s" % (uidA, "在座" if okA else "不在座"))
    sessB, uidB = P.login_as(uB, pB)
    P.join(sessB, uidB, "RED", args.room, base7)
    time.sleep(1)
    okB, _ = P.in_room(sessB, base7)
    w("- B(RED %s) 进房: %s" % (uidB, "在座" if okB else "不在座"))
    H.S = sessA
    started = False
    for attempt in range(6):
        for v in ({"AIStart": "false", "RoomSecond": "0"},
                  {"AIStart": "true", "RoomSecond": "0"}):
            rs = P.get(sessA, base7 + "RoomStart.asp", params=v,
                       headers={"Referer": base7 + "main.html"})
            txt = H.decode(rs.content)
            w("- RoomStart(第%d次) -> %r" % (attempt + 1, txt[:90]))
            if txt.strip() not in ("-1", "0", ""):
                started = True
                break
            time.sleep(1.5)
        if started:
            break
    if not started:
        w("  !!! 开局失败")
    io.open(os.path.join(d, "setup_log.md"), "w", encoding="utf-8").write("\n".join(H.LOG))

    deadline = time.time() + args.minutes * 60
    tick = 0
    last_score = None
    changes = []
    car = car_hex = crew = None
    shooter = None
    weapon = None
    stage = "load"
    shots = moves = 0
    loaded_at = killed_at = None
    crew_seen_after = None
    unload_try = None

    while time.time() < deadline:
        t0 = time.time()
        rec = P.sample(sessA, base7)
        rec["tick"] = tick
        rec["wall"] = time.strftime("%H:%M:%S")
        rec["score"] = S.parse_score(rec["report_all"])
        units = rec["units"]
        cities = [c for c in rec["cities"] if c.get("pos")]
        if car and shooter:
            live = C.positions(sessA, base7, [car, shooter, crew] if crew else [car, shooter]) or {}
            for k, v in live.items():
                if v:
                    units.setdefault(k, {})["pos"] = str(v)
        rec["car"] = {k: (units.get(car) or {}).get(k) for k in ("blood", "pos", "sons", "color")} if car else None
        rec["crew"] = ({k: (units.get(crew) or {}).get(k)
                        for k in ("blood", "pos", "color", "pos2", "ico")} if crew else None)
        timeline.write(json.dumps(rec, ensure_ascii=False) + "\n")
        timeline.flush()

        cur = S.flat(rec["score"])
        if cur != last_score:
            def g(k, side):
                v = (rec["score"] or {}).get(k)
                return "-" if not v else v[side]
            w("tick %-3d %s [%s] 兵力 红%s/蓝%s  歼煍 红%s/蓝%s  夺控 红%s/蓝%s"
              % (tick, rec["wall"], stage, g("remaining", "red"), g("remaining", "blue"),
                 g("killed", "red"), g("killed", "blue"),
                 g("captured", "red"), g("captured", "blue")))
            changes.append({"tick": tick, "wall": rec["wall"], "flat": cur,
                            "stage": stage, "score": rec["score"],
                            "car_blood": (units.get(car) or {}).get("blood") if car else None,
                            "crew": rec["crew"]})
            last_score = cur

        if not cities:
            tick += 1
            time.sleep(max(0.2, args.tick - (time.time() - t0)))
            continue

        # ---------- B/C：找车 + 找同格乘员 → 装车 ----------
        if stage == "load":
            if car is None:
                cars = [k for k, a in units.items()
                        if a.get("ico") == CAR_ICO and a.get("color") == "RED"
                        and str(a.get("blood")) not in ("0", "")]
                if not cars:
                    w("- 找不到红方 %s，收工" % CAR_ICO)
                    break
                car = sorted(cars)[0]
                car_hex = int(units[car]["pos"])
                same = [k for k, a in units.items()
                        if str(a.get("pos")) == str(car_hex) and k != car
                        and str(a.get("typeid")) == "1" and a.get("color") == "RED"]
                w("→ 载具 %s(%s) @%s，同格红方人员: %s"
                  % (car, units[car].get("ico"), GEO.hexid(car_hex),
                     [(k, units[k].get("ico")) for k in same] or "无"))
                if not same:
                    w("- 同格没有可装的红方人员，收工")
                    break
                crew = sorted(same)[0]
                w("  选乘员 %s (%s) blood=%s"
                  % (crew, units[crew].get("ico"), units[crew].get("blood")))
            else:
                body, echo, com_id = com_post(sessA, base7, crew,
                                              (units.get(crew) or {}).get("color") or "RED",
                                              {crew: {"inside": car}}, "上车", GEO.hexid(car_hex))
                r_in = sessA.get(base7 + "com/ObjInto.asp", timeout=30,
                                 params={"ObjID": crew, "CarID": car, "ComID": com_id},
                                 headers={"Referer": base7 + "main.html"})
                log_action({"kind": "obj_into", "unit": crew, "car": car,
                            "com_post": body[:80], "comajax": echo[:160], "com_id": com_id,
                            "obj_into": H.decode(r_in.content)[:60]})
                w("  上车 ComPost=%r  ObjInto=%r" % (body[:60], H.decode(r_in.content)[:60]))
                stage = "verify"
                shots = 0
        elif stage == "verify":
            c_blood = (units.get(crew) or {}).get("blood")
            alive = str(c_blood) not in ("0", "0.0", "", "None")
            w("  上车后：乘员 %s pos=%s blood=%s color=%r（车内 = blood 0 且 color 空）"
              % (crew, (units.get(crew) or {}).get("pos"), c_blood,
                 (units.get(crew) or {}).get("color")))
            if alive:
                w("  ! 乘员看起来还在车上外（blood 非 0），下一 tick 再看")
            pick = pick_shooter(units, car)
            if not pick:
                w("- 找不到能打这辆车的蓝方射手，收工")
                break
            _k, shooter, wp = pick
            weapon = wp[1]
            w("→ 蓝方射手 %s (%s)，武器 %s（贴到相邻格预期攻级 %s）"
              % (shooter, units[shooter].get("ico"), wp[2][0], wp[3]))
            loaded_at = tick
            stage = "approach"
        elif stage == "approach":
            frm = int(units[shooter]["pos"])
            tpos = int(units[car]["pos"] or car_hex)
            dist = GEO.distance(frm, tpos)
            if dist <= 1:
                stage = "kill"
            elif moves >= args.max_move:
                w("- 机动步数用尽（距 %d），收工" % dist)
                break
            else:
                to, st = S.step_toward(sessA, base7, shooter, frm, tpos, rec, log_action)
                if to:
                    moves += 1
                    w("  → 接近 %s %s→%s（距车 %d）"
                      % (shooter, GEO.hexid(frm), GEO.hexid(to), dist))
                else:
                    w("  ! %s 无法接近" % shooter)
                    break
        elif stage in ("kill", "after"):
            car_blood = str((units.get(car) or {}).get("blood"))
            if car_blood in ("0", "0.0", "None"):
                if killed_at is None:
                    killed_at = tick
                    w("★★ 载具 %s 已被歼（tick %d）；继续采样并试一次下车" % (car, tick))
                    stage = "after"
                # 车死后：看乘员记录 + 试一次 Obj2_Out
                crew_seen_after = dict(units.get(crew) or {})
                w("  车死后乘员记录：pos=%s blood=%s color=%r pos2=%s 存在=%s"
                  % (crew_seen_after.get("pos"), crew_seen_after.get("blood"),
                     crew_seen_after.get("color"), crew_seen_after.get("pos2"),
                     crew in units))
                if unload_try is None:
                    body2, echo2, com_id2 = com_post(sessA, base7, car, "RED",
                                                     {car: {"off": 1}}, "下车", GEO.hexid(car_hex))
                    r2 = sessA.get(base7 + "com/Obj2_Out.asp", timeout=30,
                                   params={"ObjID": car, "ObjTypeID": "1", "Time1": "",
                                           "ComID": com_id2, "ObjStack": "0"},
                                   headers={"Referer": base7 + "main.html"})
                    unload_try = {"com_post": body2[:80], "comajax": echo2[:160],
                                  "com_id": com_id2, "obj2_out": H.decode(r2.content)[:60]}
                    log_action({"kind": "obj2_out", "car": car, **unload_try})
                    w("  试下车 Obj2_Out=%r（看能否把乘员放出来）"
                      % H.decode(r2.content)[:60])
                if tick > (killed_at or tick) + 12:
                    break
            else:
                if shots >= args.max_shots:
                    w("- 达到最大开火次数，收工")
                    break
                frm = int(units[shooter]["pos"])
                tpos = int(units[car]["pos"] or car_hex)
                dist = GEO.distance(frm, tpos)
                pick = C.best_weapon(units, shooter, car, dist)
                if not pick or pick[3] is None:
                    w("- 武器类型不匹配（攻级 None），收工以免空打")
                    break
                idx, wid, info, lvl = pick
                rdy = S.weapon_ready(sessA, base7, shooter)
                step = C.fire(sessA, base7, shooter, car, wid,
                              units[shooter].get("color"), rec)
                shots += 1
                log_action({"kind": "fire", "weapon": wid, "weapon_name": info[0],
                            "expected_level": lvl, "weapon_ready": rdy, **step})
                w("  → 开火#%d %s→%s 武器 %s 距%d 预期攻级=%s 返回=%r 车血=%s 乘员血=%s"
                  % (shots, shooter, car, info[0], dist, lvl,
                     str(step.get("attack_resp"))[:40],
                     (units.get(car) or {}).get("blood"),
                     (units.get(crew) or {}).get("blood")))
        tick += 1
        time.sleep(max(0.2, args.tick - (time.time() - t0)))

    io.open(os.path.join(d, "score_changes.json"), "w", encoding="utf-8").write(
        json.dumps(changes, ensure_ascii=False, indent=1))
    timeline.close()
    actions.close()
    w("")
    w("## 结果（%d tick）" % tick)
    w("- 载具 %s  乘员 %s（装车 tick=%s，被歼 tick=%s）" % (car, crew, loaded_at, killed_at))
    w("- 计分页变化 %d 次：" % len(changes))
    for ch in changes:
        s = ch["score"]

        def g(k, side):
            v = (s or {}).get(k)
            return "-" if not v else v[side]
        w("  - tick %-3d [%s] 兵力 红%s/蓝%s 歼煍 红%s/蓝%s"
          % (ch["tick"], ch["stage"], g("remaining", "red"), g("remaining", "blue"),
             g("killed", "red"), g("killed", "blue")))
    if crew_seen_after is not None:
        w("- 车死后乘员记录：%s" % json.dumps(crew_seen_after, ensure_ascii=False))
    if unload_try:
        w("- 车死后试下车：Obj2_Out=%r" % unload_try.get("obj2_out"))
    io.open(os.path.join(d, "report.md"), "w", encoding="utf-8").write("\n".join(log))
    print("ok ->", d)


if __name__ == "__main__":
    main()
