"""登录后对**本人账号**可见的页面做只读观察。

只发 GET：不建房、不下令、不改任何服务端状态。
凭据只从环境变量读：HEXWAR_USER / HEXWAR_PASS；主机用 HEXWAR_BASE。

    $env:HEXWAR_USER='...'; $env:HEXWAR_PASS='...'
    $env:HEXWAR_BASE='http://43.143.209.228'
    py -3.13 tools/hex_observe.py -o analysis\\observe.md
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# 大厅里列出的入口 + 几个关键接口（全部 GET）
PAGES = [
    ("SetUp/SetUp_Transfer/", "推演大厅（房间列表）"),
    ("MyScore/replay.asp", "复盘回放"),
    ("MyScore/", "个人中心"),
    ("User_Get.asp", "想定参数（需在房内）"),
    ("Report_All.asp", "计分（需在房内）"),
    ("readme.txt", "更新通知"),
    ("WARGAMEAI.pdf", "比赛手册（公开）"),
]


def sha(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()[:12]


def decode(b: bytes) -> str:
    for enc in ("utf-8", "gbk"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="登录后只读观察")
    ap.add_argument("-o", "--out", type=Path, default=None)
    ap.add_argument("--keep", type=Path, default=None,
                    help="把抓到的正文存到这个目录")
    ns = ap.parse_args(argv)

    host = os.environ.get("HEXWAR_BASE", "http://www.hexwar.cn")
    base = host + "/WARGAMEAI/"
    user = os.environ.get("HEXWAR_USER", "")
    pwd = os.environ.get("HEXWAR_PASS", "")
    if not user or not pwd:
        sys.exit("请先设置 HEXWAR_USER / HEXWAR_PASS（不要写进代码）")

    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    s.get(base, timeout=30)
    s.post(base + "login/", data={"UserName": user, "UserPassword": pwd},
           timeout=30, allow_redirects=True)
    uid = s.cookies.get("UserID", "")

    out: list[str] = []
    w = out.append
    w(f"# 只读观察：`{host}`\n")
    w(f"- 账号 UserID：`{uid}`　角色 UserRole：`{s.cookies.get('UserRole','')}`"
      f"　管理 UserAdmin：`{s.cookies.get('UserAdmin','')}`")
    w("- 方式：登录后仅发 GET，不建房、不下令、不修改任何状态\n")
    w("| 页面 | 状态 | 类型 | 大小 | sha1 | 备注 |")
    w("|---|---|---|---|---|---|")

    bodies: list[tuple[str, str]] = []
    for path, label in PAGES:
        if path == "MyScore/" and uid:
            path_q = f"MyScore/?UserID={uid}"
        else:
            path_q = path
        try:
            r = s.get(base + path_q, timeout=40, allow_redirects=True)
        except Exception as exc:                               # noqa: BLE001
            w(f"| {label} | 失败 | — | — | — | {type(exc).__name__} |")
            continue
        b = r.content
        ctype = r.headers.get("Content-Type", "")
        note = ""
        if path.endswith(".pdf"):
            note = "二进制"
        w(f"| {label}（`{path_q}`） | {r.status_code} | {ctype[:24]} | "
          f"{len(b):,} | `{sha(b)}` | {note} |")
        if not path.endswith(".pdf") and len(b) < 400_000:
            bodies.append((label, decode(b)))

    w("")
    for label, txt in bodies:
        clean = re.sub(r"<script.*?</script>", " ", txt, flags=re.S | re.I)
        clean = re.sub(r"<style.*?</style>", " ", clean, flags=re.S | re.I)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        w(f"## {label}\n")
        w(f"```\n{clean[:1500]}\n```\n")
        if ns.keep:
            ns.keep.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^\w.\-]", "_", label)
            (ns.keep / f"{safe}.html").write_text(txt, encoding="utf-8")

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
