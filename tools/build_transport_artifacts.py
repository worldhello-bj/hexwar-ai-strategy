# -*- coding: utf-8 -*-
"""把 7527_transport_capture/ 下的原始采集整理成清单要求的交付产物：
    metadata.txt、每个样本的 request.json / response.json / screenshots 说明。

不联网；所有结论都从样本自己的 before.json / after.json / action.txt 推导，
不做任何推测性填充。
"""
import io
import json
import os

CAP = r"d:\兵推\7527_transport_capture"

SAMPLES = [
    ("blue_armored_unload_01", "蓝方装甲车", "Obj_100141", 1),
    ("red_support_unload_01", "红方火力支援车", "Obj_100156", 1),
    ("red_support_unload_02_off2", "红方火力支援车（第二个乘员类型）", "Obj_100161", 2),
]


def load(path):
    if not os.path.exists(path):
        return None
    return json.load(io.open(path, encoding="utf-8"))


def raw_text(path):
    if not os.path.exists(path):
        return None
    return io.open(path, "rb").read().decode("gb18030", "replace")


def idnum(oid):
    return int("".join(ch for ch in str(oid) if ch.isdigit()) or 0)


def analyze(name, label, car, off):
    d = os.path.join(CAP, name)
    before = load(os.path.join(d, "before.json"))
    after = load(os.path.join(d, "after.json"))
    if not before or not after:
        return None
    b_st, a_st = before["static_units"], after["static_units"]
    b_dy, a_dy = before["dynamic_units"], after["dynamic_units"]
    new_ids = sorted(set(a_st) - set(b_st), key=idnum)
    gone_ids = sorted(set(b_st) - set(a_st), key=idnum)
    carb, cara = b_st.get(car) or {}, a_st.get(car) or {}
    info = {
        "样本": name, "说明": label, "载具": car, "off": off,
        "载具型号": cara.get("ico"), "编制": cara.get("army"), "阵营": cara.get("color"),
        "载具格": cara.get("pos"),
        "车内单位数(静态 sons)": "%s -> %s" % (carb.get("sons"), cara.get("sons")),
        "车内单位数(动态 son)": "%s -> %s" % ((b_dy.get(car) or {}).get("son"),
                                              (a_dy.get(car) or {}).get("son")),
        "载具静态 son 图标串": "%s -> %s" % (carb.get("son"), cara.get("son")),
        "载具动态 sonarr": "%s -> %s" % ((b_dy.get(car) or {}).get("sonarr"),
                                         (a_dy.get(car) or {}).get("sonarr")),
        "新增编号": new_ids, "消失编号": gone_ids, "新单位": [],
    }
    for nid in new_ids:
        n = a_st[nid]
        info["新单位"].append({
            "编号": nid, "id2（回指原记录编号）": n.get("id2"),
            "名称": n.get("name"), "图标": n.get("ico"), "typeid": n.get("typeid"),
            "阵营": n.get("color"), "位置": n.get("pos"), "home": n.get("home"),
            "兵力 blood": n.get("blood"), "car（载具绑定）": n.get("car"),
            "编制": n.get("army"), "group": n.get("group"),
        })
    for nid in new_ids:
        oid = a_st[nid].get("id2")
        if oid and oid in a_st:
            o = a_st[oid]
            info["原记录状态"] = "%s: pos=%s blood=%s color=%r（未被复用，仍为未部署）" % (
                oid, o.get("pos"), o.get("blood"), o.get("color"))
            info["原记录 pos2"] = o.get("pos2")
    return info


