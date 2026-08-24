# target-rig 实机验收清单（A 类）

> **这份是判据定义** —— 「进游戏该看什么、看到什么算过」。里面的项目不是排期，别当待办读。

日期：2026-08-18 · 2026-08-20 复核（去掉与路线文档重复的数值）

性质：**离线做不了的那几件事，进游戏一次该看什么。** 判据全部写成"跑哪个命令 / 看哪个数字"，
不要靠人眼滚日志。路线与顺序见
[`ab-target-rig-route-2026-08-17.md`](ab-target-rig-route-2026-08-17.md)。

贯穿规矩 1：**每次进游戏只改一个主要变量**。下面四项各自是一次独立的运行，别合并。

尺子：

```bash
python tools/read_runtime_log.py "D:/Games/gakumas/gakumas-mod/mod-plugin.log"
```

退出码 0 = 全部判据通过；非 0 打印"不合格：<键名>"。`--samples` 附原文，`--all` 判整个文件。

**默认只判最后一次启动之后的内容**（日志跨会话追加，上一次跑的报错不该算到这次头上）。

---

## 1. 批次 5：组件装配 fail-closed（正常包不误报）—— ✅ 2026-08-18 已通过（日志尺子退出码 0）

装的是 `hmsz-fuyuko-icu`（11 根新骨全带摇物 + 2 条链），实测：

```text
skeleton graft 2 行   droppedInfluences [0]   fallbackVertices [0]
swingDynamicBones [203,206,236,238]  300 帧 16/23 bones moved
driverRefused / driverRolledBack / driverMissing / nullReference   全 0     ← 这次要验的
error 0（修掉两条假警报之后）
```

跑这一轮**顺带修了三个东西**，接手的人不用再踩：

1. `SkinnedMeshRenderer.ResetBounds` / `ResetLocalBounds` 在这版游戏里被裁掉了，而调用处本来
   就判空降级 —— 以前每次启动刷两条 `[ERROR]`。已降为 Info（`Il2cppUtils::GetMethod` 的
   `optional` 参数）：**假警报会把"日志里有 error 就得看一眼"这条规矩磨钝**；
2. 日志尺子自己有静默通过的 bug：`error` 写着"期望 0"、实测命中 2 行，却照样打印"全部判据通过"。
   现在判定规则必须**恰好覆盖** CHECKS（漏一项直接断言失败），并补了回归用例；
3. 日志是**跨会话追加**的。修完重跑仍报 2 条，实际是 566 行里第 68/69 行的历史。
   尺子现在默认只判**最后一个 `[BOOT]` 之后**的内容，`--all` 才看整个文件。

下面是原始判据，重跑时照此核对。



装一个**现成的、已发布过的**包（例如 `mod-workspace/mods/release/chisaki-swimsuit`），
直接回主页看人物。

| 看什么 | 期望 |
|---|---|
| `read_runtime_log.py` 退出码 | 0 |
| `driverRefused` / `driverRolledBack` / `driverMissing` | 全 0 —— 有值就是**误报**，收严收过头了 |
| `nullReference`（"按空引用跑"） | 0 —— 批次 5 之后这行不该再出现 |
| 画面 | Mesh / 材质 / 骨骼 / 颜色都对，裙摆袖口会动 |

反向那一半（坏 sidecar 必须整体拒绝）**已经离线验过**：`mod_runtime_catalog_tests` 里的
`DriverPrecheckSmoke`，且把预检打断后测试确实变红。所以这次只验"不误报"。

## 2. 批次 6：`collisionMask` 定性（只改这一项）—— ✅ 2026-08-22 已判定：**众数对，`-1` 错**

**结论先写**：拿包臀裙样本 chs-sucu-00 出的 A/B 两版（除 `collisionMask` 外逐字节相同），
实机画面判定：

```text
A 众数  skirt=1 / ribbon=256   buildId 70ec1d5e91486e73   裙摆正常贴腿
B 全 -1 collisionMask=-1 ×84   buildId 1a66d9ab686e813c   **裙摆整个炸开**（作者截图）
```

`-1` = Everything，裙摆会去撞半径 0.23m 的胯胶囊，被顶得整片翻飞 —— 症状比预期的"发僵"更极端。
所以 `swing_presets.json` 里那套原版众数（`skirt=1 / cloth=64 / sleeve=0 / ribbon=256`，
`48292` 根原版骨扫出来的）是对的，**不要再回退到 `-1` 兜底**。批次 6 到此收口。

