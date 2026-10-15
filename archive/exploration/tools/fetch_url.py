"""抓取任意 URL 并打印解码后的正文（调试用）。

    py -3.13 tools/fetch_url.py http://host/path [更多 URL...]
    py -3.13 tools/fetch_url.py --max 20000 URL
"""
from __future__ import annotations

import argparse
import sys

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="抓取 URL 并打印正文")
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--max", type=int, default=8000, help="每个 URL 最多打印多少字符")
    ap.add_argument("--raw", action="store_true", help="不剥离 HTML 标签")
    ns = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    sess = requests.Session()
    sess.headers["User-Agent"] = UA

    for u in ns.urls:
        print("=" * 72)
        print("URL:", u)
        try:
            r = sess.get(u, timeout=25, allow_redirects=True)
        except Exception as exc:                               # noqa: BLE001
            print("失败:", type(exc).__name__, exc)
            continue
        print(f"状态: {r.status_code}　类型: {r.headers.get('Content-Type','')}"
              f"　大小: {len(r.content):,}　最终: {r.url}")
        body = decode(r.content)
        print("-" * 72)
        print(body[:ns.max])
        if len(body) > ns.max:
            print(f"...（还有 {len(body) - ns.max:,} 字符未显示）")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
