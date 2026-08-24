# -*- coding: utf-8 -*-
"""实机日志尺子：把 `mod-plugin.log` / `Player.log` 里该看的那几行**量成数字**。

实机一次成本高（memory: 别把没验证的实验塞进测试包），所以进游戏之前就把"该看什么"写死在
这里，回来只跑一次这个脚本，别靠人眼滚日志。四组判据一一对应路线文档里待实机的四件事：

  A. 组件装配 fail-closed（批次 5）  预检拒绝 / 撤掉组件 / 半初始化组件泄漏
  B. 摇物真的在被解算（§11.2）      `swingDynamicBones=N`、链数、驱动器数
  C. 蒙皮真的按 lossless 走          `Applied lossless IP skeleton graft`+droppedInfluences
  D. 有没有静默洞                    "找不到骨/空引用/跳过"这类 warn

用法：
  python tools/read_runtime_log.py "D:/Games/gakumas/gakumas-mod/mod-plugin.log"
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

# 一条规矩一条正则。**只收无条件输出的行**（memory: 别 grep `bindposeMode`，当前包没有那行输出，
# 误判成失败）。数字用命名组 `n` 抓出来，判据写在 CHECKS 里，别散在打印语句中。
PATTERNS = {
    "graft": re.compile(r"Applied lossless IP skeleton graft"),
    "droppedInfluences": re.compile(r"droppedInfluences=(?P<n>\d+)"),
    "fallbackVertices": re.compile(r"fallbackVertices=(?P<n>\d+)"),
    "swingDynamicBones": re.compile(r"swingDynamicBones=(?P<n>\d+)"),
    "swingChains": re.compile(r"ActorSwing chain built on prefab"),
    "chainDestroyed": re.compile(r"ActorSwing chain has no usable rootBones, destroyed"),
    "driverAttached": re.compile(r"驱动器 .* ← ActorAnimationQuartzDriver"),
    "driverRefused": re.compile(r"拒绝挂 ActorAnimationQuartzDriver"),
    "driverRolledBack": re.compile(r"已撤掉刚挂的组件|已撤掉（不留半成品）"),
    "driverMissing": re.compile(r"的驱动器没挂上，这根骨在游戏里不会动"),
    # 这两条是**真实日志里存在**的行（2026-08-18 用 D:/Games/gakumas 的 mod-plugin.log 校准）。
    # 别写宽泛的 "missing|找不到"：那会把 whole-object 的契约缺口和"骨没找到"混成一堆。
    "socketGrown": re.compile(r"Grew missing socket nodes from replaced asset.*count=(?P<n>\d+)"),
    "wholeObjectGap": re.compile(r"Whole-object contract gap"),
    "nativeChainLayers": re.compile(r"native ActorSwing chain layers"),
    # 300 帧摇物探针 2026-08-22 从运行时删掉了（`SampleSwingMotion`，测试期的东西）。
    # 它产出的 swingMoved / swingProbe* 三个键随之下线；老日志里还有那些行也不再判。
    "boneNotFound": re.compile(r"指向的骨 .* 找不到|resolveBone .* failed"),
    "nullReference": re.compile(r"按空引用跑"),
    "error": re.compile(r"\[error\]|Log::Error|ERROR", re.IGNORECASE),
}

# (键, 期望, 判读) —— 期望写成一句话，脚本不猜；`None` = 只报数字不判。
CHECKS = (
    ("graft", "≥1", "蒙皮走的是 lossless graft（带 skeleton 的包都该走这条）"),
    ("droppedInfluences", "全部为 0", "有非 0 就是有顶点的权重被丢掉了"),
    ("fallbackVertices", "全部为 0", "有非 0 就是有顶点退回了兜底骨"),
    ("swingDynamicBones", ">0（这个包有新摇物骨时）", "游戏把骨**收进**解算表了（注册）"),
    ("driverRefused", "0", "预检拒绝 = 有 sidecar 引用对不上；正常包不该出现（批次 5）"),
    ("driverRolledBack", "0", "回滚 = 预检过了但装配失败；正常包不该出现"),
    ("driverMissing", "0", "有的话那根骨在游戏里不会动"),
    ("nullReference", "0", "半初始化组件按空引用跑 —— 批次 5 之后不该再有这行"),
    ("error", "0", "任何 error 都要看一眼"),
)

# 只报数字、不判好坏的那些（它们是"发生了什么"，不是"对不对"）
NOTES = {
    "socketGrown": "运行时从被替换资产**长出**缺的 socket 节点（手持道具挂点等），"
                   "所以参考资产里没有 socket 不影响成品",
    "wholeObjectGap": "whole-object 对照组的契约缺口 —— 出现说明这份日志来自那条已作废的路线",
    "nativeChainLayers": "原版 ActorSwing 链被读到了（层数/骨数）",
}


# 每次启动写一行 `[BOOT] ... runtime <版本> loaded`。日志是**跨会话追加**的，所以默认只判
# 最后一个 BOOT 之后的内容 —— 否则上一次跑（旧 DLL、旧包）的报错会算到这次头上。
# 2026-08-18 就撞到了：修完 ERROR 重跑，脚本仍报 2 条，实际是 566 行里第 68/69 行的历史。
BOOT_LINE = re.compile(r"\[BOOT\].*loaded")


def last_session(lines):
    """最后一次启动之后的行（含那行 BOOT）。没有 BOOT 行就返回全部。"""
    start = 0
    for index, line in enumerate(lines):
        if BOOT_LINE.search(line):
            start = index
    return lines[start:], start


def scan(path: Path, since: str | None = None, whole_file: bool = False):
    counts: Counter[str] = Counter()
    numbers: dict[str, list[int]] = {}
    samples: dict[str, list[str]] = {}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    boot_at = 0
    if not whole_file and since is None:
        lines, boot_at = last_session(lines)
    started = since is None
    for raw in lines:
        if not started:
            started = since in raw
            if not started:
                continue
        for key, pattern in PATTERNS.items():
            match = pattern.search(raw)
            if not match:
                continue
            counts[key] += 1
            if "n" in (match.groupdict() or {}):
                numbers.setdefault(key, []).append(int(match.group("n")))
            if len(samples.setdefault(key, [])) < 3:
                samples[key].append(raw.strip()[:160])
    return counts, numbers, samples, boot_at


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("log", type=Path)
    parser.add_argument("--since", default=None,
                        help="只看含这个字串（一般是时间戳）的那一行之后的内容")
    parser.add_argument("--samples", action="store_true", help="每类附最多 3 行原文")
    parser.add_argument("--all", action="store_true",
                        help="判整个文件（默认只判最后一次启动之后的内容）")
    args = parser.parse_args(argv)
    if not args.log.is_file():
        raise SystemExit(f"日志不存在：{args.log}（先确认插件目录是拷贝、且重启过游戏）")

    counts, numbers, samples, boot_at = scan(args.log, args.since, whole_file=args.all)
    scope = ("整个文件" if args.all or args.since else f"最后一次启动（第 {boot_at + 1} 行起）")
    print(f"日志 {args.log}（{args.log.stat().st_size / 1024:.0f} KiB）；判定范围：{scope}")
    print("\n判据：")
    for key, expected, note in CHECKS:
        values = numbers.get(key)
        detail = (f"值 {sorted(set(values))}" if values else f"命中 {counts.get(key, 0)} 行")
        print(f"  {key:20} 期望 {expected:22} {detail:26} {note}")
    print("\n其余计数（只报数字，不判好坏）：")
    for key in PATTERNS:
        if key in {name for name, _e, _n in CHECKS}:
            continue
        values = numbers.get(key)
        detail = f"值 {sorted(set(values))}" if values else str(counts.get(key, 0))
        print(f"  {key:20} {detail:22} {NOTES.get(key, '')}")
    if args.samples:
        print("\n原文样本：")
        for key, lines in sorted(samples.items()):
            for line in lines:
                print(f"  [{key}] {line}")
    # 判据表里写了期望的每一项都必须真的参与判定。之前 `error` 写着"期望 0"、实测命中 2 行，
    # 脚本却照样打印"全部判据通过" —— 那正是这套工具存在意义的反面（静默通过）。
    # 所以三类规则合起来必须**恰好覆盖** CHECKS，少一个就在这里断言失败，别再手抄键名清单。
    zero_count_keys = {"driverRefused", "driverRolledBack", "driverMissing",
                       "nullReference", "error"}
    zero_value_keys = {"droppedInfluences", "fallbackVertices"}
    positive_keys = {"graft", "swingDynamicBones"}
    assert zero_count_keys | zero_value_keys | positive_keys == {
        name for name, _expected, _note in CHECKS}, "判定规则没覆盖 CHECKS 里的全部项"

    bad = [key for key in sorted(zero_value_keys)
           if any(value != 0 for value in numbers.get(key, []))]
    bad += [key for key in sorted(zero_count_keys) if counts.get(key)]
    if not counts.get("graft"):
        bad.append("graft（这份日志里可能根本没应用过 mod）")
    for key in ("swingDynamicBones",):
        # 有输出但全是 0 = 探针跑到了、结论是"没有"，这不叫通过
        if numbers.get(key) and not any(value > 0 for value in numbers[key]):
            bad.append(f"{key}（有输出但全是 0）")
    if bad:
        print("\n不合格：" + "、".join(bad))
        return 1
    print("\n全部判据通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
