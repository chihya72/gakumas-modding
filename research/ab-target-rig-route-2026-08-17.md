# AB 目标骨架路线（target-rig）：架构、契约与落实顺序

日期：2026-08-17

性质：**路线与顺序的唯一入口。** 本文取代 `ab-source-proxy-summary-and-roadmap-tpose-locked-2026-08-16.md`
的路线职责（两副骨架桥与 whole-object 转向）；那份对照组记录已于 2026-08-20 从 `research/` 删除，
结论见 [`lessons-learned.md`](lessons-learned.md) §7。

两份主文档的分工：

| 文档 | 管什么 |
|---|---|
| **本文** | **做什么、按什么顺序做**（架构、数据契约、闸门、落实顺序） |
| [`ab-consolidated-facts-and-evidence-2026-08-16.md`](ab-consolidated-facts-and-evidence-2026-08-16.md) | **已知什么、量到多少、怎么量才不出错**（事实与证据的唯一入口） |

冲突时：路线与顺序以本文为准，事实与数字以事实文档为准。

---

## §0 这条路线做完了什么 —— 历史记录

日期：2026-08-22 收口。**本文是历史记录，不是计划**：下面每格都是当时可复跑的数字，
不写"下一步""待办"。要开新工作请另立文档，别把这里的记录当成排期。

| 批次 | 状态 | 可复跑判据 |
|---|---|---|
| 1 仪表与词汇 | ✅ | 原版身体 `104/104` 根方向差 `0.00°`；小臂反例 `172°` 报红、位置差 `0`；chisaki `347` 骨 → `75` 行 |
| 2 参考资产 | ✅ | 逐骨 `150` 根（无权重 `18`）；最大位置差 `0.00008 mm`、朝向差 `0.000000°` |
| 3 权重与闸门 | ✅ | 删除 `LeftShoulder` 后 `864` 顶点最大误差 `5.96e-08`；拦下导出的判据 `7` 组（逐条 + 实现位置见批次 3 的表）；朝向差 `≥15°` 拒绝导出 |
| 4 打包 | ✅ | zip `10.8 MiB`；bundle 对象 `11/11` 逐项一致；覆盖 Blender `4.2/4.5.3` |
| 5 Runtime 收严 | ✅ | `hmsz-fuyuko-icu` 会话：`graft=2`、`droppedInfluences=0`、`fallbackVertices=0`；`driverRefused/RolledBack/Missing/nullReference/error=0`；`swingDynamicBones=[203,206,236,238]`。（当时还有一条 300 帧探针的 `16/23` 根移动 —— 探针已于 2026-08-22 从运行时删除） |
| 6 物理 | ✅ 3/3（2026-08-22 收口） | 驱动器作用域 `1/1`、置灰+闸门 `1/1`；`collisionMask` **定性已做**：拿包臀裙样本出 A/B 两版（除 84 处 `collisionMask` 外逐字节相同），`-1` **裙摆整个炸开**、众数（`skirt=1/ribbon=256`）正常 —— 判据是画面，见 [`ab-target-rig-ingame-checklist.md`](ab-target-rig-ingame-checklist.md) §2 |
| 7 验证样本 | ✅ 做了三个 | 样本 `1`（只有人体骨，fktn-miku）实机通过；样本 `2a`（源自带裙骨，dress-2219）定版 `1375a006a8fc685f`；跨游戏源 chs-sucu-00（IP 的包臀裙）实机通过（见 §H），顺带修掉 8 个插件缺陷 + 2 个新路径专有缺陷。判据见 [`ab-target-rig-ingame-checklist.md`](ab-target-rig-ingame-checklist.md) |

几何判部件类型已进生产、五档补齐 `bake`/`reject` 两档并接上闸门、节数不同的塌链会被标出来。

### 环境现状

- `D:/Games/gakumas/xinput1_3.dll`：**2026-08-19 已换成不带半透明探针的版本**，SHA-256
  `AAC1D606405BDAEAA294C8F6987AB95C36EBC3432A03B035996BCFFEDC40635B`（`tools/package.ps1 -Version dev`
  产出，`3/3` 原生检查通过）；`version.dll` 未改动。
  - 换掉的那版是 `3F1E3D81…`：它每次启动都装 7 个 VL 半透明只读探针
    （`VLActorTransparentPass.Execute` / `VLActorGBuffer.*` / `VLDeferredPass.*` / `VLPostProcessPass.*`），
    A→B→D 三轮实机全程带着这个**没人声明的变量**。现在这些探针收在 `InstallVLProbeHooks()` 里，
    只有半透明路线自己的任一 `.on` 开关（或空文件 `vl-probes.on`）存在时才装 —— 那条路线要用照样打开。
  - `gakumas-mod/gmi_shaders.bundle` 已从游戏目录移除（与 `gakumas-mod-runtime/packaging/gmi_shaders.bundle`
    逐字节相同，随时可放回）。
- `gakumas-mod/config.json`：当前 `logLevel=info`。**2026-08-21 装机状态**：启用
  `batch7-sample1-fktn-miku`（`86cca1693c476307`）和 `mdl-chr-chs-sucu-00-body-ab`
  （`70ec1d5e91486e73`，见 §H）；`batch7-sample2a-hmsz-source-skirt`（`1375a006a8fc685f`）
  **已 `enabled:false`** —— 它和 chs-sucu 抢同一个 `mdl_chr_hmsz-cstm-0059_body` 槽，
  同槽同优先级只能有一个生效。
- 当前窄裙 Bundle：SHA-256 `C5C0C7FFF2B273A9C63246EB273A66BC0FE6E82A14A17A358195A3E552CBE2DB`；日志最近会话 `error=0`，但有大量 info 诊断输出。
- 两仓工作区状态：2026-08-20 已全部提交（`gakumas-modding` 批次 1–7 + 四个修复；`gakumas-mod-runtime`
  批次 5 收严 + 300 帧探针）。推送状态见各仓 `git status`。

### 全套回归

当前全绿基线：pytest `136/136`（2026-08-21 复跑，比 08-20 多的 6 条全是这一批新增闸门/尺子的正反用例）、
Blender 冒烟 `5/5`；runtime 构建包含 `3/3` 个原生检查。

> 2026-08-19：这条曾经是红的（`111/112`）。`--collision-mask vanilla --install` 装了众数，
> 但 `tests/test_bundle_source_contract.py` 里还钉着 `collisionMask == -1`，实测出的是 `256`。
> 现在改成「出的值等于基准表」+ 单独钉住基准表那四个众数，改预设不再让它无故变红。

```powershell
python -m pytest tests/ -q                                      # 130 passed
$smokes = @('blender_ui_smoke.py','blender_smoke.py','blender_reference_rig_smoke.py','blender_weight_split_smoke.py','blender_bake_rest_offset_smoke.py')
foreach ($name in $smokes) { blender --background --factory-startup --python-exit-code 1 --python "tests/$name" }  # 5 套；4.2 与 4.5.3
Push-Location ..\gakumas-mod-runtime; .\tools\package.ps1 -Version dev; Pop-Location  # 构建 + 3 个原生检查 + 打包
python tools/read_runtime_log.py "D:/Games/gakumas/gakumas-mod/mod-plugin.log"                  # 日志尺子，退出码 0 才算通过
```

runtime 的 3 个原生检查是 `ModPresentationModelTests`、`DriverPrecheckSmoke`、`ModRuntimeCatalogSmoke`。

### 三条反复复现的教训

1. **先确认量的是不是你以为的东西**。
2. **每个检查证两个方向**：坏样本会报，正常样本不误报。
3. **能读就别猜**：先读源码和日志，再下结论。

---

### 批次 7·2a 的实机回归（2026-08-19，已收口）

六轮实机的过程叙述已删，留结论与可复跑的包哈希：

| 包 | 现象 | 结论 |
|---|---|---|
| B `c06816ff7908dcee` / `095EDA04…` | 整件衣服向角色右侧偏移 | 导出脚本把**所有非 `direct` 骨**一起乘上了人体父骨的目标矩阵差，绕过了五档分类 |
| D `a157b8da783ac081` / `C5C0C7FF…` | 腰线与主体裙摆回中心，小挂饰仍偏 | 只对人体 `direct` 骨对齐、装饰骨保留源矩阵。离线凭据：`boneCount=225`、helper-rig 权重 `13.5%`（原版 `11.28%`）、与目标 `156` 个共同骨最大位置差 `0mm`／朝向差 `0.0497°` |
| E（小挂饰按 ribbon） | 小挂饰没修好，**裙摆花边被拖出锯齿** | 按骨名选作用范围、没量影响面。两条 `Spine_Bow_*_A` 主导 `0` 顶点却在 `1185` 个顶点上当配角 —— 改它就是拖坏别人的形状 |
| F（真根因） | 挂饰左右不对称 | 内置名字规则泄漏到同结构组的邻居：右腿花边与挂坠同锚点同链长被并成一组，`lace` 的 `follow_skirt` 带着挂坠跑。修在 `25c0457` |

