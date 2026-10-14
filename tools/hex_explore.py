# -*- coding: utf-8 -*-
"""登录后探查入口页与推演室相关页面（只读）。"""
import os
import sys
import re
import json
import pickle
import requests
from bs4 import BeautifulSoup

BASE = os.environ.get("HEXWAR_BASE", "http://www.hexwar.cn") + "/WARGAMEAI/"
OUTDIR = r"d:\兵推\snapshot"
os.makedirs(OUTDIR, exist_ok=True)
LOG = r"d:\兵推\analysis\explore.md"
COOKIE_FILE = os.path.join(OUTDIR, "session.pkl")

USERNAME = os.environ.get("HEXWAR_USER", "")
PASSWORD = os.environ.get("HEXWAR_PASS", "")
if not USERNAME or not PASSWORD:
    sys.exit("请先设置环境变量 HEXWAR_USER / HEXWAR_PASS（不要写进代码）")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
})

log = []
def w(x=""):
    log.append(x)

def sv(name, r):
    p = os.path.join(OUTDIR, name)
    with open(p, "wb") as f:
        f.write(r.content)
    return len(r.content)

w("# 登录后探查")
w()

# 登录
s.get(BASE, timeout=30)
r1 = s.post(BASE + "login/", data={"UserName": USERNAME, "UserPassword": PASSWORD},
            timeout=30, allow_redirects=True)
w("- 登录最终 URL: %s" % r1.url)
w("- cookies: %s" % requests.utils.dict_from_cookiejar(s.cookies))
w()

def show(title, url, fname=None):
    w("## %s" % title)
    w()
    try:
        r = s.get(url, timeout=30, allow_redirects=True)
    except Exception as e:
        w("- 请求失败: %r" % (e,))
        w()
        return None
    w("- GET %s" % url)
    w("- 状态 %s -> %s" % (r.status_code, r.url))
    if fname:
        n = sv(fname, r)
        w("- 已保存 %s (%d 字节)" % (fname, n))
    try:
        html = r.content.decode("utf-8", errors="replace")
    except Exception:
        html = ""
    w()
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if href:
            links.append((href, a.get_text(strip=True)[:30], (a.get("onclick") or "")[:60]))
    if links:
        w("| href | 文本 | onclick |")
        w("|---|---|---|")
        for h, t, o in links:
            w("| `%s` | %s | %s |" % (h, t, o))
        w()
    forms = soup.find_all("form")
    for i, f in enumerate(forms):
        w("- form#%d action=`%s` method=`%s`" % (i, f.get("action"), f.get("method")))
        for el in f.find_all(["input", "select"]):
            w("  - %s name=`%s` type=`%s` value=`%s`" % (el.name, el.get("name"), el.get("type"), (el.get("value") or "")[:40]))
    w()
    body = soup.get_text("\n", strip=True)
    w("### 页面文本（前 1500 字）")
    w()
    w("```")
    w(body[:1500])
    w("```")
    w()
    return html

show("1. 入口页（登录态）", BASE, "entry_logged_in.html")
show("2. SetUp 目录", BASE + "SetUp/", "setup_dir.html")

with open(LOG, "w", encoding="utf-8") as f:
    f.write("\n".join(log))
with open(COOKIE_FILE, "wb") as f:
    pickle.dump(s.cookies, f)
print("explore done")