游戏已切回 A；对照包 B 留在 `mods/mdl-chr-chs-sucu-00-body-ab-maskall/`（`enabled:false`），
要复现把它打开、把 A 关掉、**重启游戏**（别用游戏内 UI 切，那条路径会崩，见路线文档 §H）。

<details><summary>原始判据（重跑时照此核对）</summary>


⚠️ **众数已经装进预设了**（2026-08-18 02:50，`tools/scan_vanilla_swing_bones.py … --collision-mask vanilla --install` 跑过）。
四个数字看 `gakumas_mi/swing_presets.json` 的 `_collisionMask` 注，本文不复写。这一项 2026-08-22 已用有对照的画面判定收口（见本节开头）。
拿同一个窄裙样本各出一版 `-1` 与众数，同机位各录一张。

**两版已经出好并装机（2026-08-21）**，载具就是 chs-sucu-00 那条包臀裙：

```text
A 众数（现状）  mdl-chr-chs-sucu-00-body-ab          buildId 70ec1d5e91486e73  enabled=true
                skirt=1 ×42、ribbon=256 ×42
B 全 -1（对照） mdl-chr-chs-sucu-00-body-ab-maskall  buildId 1a66d9ab686e813c  enabled=false
                collisionMask=-1 ×84
```

B 是拿 A 的 `bundle-src` 只改 `collisionMask` 重打的，**已逐项证明只差这一个变量**：
6 张贴图 + geojson 的 SHA-256 逐字节相同；两份 sidecar 的差异只有 84 处 `collisionMask`
和 `buildId`；`boneCount 184`、`swingChains 4`、`extraSwingBones 14` 三项计数一致。

切换方式：改两个 `mod.json` 的 `enabled`（或用管理器 UI 切），然后**切一次服装/角色**让
`BuildModel` 重跑，物理才会按新值重建。同机位各录一张。

进游戏对比：

| 看什么 | 期望 |
|---|---|
| 裙摆贴腿 | 不发僵、不穿插（`-1` 去撞半径 0.23m 的胯胶囊就是这个症状） |
| 该撞的还撞 | 裙摆与腿仍有碰撞，不是穿过去 |
| ~~`swingMoved`~~ | 探针已删（2026-08-22），改看画面 |

两种档各录一次同机位截图。**判据是画面**，日志只用来确认解算没停。
</details>

## 3. §11.3：八个验收场景（新骨物理）

带自建摇物链的包，逐个场景看：原地待机 / 走路 / 跑步 / 跳舞 / 快速转身 / 裙腿碰撞 /
飘带身体碰撞 / 连续 300 帧运动。判据：**无重复求解、爆振、抽搐、穿透**。
日志侧同时确认 `chainDestroyed == 0`。
（`swingMoved` 那条判据没了：300 帧探针 2026-08-22 从运行时删掉了，它是测试期的东西。
现在"骨有没有被收进解算表"看 `swingDynamicBones`，"有没有真的动"只能看画面。）

## 4. 批次 7：三类样本（P8）

顺序 1 → 2a → 2b → 3，每个样本都先过离线闸门再进游戏。

| # | 样本 | 进游戏前先跑 | 进游戏看 |
|---|---|---|---|
| 1 | 只有人体骨、无额外物理骨 | 「对齐体检」全绿或仅黄；导出不被拦 | 姿势正常，转身不炸 |
| 2a | 蓬裙 + **源自带裙骨** | 同上 + `swingChains` 有值 | 裙摆会动、不压平、不穿腿 |
| 2b | 蓬裙 + **源裙子没骨**（Blender 里建骨） | 同上 | 同上 |
| 3 | 麦克风 / 手持物 / 头饰 / 特殊 socket | 手骨那几行仍是 direct 全绿 | 道具位置朝向对（socket 由运行时补，见上表） |

第 3 类在这条路线下 socket 是原版的、我们不碰，**天然应该过** —— 它验的其实是"我们没动到手骨"。

---

## 出问题时的取证顺序

1. `read_runtime_log.py --samples`：先看哪个键不合格、原文长什么样；
2. 硬崩：`Player.log` 的原生栈 + `llvm-symbolizer` + build 里的 pdb（别靠日志尾巴猜）；
3. 画面不对但日志全绿：回 Blender 点「量对齐 / 跨关节带」，那两个数决定是对齐问题还是权重问题；
4. 改任何一项之前，先确认插件目录是拷贝、且**重启过游戏**（`mod-plugin.log` 的时间戳）。