三条留下来的规矩：

1. **改一根骨的求解器之前，先量它的「带权顶点 / 主导顶点 / 只当配角」三个数**。只看骨名会把
   `Bag`/`Bow` 当小饰品；只看主导顶点会漏掉纯配角骨 —— 配角骨改坏的是别人的形状，症状离被改
   的骨很远，最难归因；
2. **判据是「与画面已确认正确的旧包逐条比对」**，不是"我觉得哪个类别更像"；
3. **`verify_ab_package` 报「摇物骨左右分布不对称」时先当 bug 查**，那是这类错误的指纹。

#### G. 收口：dress-2219 定版（2026-08-19）

**这一批到此为止。** 作者确认画面可接受，样本 2a 的物理不再往下调。

```text
装机包      buildId 1375a006a8fc685f   bundle 5a5b563cb9e2b7fd…
快照        mod-workspace/experiments/final-hmsz-dress2219-2026-08-19/（含 SHA256SUMS.txt + 定版 blend）
blend       authoring - 副本 - 副本.blend（改动逐条见下；.bak/.bak2/.bak3 三份备份保留）
runtime     c5fb1d7；游戏里跑的是 7c8a3fef（探针 v1，latch 有 bug）
```

**最终的物理配置**（全部落在 blend 表单里，`physics-override.json` 只有作者原来那句 `"Skirt": "follow_skirt"`）：

| 部件 | 策略 | 依据 |
|---|---|---|
| `Skirt_L/R_*` 30 根 | `follow_skirt` → 蹭原版 `*Skirt*_S` | 与旧 AB 08-04 逐条相同（44/44） |
| `Bag_R` / `Chain_R` / `Key_R` / `Belt_L` | `rigid` → `Hips` | 同上；作者要它们硬跟骨 |
| `Leg_pendant_L/R` | `rigid` → `LeftUpLeg` / `RightLeg` | 同上 |
| `Spine2_Bow_*` | `rigid` → `Spine2` | 作者要胸前蝴蝶结不动 |
| `Lace_R`（靴口花边） | `integrate` + `ribbon` + **链根自己摆** | 见 §F 的量测：97 主导顶点全在链根 |
| `Streamer_L/R` + `SStreamer_L` | `integrate` + `ribbon` | 见下方原版统计 |
| `Spine_Bow_L/R_*` | 保持 `integrate` + `skirt` | **没动过、也没量过画面**，见"仍然开着的口子" |

**飘带定 `ribbon` 的依据（48292 根原版摇物骨扫出来的）**：

```text
                       原版 Ribbon/Streamer/Sash 类     原版 Skirt 类
样本                    5085 根                         15865 根
挂在链上的              0 / 5085  =  0.0%               15057 / 15865 = 94.9%
collisionMask 众数      256 / -1                        1 / 2
limitZ 众数             (-90,0) (-180,180) (-60,0)      (-20,0) (-40,0)
```

**原版 5085 根飘带类骨，挂链的是 0 根。** 这不是倾向，是结构上的二分 —— `ActorSwingChain`
的环形 `around/radius` 解算是给"一圈裙板互相不穿插"用的，背后两根飘带凑不成一圈。
作者 blend 里原本写的 `skirt` 是与原版相反的一档（挂链 + 撞胯胶囊 + 摆动夹到 20°）。

**收口时的两条记录**（作者 2026-08-21 判定画面合理，不再改）：`Spine_Bow_L/R` 保持 skirt 档；
飘带定 `ribbon`。参照系留着：原版飘带骨 `CenterLeftLRibbon1_S` 峰值 `28.21°`、原版裙摆末端 `90.03°`。
导出时有 `38` 个未决定组靠闸门 9 的显式放行过的，sidecar 里记着 `undecided {"count": 38, "allowed": true}`。

**这一批真正的产出是插件侧的四个修复**，样本只是载具：

| 提交 | 修的什么 |
|---|---|
| `40819e4` | 闸门 9：`undecided` 默认拦，放行留痕 |
| `25c0457` | 内置名字规则不再泄漏到同组邻居（装饰骨左右不对称） |
| `cf12f94` | **物理指令按链算不按结构组** —— 作者的 `follow_skirt` 一直被同组吞掉 |
| `c6fbcd2` | 「链根自己摆」逐行开关 + 空摇物链硬拦 |

第三条影响最大：结构分组在这个模型上一组装下 57 根骨（整条下半身），
"整组一个指令、第一个带覆盖的骨说了算"让整条裙子被误判成自建摇物，
自建骨 69 根 → 修完 18 根，左右分布 `31/34` → `9/9`。

#### H. 跨游戏源样本 chs-sucu-00 → hmsz-cstm-0059（2026-08-21，实机通过）

**性质**：第一次把「另一个游戏的整套服装」从解包一路做到画面可接受，也是第一次
**把 Mesh JSON 导进 Blender 再出包**（以前作者的网格都是自己在 Blender 里导入的 FBX/PMX）。
这条新路径一次性撞出 7 个缺陷，量化数字见事实文档 §4b。

装机 `buildId 70ec1d5e91486e73`（`ribbon 14 + skirt 14`、4 条链、`boneCount 184`）。
作者判定：摇物链正常、无目视问题（判定是在 `f1dbfcefe5cf49fe` 上做的；当前版只把部件类型
从 auto 钉成显式 skirt，物理参数逐项相同）。

**这一批的产出是插件侧的 8 项修复**（样本仍然只是载具）：

| 修的什么 | 落点 | 作者原来会不会中 |
|---|---|---|
| 作者的物理策略被「按名字撞上目标骨」压过 | `operators._resolve_source_bone_remap` | **会**：源与目标同名但几何差 221mm 时，作者点的「自建摇物链」被静默忽略 |
| 自建骨与目标骨架重名 | 闸门 12 `core.new_bone_name_collision_error` | **会**，且以前零提示 |
| 合成链尾硬写在骨的局部 -Z | `core.build_source_extra_bones` + `operators._dominant_group_tip_offsets` | **会**，且以前零提示（dress-2219 定版包里同样是坏的） |
| 归组的链长 ±1 跟上一条比 → 多米诺 | `core.structural_bone_groups` | **会**：12 条链并成 24 根一组 |
| 部件类型按结构组发 → 邻居把类别带跑 | `core.geometric_swing_categories` + 新抽出的 `core.resolve_chains` | **会**：与 `cf12f94` 修物理指令是同一类错误 |
| 「几何全在链根」只在导出后闪一句 WARNING | 表单常驻黄标 `core.anchor_only_roots` + `ui` | **会**（能看到但极易错过） |
| 「拆开这一组」丢掉链根自己摆/黄标 | `gmi.split_bone_group` | 会 |
| `verify_ab_package._side_of` 只看名字开头 | 尺子本身 | 加了 mod 前缀后「左右不对称」这条 bug 指纹会哑掉 |

**另外两条只在「JSON → Blender → 出包」这条新路径上才会中**（作者的 FBX/PMX 流程不受影响）：

- `core.read_weighted_reference` 导入时翻 `v`、导出端不翻回去 → 整身贴图错乱。那个函数原来
  只被两个**导入参考模型**的算子用，从来没被再出包，所以潜伏了两个月；
- body 导出器按材质槽写常量 COLOR，一个 `m_bdy` 槽里的皮肤和布料共用一行 ramp。新增描边模式
  `SOURCE`「沿用源模型顶点色」（缺 COLOR 硬拦）。外部 rip 本来就没有学马语义顶点色，
  原来三档对他们是对的。

**P2 对齐这次是必须做的**：IP 与学马同中间件、骨名一一对应，但体型差 9%（Head 差 124mm）。
不对齐的画面症状是头飘在脖子上方、手够不到手骨。做法（等比 + 逐骨摆到目标静止矩阵 +
骨架修改器把形变烘进网格）的定版脚本随样本保存在
`mod-workspace/mods/work/chs-sucu-00_body_ab-2026-08-21/`，
实测最大骨差 `179.3mm → 0.000mm`。**闸门 6（位置只报不拦）在这个量级明显不够**，见下方口子。

**这个样本顺带把批次 6 收口了（2026-08-22）**：它正好是验收清单 §2 要的"窄裙样本"。拿它的
`bundle-src` 只改 `collisionMask` 重打了一版对照（84 处改成 `-1`，6 张贴图 + geojson 的
SHA-256 逐字节相同、`boneCount/swingChains/extraSwingBones` 三项计数一致，逐项证明只差这一个变量）：

