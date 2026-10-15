"""对官方站点做**轻量、只读**的公开信息发现。

原则
----
1. 只访问**公开可猜到的普通页面**（站点根、大厅、readme、robots.txt 等）；
2. **不做端口扫描、不做目录爆破、不做参数模糊测试**——那既不礼貌也不可靠；
3. 需要登录的路径一律走**使用者本人的账号**（环境变量），只做正常观察；
4. 全程只发 GET，不改动任何服务端状态。

用法
----
    py -3.13 tools/probe_site.py                 # 只用公开页面
    py -3.13 tools/probe_site.py --with-login    # 额外用本人账号正常登录后观察
    py -3.13 tools/probe_site.py -o analysis\\site_probe.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import re
import sys
from pathlib import Path

import requests

BASE = "http://www.hexwar.cn"
HALL = f"{BASE}/WARGAMEAI"
CLIENT = f"{BASE}/WARGAMEAI7"

# 只列「公开、普通、可猜到」的页面，不做任何枚举/爆破
PUBLIC_URLS: list[tuple[str, str]] = [
    (f"{BASE}/robots.txt", "站点 robots.txt"),
    (f"{BASE}/", "站点根"),
    (f"{HALL}/", "推演大厅"),
    (f"{HALL}/readme.txt", "readme（规则更新常放这里）"),
    (f"{HALL}/Readme.txt", "readme 大小写变体"),
    (f"{HALL}/default.asp", "大厅默认页"),
    (f"{HALL}/index.asp", "大厅索引页"),
    (f"{CLIENT}/", "客户端根"),
    (f"{CLIENT}/main.html", "客户端主页面"),
    # 以下来自 readme 公告与站点根链接（均为公开入口，只做一次 GET）
    (f"{BASE}/demo", "厂商 demo 入口"),
    (f"{BASE}/The_case_shows.html", "厂商案例展示"),
    ("https://www.wargame.cool/", "平台主站"),
    ("https://www.gfsy.org.cn/", "关联站点 gfsy"),
    # readme 公告的「练习服务器2（比赛模式）」
    ("http://43.143.209.228/WARGAMEAI/", "比赛模式服 · 大厅"),
    ("http://43.143.209.228/WARGAMEAI/readme.txt", "比赛模式服 · readme"),
    ("http://43.143.209.228/WARGAMEAI7/main.html", "比赛模式服 · 客户端主页"),
    # 主站 HTTPS 经本机代理握手失败，改走 HTTP 对照
    ("http://www.wargame.cool/", "平台主站（HTTP）"),
    # 棋酷网的公开分类页（WordPress），可能含公开规则/资料
    ("https://www.wargame.cool/category/wp-book", "棋酷网 · 书籍分类"),
    ("https://www.wargame.cool/category/wp-inventory", "棋酷网 · 清单分类"),
    ("https://www.seaofwargaming.com/", "Sea of Wargaming 社区"),
    # 产品页：可能枚举平台支持的功能（可用来交叉验证指令词汇表）
    ("https://seaofwargaming.com/产品展示/兵棋与兵棋推演/",
     "产品页 · 兵棋与兵棋推演"),
    ("https://www.wargame.cool/wp-book/1337.html", "棋酷网 · 书籍帖样例"),
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

TIMEOUT = 15


def sniff(raw: bytes) -> str:
    """判断响应体编码（站点 .asp 多为 GBK）。"""
    if not raw:
        return "ascii"
    try:
        raw.decode("ascii")
        return "ascii"
    except UnicodeDecodeError:
        pass
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "gbk"


def text_of(raw: bytes) -> str:
    return raw.decode(sniff(raw), "replace")


def title_of(txt: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", txt, re.I | re.S)
    return html.unescape(m.group(1).strip()) if m else ""


def fetch(sess: requests.Session, url: str, verify: bool = True) -> dict:
    try:
        r = sess.get(url, timeout=TIMEOUT, allow_redirects=True, verify=verify)
    except Exception as exc:                                   # noqa: BLE001
        return {"url": url, "err": f"{type(exc).__name__}: {exc}"}
    enc = sniff(r.content)
    body = text_of(r.content)
    return {
        "url": url,
        "status": r.status_code,
        "final": r.url,
        "ctype": r.headers.get("Content-Type", ""),
        "server": r.headers.get("Server", ""),
        "len": len(r.content),
        "enc": enc,
        "title": title_of(body),
        "snippet": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))[:800].strip(),
        "body": body,
    }


# ------------------------------------------------------------------ 登录

def login(sess: requests.Session, user: str, pwd: str) -> bool:
    """仅做正常登录：POST 表单 → 跟随 302 → 走完会话链路。"""
    try:
        sess.post(f"{HALL}/login/", data={"UserName": user, "UserPassword": pwd},
                  timeout=TIMEOUT, allow_redirects=True)
        sess.get(f"{HALL}/SetUp/SetUpSave.asp", timeout=TIMEOUT, allow_redirects=True)
        r = sess.get(f"{CLIENT}/main.html", timeout=TIMEOUT, allow_redirects=True)
        return r.status_code == 200
    except Exception as exc:                                   # noqa: BLE001
        print(f"登录异常：{exc}", file=sys.stderr)
        return False


def cookie_names(sess: requests.Session) -> list[str]:
    try:
        return sorted(sess.cookies.get_dict().keys())
    except Exception:                                          # noqa: BLE001
        return []


# ------------------------------------------------------------------ 输出

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="对官网做轻量公开发现")
    ap.add_argument("--with-login", action="store_true",
                    help="用本人账号（HEXWAR_USER/HEXWAR_PASS）正常登录后观察")
    ap.add_argument("--insecure", action="store_true",
                    help="对证书过期/自签名站点降级为不校验证书（仅读公开页面）")
    ap.add_argument("-o", "--out", type=Path, default=None)
    ns = ap.parse_args(argv)

    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    if ns.insecure:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    out: list[str] = []
    w = out.append
    w("# 官方站点轻量探测报告\n")
    w(f"- 时间：{dt.datetime.now():%Y-%m-%d %H:%M:%S}")
    w("- 方式：只读 GET，仅公开页面；**未做**端口扫描或目录爆破")
    w("")

    # 先全部取一遍，便于对失败项统一降级重试
    results: list[tuple[str, dict]] = [(label, fetch(sess, url))
                                       for url, label in PUBLIC_URLS]

    # 证书过期/自签名等站点：可选降级到不校验证书，仅用于读取公开页面
    if ns.insecure:
        for idx, (label, r) in enumerate(results):
            if "err" not in r or "SSL" not in r["err"]:
                continue
            r2 = fetch(sess, r["url"], verify=False)
            if "err" not in r2:
                r2["insecure_note"] = True
                results[idx] = (label, r2)
                print(f"[降级 verify=False] {label} 重取成功", file=sys.stderr)

    w("## 公开页面\n")
    w("| 页面 | 状态 | 类型 | 大小 | 编码 | 标题 |")
    w("|---|---|---|---|---|---|")
    for label, r in results:
        if "err" in r:
            w(f"| {label} | 失败 | — | — | — | {r['err'][:60]} |")
        else:
            red = "" if r["final"] == r["url"] else f" → {r['final']}"
            flag = " ⚠️未验证证书" if r.get("insecure_note") else ""
            w(f"| {label}{red}{flag} | {r['status']} | {r['ctype'][:28]} | "
              f"{r['len']:,} | {r['enc']} | {r['title'][:40]} |")
    w("")

    # 失败项要看完整错误：本机有 TUN 代理时 SSLError 常是代理产物，不是站点故障
    fails = [(lbl, r) for lbl, r in results if "err" in r]
    if fails:
        w("## 失败详情\n")
        w("> 本机若开着 TUN/系统代理，`SSLError` 很可能是**代理**产物（对 `CONNECT` "
          "乐观返回），不代表站点不可用；换网络环境复测再下结论。\n")
        for lbl, r in fails:
            w(f"- **{lbl}** — `{r['url']}`\n\n  ```\n  {r['err']}\n  ```\n")
        w("")

    # 把有内容的页面摘出来
    for label, r in results:
        if "err" in r or r["status"] != 200 or r["len"] < 40:
            continue
        if r["ctype"].startswith(("image/", "font/")):
            continue
        w(f"### {label}\n")
        w(f"- URL：`{r['final']}`")
        w(f"- 编码判定：{r['enc']}　大小：{r['len']:,} 字节")
        if r["title"]:
            w(f"- 标题：{r['title']}")
        # 小体积纯文本（readme 之类）直接给全文，不截断
        if r["ctype"].startswith("text/plain") and r["len"] < 8000:
            main_txt = r["body"]
        else:
            main_txt = r["snippet"]
        w(f"\n```\n{main_txt}\n```\n")

    # 登录后观察
    if ns.with_login:
        user = os.environ.get("HEXWAR_USER", "")
        pwd = os.environ.get("HEXWAR_PASS", "")
        if not user or not pwd:
            w("## 登录后观察\n")
            w("未设置 `HEXWAR_USER` / `HEXWAR_PASS`，跳过。\n")
        else:
            w("## 登录后观察\n")
            ok = login(sess, user, pwd)
            w(f"- 登录流程：{'成功' if ok else '失败'}")
            w(f"- Cookie 名（不记录值）：{', '.join(cookie_names(sess)) or '（无）'}")
            w("")
            for url, label in [(f"{HALL}/User_Get.asp", "User_Get（想定参数）"),
                               (f"{HALL}/Report_All.asp", "Report_All（计分）")]:
                r = fetch(sess, url)
                if "err" in r:
                    w(f"- {label}：失败 {r['err'][:60]}")
                else:
                    w(f"- {label}：{r['status']}，{r['len']:,} 字节")
            w("")

    # 关键页面上的链接：可能暴露其它产品、版本、开源资源或玩法入口
    INTERESTING = ("站点根", "平台主站", "厂商案例展示", "棋酷网",
                   "Sea of Wargaming", "比赛模式服")
    for label, r in results:
        if "err" in r or r.get("status") != 200:
            continue
        if not any(label.startswith(k) for k in INTERESTING):
            continue
        links = sorted({l for l in re.findall(r"href=[\"']([^\"']+)[\"']",
                                              r["body"], re.I)
                        if not l.lower().startswith(("javascript:", "#", "mailto:"))})
        w(f"## `{label}` 上的链接\n")
        if links:
            for l in links:
                w(f"- `{l}`")
        else:
            w("（无）")
        w("")

    # 文档/压缩包链接：可能藏有更新版手册或想定资料
    DOC_EXT = (".pdf", ".doc", ".docx", ".zip", ".rar", ".xls", ".xlsx")
    docs: list[tuple[str, str]] = []
    for label, r in results:
        if "err" in r:
            continue
        for l in re.findall(r"href=[\"']([^\"']+)[\"']", r["body"], re.I):
            if l.lower().split("?")[0].endswith(DOC_EXT):
                docs.append((label, l))
    if docs:
        w("## 文档/压缩包链接\n")
        for label, l in sorted(set(docs)):
            w(f"- `{l}`（来自 {label}）")
        w("")

    md = "\n".join(out)
    if ns.out:
        ns.out.parent.mkdir(parents=True, exist_ok=True)
        ns.out.write_text(md, encoding="utf-8")
        print(f"已写入 {ns.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
