# -*- coding: utf-8 -*-
"""验证乱码修复：检查各资源的 Content-Type charset 与解码结果。"""
import re
import requests

B = "http://127.0.0.1:8080/WARGAMEAI7/"
OUT = r"d:\兵推\analysis\encoding_fix.md"

FILES = [
    "main.html", "war.min.js", "war.min.css", "user.css", "observe.css", "common.css",
    "lib/jAlert/js/jquery.alerts.js", "lib/paint/paint.js", "lib/jquery-1.8.3.min.js",
    "User_Get.asp", "ObjAjax.asp", "Report_Attack.asp",
]

L = ["# 乱码修复验证", ""]
L.append("| 资源 | Content-Type | 按声明解码后是否出现替换字符 | 中文抽样 |")
L.append("|---|---|---|---|")

for f in FILES:
    r = requests.get(B + f, timeout=20)
    ct = r.headers.get("Content-Type", "")
    m = re.search(r"charset=([\w-]+)", ct)
    enc = m.group(1) if m else "utf-8"
    try:
        t = r.content.decode(enc)
        bad = "\uFFFD" in t
    except Exception as e:
        t = ""
        bad = "解码失败 %r" % (e,)
    zh = sorted(set(re.findall(r"[\u4e00-\u9fff]{2,}", t)))[:6]
    L.append("| `%s` | %s | %s | %s |" % (f, ct, bad, " / ".join(zh) if zh else "-"))

L.append("")
L.append("## jAlert 库内默认按钮文案")
L.append("")
r = requests.get(B + "lib/jAlert/js/jquery.alerts.js", timeout=20)
t = r.content.decode("gbk")
for mm in re.finditer(r"(okButton|cancelButton|title)\s*:\s*['\"]([^'\"]*)['\"]", t):
    L.append("- `%s` = `%s`" % (mm.group(1), mm.group(2)))
L.append("")
L.append("## 结论")
L.append("")
allok = True
for f in FILES:
    r = requests.get(B + f, timeout=20)
    ct = r.headers.get("Content-Type", "")
    mm = re.search(r"charset=([\w-]+)", ct)
    enc = mm.group(1) if mm else "utf-8"
    try:
        if "\uFFFD" in r.content.decode(enc):
            allok = False
    except Exception:
        allok = False
L.append("- 全部资源按声明的 charset 解码无替换字符: **%s**" % ("是" if allok else "否"))

open(OUT, "w", encoding="utf-8").write("\n".join(L))
print("written", OUT)
