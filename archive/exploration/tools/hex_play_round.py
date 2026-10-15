# -*- coding: utf-8 -*-
"""真打一局并全程采集信息。

流程：复位房间 -> 导演(A)进房 -> 玩家(B)进房 -> 导演开局 -> 按脚本下达动作 -> 周期性采样。

采集内容（每个 tick 一条记录，写入 timeline.jsonl）：
  User_Get（StartTime/RoomSecond/回合等）、Obj_Get+ObjAjax（单位位置/兵力/压制/车内数）、
  City_Get（夺控点归属）、Report_All（双方夺控分/兵力分/战果分/总分）、Report_Attack（战报）、
  RoomStat。

动作（各自把请求参数与响应原文记进 actions.jsonl）：
  * 机动：ComPost {"<单位>":{"move":"<frm>,<to>","speed":0}} + com/updatePos.asp + com/MoveEnd.asp
  * 射击：ComPost {"<单位>":{"attack":"<目标>","weapon":n}}（可带 track:1 = 持续打击）
  * 夺控：com/CityTake.asp

用法：
    $env:HEXWAR_USER='...'; $env:HEXWAR_PASS='...'
    $env:HEXWAR_USER2='...'; $env:HEXWAR_PASS2='...'; $env:HEXWAR_ALLOW_HTTP='1'
    py -3.13 tools/hex_play_round.py --room 7 --minutes 12
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
import hex_transport_capture as H          # noqa: E402
from engine import geometry as GEO         # noqa: E402

CAP = r"d:\兵推\7527_transport_capture"


def new_session():
    s = requests.Session()
    s.headers.update({"User-Agent": H.UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    return s


def login_as(user, pwd):
    H.USERNAME, H.PASSWORD = user, pwd
    H.S = new_session()
    return H.S, H.login()


def get(sess, url, **kw):
    kw.setdefault("timeout", 30)
    return sess.get(url, **kw)


def jget(sess, base7, path, **params):
    r = get(sess, base7 + path, params=params or None,
            headers={"Referer": base7 + "main.html"})
    return r, H.decode(r.content)


def parse_cities(html):
    out = []
    for m in re.finditer(r'id="(C_[^"]*)"[^>]*', html):
        tag = m.group(0)
        d = {"id": m.group(1)}
        for k in ("name", "pos", "flag", "l1", "ico"):
            mm = re.search(r'%s="([^"]*)"' % k, tag)
            if mm:
                d[k] = mm.group(1)
        out.append(d)
    return out


def sample(sess, base7):
    """采一次全量状态。"""
    u, ug = jget(sess, base7, "User_Get.asp", userAgent="play")
    parts = ug.split("$")
    _, obj = jget(sess, base7, "Obj_Get.asp")
    _, ajax = jget(sess, base7, "ObjAjax.asp")
    _, city = jget(sess, base7, "City_Get.asp")
    _, rep = jget(sess, base7, "Report_All.asp")
    _, atk = jget(sess, base7, "Report_Attack.asp")
    _, st = jget(sess, base7, "RoomStat.asp", RoomID=parts[5] if len(parts) > 5 else "")
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "user_get": {str(i): parts[i] for i in range(len(parts))} if len(parts) > 20 else ug,
        "units": H.parse_obj_get(obj),
        "dynamic": H.parse_obj_ajax(ajax),
        "cities": parse_cities(city),
        "report_all": " ".join(rep.split()),
        "report_attack": " ".join(atk.split()),
        "room_stat": st.strip(),
    }


def post_cmd(sess, base7, objid, color, command, task, pos_hex, map_hex=""):
    params = {"ObjID": objid, "Command": json.dumps(command, ensure_ascii=False),
              "ObjColor": color, "TaskName": task, "ObjPos": pos_hex, "MapID": map_hex}
    r = get(sess, base7 + "com/ComPost.asp", params=params,
            headers={"Referer": base7 + "main.html"})
    body = H.decode(r.content)
    _, echo = jget(sess, base7, "com/ComAjax.asp")
    m = re.search(r"(\d+)\|[^|]*\|", echo)
    com_id = m.group(1) if m else ""
    return {"params": params, "com_post": body, "comajax": echo[:400], "com_id": com_id}


def act_move(sess, base7, unit, frm, to, rec):
    """一步机动：ComPost -> updatePos -> MoveEnd。"""
    u = rec["units"].get(unit) or {}
    color = u.get("color") or ""
    step = post_cmd(sess, base7, unit, color,
                    {unit: {"move": "%d,%d" % (frm, to), "speed": 0}}, "机动",
                    GEO.hexid(frm), GEO.hexid(to))
    up, _ = jget(sess, base7, "com/updatePos.asp", ObjID=unit, MapID=to, ObjRot=180,
                 GridType=0, MapStep=1, preIDhex=GEO.hexid(frm), posIDhex=GEO.hexid(to),
                 posIDcond=0, HuiHe=0, steep=0, ComID=step["com_id"] or 1, Index=1,
                 Speed=0, RoomDay=0, RoomWeather=0, MineArea=0, GasArea=0, Bridge=0,
                 EleLow=145, EleDiv=5)
    me, _ = jget(sess, base7, "com/MoveEnd.asp", ComID=step["com_id"] or 1, ObjID=unit,
                 StageID=0, RoomSecond=0, ObjPos=GEO.hexid(frm), ObjNewPos=GEO.hexid(to),
                 MoveFlag=0)
    step["updatePos_ms"] = H.decode(up.content).strip()
    step["move_end"] = H.decode(me.content).strip()
    step["unit"] = unit
    step["frm"], step["to"] = frm, to
    return step


def act_fire(sess, base7, unit, target, weapon, rec, track=0):
    u = rec["units"].get(unit) or {}
    cmd = {unit: {"attack": target, "weapon": weapon}}
    if track:
        cmd[unit]["track"] = 1
    step = post_cmd(sess, base7, unit, u.get("color") or "", cmd,
                    "射击", GEO.hexid(int(u.get("pos") or 0)),
                    GEO.hexid(int((rec["units"].get(target) or {}).get("pos") or 0)))
    step["unit"], step["target"], step["weapon"], step["track"] = unit, target, weapon, track
    return step


def act_take_city(sess, base7, unit, rec):
    u = rec["units"].get(unit) or {}
    color = u.get("color") or ""
    stage = rec["user_get"].get("5", "") if isinstance(rec["user_get"], dict) else ""
    second = rec["user_get"].get("20", "0") if isinstance(rec["user_get"], dict) else "0"
    r = get(sess, base7 + "com/CityTake.asp", params={
        "ObjID": unit, "ObjColor": color, "StageID": stage or "0", "ObjAttack": "0",
        "ComID": "1", "RoomSecond": second},
        headers={"Referer": base7 + "main.html"})
    return {"unit": unit, "params": {"ObjID": unit, "ObjColor": color},
            "response": H.decode(r.content).strip()}


def quit_room(sess, uid):
    """尽量退出当前推演室（失败不致命）。"""
    import requests as _rq
    from urllib.parse import urlsplit
    c = _rq.cookies.create_cookie(name="UserID", value=uid or "",
                                  domain=urlsplit(H.HOST).hostname, path="/")
    sess.cookies.set_cookie(c)
    try:
        return sess.get(H.BASE + "SetUp/SetUp_Transfer/Quit.asp", timeout=30)
    except Exception:                                               # noqa: BLE001
        return None
    finally:
        sess.cookies.clear(urlsplit(H.HOST).hostname, "/", "UserID")


def in_room(sess, base7):
    """返回 (是否真的在房内, User_Get 字段)。"""
    _, ug = jget(sess, base7, "User_Get.asp", userAgent="play")
    parts = ug.split("$")
    return (len(parts) >= 21 and parts[5].strip() not in ("", "-1"), parts)


def join(sess, uid, color, room, base7):
    """(必要时退出) -> 进房 -> 校验确实在房内。"""
    quit_room(sess, uid)
    time.sleep(0.5)
    H.S = sess
    H.enter(room, color, uid)
    ok, parts = in_room(sess, base7)
    return ok, parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", type=int, default=7)
    ap.add_argument("--color2", default="RED")
    ap.add_argument("--minutes", type=float, default=12.0, help="真实时间上限（分钟）")
    ap.add_argument("--tick", type=float, default=5.0, help="采样间隔（秒）")
    args = ap.parse_args()

    H.guard()
    uA, pA = os.environ.get("HEXWAR_USER", ""), os.environ.get("HEXWAR_PASS", "")
    uB, pB = os.environ.get("HEXWAR_USER2", ""), os.environ.get("HEXWAR_PASS2", "")
    if not uB or not pB:
        sys.exit("请设置 HEXWAR_USER2 / HEXWAR_PASS2")
    base7 = "%s/WARGAMEAI%d/" % (H.HOST, args.room)
    H.BASE7 = base7
    stamp = time.strftime("%Y%m%d-%H%M%S")
    d = os.path.join(CAP, "play_round_%s" % stamp)
    os.makedirs(d, exist_ok=True)
    timeline = io.open(os.path.join(d, "timeline.jsonl"), "w", encoding="utf-8")
    actions = io.open(os.path.join(d, "actions.jsonl"), "w", encoding="utf-8")
    log = []

    def w(x=""):
        log.append(str(x))
        print(x)

    w("# 打一局采集  %s" % stamp)
    w("- 客户端目录 %s  采样间隔 %.0fs  真实时间上限 %.0f 分钟"
      % (base7, args.tick, args.minutes))

    # ---------- 1) 复位房间 ----------
    sessA, _ = login_as(uA, pA)
    url = "%s/WARGAMEAI%d/Reset/Post.asp" % (H.HOST, args.room)
    r = get(sessA, url, params={"scenarioId": "7527", "roomId": str(args.room)})
    m = re.search(r'<form[^>]*action="([^"]*)"[^>]*>(.*?)</form>', H.decode(r.content), re.S)
    if m:
        data = {}
        for im in re.finditer(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>',
                              m.group(2), re.S):
            data[im.group(1)] = im.group(2).strip()
        r2 = sessA.post(requests.compat.urljoin(url, m.group(1)), data=data, timeout=30)
        w("- 复位房间 SetUp/Reset -> %s" % r2.status_code)
    else:
        w("- 复位房间：未拿到表单（可能无需复位）")

    # ---------- 2) 两边进房（两边都必须确实在座，否则开局会返回 -1）----------
    sessA, uidA = login_as(uA, pA)
    okA, partsA = join(sessA, uidA, "NONE", args.room, base7)
    w("- A(导演 %s) 进房: %s  RoomTitle=%s"
      % (uidA, "在座" if okA else "**不在座**", partsA[14] if len(partsA) > 14 else "?"))

    sessB, uidB = login_as(uB, pB)
    okB, partsB = join(sessB, uidB, args.color2, args.room, base7)
    w("- B(%s %s) 进房: %s" % (args.color2, uidB, "在座" if okB else "**不在座**"))
    # B 再校验一次（进房后 SetUpSave 可能被拒）
    time.sleep(1)
    okB, partsB = in_room(sessB, base7)
    w("- B 复核: %s  RoomID=%s" % ("在座" if okB else "**不在座**",
                                  partsB[5] if len(partsB) > 5 else "?"))

    # ---------- 3) 开局（最多重试若干次）----------
    H.S = sessA
    started = False
    for attempt in range(6):
        for v in ({"AIStart": "false", "RoomSecond": "0"},
                  {"AIStart": "true", "RoomSecond": "0"}):
            rs = get(sessA, base7 + "RoomStart.asp", params=v,
                     headers={"Referer": base7 + "main.html"})
            txt = H.decode(rs.content)
            w("- RoomStart(第%d次) %s -> %r" % (attempt + 1, v, txt[:120]))
            if txt.strip() not in ("-1", "0", ""):
                w("  >>> 开局成功 Time1=%s" % txt.split(",")[0])
                started = True
                break
            time.sleep(1.5)
        if started:
            break
        # 开局失败时把两边重新拉一遍再试
        if not started:
            okB, _ = in_room(sessB, base7)
            if not okB:
                okB, _ = join(sessB, uidB, args.color2, args.room, base7)
                w("  - B 不在座，已重新进房：%s" % ("在座" if okB else "仍不在座"))
    if not started:
        w("  !!! 开局失败，本局数据无效（只有观测，无推演推进）")

    # 把进房过程的原始日志留档，便于排查
    io.open(os.path.join(d, "setup_log.md"), "w", encoding="utf-8").write("\n".join(H.LOG))

    # ---------- 4) 主循环 ----------
    deadline = time.time() + args.minutes * 60
    tick = 0
    history = []
    while time.time() < deadline:
        t0 = time.time()
        rec = sample(sessA, base7)
        rec["tick"] = tick
        rec["wall"] = time.strftime("%H:%M:%S")
        timeline.write(json.dumps(rec, ensure_ascii=False) + "\n")
        timeline.flush()
        history.append(rec)

        ug = rec["user_get"] if isinstance(rec["user_get"], dict) else {}
        rsec = ug.get("20", "?")
        alive = sum(1 for a in rec["units"].values() if str(a.get("blood")) != "0")
        w("tick %2d  %s  RoomSecond=%-4s 单位存活=%-3d 战报=%s"
          % (tick, rec["wall"], rsec, alive, (rec["report_attack"] or "-")[:60]))

        # ---- 脚本动作（只在开局存在时执行）----
        if ug.get("3", "").strip():
            units = rec["units"]
            dyn = rec["dynamic"]
            blue = [k for k, a in units.items()
                    if a.get("color") == "BLUE" and str(a.get("blood")) != "0" and a.get("typeid") != "4"]
            red = [k for k, a in units.items()
                   if a.get("color") == "RED" and str(a.get("blood")) != "0"]
            cities = [c for c in rec["cities"] if c.get("pos")]
            # 3.1 前 6 个 tick：蓝方一支单位逐格向红方靠拢（每 tick 走一格）
            if tick == 1 and blue:
                uid_ = sorted(blue, key=lambda k: units[k].get("ico", ""))[0]
                history_state = {"mover": uid_}
                w("  → 选定机动单位 %s (%s) @%s" % (uid_, units[uid_].get("ico"),
                                                 GEO.hexid(int(units[uid_]["pos"]))))
                io.open(os.path.join(d, "plan.json"), "w", encoding="utf-8").write(
                    json.dumps(history_state, ensure_ascii=False))
            try:
                plan = json.load(io.open(os.path.join(d, "plan.json"), encoding="utf-8"))
                mover = plan.get("mover")
            except Exception:                                       # noqa: BLE001
                mover = None
            if mover and mover in units and tick in (2, 3, 4):
                frm = int(units[mover]["pos"])
                # 朝最近的敌方单位走一格
                foe = None
                best = 999
                for t in red + blue:
                    if units[t].get("color") == units[mover].get("color"):
                        continue
                    dd = GEO.distance(frm, int(units[t]["pos"]))
                    if dd < best:
                        best, foe = dd, int(units[t]["pos"])
                if foe is not None:
                    nbrs = sorted(GEO.neighbors(frm), key=lambda n: GEO.distance(n, foe))
                    to = nbrs[0]
                    step = act_move(sessA, base7, mover, frm, to, rec)
                    step["kind"] = "move"
                    actions.write(json.dumps(step, ensure_ascii=False) + "\n")
                    actions.flush()
                    w("  → 机动 %s %s→%s updatePos=%s MoveEnd=%r"
                      % (mover, GEO.hexid(frm), GEO.hexid(to), step["updatePos_ms"],
                         step["move_end"][:40]))
            # 3.2 第 8 个 tick：蓝方对射程内目标开火
            if tick == 8 and blue and red:
                best = None
                for a in blue:
                    for t in red:
                        dd = GEO.distance(int(units[a]["pos"]), int(units[t]["pos"]))
                        if best is None or dd < best[2]:
                            best = (a, t, dd)
                if best:
                    step = act_fire(sessA, base7, best[0], best[1], 0, rec)
                    step["kind"] = "fire"
                    actions.write(json.dumps(step, ensure_ascii=False) + "\n")
                    actions.flush()
                    w("  → 射击 %s -> %s（距离 %d 格）ComPost=%r"
                      % (best[0], best[1], best[2], step["com_post"][:60]))
            # 3.3 第 12 个 tick：持续打击
            if tick == 12 and blue and red:
                a = blue[0]
                t = min(red, key=lambda x: GEO.distance(int(units[a]["pos"]),
                                                        int(units[x]["pos"])))
                step = act_fire(sessA, base7, a, t, 0, rec, track=1)
                step["kind"] = "fire_track"
                actions.write(json.dumps(step, ensure_ascii=False) + "\n")
                actions.flush()
                w("  → 持续打击 %s -> %s ComPost=%r" % (a, t, step["com_post"][:60]))
            # 3.4 第 16 个 tick：夺控
            if tick == 16 and blue and cities:
                a = blue[0]
                step = act_take_city(sessA, base7, a, rec)
                step["kind"] = "city_take"
                actions.write(json.dumps(step, ensure_ascii=False) + "\n")
                actions.flush()
                w("  → 夺控 %s 返回=%r" % (a, step["response"][:60]))

        tick += 1
        time.sleep(max(0.5, args.tick - (time.time() - t0)))

    # ---------- 5) 汇总 ----------
    first, last = history[0], history[-1]
    smry = {"round_dir": d, "ticks": len(history),
            "first": {"wall": first["wall"], "user_get": first["user_get"],
                      "report_all": first["report_all"]},
            "last": {"wall": last["wall"], "user_get": last["user_get"],
                     "report_all": last["report_all"]},
            "actions": sum(1 for _ in io.open(os.path.join(d, "actions.jsonl"), encoding="utf-8")),
            "unit_moves": []}
    # 统计每个单位在整局中的位置/兵力变化
    for uid_ in first["units"]:
        p0 = first["units"][uid_].get("pos")
        p1 = (last["units"].get(uid_) or {}).get("pos")
        b0 = first["units"][uid_].get("blood")
        b1 = (last["units"].get(uid_) or {}).get("blood")
        if str(p0) != str(p1) or str(b0) != str(b1):
            smry["unit_moves"].append({"id": uid_, "ico": first["units"][uid_].get("ico"),
                                       "color": first["units"][uid_].get("color"),
                                       "pos": [p0, p1], "blood": [b0, b1]})
    io.open(os.path.join(d, "summary.json"), "w", encoding="utf-8").write(
        json.dumps(smry, ensure_ascii=False, indent=1))
    timeline.close()
    actions.close()

    w("")
    w("## 结果")
    w("- 采样 %d 次；动作 %d 个" % (smry["ticks"], smry["actions"]))
    w("- 起始 RoomSecond=%s → 结束 RoomSecond=%s"
      % (first["user_get"].get("20") if isinstance(first["user_get"], dict) else "?",
         last["user_get"].get("20") if isinstance(last["user_get"], dict) else "?"))
    w("- 位置或兵力有变化的单位 %d 个" % len(smry["unit_moves"]))
    for mv in smry["unit_moves"][:20]:
        w("  - %s %s %s pos %s→%s blood %s→%s"
          % (mv["id"], mv["color"], mv["ico"], mv["pos"][0], mv["pos"][1],
             mv["blood"][0], mv["blood"][1]))
    w("- 起始计分: %s" % (first["report_all"] or "")[:220])
    w("- 结束计分: %s" % (last["report_all"] or "")[:220])
    io.open(os.path.join(d, "report.md"), "w", encoding="utf-8").write("\n".join(log))
    print("ok ->", d)


if __name__ == "__main__":
    main()
