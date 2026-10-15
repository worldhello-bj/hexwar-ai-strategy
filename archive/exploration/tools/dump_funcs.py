# -*- coding: utf-8 -*-
"""把 war.min.js 中的函数逐个导出为独立文件（含美化断行），便于完整阅读。"""
import os
import re
import sys
import json

SRC = r"d:\兵推\analysis\bodies\www.hexwar.cn_WARGAMEAI7_war.min.js.js"
OUT = r"d:\兵推\analysis\jsfuncs"
os.makedirs(OUT, exist_ok=True)

js = open(SRC, "r", encoding="utf-8", errors="replace").read()

def find_func(name):
    for p in (r"function\s+%s\s*\(" % re.escape(name),
              r"\b%s\s*=\s*function\s*\(" % re.escape(name),
              r"[,;{]\s*function\s+%s\s*\(" % re.escape(name)):
        m = re.search(p, js)
        if not m:
            continue
        # 从 function 关键字开始
        s = js.rfind("function", 0, m.end())
        if s < 0:
            continue
        i = js.find("(", s)
        depth = 0
        j = i
        while j < len(js):
            if js[j] == "(":
                depth += 1
            elif js[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        k = js.find("{", j)
        d = 0
        e = k
        while e < len(js):
            c = js[e]
            if c == "{":
                d += 1
            elif c == "}":
                d -= 1
                if d == 0:
                    break
            e += 1
        return js[s:e + 1]
    return None

def pretty(src):
    """按 ; { } 断行，便于阅读（不做完整 JS 美化）。"""
    s = src.replace(";", ";\n")
    s = re.sub(r"\{", "{\n", s)
    s = re.sub(r"\}", "\n}\n", s)
    lines = [l.rstrip() for l in s.split("\n")]
    out = []
    ind = 0
    for l in lines:
        ls = l.strip()
        if not ls:
            continue
        if ls.startswith("}"):
            ind = max(0, ind - 1)
        out.append("    " * ind + ls)
        if ls.endswith("{"):
            ind += 1
    return "\n".join(out)

names = sys.argv[1:]
if not names:
    names = ["ComPost", "CommandAttack", "CommandMove", "ComAjax", "ObjUpdate"]
res = []
for n in names:
    src = find_func(n)
    if not src:
        res.append((n, None, 0))
        continue
    p = os.path.join(OUT, n + ".js")
    with open(p, "w", encoding="utf-8") as f:
        f.write("// %s  (原长 %d)\n\n" % (n, len(src)))
        f.write(pretty(src))
    res.append((n, p, len(src)))

for n, p, ln in res:
    print("%-22s %s %d" % (n, "OK " if p else "MISS", ln))
