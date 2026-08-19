# 批次 7 实验脚本存档（2026-08-18 ～ 08-19）

这些是 dress-2219 / hmsz-cstm-0059 那一批实机实验的**复现配方**，原先只存在于
`mod-workspace/experiments/`（不在任何 git 仓里）。2026-08-20 收进仓，去掉了纯路径差异的重复件。

跑法一律是无头 Blender 4.2，最后一个参数是作者 blend：

```
blender --background --python tools/experiments/<脚本>.py -- <authoring.blend>
```

脚本里的 `repo` / `template` / `package_root` 是硬编码绝对路径，换机要改。输出目录已存在时脚本
主动报错拒绝覆盖（原样保留，这是当时的防呆）。

| 脚本 | 对应实验 | 路线文档 |
| --- | --- | --- |
| `batch7_sample2a_inspect.py` | 只读：列 blend 里的对象/骨架 | — |
| `batch7_sample2a_modifiers.py` | 只读：列修改器栈 | — |
| `batch7_sample2a_report.py` | 只读：出对齐尺子报告 | — |
| `batch7_sample2a_align_export.py` | 最早的整体对齐导出（挂饰横向错位的那版） | route §B |
| `batch7_sample2a_rebuild_preserve_accessories.py` | D 包：只校正人体 direct 骨，保留饰骨原始矩阵 | route §D |
| `batch7_sample2a_control_export.py` | 对照组：D 的逻辑 + 旧 physics-override（`.bak-2026-08-19`） | route §E |
| `batch7_sample2a_ribbon_accessories_export.py` | D + 把 Bag/Chain/Key/Spine_Bow 判成 ribbon | route §E/§274 |
| `batch7_sample2a_selective_root_export.py` | 「链根自己摆」的第一版 | route §F |
| `batch7_sample2a_lock_d_physics.py` | 纯数据：把 D 的物理参数锁进 physics-override | route §F |
| `batch7_sample2a_reduce_to_d_plus_roots.py` | 纯数据：把 override 缩到 D + 链根 | route §F |
| `batch7_sample2a_fuku_export.py` | 作者 123 行表单直出（**下面 6 次重跑用的是同一份脚本**） | route §G |
| `batch7_fuku_accessory_swing_export.py` | 同上 + 挂饰摇物那一次 | route §G |
| `batch7_gate9_negative.py` | 闸门 9 反例：`gmi_allow_undecided = False`，验证默认会拦 | route 批次 3 |

**没收进来的重复件**：`batch7_fuku_{anchor,lace,revert,ribbon,rigid,symfix}_export.py` 六个文件与
`batch7_sample2a_fuku_export.py` 除了 `package_root` 一行**完全相同**——那六次实验的变量全在
作者 blend 的 123 行表单里，不在脚本里。要重跑就改 `package_root`。

`batch7_gate9_negative.py` 依赖 bpy + `libraries/assetstudio-body-json` + 模板 bundle，跑不成
单元测试；`tests/test_undecided_gate.py` 是它的离线版。
