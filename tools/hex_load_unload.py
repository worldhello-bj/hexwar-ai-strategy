# -*- coding: utf-8 -*-
"""完整"装卸循环"采集：上车(ObjInto) -> 车内状态 -> 下车(Obj2_Out) -> 恢复。

前提：房间已开局（Time1 非空）且乘员与载具同格（想定初始就是如此）。
跑法（账号 A 需已在房内，脚本会按 PortID 跟到对应客户端目录）：

    $env:HEXWAR_USER='...'; $env:HEXWAR_PASS='...'; $env:HEXWAR_ALLOW_HTTP='1'
    py -3.13 tools/hex_load_unload.py --room 7

产物写到 7527_transport_capture/load_unload_*/ 下。
"""
import argparse
import io
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hex_transport_capture as H   # noqa: E402

CAP = r"d:\兵推\7527_transport_capture"

# 想定 7527 初始：蓝方每个装甲车同格有一个步兵班；红方每个火力支援车同格有
# 步兵班(人)+无人察打车(车)+旋翼无人机+巡飞弹。用 ico 定位，避免写死编号。
SAMPLES = [
    # (标签, 载具ico, 载具所属 army 关键字, 乘员ico, 乘员类型码 off, 动作)
    ("blue_armored", "M113TW", "A连", "COD-M4", 1),
    ("red_support", "ZBD100", "1连", "PLA2-191", 1),
    ("red_support_ugvs", "ZBD100", "1连", "UGVS", 2),
]


def snapshot(sess, base7, tag):
    ug = H.decode(sess.get(base7 + "User_Get.asp", params={"userAgent": "lu"}, timeout=30,
                           headers={"Referer": base7 + "main.html"}).content)
    parts = ug.split("$")
    st = sess.get(base7 + "Obj_Get.asp", timeout=30, headers={"Referer": base7 + "main.html"})
    units = H.parse_obj_get(H.decode(st.content))
    dy = sess.get(base7 + "ObjAjax.asp", timeout=30, headers={"Referer": base7 + "main.html"})
    dyn = H.parse_obj_ajax(H.decode(dy.content))
    rep = H.decode(sess.get(base7 + "Report_All.asp", timeout=30,
                            headers={"Referer": base7 + "main.html"}).content)
    return {"captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "tag": tag,
            "session": {str(i): parts[i] for i in range(min(30, len(parts)))},
            "static_units": units, "dynamic_units": dyn,
            "report_all": " ".join(rep.split())[:2000]}


def find_units(units, car_ico, army_kw):
    cars = [o for o, a in units.items() if a.get("ico") == car_ico and army_kw in (a.get("army") or "")]
    return cars


def same_hex_units(units, pos, ico):
    return [o for o, a in units.items() if str(a.get("pos")) == str(pos) and a.get("ico") == ico]