```text
A 众数  skirt=1 / ribbon=256   70ec1d5e91486e73   裙摆正常
B 全 -1 collisionMask=-1 ×84   1a66d9ab686e813c   **裙摆整个炸开**
```

`-1` = Everything 会去撞半径 0.23m 的胯胶囊，症状比预期的"发僵"更极端。**原版众数是对的，
不要再回退到 `-1` 兜底。** 对照包留在 `mods/…-maskall/`（`enabled:false`）。

⚠️ **切 mod 别用游戏内管理器 UI**：2026-08-22 实测，两个 mod 抢同一个槽时点被拒的那个会崩
（`CampusUiProbe.cpp` 的 `PressHook → HandleModToggle → ApplyPresentationModelToToggleBindings
→ SetCampusText → Call`，对已销毁的 il2cpp UI 对象 invoke，只有空指针检查没有活体检查）。
改 `mod.json` 的 `enabled` 再重启游戏，顺带也保证 `BuildModel` 重跑、物理按新值重建。

**这条路线交付时的已知限制**（陈述事实，不是排期）：

- 游戏内 mod 管理器 UI 在「两个 mod 抢同一个槽、点被拒的那个」时会崩
  （`CampusUiProbe.cpp` 的 `PressHook → HandleModToggle → ApplyPresentationModelToToggleBindings
  → SetCampusText → Call`，对已销毁的 il2cpp UI 对象 invoke，只有空指针检查）。**切 mod 请改
  `mod.json` 的 `enabled` 再重启游戏** —— 那样也保证 `BuildModel` 重跑、物理按新值重建；
- 闸门 6（静止位置差）只报不拦，作者判定这样就够；
- 导出器逐 corner 写顶点，源 `11870` → 出包 `45444`（`3.8×`）；
- `tools/process_ip_geo_body.py` 只认 2 个 submesh，第 3 段的 `86` 个顶点按错图集分类描边；
- IP 源的肤色没有按目标角色校准（IP 文档 §5 自己也标着跳过）；
- 顶点 COLOR 的 RampAdd 行 / rim 档跨游戏不同族（量到了，作者判定画面没问题，保持保留源值）。


---

## 2. 为什么是这条路线

三条路线各自欠什么，以及欠账有没有施工方法：

| | 要求 1<br>除 Blender 外成本最低 | 要求 2<br>源权重保留、不拉扯 | 要求 3<br>物理真实自然 |
|---|---|---|---|
| **target-rig（本文）** | ✅ 免 Unity | 🟡 **要对齐 + 缺骨劈权重**——**有方法**，即本文 P2/P3 | ✅ 2026-08-11 画面级跑通，参数取自 530 套原版真值 |
| 双骨架 bridge | ✅ 免 Unity | ✅✅ 零改动 | ❌ **从未实现**，且**无方法** |
| whole-object | ❌ **必须 Unity**，无方法 | ✅✅ 零改动 | ❌ 没在被解算 |

**双骨架的欠账是结构性的**：代理骨必须带 `__gmi_sp_<下标>_` 前缀（body/face/hair 共用一张
`BoneNameToTransformDictionary`，重名抛 `ArgumentException` 打断建模），于是游戏侧一切
**按名字找骨**的机制都够不到代理骨——`AttachQuartzDriver` 的 `resolveBone`、`RegisterBones`、
道具挂点、IK 目标、碰撞体点击判定、相机取景。所以「物理从未实现」不是排期问题，是要从零
自己写一整套求解器和挂点转发。

**whole-object 的欠账无解**：带组件的 prefab UnityPy 造不出来（搬 nodes 会碎、清 typetree 被
Unity 拒、留旧 typetree 写新字节原生崩），必须 Unity 出包，直接违反要求 1。

**target-rig 的欠账是可施工的**，本文 P2–P4 就是施工方案。

### 2.1 这条路线交出去的东西

**源身体比例。** 网格对齐到原版关节位置之后，人物变成学马体型。如果某个模型的卖点就是体型，
这条路线交付不了它——那种情况才轮到双骨架兼容模式。

**注意区分**：交出的是**人体比例**，不是**服装形状**。裙子更蓬、袖子更宽、飘带更长全部保留，
理由见 §7。

---

## 3. 三条基调（作者目标）

1. **除 Blender 以外的使用成本越低越好**——不装 Unity、不装 Python、不自己挑模板
2. **外部模型的权重尽可能保留**，不出现部件权重拉扯
3. **摇物链与新增骨的物理越真实自然越好**，不出现碰撞抽搐

本文每一步都对应到这三条中的至少一条；不对应任何一条的工作不做。

---

## 4. P0 — 冻结路线与数据契约

> ✅ 已冻结，落地面见 [`ab-target-rig-contract.md`](ab-target-rig-contract.md)（本节的可执行版本：
> 约束、五档判定、尺子阈值都指到代码里的同一个函数）。

### 4.1 `target-rig` 契约

- 学马 70 根人体骨的**名称、层级、静止变换、根骨**不可修改；
- **mod mesh 的 bindpose 必须等于对应学马骨静止世界矩阵的逆**（renderer 空间下）；
- Renderer 的 `bones[]` 顺序与 mesh 的权重索引、bindpose 数量必须一致；
- 允许新增的服装辅助骨必须带 mod 前缀（防撞名，见 §2）并显式声明在 sidecar 中。

> ⚠️ **bindpose 是网格的属性，不是骨架的属性。** 运行时用的就是 mesh 自带的 bindpose 配原版
> 活体骨，两者不自洽 = 静止偏移。所以契约要钉的是"mesh 的 bindpose 等于什么"，不是
> "骨架的 bindpose 不许改"。

> ⚠️ **骨名一律用 transform 名。** `LeftUpperArm` 是 Unity Humanoid 的 API 名，游戏里的
> transform 名是 `LeftArm`，运行时按 transform 名解析。契约文档与预设表统一用后者。

### 4.2 每根来源骨的五档处理

每根来源骨最终**只能**处于以下之一，**不允许"未决定"进入导出**：

| 档 | 含义 |
|---|---|
| `direct` | 直接映射到一根学马骨 |
| `merge` | 合并到一根学马骨（多对一） |
| `helper` | 保留为新增辅助骨，挂在学马骨架下 |
| `bake` | 把它造成的静止形变烘焙进网格（或 Shape Key），再合并到父级学马骨 |
| `reject` | 无法安全处理，**禁止导出** |

**绝对不能让插件静默把未知来源骨猜成某根学马骨。** 当前缺陷：映射表没有来源标注，
72 根静默塌 `Hips` 的骨和真映射长得一模一样，排错只能去 dump JSON。五档状态本身就是这个
标注——它是**决定**不是**猜测**，且必须显示在表单里。

### 4.3 五档必须按组赋值

五档的语义是"每根骨一个状态"，但**赋值的粒度必须是组**——裙子 40 根骨一根一根选 `helper`，
就是当前痛点原样重演（chisaki 的 MMD 裙子作者手动点过几十次）。

所以 P0 与结构分组绑死，同批施工：

```text
gakumas_mi/ui.py   GMI_UL_bone_map  「一行 = 一根带权重的源骨」  ← 痛点的根
gakumas_mi/core.py group_key()（在 build_accessory_physics_remap 内）正则剥 left/right ← 日语/中文/乱码全废
gakumas_mi/core.py swing_category_by_geometry()  ← 已写好，只有测试在调
```

分组换成**结构信号，一个骨名不读**：

| 信号 | 怎么算 | 作用 |
|---|---|---|
| **锚点** | 沿父链向上第一根人体骨 | 天然分开「挂 Pelvis 的裙」和「挂 ForeArm 的袖」 |
| **链** | 连通分支，分叉即断（与"不建分叉链"的规矩对齐） | 一条链一行 |
| **归组** | 同锚点 + 层数相同 ±1 + 影响顶点在网格上连片 | 12 片裙摆合成一行 |

UI 改成一行一组，展开可逐根覆盖。报警语义同时改：**装饰骨没有目标是正常状态**
（fuyuko 底部那句「还有 57 个骨没指定目标」就是这么来的），改成「这一组还没决定」。

**验收**：chisaki 那条 MMD 裙子从 N 行降到 ≤5 行；日语/乱码骨名样本的分组结果与英文样本一致。

---

## 5. P1 — 建立学马标准目标骨架（**只读参考资产**）

从原版 prefab 提取一套供 Blender 加载的标准参考，作者不需要自己处理 Unity 骨架。

