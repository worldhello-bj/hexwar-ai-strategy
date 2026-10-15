# -*- coding: utf-8 -*-
"""两个账号凑一局（正确顺序）：复位房间 -> A 当导演进房 -> B 当玩家进房 -> A 开局。

账号从环境变量读：
    HEXWAR_USER  / HEXWAR_PASS    -> A（导演）
    HEXWAR_USER2 / HEXWAR_PASS2   -> B（玩家，阵营由命令行第 1 个参数指定，默认 RED）

顺序很关键：**推演一开始就不允许中途进入**，所以两边必须先都在座，再由导演开局。
"""
import io
import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, r"d:\兵推\tools")
import hex_transport_capture as H   # noqa: E402

ROOM = int(os.environ.get("HEXWAR_ROOM", "7"))
CAP = r"d:\兵推\7527_transport_capture"
out = []


def new_session():
    s = requests.Session()
    s.headers.update({"User-Agent": H.UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    return s


def login_as(user, pwd):
    H.USERNAME, H.PASSWORD = user, pwd
    H.S = new_session()
    return H.S, H.login()


def state(sess, base7, tag):
    """抓一份当前状态：会话参数 + 静态/动态单位 + 计分，返回 dict。"""
    ug = H.decode(sess.get(base7 + "User_Get.asp", params={"userAgent": "2p"}, timeout=30,
                           headers={"Referer": base7 + "main.html"}).content)
    parts = ug.split("$")
    if len(parts) < 21:
        out.append("[%s] User_Get 未进房：%r" % (tag, parts[:4]))
        return None
    st = sess.get(base7 + "Obj_Get.asp", timeout=30, headers={"Referer": base7 + "main.html"})
    io.open(os.path.join(CAP, "raw_Obj_Get_%s.bin" % tag), "wb").write(st.content)
    units = H.parse_obj_get(H.decode(st.content))
    dy = sess.get(base7 + "ObjAjax.asp", timeout=30, headers={"Referer": base7 + "main.html"})
    dyn = H.parse_obj_ajax(H.decode(dy.content))
    rep = H.decode(sess.get(base7 + "Report_All.asp", timeout=30,
                            headers={"Referer": base7 + "main.html"}).content)
    snap = {"captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "tag": tag, "host": H.HOST,
            "session": {str(i): parts[i] for i in range(min(30, len(parts)))},
            "static_units": units, "dynamic_units": dyn,
            "report_all": " ".join(rep.split())[:2000]}
    carr = [(o, a) for o, a in sorted(units.items(), key=lambda kv: int(kv[0].split("_")[1]))
            if str(a.get("sons") or "0") not in ("0", "")]
    out.append("[%s] 单位=%d 已装乘员载具=%d 未部署(blood=0)=%d  StartTime=%r RoomSecond=%s"
               % (tag, len(units), len(carr),
                  sum(1 for a in units.values() if str(a.get("blood")) == "0"), parts[3], parts[20]))
    for o, a in carr:
        out.append("     载具 %s %s sons=%s color=%s pos=%s" % (o, a.get("ico"), a.get("sons"),
                                                               a.get("color"), a.get("pos")))
    return snap


def reset_room(sess, room):
    """官方“初始化推演室”：GET 拿自动提交表单，再 POST 它。"""
    url = "%s/WARGAMEAI%d/Reset/Post.asp" % (H.HOST, room)
    r = sess.get(url, params={"scenarioId": "7527", "roomId": str(room)}, timeout=30)
    raw = H.decode(r.content)
    m = re.search(r'<form[^>]*action="([^"]*)"[^>]*>(.*?)</form>', raw, re.S)
    out.append("Reset GET -> %s len=%d" % (r.status_code, len(r.content)))
    if not m:
        out.append("  未拿到表单：%r" % raw[:160])
        return False
    data = {}
    for im in re.finditer(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>', m.group(2), re.S):
        data[im.group(1)] = im.group(2).strip()
    r2 = sess.post(requests.compat.urljoin(url, m.group(1)), data=data, timeout=30)
    out.append("Reset POST -> %s len=%d" % (r2.status_code, len(r2.content)))
    return True


def main():
    H.guard()
    colorB = sys.argv[1] if len(sys.argv) > 1 else "RED"
    uA, pA = os.environ.get("HEXWAR_USER", ""), os.environ.get("HEXWAR_PASS", "")
    uB, pB = os.environ.get("HEXWAR_USER2", ""), os.environ.get("HEXWAR_PASS2", "")
    if not uB or not pB:
        sys.exit("请设置 HEXWAR_USER2 / HEXWAR_PASS2")
    out.append("A=%s(导演)  B=%s(%s)  房间=%d" % (uA, uB, colorB, ROOM))
    os.makedirs(CAP, exist_ok=True)
    H.BASE7 = "%s/WARGAMEAI%d/" % (H.HOST, ROOM)

    # 1) 复位房间（正在跑的推演会让红方进不去）
    sessA, uidA = login_as(uA, pA)
    reset_room(sessA, ROOM)
    time.sleep(1)

    # 2) A 重新登录 -> 以导演进房
    sessA, uidA = login_as(uA, pA)
    H.S = sessA
    H.enter(ROOM, "NONE", uidA)
    base7 = H.BASE7
    out.append("A 进房完成，客户端目录 %s" % base7)

    # 3) B 以玩家身份进房
    sessB, uidB = login_as(uB, pB)
    out.append("B 登录成功 uid=%s" % uidB)
    H.S = sessB
    H.enter(ROOM, colorB, uidB)
    out.append("B 进房完成")

    # 4) 开局前状态（关键：有玩家在座时车内是否会装乘员）
    H.S = sessA
    before = state(sessA, base7, "开局前-A")
    H.S = sessB
    state(sessB, base7, "开局前-B")

    # 5) 导演开局
    H.S = sessA
    ok = ""
    for v in ({"AIStart": "false", "RoomSecond": "0"}, {"AIStart": "true", "RoomSecond": "0"}):
        r = sessA.get(base7 + "RoomStart.asp", params=v, timeout=30,
                      headers={"Referer": base7 + "main.html"})
        txt = H.decode(r.content)
        out.append("RoomStart %s -> %r" % (v, txt[:160]))
        if txt.strip() not in ("-1", "0", ""):
            ok = txt
            break
        time.sleep(1)
    time.sleep(2)
    after = state(sessA, base7, "开局后-A")
    out.append(">>> 开局结果：%s  Time1=%r" % ("成功" if ok else "失败",
                                              ok.split(",")[0] if ok else ""))

    if before:
        io.open(os.path.join(CAP, "2p_before_start.json"), "w", encoding="utf-8").write(
            json.dumps(before, ensure_ascii=False, indent=1))
    if after:
        io.open(os.path.join(CAP, "2p_after_start.json"), "w", encoding="utf-8").write(
            json.dumps(after, ensure_ascii=False, indent=1))
    io.open(os.path.join(CAP, "2p_round.txt"), "w", encoding="utf-8").write("\n".join(out))
    print("ok ->", os.path.join(CAP, "2p_round.txt"))


if __name__ == "__main__":
    main()
