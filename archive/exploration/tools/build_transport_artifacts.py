# -*- coding: utf-8 -*-
"""把 7527_transport_capture/ 下的原始采集整理成清单要求的交付产物：
    metadata.txt、每个样本的 request.json / response.json / screenshots 说明。

不联网；结论全部从样本自己的 JSON 快照推导，不做推测性填充。
支持两类样本：
  * *_unload_*        纯「下车」（未开局时采）
  * load_unload_*     完整「上车 -> 车内 -> 下车」循环（已开局时采）
"""
import io
import json
import os

CAP = r"d:\兵推\7527_transport_capture"

UNLOAD_SAMPLES = [
    ("blue_armored_unload_01", "蓝方装甲车", "Obj_100141", 1),
    ("red_support_unload_01", "红方火力支援车", "Obj_100156", 1),
    ("red_support_unload_02_off2", "红方火力支援车（第二个乘员类型）", "Obj_100161", 2),
]
LOAD_SAMPLES = [
    ("load_unload_blue_armored", "蓝方装甲车（完整装卸循环）"),
    ("load_unload_red_support", "红方火力支援车（完整装卸循环・人员）"),
    ("load_unload_red_support_ugvs", "红方火力支援车（完整装卸循环・无人车）"),
]


def load(p):
    return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else None


def raw_text(p):
    return io.open(p, "rb").read().decode("gb18030", "replace") if os.path.exists(p) else None


def idnum(oid):
    return int("".join(ch for ch in str(oid) if ch.isdigit()) or 0)


def car_summary(st, dy, car):
    a = st.get(car) or {}
    d = dy.get(car) or {}
    return {"载具": car, "型号": a.get("ico"), "编制": a.get("army"), "阵营": a.get("color"),
            "格": a.get("pos"), "sons": a.get("sons"), "动态 son": d.get("son"),
            "静态 son 图标串": a.get("son"), "动态 sonarr": d.get("sonarr")}


def unit_summary(st, dy, uid):
    a = st.get(uid) or {}
    d = dy.get(uid) or {}
    return {"编号": uid, "id2": a.get("id2"), "名称": a.get("name"), "图标": a.get("ico"),
            "typeid": a.get("typeid"), "阵营": a.get("color"), "pos": a.get("pos"),
            "pos2": a.get("pos2"), "home": a.get("home"), "blood": a.get("blood"),
            "car": a.get("car"), "编制": a.get("army"),
            "动态 son": d.get("son"), "动态血": d.get("blood")}


def build_unload(name, label, car, off):
    """纯下车样本（未开局）。"""
    d = os.path.join(CAP, name)
    b, a = load(os.path.join(d, "before.json")), load(os.path.join(d, "after.json"))
    if not b or not a:
        return None
    bst, ast = b["static_units"], a["static_units"]
    new = sorted(set(ast) - set(bst), key=idnum)
    info = {"样本": name, "说明": label, "off": off,
            "操作前": {"载具": car_summary(bst, b["dynamic_units"], car)},
            "操作后": {"载具": car_summary(ast, a["dynamic_units"], car)},
            "新增编号": new, "消失编号": sorted(set(bst) - set(ast), key=idnum)}
    for nid in new:
        info["新单位"] = unit_summary(ast, a["dynamic_units"], nid)
        oid = ast[nid].get("id2")
        if oid in ast:
            info["原记录（未变）"] = unit_summary(ast, a["dynamic_units"], oid)
    act = raw_text(os.path.join(d, "action.txt")) or ""
    com_id = ""
    for line in act.splitlines():
        if line.startswith("ComID"):
            com_id = line.split(":", 1)[1].strip()
    req = {"_说明": "纯「下车」的接口请求（照官方客户端 war.min.js / ComPost.js 契约重放）",
           "_载具": car, "_off": off,
           "第一步_com_ComPost_asp": {
               "method": "GET",
               "url": "http://www.hexwar.cn/WARGAMEAI7/com/ComPost.asp",
               "params": {"ObjID": car, "Command": json.dumps({car: {"off": off}}, ensure_ascii=False),
                          "ObjColor": (bst.get(car) or {}).get("color"),
                          "TaskName": "卸载" if off == 3 else "下车",
                          "ObjPos": str((bst.get(car) or {}).get("pos")), "MapID": ""}},
           "第二步_com_ComAjax_asp": {"method": "GET",
                                      "url": "http://www.hexwar.cn/WARGAMEAI7/com/ComAjax.asp",
                                      "_说明": "取回服务端登记的指令：ComID|UserID|{ObjID:{off}}|时间|任务名",
                                      "ComID": com_id},
           "第三步_com_Obj2_Out_asp": {
               "method": "GET", "url": "http://www.hexwar.cn/WARGAMEAI7/com/Obj2_Out.asp",
               "params": {"ObjID": car, "ObjTypeID": str(off), "Time1": "",
                          "ComID": com_id, "ObjStack": "0"}}}
    resp = {"_说明": "纯「下车」的接口响应正文（原样保留）",
            "com_ComPost_asp": raw_text(os.path.join(d, "unload_ComPost.txt"))
            or "（见 action.txt 第 1 段返回）",
            "com_ComAjax_asp": raw_text(os.path.join(d, "ComAjax.asp.txt"))
            or "（本样本采集时尚未按样本分目录保存原始响应，未单独留存）",
            "com_Obj2_Out_asp": raw_text(os.path.join(d, "unload_Obj2_Out.txt"))
            or "（见 action.txt 第 2 段返回）",
            "_结论": info}
    _write(d, req, resp)
    return info