> ⚠️ **不出 prefab。** 老 AB 路线从不交付 prefab——runtime 是在原版 prefab 上原地打补丁。
> 「标准 prefab 进游戏与原版一致」这条验收**不成立**：真做出来那就是 whole-object，违反要求 1。
> **验收改成离线：参考骨架与原版资产逐骨 diff 为零。**

参考资产该装什么、不该装什么：

| 该进参考 | 不该进 |
|---|---|
| 骨架静止姿势（位置 **+ 朝向**）✅ | 原生 Animator / IK / 驱动器 / 碰撞体 |
| ~~socket 节点位置~~ —— body 骨列表里没有，而且**运行时会从被替换资产补齐**（实机日志 count=9 / 0deg），不需要进参考 | 原版动态链的 `active`/`around`/`collisionMask` |
| 各骨的权重分布（P3 劈权重的来源） | |
| 动态链锚点区间（判自建链根落哪） | |
| 目标资源的缩放与坐标系 | |

右列在这条路线下**原封不动留在游戏里**，搬进 Blender 是无用功。

**链参数别重建**：`gakumas_mi/swing_presets.json` 已经是 530 套原版扫描的结果
（4 档 × 3 个链上角色，bundle 内嵌 typetree 按名字读，不是按偏移猜）。

---

## 6. P2 — Blender 中手动对齐网格

作者只在 Blender 做这部分：

- 把外部网格放到学马静止姿势；
- 对齐 `Hips`、`Spine`、肩、肘、腕、膝、踝、头等承重关节的**位置**；
- **同时对齐骨的静止朝向（roll）**；
- 保留外部模型自己的体型和服装形状。

### 6.1 朝向是唯一看不见的杀手

对齐位置容易自查，**朝向不行**：骨绕自身轴的滚转差在静止截图里完全正常，**转身之后手臂整个
炸开、手指变面条**——实机三次坐实（肩差 172°）。而且它不在「头/手/脚/根骨」这几个容易抽查的
位置上，它在**肩和手指**。

所以：

- P2 的表述必须写「关节位置 **+ 骨静止朝向**」；
- P4 的闸门必须**对全部 `direct` 映射骨查朝向**，不是抽查几个；
- 作者需要一把**逐骨仪表**（见 §15 批次 1），因为这是他唯一自查不到的东西。

### 6.2 服装形状不需要缩成原版

学马骨架只负责运动，不会因为原版裙骨比较垂就把静态网格压扁——**蓬裙的顶点根本不绑在原版
裙骨上**（走 `helper`，见 §7）。裙更蓬、袖更宽、飘带更长全部保留。

---

## 7. P3 — 权重映射

### 7.1 能对应的骨：显式映射，不重新生成

```text
目标骨权重 = 所有映射到该目标骨的来源骨权重之和    （最后归一化）

Source_Hip      → Hips
Source_Spine01  → Spine
Source_LeftArm  → LeftArm
```

原权重比例保留。这直接满足要求 2。

### 7.2 对不上的来源骨

| 情形 | 处理 |
|---|---|
| **静态装饰骨** | `bake`：先把静止形变烘进网格，再合并到父级学马骨 |
| **独立变形骨**（裙、袖、飘带、发、尾） | `helper`：保留为辅助骨，挂在学马骨架下 |
| **需要物理的骨** | 映射到已有学马动态链 / 建新辅助物理链 / 放弃动态改 `bake` |

辅助骨层级示例——**官方 70 根骨仍然一根不变**，裙子继续使用自己的权重和自由度：

```text
Hips
└── Gmi_Skirt_L0
    └── Gmi_Skirt_L1
        └── Gmi_Skirt_L2
```

> 如果坚持"只能用 70 根学马骨、绝不允许辅助骨"，来源独有的裙摆、飘带和装饰动态**不可能
> 完整保留**。这是个明确的产品取舍，不是实现细节。

**不要把蓬裙映射到原版裙骨**：会同时坏两次——顶点离自己的骨 10–20cm，旋转中心错（这就是
"拉扯"）；原版 `Skirt` 驱动器按窄裙轨迹推它，蓬度当场压平。**想用原版裙摆驱动器就得接受
原版裙形；想保住蓬就自建摇物**，没有中间态。

### 7.3 学马有、源没有的骨：三分法

判据是**这根骨在原版身上扛多少权重**。

**档 1 — 必需骨（21 根，`core.CRITICAL_TARGET_BONES`）**
没拿到权重不是"少个细节"，是那块几何**跟着别的骨乱跑**（实测：整只手 100% 钉在 `Spine1`）。

| 常缺 | 常见于 | 从哪劈 | 原版基线 |
|---|---|---|---|
| `Shoulder` | MMD / Biped（Spine2 直接接 UpperArm） | `Arm` 根部那一圈 | 跨肩带 **13.3%** |
| `Neck` | Head 直接挂 Spine2 | `Head` 底部那圈 | — |
| `ToeBase` | 只有一根脚骨的源 | `Foot` 前端 | — |

劈法：**只对这几根**做分批 Data Transfer，从原版身体对应骨的权重分布投影过来——**不是全身
重绘**。分批的意义是让投影只能在同一骨组内找最近点，食指不会串到中指、大腿内侧不会串到对面腿。

**档 2 — 可选骨：明确留空，别硬凑**
`Pelvis`、`Spine2`、全部 14–16 根 `*_H`。

- 原版把关节那圈权重挪到 `_H` 上是**一种画法**，源模型连续画在人体骨上是**另一种画法**，
  两种各自自洽。不需要为凑够 70 把源的画法改成原版的；
- 量化：`_H` **弯曲工况收益 0.0%**，只有扭转工况有差（装 −0.5% / 不装 −8.7%）；
- 这条路线下 `_H` 骨**就是原版的活体骨**，同名就在那儿，游戏驱动器照常驱动它，只是没有你的
  顶点绑在上面。留空不崩、不报错；
- `Spine2` 闸门故意不查——两节脊椎的源（Auto-Rig Pro 之类）一拦就是全体误伤。

**档 3 — 节数不同：塌进最近的语义骨，但必须标出来**
手指 3 节 vs 4 节、脊椎 2 节 vs 3 节。塌是安全的（末节权重质量极小），但**塌错是"有值但错"，
闸门永远抓不到**——只有 §4.2 的五档状态 + 来源标注能看见。

### 7.4 一个必须让作者知道的对立

「尽量保留源权重」和「肩膀不崩」在**人体贴身区是对立的**——源自己跨肩带只有 4.9%
（原版 13.3%），保留它就是保留崩坏。

分区不是折中，是各取所长：**辅助骨区保源权重（细节全在），人体区缺骨处取原版（过渡带质量）。**
这句话要写进 UI，否则作者会以为哪个都能全要。

---

## 8. P4 — 导出前的硬闸门与权重报告

### 8.1 硬闸门

导出前必须全过：

1. **21 个承重关节都有权重**（已实现：`critical_coverage_error`）
2. 没有未映射的 deform bone
3. 没有未归一化或全零权重
4. Renderer `bones[]` 数量、顺序与 bindpose 一致
5. 目标骨 bindpose 没被来源骨覆盖
6. 头、手、脚和根骨没有明显静止姿势偏移
7. **全部 `direct` 映射骨的静止朝向差在阈值内**（新增，见 §6.1；定义 = 本骨 → 人形子骨的方向）
8. ~~**`bindpose · 骨静止世界 ≈ I`**~~ —— **作废**：2026-08-17 标定，这条在**原版自己的身体**上
   就报错（Blender 侧不保留绕骨轴的 roll，104 根里 69 根差 180°）。它属于自带骨架的 SDK 路线；
   target-rig 下第 7 条就是它的等价物
9. 来源辅助骨均有明确的 `helper` / `bake` / `reject` 状态
10. 网格没有引用不存在的骨
11. **没有空摇物链**（垂到胯下、没人驱动的衣物链；2026-08-19 新增，原版此类链 0.00%）

> ⚠️ 原来这里写「只量节点静止姿势的角度不够，要查 `bindpose · 骨静止世界 ≈ I`」——那是
> 自带骨架路线的教训，套到 target-rig 上会把原版自己判红（见第 8 条）。target-rig 下
> 真正会漏的是**只量位置**：肩差 172° 的包位置差是 0。

> ⚠️ **闸门文案要分两条出路。** 现在那句「源模型的骨名没有被识别…请在骨骼映射表里指定」
> 假设的是"骨存在但没认出来"。而"骨压根不存在"时作者按提示去表单里找，找不到，卡死。
> 两种情形必须给不同的出路：去表单指定 / 用「从相邻骨劈权重」算子。

### 8.2 权重报告

让"尽可能保留权重"可量化，而不是凭画面猜：

