"""勘察某个推演服务器对外暴露了哪些端点（**不登录、只发 GET**）。

目的：了解服务端表面（哪些端点存在、哪些需要会话），
不做爆破、不做参数模糊测试。

用法：
    py -3.13 tools/probe_endpoints.py --base http://43.143.209.228
    py -3.13 tools/probe_endpoints.py --base http://www.hexwar.cn --out analysis\\ep.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

# 从客户端脚本中静态抽取的高价值端点（见 tools/extract_commands.py）
ENDPOINTS = [
    "/WARGAMEAI/Map_Get.asp",
    "/WARGAMEAI/Map_Get_Under.asp",
    "/WARGAMEAI/Obj_Get.asp",
    "/WARGAMEAI/Obj_Get_2.asp",
    "/WARGAMEAI/City_Get.asp",
    "/WARGAMEAI/offlinemapdata.asp",
    "/WARGAMEAI/ArmyList.asp",
    "/WARGAMEAI/SystemArmy.asp",
    "/WARGAMEAI/GamePost.asp",
    "/WARGAMEAI/GroupList.asp",
    "/WARGAMEAI/UserStat.asp",
    "/WARGAMEAI/UserCheck.asp",
    "/WARGAMEAI/MeterGrid.asp",
    "/WARGAMEAI/ChangeGmap.asp",
    "/WARGAMEAI/GetRoadRot.asp",
    "/WARGAMEAI/ObjInfo.asp",
    "/WARGAMEAI/Obj_Weapon.asp",
    "/WARGAMEAI/ObjAjax.asp",
    "/WARGAMEAI/ObjOver.asp",
    "/WARGAMEAI/ObjFire.asp",
    "/WARGAMEAI/RoomStat.asp",
    "/WARGAMEAI/RoomStart.asp",
    "/WARGAMEAI/Caijue.asp",
    "/WARGAMEAI/loadInfo.asp",
    "/WARGAMEAI/AIUser.asp",
    "/WARGAMEAI/RecordBackUp.asp",
    "/WARGAMEAI/com/TgList.asp",
    "/WARGAMEAI/logout/logout.asp",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 20


def probe(sess: requests.Session, base: str, path: str) -> dict:
    try:
        r = sess.get(base + path, timeout=TIMEOUT, allow_redirects=False)
    except Exception as exc:                                   # noqa: BLE001
        return {"err": f"{type(exc).__name__}: {exc}"}
    raw = r.content
    try:
        txt = raw.decode("gbk")
    except UnicodeDecodeError:
        txt = raw.decode("utf-8", "replace")
    return {"status": r.status_code, "len": len(raw),
            "head": txt[:120].replace("\r", " ").replace("\n", " ").strip()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="勘察服务器暴露的端点（只读）")
    ap.add_argument("--base", required=True, help="形如 http://host")
    ap.add_argument("-o", "--out", type=Path, default=None)
    ns = ap.parse_args(argv)

    sess = requests.Session()
    sess.headers["User-Agent"] = UA

    out: list[str] = []
    w = out.append
    w(f"# 端点勘察：`{ns.base}`\n")
    w("- 方式：只读 GET，**未登录**；不做爆破、不做模糊测试")
    w("- 说明：`.asp` 返回 200 但内容很短（如 `-1`/空）表示**需要会话**；404 表示该端点不存在\n")
    w("| 端点 | 状态 | 大小 | 内容开头 |")
    w("|---|---|---|---|")

    n404 = nok = nerr = 0
    for p in ENDPOINTS:
        r = probe(sess, ns.base, p)
        if "err" in r:
            nerr += 1
            w(f"| `{p}` | 失败 | — | {r['err'][:60]} |")
            continue
        if r["status"] == 404:
            n404 += 1
        else:
            nok += 1
        head = r["head"].replace("|", "\\|")
        w(f"| `{p}` | {r['status']} | {r['len']:,} | `{head[:60]}` |")

    w("")
    w(f"合计：存在 **{nok}**，404 **{n404}**，取数失败 **{nerr}**\n")
    md = "\n".join(out)
    if ns.out:
        ns.out.parent.mkdir(parents=True, exist_ok=True)
        ns.out.write_text(md, encoding="utf-8")
        print(f"已写入 {ns.out}")
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
