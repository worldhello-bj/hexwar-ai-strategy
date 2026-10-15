# -*- coding: utf-8 -*-
"""受控实验：定死"脚本机动后服务端存的 pos 到底是什么参数"。

背景（受控结论）：
  * 只调 com/updatePos.asp **不会**移动单位（5 组参数已证）。
  * 机动后服务端把 pos 存成了 **ComPost 的 MapID 原值**（如 3435 = 目标格格号）。
  * 客户端 war.min.js：`ComPost` 的 `Command.move` = FindPath 结果（mapid 串）；
    `ObjPos`=HexID(当前 pos)、`MapID`=MapArr[...].hexid。

本实验对**不同单位**各跑一种参数组合，逐一读回 ObjAjax 的 pos，与期望 mapid 比对。

用法：
    $env:HEXWAR_USER=...; $env:HEXWAR_USER2=...; $env:HEXWAR_ALLOW_HTTP=1
    py -3.13 tools/hex_move_probe.py --room 7
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
import hex_transport_capture as H                 # noqa: E402
from engine import geometry as GEO                # noqa: E402

MAP_FILE = r"d:\兵推\snapshot\parsed\map_hexes.json"
try:
    MAPINFO = json.load(io.open(MAP_FILE, encoding="utf-8"))
except Exception:                                 # noqa: BLE001
    MAPINFO = {}


def cell(mid):
    return MAPINFO.get(str(int(mid))) or MAPINFO.get(str(mid)) or {}


def new_session():
    s = requests.Session()
    s.headers.update({"User-Agent": H.UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    return s


def login_as(user, pwd):
    H.USERNAME, H.PASSWORD = user, pwd
    H.S = new_session()
    return H.S, H.login()


def jget(s, base7, path, **params):
    r = s.get(base7 + path, params=params or None, timeout=30,
              headers={"Referer": base7 + "main.html"})
    return H.decode(r.content)


def pos_of(s, base7, unit):
    dyn = H.parse_obj_ajax(jget(s, base7, "ObjAjax.asp"))
    d = dyn.get(unit) or {}
    try:
        return int(d.get("pos"))
    except (TypeError, ValueError):
        return None


def in_room(s, base7):
    parts = jget(s, base7, "User_Get.asp", userAgent="mp").split("$")
    return (len(parts) >= 21 and parts[5].strip() not in ("", "-1"), parts)


def quit_room(s, uid):
    from urllib.parse import urlsplit
    c = requests.cookies.create_cookie(name="UserID", value=uid or "",
                                       domain=urlsplit(H.HOST).hostname, path="/")
    s.cookies.set_cookie(c)
    try:
        return s.get(H.BASE + "SetUp/SetUp_Transfer/Quit.asp", timeout=30)
    finally:
        s.cookies.clear(urlsplit(H.HOST).hostname, "/", "UserID")


def move(s, base7, unit, color, frm, to, objpos_kind, mapid_kind, do_updatepos=True):
    """objpos_kind / mapid_kind ∈ {'hexid','mapid'}。"""
    def val(kind, mid):
        return GEO.hexid(mid) if kind == "hexid" else mid

    cmdjson = json.dumps({unit: {"move": "%d,%d" % (frm, to), "speed": 0}},
                         ensure_ascii=False)
    params = {"ObjID": unit, "Command": cmdjson, "ObjColor": color, "TaskName": "机动",
              "ObjPos": str(val(objpos_kind, frm)), "MapID": str(val(mapid_kind, to))}
    body = jget(s, base7, "com/ComPost.asp", **params)
    echo = jget(s, base7, "com/ComAjax.asp")
    m = re.search(r"(\d+)\|[^|]*\|", echo)
    com_id = m.group(1) if m else ""
    tc = cell(to)
    up = ""
    if do_updatepos:
        up = jget(s, base7, "com/updatePos.asp", ObjID=unit, MapID=to, ObjRot=180,
                  GridType=tc.get("hextype", 1), MapStep=tc.get("step", 1),
                  preIDhex=cell(frm).get("hex", 0), posIDhex=tc.get("hex", 0),
                  posIDcond=tc.get("cond", 0), HuiHe=1, steep=0, ComID=com_id or 0,
                  Index=1, Speed=0, RoomDay=0, RoomWeather=0, MineArea=0, GasArea=0,
                  Bridge=0, EleLow=145, EleDiv=5)
    # ★ 第三步：MoveEnd 才是"提交这一步"（客户端 CommandMoveEnd，ObjPos/ObjNewPos 用 mapid）
    me = jget(s, base7, "com/MoveEnd.asp", ComID=com_id or 1, ObjID=unit,
              StageID=0, RoomSecond=0, ObjPos=frm, ObjNewPos=to, MoveFlag=0)
    return {"unit": unit, "frm": frm, "to": to, "com_post": body, "com_id": com_id,
            "update_pos": up.strip() if isinstance(up, str) else up,
            "move_end": me.strip() if isinstance(me, str) else me}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", type=int, default=7)
    ap.add_argument("--color2", default="RED")
    args = ap.parse_args()

    H.guard()
    uA, pA = os.environ.get("HEXWAR_USER", ""), os.environ.get("HEXWAR_PASS", "")
    uB, pB = os.environ.get("HEXWAR_USER2", ""), os.environ.get("HEXWAR_PASS2", "")
    if not uB or not pB:
        sys.exit("请设置 HEXWAR_USER2 / HEXWAR_PASS2")
    base7 = "%s/WARGAMEAI%d/" % (H.HOST, args.room)
    H.BASE7 = base7
    out = []
    d = r"d:\兵推\7527_transport_capture\move_probe_%s" % time.strftime("%Y%m%d-%H%M%S")
    os.makedirs(d, exist_ok=True)

    def w(x=""):
        out.append(str(x))
        print(x)

    w("# 机动参数受控实验 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))

    # ---- 准备一局 ----
    sessA, _ = login_as(uA, pA)
    url = "%s/WARGAMEAI%d/Reset/Post.asp" % (H.HOST, args.room)
    m = re.search(r'<form[^>]*action="([^"]*)"[^>]*>(.*?)</form>',
                  jget(sessA, "%s/WARGAMEAI%d/" % (H.HOST, args.room), "Reset/Post.asp",
                       scenarioId=7527, roomId=args.room), re.S)
    if m:
        data = {}
        for im in re.finditer(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>',
                              m.group(2), re.S):
            data[im.group(1)] = im.group(2).strip()
        r2 = sessA.post(requests.compat.urljoin(url, m.group(1)), data=data, timeout=30)
        w("- 复位房间 -> %s" % r2.status_code)

    sessA, uidA = login_as(uA, pA)
    quit_room(sessA, uidA)
    time.sleep(0.5)
    H.S = sessA
    H.enter(args.room, "NONE", uidA)
    okA, _ = in_room(sessA, base7)
    w("- A(导演 %s) 在座=%s" % (uidA, okA))

    sessB, uidB = login_as(uB, pB)
    quit_room(sessB, uidB)
    time.sleep(0.5)
    H.S = sessB
    H.enter(args.room, args.color2, uidB)
    okB, _ = in_room(sessB, base7)
    w("- B(%s %s) 在座=%s" % (args.color2, uidB, okB))

    started = ""
    for attempt in range(5):
        txt = jget(sessA, base7, "RoomStart.asp", AIStart="false", RoomSecond="0")
        w("- RoomStart 第%d次 -> %r" % (attempt + 1, txt[:90]))
        if txt.strip() not in ("-1", "0", ""):
            started = txt
            break
        time.sleep(1.5)
    if not started:
        w("!!! 开局失败")
        io.open(os.path.join(d, "report.md"), "w", encoding="utf-8").write("\n".join(out))
        return
    w("- 开局成功")

    units = H.parse_obj_get(jget(sessA, base7, "Obj_Get.asp"))
    # 取地面车辆（typeid=2）、有 pos 的，按编号排序，尽量分散
    cand = [k for k, a in sorted(units.items(), key=lambda kv: int(kv[0].split("_")[1]))
            if a.get("typeid") == "2" and str(a.get("pos") or "0") not in ("0", "")]

    variants = [
        ("V1 ComPost(ObjPos=格号,MapID=格号) +更新pos", "hexid", "hexid", True),
        ("V2 ComPost(ObjPos=格号,MapID=mapid) +更新pos", "hexid", "mapid", True),
        ("V3 ComPost(ObjPos=mapid,MapID=mapid) +更新pos", "mapid", "mapid", True),
        ("V4 ComPost(ObjPos=格号,MapID=mapid) 不更新pos", "hexid", "mapid", False),
        ("V5 ComPost(ObjPos=格号,MapID=格号) 不更新pos", "hexid", "hexid", False),
    ]
    if len(cand) < len(variants):
        w("候选车辆不足（%d）" % len(cand))
    w("")

    for i, (name, opk, mk, dup) in enumerate(variants):
        if i >= len(cand):
            break
        unit = cand[i]
        u = units[unit]
        cur = int(u["pos"])
        nbr = sorted(GEO.neighbors(cur))[0]
        w("== %s" % name)
        w("   单位 %s (%s)  起始 mapid=%d(格号%s)" % (unit, u.get("ico"), cur, GEO.hexid(cur)))
        res = move(sessA, base7, unit, u.get("color") or "", cur, nbr, opk, mk, dup)
        w("   ComPost -> %r   ComID=%s   updatePos=%r   MoveEnd=%r"
          % (res["com_post"], res["com_id"], res["update_pos"], res.get("move_end")))
        time.sleep(2.5)
        got = pos_of(sessA, base7, unit)
        w("   期望 mapid=%d(格号%s) | 服务端 pos=%s -> %s"
          % (nbr, GEO.hexid(nbr), got,
             "✔ 正确" if str(got) == str(nbr) else "✘ 错误"))
        w("")

    io.open(os.path.join(d, "report.md"), "w", encoding="utf-8").write("\n".join(out))
    print("done ->", d)


if __name__ == "__main__":
    main()