- 直接保留了多少权重（`direct`）
- 合并了多少权重（`merge`）
- 烘焙了多少权重（`bake`）
- 哪些顶点发生了较大影响变化
- **跨关节带与原版逐关节对比**（`audit_ab_rig.cross_joint_bands` 已实现）

最后一项是唯一能**预判**「肩膀会不会崩」的数字。原版真值：**肩 13.3% / 肘 3.9% /
腕 6.2% / 膝 9.5%**。作者那句"A→T 之后肩膀变小崩坏"，量出来就是源自己跨肩带只有 4.9%。

### 8.3 `bake` 是破坏性步骤

按不变量 7，`bake` 必须**可见、可关、可量化、可撤销**；形状保真那把尺子要认这个变形是预期的
（否则闸门会全红），判据从"接近浮点误差"改成"变形量与 `bake` 声明的一致"。

---

## 9. P5 — AB 打包

作者侧不应再要求：装 Unity、装 UnityPy、自己找 Python、自己下载并挑选模板。

```text
Blender 插件
+ 项目自带打包器
+ 项目管理的目标模板缓存
```

Unity 与 UnityPy 保留在**项目维护者一侧**，用于生成或更新模板，不再是作者的安装成本。

**打包器形态先试更省的那个**：Blender 自带 Python，如果 UnityPy 的 native 扩展能对 Blender
内置解释器打出 wheel，**随插件 zip 一起装**即可——零额外进程、零 PATH、零下载。打不出来再退回
独立 `gmi-pack.exe`。花半天试，不行马上退，别为此纠结。

**模板需求没有想象中大**：这条路线是在**被替换的那个资源自己**的 bundle 上打补丁，作者选了
`atbm-cstm-0140` 就只需要那一个。第一阶段继续复用现有 R32 模板；第二阶段按目标资源按需下载
或由项目统一缓存。

**完全摆脱模板、自己实现 Unity AssetBundle 序列化，单独作为高风险长期项目，不阻塞本路线。**

---

## 10. P6 — Runtime 改造原则

Runtime 尽量不增加"智能猜测"：

- 保留原版目标 prefab；
- 只替换 Mesh、材质和必要的 `bones[]` / bindpose；
- 学马 Animator、IK、驱动器、碰撞体、socket 继续使用原版；
- sidecar 只描述**已经在 Blender 中确定**的辅助骨和物理数据；
- 不做来源骨架 bridge；
- 不复制未知组件；
- 不在运行时自动修权重。

这正是 1.0.0 runtime 当前的薄职责，本步只是把导出的资产契约做严格。

**一处现存违反要落到这一步**：

```text
ModRuntime.cpp  AddComponent 早于引用循环检查
ModRuntime.cpp  空引用只 warn 后继续  → 半初始化组件泄漏
```

改成 **AddComponent 之前预检、缺任一必需引用整体拒绝**。
验收：构造缺引用的坏 sidecar 必须整体拒绝并写明原因；正常包不误报。

---

## 11. P7 — 物理

分两层：

**学马原生骨**：直接使用目标 prefab 的原生组件和参数，我们不碰。

**外部新增服装骨**：使用明确的辅助链配置——chain root、parent、`active`/`around`、
mass、stiffness、damping、collider、collision mask、limit、solver owner。

### 11.1 硬规矩（违反 = 硬崩或抽搐）

1. **每根骨只能被一个 solver 驱动**，不能同时挂原版 driver 和自建 driver
   （原版 60 套 327 个裙摆驱动器**零重叠**）
2. **静态碰撞体从不挂 `_H` 骨**（原版挂 Hips/Spine/Neck/Arm/ForeArm/Hand/UpLeg/Leg/Foot）
3. **`ActorSwingChain` 是环容器，允许与驱动器共骨**——这是规矩 1 的唯一例外，一刀切禁掉会把
   裙摆的环形碰撞解算一起禁了
4. 一条骨脉至多一个 QuartzDriver
5. **层 0 是锚定层**：一条链至少两根骨，单根骨的飘带/裙摆在游戏里不会动
6. `collisionMask` 分档别落错：skirt 档原版取 `1`；落进 cloth 档变 `−1` 去撞半径 0.23m 的
   胯胶囊 → 发僵、穿插

> ⚠️ **值已装、实机未验（2026-08-20 复核）**：`gakumas_mi/swing_presets.json` 2026-08-18 02:50 起
> 装的是**逐档众数，不再是统一 `−1`**；`-1` 在原版任何一档都只占 14~24%，规矩 6 坐实。
>
> **四个数字只写在 `gakumas_mi/swing_presets.json` 的 `_collisionMask` 注里，本文不复写。**
> 这个事实此前存了四份（§0 / 本节 / 批次 6 / 预设），漂掉的就是本条。预设自己写着这是
> 「实机实验档」的标注已作废：2026-08-22 的 A/B 画面判定确认众数是对的。

### 11.2 诊断顺序：先证明在被解算，再谈参数

whole-object 那边三轮参数工作**全部作废**，根因是跳过了这一步——三组实质不同的输入产生
像素级相同的输出，而那个模式本身就是"输入没被读"的证据。

正确起点：读无条件日志的 `swingDynamicBones=N`（当时还配了一把 300 帧局部旋转峰值探针，2026-08-22 已删）。
**只有确认有骨真的在动之后，参数、碰撞笼、限位才有讨论意义。**

### 11.3 验收场景的定义

判"摇物做得对不对"看这些工况：原地待机 / 走路 / 跑步 / 跳舞 / 快速转身 / 裙子与腿部碰撞 / 飘带与身体碰撞 /
连续 300 帧运动。判据：无重复求解、爆振、抽搐、穿透。

### 11.4 参数来源

- **源自带物理元数据**（PMX 刚体、VRM PhysBone、Unity DynamicBone）→ 逐实例读取转换。
  **别用中位数猜**——中位数与源作者调好的值差最多 7 倍
- **源只有 FBX + PNG** → 只能合成，天花板就低，别拿这种源评判路线好坏
- 参数**不能跨服装抄**：同角色不同衣服的 stiffness/pendulum 能差 100 倍

> 优先级说明：源元数据逐实例读取排在最后。1.1.0 自己实测过——五个参数从原版分布一端拉到
> 另一端，摆幅只动 ±35% 且方向与预期相反，收益上限低。

---

## 12. P8 — 首批验证模型

不要一开始支持所有外部模型。三类样本全过之后再扩大到复杂服装：

| # | 样本 | 主要验什么 | 风险 |
|---|---|---|---|
| 1 | 只有人体骨、没有额外物理骨 | P2 对齐 + P3 映射 + P4 闸门 | 中 |
| 2a | 蓬松裙子，**源自带裙骨** | `helper` 链 + 自建物理 | **高** |
| 2b | 蓬松裙子，**源裙子没有骨** | 必须在 Blender 里建骨 | **高**（唯一省不掉的美术工作） |
| 3 | 带麦克风、手持物、头饰、特殊 socket | 我们没动到手骨 | **低** |

> 第 3 类在这条路线下 socket 是原版的、我们不碰，**天然应该过**——它验的其实是"我们没动到
> 手骨"。真正的风险全在第 2 类，所以把它拆成 2a / 2b 两个样本。

---

## 13. 明确不做

| 不做 | 一句理由 |
|---|---|
| whole-object 并入发布线 | 违反要求 1——带组件的 prefab UnityPy 造不出，必须 Unity |
| 双骨架 bridge 作为默认路线 | 前缀是结构性的，物理与挂点等于从零造子系统。保留为特殊兼容模式 |
| 12 类驱动器全接通 | 运行时只实现 3 类（Skirt / Frill / HumanoidSleeve）；✅ 置灰与导出闸门已做对（批次 6） |
| 自动 A→T 烘焙 | 独立实验，不进主线 |
| 全自动对齐 | 两次都产废品；尺子 + 手工是已定的分工 |
| 全身权重重绘 | 要求 2 选了保留源权重，重绘只用在 §7.3 档 1 那几根缺骨 |
| 自己实现 AB 序列化 | 高风险长期项目，不阻塞本路线 |
| 硬堆启发式去猜一切源模型的怪异绑骨 | 见 §13.1 |

### 13.1 泛用化的边界（并自已删除的 `universal-mod-automation-plan.md`）

那份文档 2026-08-20 删除（早于两份主文档、状态段已过期），只有这几条结论仍然管事：

1. **两层要分开谈，混着谈会得出错误的优先级。** 一次性基建（崩溃修复、运行时组件三修、
   swing 参数自动合并）埋在插件/运行时里，作者一键白嫖，是"从跑不起来到能跑"；
   每 mod 启发式（骨分类、蹭 vs 整搬）才是让一键变脆的地方；
