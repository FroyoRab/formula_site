#!/usr/bin/env python3
"""批量导入配方到 formula_site。"""

from __future__ import annotations

import argparse
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List


@dataclass
class Formula:
    name: str
    content: str


def parse_blocks(raw_text: str) -> List[Formula]:
    blocks = [block.strip() for block in raw_text.replace("\r\n", "\n").split("\n\n")]
    formulas: List[Formula] = []
    for block in blocks:
        if not block:
            continue
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        name = lines[0]
        content = "\n".join(lines[1:]).strip()
        if not content:
            # 若某段只有标题没有内容，仍保留一行占位，避免后端 required 校验失败。
            content = "待补充"
        formulas.append(Formula(name=name, content=content))
    return formulas


def submit_formula(target: str, formula: Formula, timeout: int = 20) -> tuple[bool, str]:
    payload = urllib.parse.urlencode({"name": formula.name, "content": formula.content}).encode("utf-8")
    request = urllib.request.Request(target, data=payload, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            code = response.getcode()
            ok = 200 <= code < 400
            return ok, f"HTTP {code}"
    except urllib.error.HTTPError as err:
        return False, f"HTTP {err.code}"
    except Exception as err:  # noqa: BLE001
        return False, f"{type(err).__name__}: {err}"


def main() -> int:
    parser = argparse.ArgumentParser(description="批量导入配方到 formula_site")
    parser.add_argument("input", help="包含配方原文的 txt 文件路径")
    parser.add_argument("--host", default="8.153.76.179:65521", help="目标主机:端口")
    parser.add_argument("--base-path", default="/12sagittarius_ghpishbc", help="站点根路径")
    parser.add_argument("--dry-run", action="store_true", help="仅解析不提交")
    args = parser.parse_args()

    raw_text = open(args.input, "r", encoding="utf-8").read()
    formulas = parse_blocks(raw_text)
    if not formulas:
        print("未解析到任何配方，请检查输入格式。", file=sys.stderr)
        return 1

    print(f"解析到 {len(formulas)} 条配方。")
    if args.dry_run:
        for index, formula in enumerate(formulas, start=1):
            print(f"[{index:02d}] {formula.name}")
        return 0

    base = args.base_path.rstrip("/")
    target = f"http://{args.host}{base}/formula/create"

    success = 0
    for index, formula in enumerate(formulas, start=1):
        ok, message = submit_formula(target, formula)
        flag = "OK" if ok else "FAIL"
        print(f"[{index:02d}] {flag} {formula.name} -> {message}")
        if ok:
            success += 1

    print(f"完成：成功 {success}/{len(formulas)}")
    return 0 if success == len(formulas) else 2


if __name__ == "__main__":
    raise SystemExit(main())
