# -*- coding: utf-8 -*-
"""登录 www.hexwar.cn/WARGAMEAI/ 并抓取会话/页面信息。只读，不调用任何对局命令接口。"""
import os
import re
import sys
import json
import pickle
import requests
from urllib.parse import urlsplit
from bs4 import BeautifulSoup

# 主机可用 HEXWAR_BASE 覆盖，以便指向比赛服（默认练习服）
_HOST = os.environ.get("HEXWAR_BASE", "http://www.hexwar.cn")
if urlsplit(_HOST).scheme.lower() != "https":
    sys.exit("Refusing to send credentials over HTTP. Configure a verified HTTPS endpoint; if unavailable, do not use this login script.")
BASE = _HOST + "/WARGAMEAI/"
BASE7 = _HOST + "/WARGAMEAI7/"
# 输出目录与日志也可用环境变量覆盖，便于把两台服务器的抓取分开存放
OUTDIR = os.environ.get("HEXWAR_OUT", r"d:\兵推\snapshot")
os.makedirs(OUTDIR, exist_ok=True)
LOG = os.environ.get("HEXWAR_LOG", r"d:\兵推\analysis\login_step1.md")

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
})

def dump(name, r, limit=None):
    """把响应体存到 snapshot 目录，返回 (路径, 长度)。"""
    body = r.content
    p = os.path.join(OUTDIR, name)
    with open(p, "wb") as f:
        f.write(body)
    return p, len(body)

w("# 第 1 步：登录与首屏抓取")
w()

# --- 1. 打开入口页，拿会话 cookie ---
r0 = s.get(BASE, timeout=30)
w("- 入口页: %s  status=%s  cookies=%s" % (r0.url, r0.status_code, "[REDACTED]"))
html0 = r0.content.decode("utf-8", errors="replace")
w("- 入口页含 'md5': %s" % ("md5" in html0.lower()))
w("- 入口页含 'UserPassword': %s" % ("UserPassword" in html0))
w()

# --- 2. 提交登录 ---
r1 = s.post(BASE + "login/", data={"UserName": USERNAME, "UserPassword": PASSWORD},
            timeout=30, allow_redirects=False)
if 300 <= r1.status_code < 400:
    sys.exit("Login redirect stopped. Verify the destination manually before continuing.")
w("## 登录请求")
w()
w("- POST %slogin/  (UserName=%s)" % (BASE, USERNAME))
w("- 状态: %s   最终 URL: %s" % (r1.status_code, r1.url))
w("- 重定向链: %s" % [(h.status_code, h.headers.get("Location")) for h in r1.history])
w("- 登录后 cookies: %s" % "[REDACTED]")
w()
p, ln = dump("after_login.html", r1)
w("- 响应体(%d 字节) -> `%s`" % (ln, p))
txt1 = r1.content.decode("utf-8", errors="replace")
w("- 响应体前 400 字: %s" % txt1[:400].replace("\n", " "))
w()
w("- URL 出现 'error' / 'fail': %s" % bool(re.search(r"error|fail|错误|失败", txt1, re.I)))
w()

# --- 3. 若落在 main.html，继续抓取；否则尝试跳转 ---
with open(LOG, "w", encoding="utf-8") as f:
    f.write("\n".join(log))
print("step1 done, final url:", r1.url)
with open(r"d:\兵推\analysis\_final_url.txt", "w", encoding="utf-8") as f:
    f.write(r1.url)