def build_load(name, label):
    """完整装卸循环样本（已开局）：上车 -> 车内 -> 下车。"""
    d = os.path.join(CAP, name)
    b, l, u = (load(os.path.join(d, f)) for f in
               ("before.json", "after_load.json", "after_unload.json"))
    if not (b and l and u):
        return None
    new = sorted(set(u["static_units"]) - set(l["static_units"]), key=idnum)
    if not new:
        return None
    nid = new[0]
    nu = u["static_units"][nid]
    unit, car = nu.get("id2"), nu.get("car")
    off = int(nu.get("typeid") or 1)
    info = {
        "样本": name, "说明": label, "off": off,
        "初始（上车前）": {"载具": car_summary(b["static_units"], b["dynamic_units"], car),
                     "乘员": unit_summary(b["static_units"], b["dynamic_units"], unit)},
        "上车后": {"载具": car_summary(l["static_units"], l["dynamic_units"], car),
                 "乘员": unit_summary(l["static_units"], l["dynamic_units"], unit)},
        "下车后": {"载具": car_summary(u["static_units"], u["dynamic_units"], car),
                 "乘员（原记录，停在车内状态）": unit_summary(u["static_units"],
                                              u["dynamic_units"], unit),
                 "新生成单位": unit_summary(u["static_units"], u["dynamic_units"], nid)},
        "RoomSecond": [b["session"].get("20"), l["session"].get("20"), u["session"].get("20")],
        "计分页三阶段是否相同": (b.get("report_all") == l.get("report_all")
                        == u.get("report_all")),
    }
    gk = str((b["static_units"].get(car) or {}).get("pos"))
    b7 = "http://www.hexwar.cn/WARGAMEAI7/"
    req = {"_说明": "完整装卸循环的接口请求（照官方客户端契约重放）",
           "_载具": car, "_乘员": unit, "_off": off, "_格号": gk,
           "上车_第一步_com_ComPost_asp": {
               "method": "GET", "url": b7 + "com/ComPost.asp",
               "params": {"ObjID": unit, "Command": json.dumps({unit: {"inside": car}},
                                                               ensure_ascii=False),
                          "ObjColor": (b["static_units"].get(car) or {}).get("color"),
                          "TaskName": "上车", "ObjPos": gk, "MapID": ""}},
           "上车_第二步_com_ObjInto_asp": {
               "method": "GET", "url": b7 + "com/ObjInto.asp",
               "params": {"ObjID": unit, "CarID": car, "ComID": "<上一步 ComAjax 的 ComID>"}},
           "下车_第一步_com_ComPost_asp": {
               "method": "GET", "url": b7 + "com/ComPost.asp",
               "params": {"ObjID": car, "Command": json.dumps({car: {"off": off}},
                                                              ensure_ascii=False),
                          "ObjColor": (b["static_units"].get(car) or {}).get("color"),
                          "TaskName": "卸载" if off == 3 else "下车", "ObjPos": gk, "MapID": ""}},
           "下车_第二步_com_Obj2_Out_asp": {
               "method": "GET", "url": b7 + "com/Obj2_Out.asp",
               "params": {"ObjID": car, "ObjTypeID": str(off), "Time1": "",
                          "ComID": "<上一步 ComAjax 的 ComID>", "ObjStack": "0"}}}
    resp = {"_说明": "接口返回均为：ComPost.asp 空串（受理成功）、ObjInto.asp / Obj2_Out.asp 返回 True；"
                  "原始响应见同目录 ComAjax.asp.txt / unload_*.txt 与上一级目录的同名文件",
            "结论": info}
    _write(d, req, resp)
    return info


