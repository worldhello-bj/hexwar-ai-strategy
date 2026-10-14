# -*- coding: utf-8 -*-
"""登录后：探查 SetUp_Color.asp 可选阵营，并定位客户端 FirstID/LastID 计算方式。"""
import os
import sys
import re
import requests
from bs4 import BeautifulSoup

BASE = os.environ.get("HEXWAR_BASE", "http://www.hexwar.cn") + "/WARGAMEAI/"
OUTDIR = r"d:\兵推\snapshot"
os.makedirs(OUTDIR, exist_ok=True)
LOG = r"d:\兵推\analysis\room_probe.md"

USERNAME = os.environ.get("HEXWAR_USER", "")
PASSWORD = os.environ.get("HEXWAR_PASS", "")
if not USERNAME or not PASSWORD:
    sys.exit("请先设置环境变量 HEXWAR_USER / HEXWAR_PASS（不要写进代码）")

log = []
def w(x=""):
    log.append(x)

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": BASE + "SetUp/",
})

s.get(BASE, timeout=30)
s.post(BASE + "login/", data={"UserName": USERNAME, "UserPassword": PASSWORD},
       timeout=30, allow_redirects=True)
w("# 房间/阵营探查")
w()
w("- cookies: %s" % requests.utils.dict_from_cookiejar(s.cookies))
w()

# 1) 打开大厅，拿 SetUp 页
r = s.get(BASE + "SetUp/", timeout=30)
w("## 大厅页面")
w("- status=%s len=%d" % (r.status_code, len(r.content)))
w()

# 2) 探查 SetUp_Color.asp（只取可选阵营，不提交）
for rid in (228,):
    try:
        rc = s.post(BASE + "SetUp/SetUp_Color.asp", data={"RoomID": str(rid)}, timeout=30)
        w("## POST SetUp/SetUp_Color.asp  RoomID=%s" % rid)
        w("- status=%s len=%d" % (rc.status_code, len(rc.content)))
        txt = rc.content.decode("gb18030", errors="replace")
        p = os.path.join(OUTDIR, "setup_color_%s.html" % rid)
        with open(p, "w", encoding="utf-8") as f:
            f.write(txt)
        w("- 已保存 `%s`" % p)
        w()
        w("```html")
        w(txt[:4000])
        w("```")
        w()
        soup = BeautifulSoup(txt, "lxml")
        for el in soup.find_all(["input", "a", "button", "div", "span", "label"]):
            oc = el.get("onclick") or ""
            if oc:
                w("- <%s> onclick=`%s`" % (el.name, oc[:160]))
        w()
    except Exception as e:
        w("- 失败: %r" % (e,))
        w()

# 3) 定位客户端 FirstID / LastID
js = open(r"d:\兵推\analysis\bodies\www.hexwar.cn_WARGAMEAI7_war.min.js.js",
          "r", encoding="utf-8", errors="replace").read()
w("## war.min.js 中 FirstID / LastID / CenterID / HexCols 的赋值点")
w()
for key in ("FirstID", "LastID", "CenterID", "HexCols", "HexRows", "EleLow", "HexRowHeight", "HexColWidth"):
    w("### %s" % key)
    w()
    for m in re.finditer(re.escape(key), js):
        a, b = max(0, m.start() - 120), min(len(js), m.end() + 140)
        w("- @%d: `%s`" % (m.start(), js[a:b].replace("\n", " ")))
    w()

with open(LOG, "w", encoding="utf-8") as f:
    f.write("\n".join(log))
print("room probe done")
