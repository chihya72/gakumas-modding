# -*- coding: utf-8 -*-
"""资源 id ↔ 游戏内服装名互查，用于抓帧前确认该换哪件衣服。

数据来自 gakumas-local 汉化插件落地的 master 数据（游戏目录
`gakumas-local/local-files/masterTrans/`），不需要解包。

用法：
  python tools/costume_name.py fktn-cstm-0119            # id → 名字
  python tools/costume_name.py mdl_chr_fktn-cstm-0119_body   # 资源名也认
  python tools/costume_name.py 泳装                       # 名字/描述模糊搜
  python tools/costume_name.py --character fktn          # 列某角色全部服装
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_MASTER = Path(r"D:\Games\gakumas\gakumas-local\local-files\masterTrans")


def load(master: Path):
    def table(name):
        data = json.loads((master / name).read_text(encoding="utf-8"))["data"]
        return {row["id"]: row for row in data}

    costumes = table("Costume.json")
    # 发型表的 id 多一层 costume_head_ 前缀，统一剥掉，查询时不用关心
    heads = {row_id.replace("costume_head_", ""): row for row_id, row in table("CostumeHead.json").items()}
    characters = table("Character.json")
    return costumes, heads, characters


def character_of(asset_id: str, characters: dict) -> str:
    row = characters.get(asset_id.split("-")[0], {})
    name = f"{row.get('lastName', '')}{row.get('firstName', '')}".strip()
    return name or asset_id.split("-")[0]


def normalize(query: str) -> str:
    """`mdl_chr_fktn-cstm-0119_body` → `fktn-cstm-0119`。"""
    text = query.strip()
    if text.startswith("mdl_chr_"):
        text = text[len("mdl_chr_"):]
    for suffix in ("_body", "_hair", "_face"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def describe(asset_id: str, row: dict, characters: dict, kind: str) -> str:
    return (f"{asset_id:22} {row['name']}"
            f"   [{character_of(asset_id, characters)}·{kind}]"
            f"\n{'':22} 获取：{row.get('description', '')}")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", nargs="?", default="", help="资源 id、资源名，或一段服装名/获取方式")
    parser.add_argument("--character", help="按角色前缀列全部，如 fktn / ttmr / hmsz")
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER, help="masterTrans 目录")
    args = parser.parse_args(argv)
    if not args.master.is_dir():
        raise SystemExit(f"找不到 masterTrans：{args.master}")
    costumes, heads, characters = load(args.master)

    if args.character:
        rows = [(i, r, "服装") for i, r in costumes.items() if i.startswith(args.character + "-")]
        rows += [(i, r, "发型") for i, r in heads.items() if i.startswith(args.character + "-")]
        if not rows:
            print(f"没有前缀为 {args.character} 的条目")
            return 1
        for asset_id, row, kind in sorted(rows, key=lambda item: item[0]):
            print(describe(asset_id, row, characters, kind))
        return 0

    if not args.query:
        parser.print_help()
        return 2

    key = normalize(args.query)
    for source, kind in ((costumes, "服装"), (heads, "发型")):
        if key in source:
            print(describe(key, source[key], characters, kind))
            return 0

    hits = [(i, r, kind) for source, kind in ((costumes, "服装"), (heads, "发型"))
            for i, r in source.items()
            if args.query in r["name"] or args.query in r.get("description", "")]
    if not hits:
        print(f"没找到：{args.query}")
        return 1
    for asset_id, row, kind in sorted(hits, key=lambda item: item[0]):
        print(describe(asset_id, row, characters, kind))
    print(f"\n共 {len(hits)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