2. **没有启发式能 100% 猜对源模型的怪异绑骨。** 正解是**自动兜 90% + 傻瓜 override 兜 10%**：
   作者不懂骨，只在画面明显不对时说一句"这块跟着那块动"。硬堆启发式去猜一切 = 把事情做复杂；
3. **默认偏「整搬 / 信任源」而不是「位置蹭」。** 位置蹭是脆弱来源（花边挂腿正是位置匹配被源
   绑骨误导），已降级为 **override-only**：默认忠实保留源层级 + 源物理；
4. 每修一个边角都是对启发式的**永久加固**，同类源以后白嫖 —— 但压力测试样本（镜像源 +
   左右不对称 + 花边绑腿 + bow 拆链）不是常态，别按它定默认值。

---

## 14. 与已发布 1.1.0 / 1.0.0 的对接

**不废弃**。GakumasMI 1.1.0 与 gakumas-mod-runtime 1.0.0 继续作为 AB 与 Runtime 的基础，
导出器、权重映射和物理验证按本文契约重做。

| 已有资产 | 怎么用 |
|---|---|
| `gakumas_mi/swing_presets.json` | **直接复用**，别重建（530 套原版扫描） |
| `core.CRITICAL_TARGET_BONES` | P4 闸门 1 已实现，只需补出路文案 |
| `core.swing_category_by_geometry()` | ✅ 已进生产（`core.geometric_swing_categories`）；2026-08-21 起**按链发**，不再一组一档 |
| `core.build_accessory_physics_remap` 里的 `group_key()` | ✅ 已退成兜底（生产路径走 `structural_bone_groups`） |
| `ui.GMI_UL_bone_map` | ✅ 已改成一行一组（+ 五档状态列 + 「拆开这一组」+ 2026-08-21 起「几何全在链根」常驻黄标） |
| 旧 `tools/report_joint_alignment.py` | ✅ 已搬进面板（`core.rest_alignment`，并补上朝向差）；零引用旧脚本已删除 |
| `audit_ab_rig.cross_joint_bands` | ✅ 已搬进面板（`core.cross_joint_bands`；那边按骨下标算，两处同源要一起改） |
| `operators._form_driver_categories`（旧名） | ✅ 已作用域化 → `_form_driver_bones`（`{骨名: 类别}`，一行=一组=一条链） |
| whole-object / 双骨架桥代码 | **标为对照组，勿再投入，不删** |

---

## 15. 落实顺序

P 编号是分层，不是时序。实际施工按批次：

### 批次 1 — 仪表与词汇（P0 + P2 的仪表）✅ 2026-08-17

先有尺子和词汇，后面每一步才有验收基础。

1. **对齐尺子进面板**：逐骨报「关节位置差 / 静止朝向差」，红黄绿
   （验收：已知好包报绿；肩差 172° 的已知坏样本报红）
   → `core.rest_alignment` + 算子 `gmi.report_rig_alignment` + 导出面板「对齐体检」。
   **朝向定义纠正过一次**：第一版量骨自身坐标系的整体转角，拿原版自己的身体一标定
   就是 104 根里 69 根报 180°（Blender 侧没保留 roll）——已改成事实文档 §6.2 那个
   已验证的定义「本骨 → 人形子骨的方向」，原版自己 104 根全绿 0.00°。
   验收：原版身体全绿；小臂方向差 172° 报红且位置差仍是 0（`tests/blender_smoke.py`）
2. **跨关节带进面板**：导出后报「肩 4.9% vs 原版 13.3%」
   （验收：Claymore 那副 rip 必须报肩 4.9%，已量过的真值）
   → `core.cross_joint_bands` / `cross_joint_band_findings`，与尺子同一个按钮。
   基线：有带权重参考体就现算（复核与真值表逐项相同），没有才用表。
   **Claymore 复量：肩 3.6% / 肘 1.6% / 腕 6.1% / 膝 5.1%**（原始 FBX + 预设映射）——
   与记录值同量级、结论相同（跨肩带只有原版四分之一 → 红），数字对不上是因为输入不同，
   见契约文档 §3.2。顺带查明**带宽随"没映射的源骨怎么解析"变化**（肩 0.0% vs 3.6%），
   面板已改成与导出同一份解析
3. **结构分组进生产** + UI 一行一组 + 报警语义改 + 五档状态列
   （验收：chisaki 的 MMD 裙子从 N 行降到 ≤5 行；日语/乱码样本与英文样本分组一致）
   → `core.structural_bone_groups`（锚点+链+链长，一个骨名不读）接进表单与
   `build_accessory_physics_remap`；`core.row_state` 五档列；报警改「这一组还没决定」；
   新增「拆开这一组」。**chisaki 实测：347 根带权重骨 → 表单 75 行**（老版本 347 行），
   其中 280 根装饰骨 → **6 组**，那条裙子的 260 根骨并成 **1 行**；日语/乱码/英文三个
   合成样本分组结果逐项相同
4. **冻结 `target-rig` 契约文档**（§4）→ [`ab-target-rig-contract.md`](ab-target-rig-contract.md)

> 批次 1 顺带查出、**要在批次 3 改的**：路线文档 §8.1 第 8 条闸门（`bindpose · 骨静止世界 ≈ I`）
> 按字面实现会在**原版自己的身体**上报错（roll 差 180°，见上）。那条判据属于自带骨架的
> SDK 路线；target-rig 下的等价物是本文的「朝向 = 本骨→人形子骨方向」+ 位置差。

顺带修掉的：`group_key()` 正则退成兜底；`build_accessory_physics_remap` 的
「逐骨蹭 / 按质心蹭」从 skirt/dress/cloth 词表改成**链数**（外语命名的一圈裙摆从前全落进
按质心 = 40 根骨绑同一根摇物骨）；`tests/blender_ui_smoke.py` 里 `native_driver` 之后
就没更新过的枚举断言。

### 批次 2 — 参考资产（P1）✅ 2026-08-17

提取只读参考骨架；验收是与原版资产**逐骨 diff 为零**（离线，不进游戏）。

作者用的参考资产就是步骤①那个「导入参考模型与骨架」，不新造 —— 补的是它缺的两样：

1. **朝向照搬原版**（`operators._create_armature` 改成写 `EditBone.matrix`）。旧版只按
   head→tail 摆骨、roll 留默认值，实测 104 根里 69 根（镜像那一侧）与原版差整整 180°：
   作者拿这副骨架对齐，看到的轴向是错的。
2. **无权重节点也建骨**（`operators.reference_rest_world`）：`Reference`、`Pelvis`、动态链
   锚点 `*_A`/`*_O`、摇物链根 `*_S` —— 18 根，旧版整批丢掉。它们没有 bindPose，位置只能从
   最近的带权重祖先按**完整 local 矩阵**合成（只累加 `localPosition` 会让带旋转的关节
   以下全错，151 个节点里 57 个带非单位 `localRotation`）。

验收（`tests/blender_reference_rig_smoke.py`，已进 CI）：逐骨查位置 / 朝向 / 父子关系 / 节点覆盖。

```text
仓内 profile（mesh-only 时代合成的骨架）  骨 132（无权重 0）   位置 0.000119mm  朝向 0.000000°
资源库骨架（真数据，今天新建 profile 的形态）骨 150（无权重 18）  位置 0.000080mm  朝向 0.000000°
```

**没做到的一样：socket 节点。** §5 列了「socket 节点位置」，但 body renderer 的骨列表里
根本没有手持道具挂点 —— 那 18 个无权重节点全是链锚点。socket 在角色/手部 prefab 上，
要单独一条读原始 bundle 的管线。这条路线下 socket 是原版的、我们不碰（§12 第 3 类样本），
所以不阻塞；真要进参考资产再单独开。

### 批次 3 — 权重映射与闸门（P3 + P4）✅ 2026-08-17

缺骨三分法、「从相邻骨劈权重」算子、10 条硬闸门、权重报告。

> **那条"新管道"不用建**：步骤①的「导入参考模型与骨架」已经把原版 body 导成带权重的
> Blender 网格了（批次 2 又把它的朝向和锚点补齐），它就是权重转移源。

**「从相邻骨劈权重」（`gmi.split_weight_from_neighbours` + `core.redistribute_family_weight`）**
—— 档 1 缺骨（MMD/Biped 没有锁骨、Head 直接挂 Spine2）的施工方案。规矩三条：

1. **只在作者和原版都认的骨之间重分**。作者有权重、原版在那一点上没有的骨不进族，原样不动
   （§7.3 档 2：两种画法各自自洽）；