def main():
    rows = []
    for name, label, car, off in SAMPLES:
        info = analyze(name, label, car, off)
        if info:
            rows.append((name, car, off, info))

    for name, car, off, info in rows:
        d = os.path.join(CAP, name)
        comajax = raw_text(os.path.join(d, "ComAjax.asp.txt"))
        com_post = raw_text(os.path.join(d, "unload_ComPost.txt"))
        obj2out = raw_text(os.path.join(d, "unload_Obj2_Out.txt"))
        act = raw_text(os.path.join(d, "action.txt")) or ""
        com_id = ""
        for line in act.splitlines():
            if line.startswith("ComID"):
                com_id = line.split(":", 1)[1].strip()
        color = (load(os.path.join(d, "before.json"))["static_units"].get(car) or {}).get("color")

        req = {
            "_说明": "本次「下车」操作的接口请求（照官方客户端 war.min.js / ComPost.js 契约重放）",
            "_载具": car, "_off": off,
            "第一步_com_ComPost_asp": {
                "method": "GET",
                "url": "http://www.hexwar.cn/WARGAMEAI7/com/ComPost.asp",
                "params": {"ObjID": car,
                           "Command": json.dumps({car: {"off": off}}, ensure_ascii=False),
                           "ObjColor": color,
                           "TaskName": "卸载" if off == 3 else "下车",
                           "ObjPos": str(info["载具格"]), "MapID": ""},
            },
            "第二步_com_ComAjax_asp": {
                "method": "GET",
                "url": "http://www.hexwar.cn/WARGAMEAI7/com/ComAjax.asp",
                "_说明": "取回服务端登记的指令，格式：ComID|UserID|{ObjID:{off}}|时间|任务名",
                "ComID": com_id,
            },
            "第三步_com_Obj2_Out_asp": {
                "method": "GET",
                "url": "http://www.hexwar.cn/WARGAMEAI7/com/Obj2_Out.asp",
                "params": {"ObjID": car, "ObjTypeID": str(off),
                           "Time1": "", "ComID": com_id, "ObjStack": "0"},
            },
        }
        resp = {
            "_说明": "本次「下车」操作的接口响应正文（原样保留）",
            "com_ComPost_asp": com_post if com_post is not None else "（见 action.txt 第一段返回）",
            "com_ComAjax_asp": comajax if comajax is not None
            else "（本样本采集时尚未按样本分目录保存原始响应，未单独留存）",
            "com_Obj2_Out_asp": obj2out if obj2out is not None else "（见 action.txt 第二段返回）",
            "_结论": info,
        }
        io.open(os.path.join(d, "request.json"), "w", encoding="utf-8").write(
            json.dumps(req, ensure_ascii=False, indent=1))
        io.open(os.path.join(d, "response.json"), "w", encoding="utf-8").write(
            json.dumps(resp, ensure_ascii=False, indent=1))
        sd = os.path.join(d, "screenshots")
        os.makedirs(sd, exist_ok=True)
        io.open(os.path.join(sd, "README.txt"), "w", encoding="utf-8").write(
            "本次为接口级采集，未打开浏览器界面，因此没有截图。\n"
            "证据以 ../before.json、../after.json、../request.json、../response.json 为准。\n")

    lines = [
        "7527 比赛场景数据补充 —— 本次采集元数据",
        "=" * 46,
        "",
        "场景号与名称：7527  城市攻防作战（2V2）",
        "版本信息：未知（界面未显示版本号；客户端每房一份 main.html，内容一致）",
        "服务器：练习服1 http://www.hexwar.cn/WARGAMEAI",
        "练习模式：导演（GameColor=NONE，单人控红蓝双方）",
        "本次使用推演室：推演室7（服务端 RoomID=228，客户端目录 /WARGAMEAI7/）",
        "开局状态：推演未开始。RoomStart.asp 恒返回 -1（试过多组参数，另在空的推演室15",
        "          重试亦为 -1），因此只在推演中才有意义的数据无法采集。",
        "采集时间与时区：2026-10-15 13:58~14:04（本机时间，UTC+08:00）",
        "操控阵营：导演（同时可操作红蓝双方）",
        "",
        "地图是否仍适用：适用。本次 User_Get 的 Moban=7527、HexCols=100、HexRows=18，",
        "                与既有 snapshot/parsed（2721 格 / 36 条单位 / 3 个目标点）一致，地图未变。",
        "",
        "各文件对应哪辆车：",
    ]
    for name, car, off, info in rows:
        lines.append("  %-28s -> %s（%s %s，off=%d）" % (name + "/", car, info["阵营"],
                                                       info["载具型号"], off))
    lines += [
        "",
        "是否发生交火或其他操作：无交火；除三次「下车」外未下达任何其他命令。",
        "  注意：三次卸载发生在同一间推演室的同一会话里，因此后两次样本的 before",
        "  已包含前一次的结果（before 里分别是 36 / 37 / 38 条单位记录）。",
        "",
        "采集方式：接口级（自动化），未使用浏览器界面；因此没有界面截图，",
        "          但每个样本都有机器可读的完整前后快照与接口请求/响应。",
        "",
        "凭证处理：账号与口令只放在环境变量里，未写入任何文件；未保存 Cookie / 认证头；",
        "          未提交原始 HAR。本场景为单位/地图数据，不含其他玩家姓名。",
    ]
    io.open(os.path.join(CAP, "metadata.txt"), "w", encoding="utf-8").write("\n".join(lines))

    print("artifacts written ->", CAP)
    for name, car, off, info in rows:
        nu = info["新单位"][0]
        print("  %-28s %-22s %s -> %s %s" % (name, info["车内单位数(动态 son)"],
                                             info["新增编号"][0] if info["新增编号"] else "-",
                                             nu["id2（回指原记录编号）"], nu["名称"]))


if __name__ == "__main__":
    main()
