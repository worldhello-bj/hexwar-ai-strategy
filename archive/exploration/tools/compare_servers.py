"""比对练习服与比赛服的客户端资源是否同一版本。

只发 GET、只读公开静态资源，不登录、不提交任何数据。

用法：
    py -3.13 tools/compare_servers.py
    py -3.13 tools/compare_servers.py --a http://www.hexwar.cn --b http://43.143.209.228
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import requests

PRACTICE = "http://www.hexwar.cn"
COMPETE = "http://43.143.209.228"

# 公开静态资源（客户端与配置），足以判断版本是否一致
PATHS = [
    "/WARGAMEAI/",
    "/WARGAMEAI/readme.txt",
    "/WARGAMEAI/User_Get.asp",
    "/WARGAMEAI/GetServerTime.asp",
    "/WARGAMEAI/Report_All.asp",
    "/WARGAMEAI7/",
    "/WARGAMEAI7/main.html",
    "/WARGAMEAI7/war.min.js",
    "/WARGAMEAI7/war.min.css",
    "/WARGAMEAI7/observe.css",
    "/WARGAMEAI7/user.css",
    "/WARGAMEAI7/common.css",
    "/WARGAMEAI7/data.js",
    "/WARGAMEAI7/SetUp.js",
    "/WARGAMEAI7/lib/jquery-1.8.3.min.js",
    "/WARGAMEAI7/lib/paint/paint.js",
    "/WARGAMEAI7/lib/jAlert/js/jquery.alerts.js",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 20


def fetch(sess: requests.Session, base: str, path: str) -> dict:
    url = base + path
    try:
        r = sess.get(url, timeout=TIMEOUT, allow_redirects=True)
    except Exception as exc:                                   # noqa: BLE001
        return {"err": f"{type(exc).__name__}: {exc}"}
    return {
        "status": r.status_code,
        "len": len(r.content),
        "sha1": hashlib.sha1(r.content).hexdigest()[:12],
        "ctype": r.headers.get("Content-Type", ""),
        "final": r.url,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="比对两台服务器的客户端版本")
    ap.add_argument("--a", default=PRACTICE, help="练习服")
    ap.add_argument("--b", default=COMPETE, help="比赛服")
    ap.add_argument("-o", "--out", type=Path, default=None)
    ns = ap.parse_args(argv)

    sa, sb = requests.Session(), requests.Session()
    for s in (sa, sb):
        s.headers["User-Agent"] = UA

    lines: list[str] = []
    w = lines.append
    w("# 练习服 vs 比赛服 客户端比对\n")
    w(f"- A（练习）：`{ns.a}`")
    w(f"- B（比赛）：`{ns.b}`")
    w("- 方式：只读 GET 公开静态资源，不登录、不提交数据\n")
    w("| 路径 | A 状态 | A 大小 | A sha1 | B 状态 | B 大小 | B sha1 | 一致 |")
    w("|---|---|---|---|---|---|---|---|")

    same = diff = err = 0
    for p in PATHS:
        ra, rb = fetch(sa, ns.a, p), fetch(sb, ns.b, p)
        if "err" in ra or "err" in rb:
            err += 1
            w(f"| `{p}` | 失败 | — | — | 失败 | — | — | 取数失败 |")
            continue
        if ra["sha1"] == rb["sha1"]:
            same += 1
            flag = "✅ 相同"
        else:
            diff += 1
            flag = "**不同**"
        w(f"| `{p}` | {ra['status']} | {ra['len']:,} | `{ra['sha1']}` | "
          f"{rb['status']} | {rb['len']:,} | `{rb['sha1']}` | {flag} |")

    w("")
    w(f"合计：相同 **{same}**，不同 **{diff}**，取数失败 **{err}**\n")

    md = "\n".join(lines)
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