2. **总量守恒**，不重绘全身，也不改顶点的总权重；
3. 原版只决定"分给缺骨多少"，**剩下的按作者自己的比例分回捐赠骨**（要求 2 保留源权重）。

验收（`tests/blender_weight_split_smoke.py`，已进 CI）：把**原版自己身体**的 `LeftShoulder`
整组权重删掉再归一化（就是"没有锁骨的源模型"），劈回来和真值逐顶点比 ——
**864 个顶点，最差差 5.96e-08、平均 3.96e-09，权重和最差偏 8.20e-08**；删掉时闸门必须报、
劈完必须不报。

**闸门现状 —— 这张表是闸门的唯一权威清单**（契约 §6 只留指针）。加了「实现位置」一列：
表和代码漂了的时候，`grep` 那个函数名就能发现，这是 2026-08-20 复查出「表写 🟡、代码已经是拦」
之后加的防复发措施。

| # | 内容 | 状态 | 实现位置 |
|---|---|---|---|
| 1 | 21 个承重关节都有权重 | ✅ 拦；报错文案给**两条出路**（去表单指定 / 从相邻骨劈） | `core.critical_coverage_error`（`core.critical_coverage_error`），调用 `operators._prepare_bundle_export_data` |
| 2 · 10 | 没有未映射的 deform bone / 网格没有引用不存在的骨 | ✅ 拦；文案中文 + 三条出路。两条是**同一处实现** | `operators._inverse_skin_export_data`（`unresolved and not fallback_bone`） |
| 3 | 没有未归一化或全零权重 | ✅ 拦：写包时逐顶点归一化，全零报错。另有截断量告警（第 5 个影响骨起被丢） | `core._bundle_skin`（`core._bundle_skin`） |
| 4 | `bones[]` 数量/顺序与 bindpose 一致 | ✅ 拦（骨数 vs `m_BindPose`、查骨下标越界、`m_Skin` 数量 vs 顶点数）。`verify_ab_package` 里**没有** bindpose 检查，别当第二道 | `core._bundle_geojson` + `_bundle_skin` |
| 5 | 目标骨 bindpose 没被来源骨覆盖 | ❌ **不做**：lossless 下 mod 就是要带自己的 bindpose，target-rig 下没有能成立的判据。硬凑一个会变成"在原版上也报"（风险登记 V5） | — |
| 6 | 头/手/脚/根骨没有明显静止姿势偏移 | 🟡 **只报不拦 —— 2026-08-22 作者定案：就这样，不加硬阈值**。作者能在面板上看到这个误差就够了，剩下的是他的判断。（反例仍然记着：IP 源体型比学马小 9%、Head 差 `124mm`，那个量级重定向吸收不了，画面上头飘在脖子上方，见 §H；但那次是**自动化脚本没看面板**，不是作者会犯的错） | `core.rest_alignment`（位置最高只判黄） |
| 7 | 全部 `direct` 映射骨的静止朝向差在阈值内 | ✅ 拦（≥15° 拒绝导出）。两个方向都验过 | `operators._rest_orientation_error`（`operators._rest_orientation_error`），调用 `:1634` |
| 8 | `bindpose · 骨静止世界 ≈ I` | ❌ **作废**，见上（原版自己会报） | — |
| 9 | 来源辅助骨均有明确的 helper/bake/reject | ✅ **拦**（`40819e4` 起）：`undecided` 默认拦下导出，显式放行必须留痕，`undecided {count, allowed}` 写进 sidecar 和权重报告。~~只报不拦~~ 是 2026-08-17 的状态 | `core.undecided_export_error` / `undecided_export_record`（`core.undecided_export_error` / `core.undecided_export_record`），调用 `operators._prepare_bundle_export_data`；`tests/test_undecided_gate.py` |
| 9b | `reject` 的骨不许进导出；标了 `bake` 却没烘也不许 | ✅ 拦 | `operators._prepare_bundle_export_data`（`reject` 与未烘的 `bake` 两段），`tests/blender_bake_rest_offset_smoke.py` |
| 11 | 空摇物链（垂到胯下、没人驱动的衣物链）不许出包 | ✅ **拦**（`2109371` 新增，§8.1 第 11 条） | `core.empty_swing_chain_error`（`core.empty_swing_chain_error`），调用 `operators._prepare_bundle_export_data` |
| 12 | 自建骨不许和目标骨架里的骨重名（契约 §4.1 防撞名） | ✅ **拦**（2026-08-21 新增）。重名时 renderer 的 `bones[]` 会取到目标骨的变换，装饰件绕错枢轴摆 | `core.new_bone_name_collision_error`，调用 `operators._prepare_bundle_export_data`；`tests/test_bundle_source_contract.py` |

**拦下导出的判据共 7 组**（1、2·10、3、4、7、9+9b、11），其中 2 与 10 是同一处实现。

**权重报告（§8.2）**：`core.weight_state_summary` 按五档给权重占比（直接保留 / 合并 / 辅助骨 /
未决定），画在「对齐体检」框里；跨关节带对比在批次 1 已经进去了。

> ⚠️ **闸门 7 会拦下一些以前能导出的包** —— A-pose 没烘、朝向差 ≥15° 的源就是拦的对象
> （Claymore 那副 rip 的肩差 172.5°）。这不是回归，是这条路线的契约；报错里点名是哪几根骨、
> 差多少度，作者按「量对齐 / 跨关节带」逐骨看。

### 批次 4 — 打包（P5）✅ 2026-08-17

先试 wheel，不行退 exe。**wheel 成了，不用退。**

关键事实：**Blender 自带的就是标准 CPython**（4.2 与 4.5.3 都是 3.11.7），所以 PyPI 上现成的
cp311 win_amd64 wheel 直接能用 —— 根本不需要"给 Blender 内置解释器打 wheel"这件难事。

```text
tools/package_blender_addon.py --with-unitypy "<Blender>/4.2/python/bin/python.exe"
  → pip install --target gakumas_mi/vendor --only-binary :all: UnityPy==1.10.18 Pillow
  → 插件 zip 10.8 MiB（507 个文件），装上就能一键打包
```

- 插件优先用自带的（`operators.vendored_unitypy()` → 同进程 import，不起子进程），
  没有才回退到「外部 Python」那条老路，**老路一行没删**；
- **版本钉死 `UnityPy==1.10.18`**：`patch_unity_bundle.py` 按 1.10.x 的 API 写，pip 装最新的
  1.25 会在 `TextAsset.text` 上直接炸（这次就撞到了）。让作者自己 pip install 就是版本轮盘赌，
  这本身也是内置的理由之一；
- 一份 zip 覆盖 4.2 与 4.5.3（同一个 ABI），Windows 之外没验。

验收（`tests/blender_vendored_pack_smoke.py`）：把 zip 装进干净的 Blender，用插件自带的打包器
补一份真模板（27MB 的 `template_mdl_chr_atbm-cstm-0140_body.bundle`），产物与**已发布、实机
验证过的** `chisaki-swimsuit.bundle` **11 个对象逐项一致**（网格几何/bindpose/蒙皮、sidecar 文本、
贴图尺寸格式、renderer 骨数）。容器字节不同 —— 两边 lz4 版本不同，压出来 40.9 vs 42.8 MiB，
所以判据是比对象，不是比 hash。测试里还把「外部 Python」栏填成垃圾值，证明它真的没被用到。

**顺带查出两个会让发布版直接坏掉的 bug**（都不是这批引入的）：

1. `gakumas_mi/unity_route.py`、`topology_map.py`、`driver_presets.json` **没入库**，而打包只收
   git 跟踪的文件 → 打出来的 zip 缺模块，**插件整个装不上**
   （`ImportError: cannot import name 'unity_route'`）。已 `git add`（未提交），并给打包脚本
   加了通用闸门：`__init__.py` 顶层 import 的每个模块都必须真的进 zip，缺一个就打包失败；
2. `driver_presets.json` 属于"运行时无条件读取"那一档，之前不在必需列表里，缺了只会静默丢功能。

模板本身还是作者自己选（第一阶段照计划复用现有 R32 模板）；按目标资源自动下载/缓存是第二阶段。

### 批次 5 — Runtime 收严（P6）✅ 2026-08-17

`AddComponent` 预检 fail-closed。改在 `gakumas-mod-runtime`：

1. **`AttachQuartzDriver` 先预检再挂**：settingClass、四张表里每个字段名、每根引用骨，缺任一项
   就整体拒绝（`Log::Error` 写明缺什么）且**不动 prefab**。旧写法先挂再逐项写、失败只 warn 后
   continue → prefab 上留一个半初始化组件，照样 Instantiate、照样 OnEnable，然后按空引用跑；