def com_post(sess, base7, objid, color, command, task, pos_hex):
    params = {"ObjID": objid, "Command": json.dumps(command, ensure_ascii=False),
              "ObjColor": color, "TaskName": task, "ObjPos": pos_hex, "MapID": ""}
    r = sess.get(base7 + "com/ComPost.asp", params=params, timeout=30,
                 headers={"Referer": base7 + "main.html"})
    body = H.decode(r.content)
    ra = sess.get(base7 + "com/ComAjax.asp", timeout=30, headers={"Referer": base7 + "main.html"})
    echo = H.decode(ra.content)
    com_id = ""
    m = __import__("re").search(r"(\d+)\|[^|]*\|", echo)
    if m:
        com_id = m.group(1)
    return body, echo, com_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", type=int, default=7)
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    H.guard()
    uid = H.login()
    base7 = "%s/WARGAMEAI%d/" % (H.HOST, args.room)
    H.BASE7 = base7
    sess = H.S
    out = []
    out.append("# 完整装卸循环采集")
    out.append("- 客户端目录: %s" % base7)

    s0 = snapshot(sess, base7, "初始")
    if len(s0["session"]) < 21:
        sys.exit("未在房内（User_Get 字段不足），请先 enter")
    out.append("- StartTime=%s RoomSecond=%s"
               % (s0["session"]["3"], s0["session"]["20"]))
    if not s0["session"]["3"].strip():
        out.append("- ⚠️ 推演未开始（StartTime 为空）")

    os.makedirs(CAP, exist_ok=True)
    io.open(os.path.join(CAP, "load_unload_initial.json"), "w", encoding="utf-8").write(
        json.dumps(s0, ensure_ascii=False, indent=1))

    for label, car_ico, army_kw, crew_ico, off in SAMPLES:
        out.append("")
        out.append("## %s：%s(%s) 与 %s" % (label, car_ico, army_kw, crew_ico))
        cars = find_units(s0["static_units"], car_ico, army_kw)
        if not cars:
            out.append("- 未找到载具，跳过")
            continue
        car = sorted(cars)[0]
        car_hex = s0["static_units"][car].get("pos")
        crews = same_hex_units(s0["static_units"], car_hex, crew_ico)
        if not crews:
            out.append("- 载具 %s 同格没有 %s，跳过" % (car, crew_ico))
            continue
        unit = sorted(crews)[0]
        color = s0["static_units"][car].get("color")
        out.append("- 载具 %s @%s，同格乘员 %s" % (car, car_hex, unit))

        d = os.path.join(CAP, "load_unload_%s" % label)
        os.makedirs(d, exist_ok=True)
        io.open(os.path.join(d, "before.json"), "w", encoding="utf-8").write(
            json.dumps(s0, ensure_ascii=False, indent=1))

        # ---- 1) 上车 ----
        body, echo, com_id = com_post(sess, base7, unit, color,
                                      {unit: {"inside": car}}, "上车", _hex(car_hex))
        r = sess.get(base7 + "com/ObjInto.asp", timeout=30,
                     params={"ObjID": unit, "CarID": car, "ComID": com_id},
                     headers={"Referer": base7 + "main.html"})
        out.append("- 上车 ComPost=%r  ComAjax=%r  ObjInto=%r"
                   % (body[:80], echo[:120], H.decode(r.content)[:80]))
        time.sleep(2)
        s1 = snapshot(sess, base7, "上车后")
        io.open(os.path.join(d, "after_load.json"), "w", encoding="utf-8").write(
            json.dumps(s1, ensure_ascii=False, indent=1))
        out.append("  上车后：载具 sons=%s  乘员 pos=%s blood=%s color=%r"
                   % (s1["static_units"][car].get("sons"),
                      s1["static_units"][unit].get("pos"), s1["static_units"][unit].get("blood"),
                      s1["static_units"][unit].get("color")))

        # ---- 2) 下车 ----
        body2, echo2, com_id2 = com_post(sess, base7, car, color,
                                        {car: {"off": off}}, "下车", _hex(car_hex))
        r2 = sess.get(base7 + "com/Obj2_Out.asp", timeout=30,
                      params={"ObjID": car, "ObjTypeID": str(off), "Time1": "",
                              "ComID": com_id2, "ObjStack": "0"},
                      headers={"Referer": base7 + "main.html"})
        out.append("- 下车 ComPost=%r  ComAjax=%r  Obj2_Out=%r"
                   % (body2[:80], echo2[:120], H.decode(r2.content)[:80]))
        time.sleep(2)
        s2 = snapshot(sess, base7, "下车后")
        io.open(os.path.join(d, "after_unload.json"), "w", encoding="utf-8").write(
            json.dumps(s2, ensure_ascii=False, indent=1))
        new_ids = sorted(set(s2["static_units"]) - set(s1["static_units"]),
                         key=lambda x: int(x.split("_")[1]))
        out.append("  下车后：载具 sons=%s  新增编号=%s" % (s2["static_units"][car].get("sons"),
                                                        new_ids))
        for nid in new_ids:
            n = s2["static_units"][nid]
            out.append("    %s id2=%s %s %s pos=%s blood=%s car=%s" % (
                nid, n.get("id2"), n.get("name"), n.get("ico"), n.get("pos"),
                n.get("blood"), n.get("car")))
        io.open(os.path.join(d, "action.txt"), "w", encoding="utf-8").write(
            "载具: %s (%s %s) 格=%s\n乘员: %s (%s)\noff=%d\n"
            "上车: ComPost {\"%s\":{\"inside\":\"%s\"}} + com/ObjInto.asp ComID=%s\n"
            "下车: ComPost {\"%s\":{\"off\":%d}} + com/Obj2_Out.asp ComID=%s\n"
            "上车后 载具sons=%s；下车后 载具sons=%s；新生成编号=%s\n"
            % (car, car_ico, s0["static_units"][car].get("army"), car_hex, unit, crew_ico, off,
               unit, car, com_id, car, off, com_id2,
               s1["static_units"][car].get("sons"), s2["static_units"][car].get("sons"),
               ",".join(new_ids) or "无"))
        s0 = s2

    io.open(os.path.join(CAP, "load_unload_log.md"), "w", encoding="utf-8").write("\n".join(out))
    print("ok ->", os.path.join(CAP, "load_unload_log.md"))


def _hex(pos):
    """pos -> 显示格号 RRCC（与客户端 HexID 一致）。"""
    try:
        pos = int(pos)
        b = pos // 10000
        c = pos % 2
        d = "%02d" % ((2 * b) if c == 0 else (2 * b + 1))
        a = int((pos - 10000 * b) / 2 + 0.5)
        if c == 1:
            a -= 1
        return d + "%02d" % a
    except Exception:                                               # noqa: BLE001
        return ""


if __name__ == "__main__":
    main()
