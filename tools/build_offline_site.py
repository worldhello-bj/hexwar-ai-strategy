# -*- coding: utf-8 -*-
"""构建离线客户端：镜像官方前端 + 生成本地桩数据 + 生成本地服务器。"""
import os
import re
import json
import shutil

SNAP = r"d:\兵推\snapshot"
RAW = os.path.join(SNAP, "raw")
ASSETS = os.path.join(SNAP, "assets")
PARSED = os.path.join(SNAP, "parsed")
OUT = r"d:\兵推\offline"
SITE = os.path.join(OUT, "site")
MOCK = os.path.join(OUT, "mock")
LOG = r"d:\兵推\analysis\offline_site.md"

for d in (SITE, MOCK):
    os.makedirs(d, exist_ok=True)

rep = []
def w(x=""):
    rep.append(x)

def cp(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)

def cp_raw(name, dst_rel):
    cp(os.path.join(RAW, name), os.path.join(SITE, dst_rel.replace("/", os.sep)))

w("# 离线客户端构建")
w()

# ---------- 1. 客户端文件 ----------
w("## 1. 客户端镜像 `offline/site/`")
w()
copied = []

# main.html（原始 GBK 字节）
cp_raw("main.html", "main.html")
copied.append("main.html")

# 根目录静态资源
for rel in ("war.min.js", "war.min.css", "user.css", "observe.css", "common.css"):
    src = os.path.join(ASSETS, rel)
    if os.path.exists(src):
        cp(src, os.path.join(SITE, rel))
        copied.append(rel)

# cdn 资源目录（原 cdn1.hexwar.cn 的内容）
for sub in ("ico", "icon"):
    src = os.path.join(ASSETS, sub)
    if os.path.exists(src):
        dst = os.path.join(SITE, "cdn1", sub)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        n = sum(len(f) for _, _, f in os.walk(dst))
        copied.append("cdn1/%s (%d)" % (sub, n))

# 其余目录
for sub in ("Hex1", "Hex", "hexcolor", "lib", "skin"):
    src = os.path.join(ASSETS, sub)
    if os.path.exists(src):
        dst = os.path.join(SITE, sub)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        n = sum(len(f) for _, _, f in os.walk(dst))
        copied.append("%s (%d)" % (sub, n))

w()
for c in copied:
    w("- %s" % c)
w()

# ---------- 2. SetUp.js 打补丁 ----------
w("## 2. SetUp.js 路径改写")
w()
su = open(os.path.join(ASSETS, "SetUp.js"), encoding="utf-8", errors="replace").read()
su2 = su.replace("http://cdn1.hexwar.cn/", "/cdn1/")
cp(os.path.join(ASSETS, "SetUp.js"), os.path.join(SITE, "SetUp.js.orig"))
with open(os.path.join(SITE, "SetUp.js"), "w", encoding="utf-8") as f:
    f.write(su2)
w("- `CDNServer` 由 `http://cdn1.hexwar.cn/` 改为 `/cdn1/`")
w("- 发现改写: %s" % ("是" if su != su2 else "否"))
w()

# ---------- 3. 桩数据 ----------
w("## 3. 桩数据 `offline/mock/`")
w()

def put(name, data, mode="wb"):
    p = os.path.join(MOCK, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if mode == "wb":
        if isinstance(data, str):
            data = data.encode("gb18030")   # 官方 ASP 输出为 GBK
        open(p, "wb").write(data)
    else:
        open(p, "w", encoding="utf-8").write(data)
    return len(data)

mock = []

# User_Get.asp —— 原样快照
ug = open(os.path.join(RAW, "User_Get.asp.txt"), "rb").read()
mock.append(("User_Get.asp", put("User_Get.asp", ug)))

# SetUp.js（跑在客户端
mock.append(("SetUp.js", len(su2.encode("utf-8"))))

# Map_Get.asp
mg = open(os.path.join(RAW, "Map_Get.asp.json"), "rb").read()
mock.append(("Map_Get.asp", put("Map_Get.asp", mg)))

# Map_Get_Under.asp
mock.append(("Map_Get_Under.asp", put("Map_Get_Under.asp", "{}")))

# offlinemapdata.asp
om = open(os.path.join(RAW, "offlinemapdata.asp.txt"), "rb").read()
mock.append(("offlinemapdata.asp", put("offlinemapdata.asp", om)))

# City_Get.asp
cg = open(os.path.join(RAW, "City_Get.asp.html"), "rb").read()
mock.append(("City_Get.asp", put("City_Get.asp", cg)))

# Obj_Get.asp
og = open(os.path.join(RAW, "Obj_Get.asp.html"), "rb").read()
mock.append(("Obj_Get.asp", put("Obj_Get.asp", og)))

# ObjAjax.asp（去掉尾逗号，保持客户端 eval 兼容）
oaj = open(os.path.join(RAW, "ObjAjax.asp.json"), "rb").read().decode("utf-8", errors="replace")
oaj = re.sub(r",\s*$", "", oaj.strip())
oaj = re.sub(r",(\s*})", r"\1", oaj)
mock.append(("ObjAjax.asp", put("ObjAjax.asp", oaj.encode("ascii", errors="replace"))))

# 其它空响应
empties = {
    "RoomStat.asp": "",
    "Report_Attack.asp": "\u79bb\u7ebf\u5feb\u7167\uff1a\u65e0\u6218\u62a5|",
    "AIUser.asp": "1243",
    "UserTeamShow.asp": ",",
    "UserCheck.asp": "",
    "UserStat.asp": "\u79bb\u7ebf\u6a21\u5f0f",
    "objinfo.asp": "",
    "ObjInfo.asp": "",
    "Obj_Weapon.asp": "",
    "Obj_Guide.asp": "",
    "SystemArmy.asp": "",
    "jmDataList.asp": "",
    "GetRoadRot.asp": "",
    "MeterGrid.asp": "",
    "MeterGridData.asp": "",
    "loadFireData.asp": "",
    "com/CheckConn.asp": "",
    "com/ComAjax.asp": "",
    "com/ObjInto.asp": "True",
    "com/ComFlag.asp": "",
    "com/ComFlagTime.asp": "",
    "com/ComTime.asp": "",
}
for k, v in empties.items():
    mock.append((k, put(k, v)))

w("| 桩文件 | 字节 |")
w("|---|---|")
for k, n in mock:
    w("| `%s` | %d |" % (k, n))
w()

with open(LOG, "w", encoding="utf-8") as f:
    f.write("\n".join(rep))
print("offline site built; mock files:", len(mock))