2. **预检过了还失败就回滚**：`setting` 建不出来、或写引用时字段/骨又没了，都
   `DestroyComponentImmediate` 撤掉刚挂的组件，不留半成品；
3. **同类洞一起补**（不只补计划点名那一处）：摇物组件 `InitializeActorSwingDynamicBone` 失败时
   组件以前留在 prefab 上、又没记进 `g_createdActorSwingBoneNames` → 后续清理也找不到它，
   现在同样撤掉；驱动器挂不上时**不静默替换成摇物**（二选一，偷偷换求解器等于给作者一个
   "能动但不是他配的"结果），只把"这根骨不会动"写进日志；
4. `ActorSwingChain` 那处**本来就已经 fail-closed**（空壳链会被销毁），没动。

验收：把纯逻辑拆进 `src/runtime/DriverPrecheck.hpp`，在现有离线测试
（`mod_runtime_catalog_tests`，Release 构建强制运行）里两个方向都验 ——
坏 sidecar（骨找不到 / 字段不存在 / 回调为空）必须报且文案点名，正常包一项都不报。
**测试自己也验了有牙**：把预检改成永远返回"没问题"，测试立刻 assert 失败（已还原）。

构建：`.\tools\package.ps1 -Version dev` 全绿（`ModPresentationModelTests` /
`DriverPrecheckSmoke` / `ModRuntimeCatalogSmoke` + Python 契约测试 5 个），DLL 已部署到
`D:/Games/gakumas/`。（当时的记录：还需要一次「正常包不误报」的进游戏验证，后来在批次 7 的样本上做过了）
这一轮只改了这一个变量）。

### 批次 6 — 物理（P7）✅ 2026-08-17 起，2026-08-22 收口

**1. `collisionMask` —— 真值量出来了，预设已装众数，2026-08-22 画面判定确认。** 48292 根原版摇物骨（`vanilla-swing-bones.json`）
逐档众数：

```text
skirt   n=24183   1:47%   2:15%   -1:14%   64:10%   256:8%
cloth   n= 5020  64:22%  -1:16%  128:14%    1:12%  256:11%
sleeve  n= 5639   0:49%  -1:24%  128:12%   64:6%
ribbon  n= 6705  256:22%  -1:19%   64:18%    0:11%   1:8%
```

§11.1 规矩 6 那句「skirt 档原版取 1」**坐实**（47% 众数），而且更有意思的是：**当时插件统一用的
-1(Everything) 在原版任何一档都只占 14~24%**。逐档众数的当前值以 `swing_presets.json` 的
`_collisionMask` 注为准（本文不复写，见 §11.1）。

**这张表已经装进预设**（下面这条命令 2026-08-18 跑过了，`tests/test_bundle_source_contract.py`
钉住基准表）。这一档仍然是 🟡，因为**判据是画面**（窄裙贴不贴腿、发僵穿插），离线量不出来：

```bash
python tools/scan_vanilla_swing_bones.py --bundles <all_body> --output <out> \
    --collision-mask vanilla --install     # 逐档写众数；不加就还是统一 -1
```

实机看两件事：窄裙样本**不再发僵/穿插**（-1 去撞半径 0.23m 的胯胶囊那个症状），以及**该撞的还撞**
（裙摆与腿）。只改这一项，别顺手动别的（贯穿规矩 1）。

**2. `native_driver` 作用域化 ✅（§14 点名的"全局类别泄漏"）。** 导出器以前收的是**类别集合**：
作者在一行上选了裙，全模型每一根 skirt 类别的新骨都跟着改走驱动器 —— 他点的是一条链，
拿到的是整件衣服。现在收 `{骨名: 类别}`，一行=一组=一条链，作用域正好是作者的本意。
默认空 = 完全不碰这条路径，现有成品重导逐字节一样（`tests/test_swing_params.py` 钉住）。

**3. 置灰做对 ✅。** 运行时只实现三类驱动器（`core.DRIVER_CATEGORIES` = Skirt / Frill /
HumanoidSleeve），UI 与导出器读同一份：选了「原版布料驱动器」而类别落在 ribbon（或"自动"猜成
ribbon）时，表单当场标 ERROR，导出**直接拦下并说清怎么改**。以前这种组合导出后那几根骨
**既没有驱动器也没有摇物** = 不会动的哑骨，而日志全绿 —— 正是这一版要消灭的静默洞。
也**不静默替换成摇物**（与批次 5 运行时那条同一个原则：不偷偷换求解器）。

### 批次 7 — 三类样本（P8）—— 实机

1 → 2a → 2b → 3。逐样本"进游戏前跑什么、进游戏看什么"见
[`ab-target-rig-ingame-checklist.md`](ab-target-rig-ingame-checklist.md)。

### A 类（实机）的仪器已就位 —— 2026-08-18

- **`tools/read_runtime_log.py`**：把 `mod-plugin.log` 里该看的行量成数字（graft /
  droppedInfluences / swingDynamicBones / 300 帧动了几根 / 预检拒绝 / 空引用 / error），
  退出码非 0 就打印"不合格：<键名>"。它自己有 6 个自检（坏日志必须报、好日志不许误报，
  `tests/test_runtime_log_reader.py`）；
- ~~**300 帧摇物峰值探针**（运行时 `SampleSwingMotion`）~~ —— **2026-08-22 已从运行时删除**
  （测试期的东西，作者判定不留）。日志尺子里 `swingMoved` / `swingProbe*` 三个键随之下线；
  现在"骨被收进解算表了"看 `swingDynamicBones`，"有没有真的在动"只能看画面；
- 拿现有日志已经量到三件事，**不用新跑**：`swingDynamicBones=158~236`；
  `17/23 bones moved, best=Bone_SkirtA02_R 94.42°`（§11.2 的前置条件成立）；
  `Grew missing socket nodes count=9`、`hostRestDelta` 全 `0deg` ——
  **socket 由运行时从被替换资产补齐，批次 2 那个"参考资产没有 socket"的缺口到此收口**。

---

## 16. 贯穿规矩

1. **每次实机验证只改变一个主要变量**（2026-08-16 违反过，导致三轮结果不可归因）
2. **每个新检查必须同时证明「坏样本会报」和「正常样本不误报」**
3. 一根骨只能有一个主要求解器（同一 Transform 每帧只能有一个最终写入者）
4. body / face / hair 的骨名在共享命名空间内唯一；`RegisterBone` 遇到重名整根跳过
5. bindpose、骨序、权重索引和 Renderer 空间必须自洽
6. 日志声称做过的事必须能从实际产物或活体读回验证
7. 破坏性改名、改姿势、改权重必须**可见、可关、可量化、可撤销**
8. 共享文件、贴图、骨名和缓存必须按模型/部件限定作用域
9. 低可信推断不得自动变成已确认事实；源数据、推断结果和作者覆盖必须可区分可追溯
10. **动手前先 grep `research/` 和记忆索引**——已有量化结论的不要重新用实机去测
11. **活跃开发期的文档不写行号。** 引用代码一律用符号名（`core.undecided_export_error`、
    `ui.GMI_UL_bone_map`），不写 `core.py:3145`。理由是实测的：2026-08-20 核对这三份文档，
    **18 条行号引用里 6 条已经指到毫不相干的函数** —— `ui.py:300` 从骨映射表的 UIList 漂到了
    `GMI_PT_step_profile.draw_step`，`core.py:3145` 从 `undecided_export_error` 漂到了
    `anchor_only_chain_note`。而漂移全是同一周自己的提交推的（`units_for` 约 70 行、闸门 9
    两个函数约 40 行、anchor 逻辑约 30 行，下面的全体下移）。
    符号名改了 grep 得到、CI 也能查；行号改了**无声无息**，而且读者会照着错位置去理解代码。

---

## 17. 相关文档

- [`ab-consolidated-facts-and-evidence-2026-08-16.md`](ab-consolidated-facts-and-evidence-2026-08-16.md)
  —— 事实与证据的唯一入口。本文引用的每一个数字都出自它
- [`lessons-learned.md`](lessons-learned.md) §7 —— 已删除文档的结论与取回（两副骨架桥 / whole-object
  的对照组记录、泛用化计划、半透明研究都在这张表里）
- [`ab-target-rig-contract.md`](ab-target-rig-contract.md) —— 本文 §4 的落地面：导出器/闸门/sidecar 的硬约束
- [`ab-target-rig-ingame-checklist.md`](ab-target-rig-ingame-checklist.md) —— 进游戏一次该看什么（判据全是命令和数字）
- `gakumas-mod-runtime/docs/manifest-v2.md` —— sidecar 契约（改格式要同时 grep 这里）
- `research/unity-humanoid-avatar-sdk/` —— Unity 实验工程，大量原版数字的原始出处