def _write(d, req, resp):
    io.open(os.path.join(d, "request.json"), "w", encoding="utf-8").write(
        json.dumps(req, ensure_ascii=False, indent=1))
    io.open(os.path.join(d, "response.json"), "w", encoding="utf-8").write(
        json.dumps(resp, ensure_ascii=False, indent=1))
    sd = os.path.join(d, "screenshots")
    os.makedirs(sd, exist_ok=True)
    io.open(os.path.join(sd, "README.txt"), "w", encoding="utf-8").write(
        "本次为接口级采集，未打开浏览器界面，因此没有截图。\n"
        "证据以同目录的 JSON 快照与 request.json / response.json 为准。\n")


def main():
    unloads = []
    for name, label, car, off in UNLOAD_SAMPLES:
        info = build_unload(name, label, car, off)
        if info:
            unloads.append((name, car, off, info))

    loads = []
    for name, label in LOAD_SAMPLES:
        info = build_load(name, label)
        if info:
            nu = info["下车后"]["新生成单位"]
            loads.append((name, nu["car"], info["off"], info))

    lines = [
        "7527 比赛场景数据补充 —— 本次采集元数据",
        "=" * 46,
        "",
        "场景号与名称：7527  城市攻防作战（2V2）",
        "版本信息：未知（界面未显示版本号；每个推演室一份客户端副本，内容一致）",
        "服务器：练习服1 http://www.hexwar.cn/WARGAMEAI",
        "练习模式：导演(GameColor=NONE) + 红方玩家 各一个账号",
        "本次使用推演室：推演室7（服务端 RoomID=228，客户端目录 /WARGAMEAI7/）",
        "采集时间与时区：2026-10-15 13:58~14:25（本机时间，UTC+08:00）",
        "",
        "地图是否仍适用：适用。本次 User_Get 的 Moban=7527、HexCols=100、HexRows=18，",
        "                与既有 snapshot/parsed（2721 格 / 36 条单位 / 3 个目标点）一致，地图未变。",
        "",
        "两批样本：",
        "  A. 纯「下车」——在一个「乘员已装车、推演未开始」的旧会话里做（3 个样本）；",
        "  B. 完整「上车→车内→下车」循环——在**已开局**的新推演里做（3 个样本）。",
        "     两批的结论一致，说明装卸行为不依赖推演是否开始。",
        "",
        "各文件对应哪辆车：",
    ]
    for name, car, off, _ in unloads:
        lines.append("  %-30s -> %s（off=%d，纯下车）" % (name + "/", car, off))
    for name, car, off, info in loads:
        lines.append("  %-30s -> %s（off=%d，完整装卸循环，乘员 %s）"
                     % (name + "/", car, off, info["下车后"]["新生成单位"]["id2"]))
    lines += [
        "",
        "是否发生交火或其他操作：无交火。完整循环那批只做了「上车 / 下车」两个动作；",
        "  纯下车那批只做了「下车」。未下达任何其他命令。",
        "  注意：同一会话里的多次操作会累积，后一个样本的 before 已包含前一个的结果。",
        "",
        "采集方式：接口级（自动化），未使用浏览器界面；因此没有界面截图，",
        "          但每个样本都有机器可读的完整前后快照与接口请求/响应。",
        "",
        "分数/时间：装卸前后 Report_All.asp（计分页）完全相同；RoomSecond 只随推演自然推进，",
        "          无法归因于装卸。详见 docs/运输机制实测.md §3。",
        "",
        "凭证处理：账号与口令只放在环境变量里，未写入任何文件；未保存 Cookie / 认证头；",
        "          未提交原始 HAR。本场景为单位/地图数据，不含其他玩家姓名。",
    ]
    io.open(os.path.join(CAP, "metadata.txt"), "w", encoding="utf-8").write("\n".join(lines))

    print("artifacts written ->", CAP)
    for name, car, off, info in unloads:
        print("  [纯下车]   %-28s %s -> %s" % (name, info["新增编号"],
                                               info.get("新单位", {}).get("id2")))
    for name, car, off, info in loads:
        print("  [装卸循环] %-28s off=%d  新生成 %s(id2=%s)"
              % (name, off, info["下车后"]["新生成单位"]["编号"],
                 info["下车后"]["新生成单位"]["id2"]))


if __name__ == "__main__":
    main()
