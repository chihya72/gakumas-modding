# 工作区归并 P0 快照

记录时间：2026-07-28（Asia/Shanghai）  
状态：P0 已验证完成；未移动或删除原文件

## 恢复点

独立备份根目录：

`C:\Users\10725\Documents\gakumas-modding-backup\2026-07-28\p0`

| 内容 | 当前状态 | 恢复文件 | SHA-256 |
|---|---|---|---|
| 主仓库 | `research/ab-route-swing-physics` @ `c1cfc262497a162940a8ed87c511a9a392e1d0ca`；9 个修改、3 个未跟踪文件 | `main\repository.bundle` | `376EA1114E3179218CA3F0CD0C216999FD8B4A1EDF31B908CB0DFC1EA0683F0B` |
| 权威 DLL runtime | `codex/checkpoint-modruntime-20260727` @ `cf154286f6ff4403aea3807862ee624bc89da612`；工作区干净 | `authoritative-runtime\repository.bundle` | `73CEC241717FBF7169FA2765CDE664057CB00951A1A55DAF22084F64EFEE8374` |
| `D:\chinosk6` 下的旧 localify 工作树 | `main` @ `43da4e83136c89dff234df37a0addc379a2c4363`；`Hook.cpp` 有未提交修改 | `older-localify-worktree\repository.bundle` | `C292D47C07818CE342027E4C093A81B333C0F62C04D2AEB2E3B416D389813B53` |

三个 bundle 均已执行 `git bundle verify`，Git 判定为完整历史。主仓库当前的 12 个未提交/未跟踪文件和旧
localify 工作树的 `Hook.cpp` 另按原相对路径复制；源文件与备份逐项比较大小和 SHA-256，全部一致。
逐项记录位于 `p0-file-manifest.csv`；清单自身的哈希从备份目录现场重算，避免在本文件中形成自引用。

## 孤立 Blend 救援

源文件：

`C:\Users\10725\Desktop\weighted.blend1`

恢复文件：

- `C:\Users\10725\Desktop\weighted.recovered-20260727.blend`
- `C:\Users\10725\Documents\gakumas-modding-backup\2026-07-28\p0\weighted.recovered-20260727.blend`

三份文件均为 8,188,472 字节，SHA-256：

`365CEF1B2F917B163706A264707958EE7699AB28B822DA62501A7770B053CE36`

Blender 4.5.3 LTS 已用后台模式打开恢复文件且未保存：

- 1 个场景；
- 7 个对象；
- 2 个 Mesh 数据块；
- 0 个 Image 数据块；
- 0 个外部 Library。

因此该 `.blend1` 已成功恢复为可读 `.blend`，原文件仍保留。

## 明确未处理

- `C:\Users\10725\Desktop\MOD` 未扫描、未复制、未移动、未删除；
- IP、SCSP 和三个受保护流程数据尚未移动或删除；
- `D:\chinosk6\gkms-localify-dmm` 不是权威 runtime 来源，其脏工作树已单独保护，暂不清理。
