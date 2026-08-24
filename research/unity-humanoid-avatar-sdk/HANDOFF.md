# 交接：任意人型模型 → 学马服装/发型 mod

写给接手的人。读完这一份就能继续，不需要翻聊天记录。
最后更新 2026-08-15。

---

## 0. 一句话

作者在 Blender 里点两下，无头 Unity 在后台把模型变成学马能穿的 AssetBundle。
**转换器只做加法**——源模型的网格、权重、骨架原样保留，学马需要的东西往上加。

---

## 1. 先读这三条，能省掉一整天

### ① 转换器只做加法，不要改写源模型

把管线的每一步按「改的是作者的东西，还是学马的东西」划一刀：

| 加法（默认开） | 破坏性（先校验 / 退成可选） |
|---|---|
| 骨名映射、必需节点、材质贴图语义、摇物几何分类、扭转骨认领 | T-pose 烘焙（改网格+bindpose）、骨坐标系对齐、关节矫正 rig（改权重+截断到 4 骨） |

一天里破坏性那三步造成：反解补偿两次在部位边界折出裙子破皮/手腕折、组件重叠硬崩一次、
两轮改动零可见收益。加法那侧只出过一个真 bug（分类器分叉），修完就过去了。

**契约：给一副 T-pose 的 FBX，管线对网格的改动是零。**

### ② 能读源码就别模拟

iOS 3.2.3 的 Il2CppInspector 导出在 `D:\GIT\gkms-localify-ios\workspace\3.2.3\`，
`inspector/cs/il2cpp.cs`（4700 万字符）直接 grep 类名。

我曾用自造的度量得出五个互相矛盾的结论，最后一次 grep 就定了性（见 §3.1）。

### ③ 任何度量都要有原版同帧对照，闸门必须在坏包上验过会报

这一天里坏掉的度量：混五个角色的姿势 / 切片穿过躯干（量出 71cm 的"手臂半径"）/
圆柱套进头纱和肩甲 / 旋转轴在父骨坐标系 / bindpose 没转置 / 闸门 children 表全空所以坏包也报绿。
**没有对照的数字不该给任何人看，包括你自己。**

---

## 2. 架构

```
作者（只开 Blender）
  │  gakumas_mi 插件：摆 T-pose、适配检查、导出
  │     ↓  FBX + job.json
无头 Unity（作者不打开）
  │  GakumasAvatarSdk：骨名桥、必需节点、材质语义、摇物、扭转驱动器、打包、渲预览图
  │     ↓  bundle + report.json + 两张 PNG
运行时插件 / 游戏
```

**分工判据**：改作者的东西（姿势/权重/贴图）→ Blender，他看得见；
改学马的东西（必需节点/材质语义/摇物/驱动器/打包）→ Unity，他不用管。

### 为什么必须有 Unity

UnityPy 写不了 MonoBehaviour 布局（搬 nodes 会碎／清 typetree 被 Unity 拒／留旧 typetree 写新字节
原生崩），也就意味着摇物/驱动器/IK 组件打不进包；而且 UnityPy 内嵌合成对象在 Unity 6 上加载硬崩过。
Unity 侧有 13 个 stub 组件类（`Runtime/`），按游戏的字段布局序列化，游戏的 il2cpp 类能直接读。

### 为什么作者不用打开 Unity

Unity 全程 `-batchmode -executeMethod`。作者装一次（约 6GB），之后永不露面。

---

## 3. 目标侧的事实（都是量出来或读出来的，可复现）

### 3.1 那 14 根 `*_H` 骨是**扭转分配**，不是防肩塌

读 `il2cpp.cs` 定的性：

| 骨（系数） | 驱动器读什么 | 作用 |
|---|---|---|
| `Arm_H` −0.8 / `Arm_Roll_H` −0.3 | MuscleHandle **41/50 = Arm Twist In-Out** | 上臂扭转分配 |
| `ForeArm_Roll_H` 0.5 / `Hand_H` 0.9 | **43/52 = Forearm Twist In-Out** | 小臂/腕扭转分配 |
| `UpLeg_H` −1.0 / `UpLeg_Roll_H` −0.6 | **23/31 = Upper Leg Twist In-Out** | 大腿扭转分配 |
| `ForeArm_H` (0,−0.4,0) / `Leg_H` (0,0,−0.5) | RotationBone，参考同侧 ForeArm / Leg | 肘/膝半角 |

**这个游戏没有肩部摆动矫正骨。** 早期"肩半宽 17.4→12.6cm、需要矫正骨"整套说法**作废**，
那是用错误取样量出来的。52 骨缺的是**扭转剪切 + 肘膝硬折**，与静止姿势是 A 还是 T 无关。

`CampusActorAnimationInitializeData` 用 `List<组件>` 收集驱动器——**按组件类型，不按骨名**，
只有 `reference`/`hips`/`head`/`moveReference` 按身份绑。所以认领源模型自带的扭转骨**不需要改名**。

### 3.2 骨架

- 530 套共有的"基础骨架" **70 根**，其中 **52 根正好是全部 Unity Humanoid 骨**（一根不缺）
- 多出的 18 根：14 根 `*_H` + `Pelvis` + `Reference` + `Left/RightBust1_S`
- 静止姿势 530 套**完全一致**，离标准 T 最大 4.0°，双臂精确 0.0°
- 骨架节点 78–203（我们出的 260 也照跑），**每套都只有 1 个 SkinnedMeshRenderer**

### 3.3 组件摆放硬规矩（违反 = 硬崩，2026-08-14 崩过一次）

- 一根骨**不能**同时挂 `ActorSwingDynamicBone`/`ActorSwingStaticBone` 和任何 QuartzDriver
  （原版 60 套 327 个裙摆驱动器**零重叠**）。`ActorSwingChain` 是环容器，**允许**和驱动器共骨。
- **静态碰撞体从不挂 `_H` 骨**（原版挂 Hips/Spine/Neck/Arm/ForeArm/Hand/UpLeg/Leg/Foot）
- 一条骨脉至多一个 QuartzDriver

### 3.4 摇物

- **层 0 是锚定层**：单根骨的飘带/裙摆在游戏里不会动，一条链至少两根
- 裙摆面片根部在胯上 **+0.3~+17.4cm**（381 套实测）；方位角分档边界 **56°/89°/124°**
- skirt 档 `collisionMask=1`，落进 cloth 档会变成 −1 去撞半径 0.23m 的胯胶囊 → 裙子发僵不贴腿

### 3.5 包里有什么 / 能自定义什么

**完全自由**：拓扑、顶点数、UV、法线、切线、权重分布、子网格数、装饰骨数量层级、贴图
**必须遵守**：出包静止姿势=T、52 根人形骨名、必需节点、一个 SkinnedMeshRenderer、
顶点 COLOR 语义（描边/ramp 编码在里面）、贴图语义（`_BaseMap`/`_DefMap`/`_ShadeMap`，t4.A=皮肤 mask）
**不能自定义**：Shader（运行时用游戏的材质，只把你的三张图塞进槽）、其余 8 个贴图槽和 56 个数值
属性（跟场景/服装走）、动画（纯肌肉 clip）

---

## 4. 实验期代码曾在哪（插件入口已于 1.3.0 删除）

### Blender 插件 `gakumas_mi/`

| 文件 | 作用 |
|---|---|
| `unity_route.py` | 实验期的三个算子与预览图加载；路线证伪后已删除 |
| `topology_map.py` | **本轮新增**。不看名字，从骨架结构认人形骨 |
| `ui.py` | 实验面板 `GMI_PT_unity_route`；1.3.0 已从正式插件删除 |
| `core.py` / `operators.py` | 原有：8 张骨名预设表、材质预设、贴图烘焙 |

### Unity SDK `research/unity-humanoid-avatar-sdk/GakumasAvatarSdk/`

`Editor/` 22 个文件，本轮新增/大改的：

| 文件 | 作用 |
|---|---|
| `ModBuilder.cs` | **CLI 入口**：`job.json` → bundle + report.json + 预览图 |
| `TwistAdopter.cs` | 认领源模型自带的扭转骨，**不改名不改权重**，挂驱动器 + 对齐轴向 |
| `HairBuilder.cs` | 发型路径（`kind:"hair"`），骨架是 `Head_Hair`+`*_S`，零人形骨 |
| `PreviewRenderer.cs` | 渲正面/侧面 PNG |
| `SdkPipeline.cs` | 后端总装；`stockJointRig` 参数默认 **false**（破坏性 rig 退成可选） |
| `TPoseBaker.cs` | T-pose **先校验**，已是 T 就一个字节不动；反解补偿已删 |
| `ChainClassifier.cs` | 几何分类；分叉 bug 已修；支持 `Overrides` |

`Runtime/` 13 个 stub 组件类，照游戏字段布局写，Unity 序列化进包。

### 尺子与闸门 `tools/`

| 工具 | 用途 |
|---|---|
| `audit_body_bundle.py` | **主闸门**，出包必跑 |
| `measure_helper_rig.py` | 从 530 套量矫正骨位置和权重剖面 |
| `render_runtime_pose.py` | 把包 + 探针记录的实机姿势渲成图（**必须传 `--actor=`**） |
| `replay_runtime_pose.py` | 同上，数值归因版 |
| `probe_joint_collapse.py` | 量上臂截面。**默认 `--motion=twist`**（扭转才是驱动器读的量），`--rig=off` 做同包 A/B |
| `measure_rig_gap.py` | 原版自己的对照：装矫正骨 vs 折成 52 骨（弯曲工况，结论恒为 0.0%，见 §8.4） |
| `inventory_body_colors.py` / `inventory_hair_colors.py` | 顶点 COLOR 的闭合清查，body 410 套 / hair 379 套 |
| `measure_live_swing.py` | 从探针 dump diff **局部**旋转，回答"这条链在实机里到底动没动"。**必须用同一场景内的两份 dump**——跨场景那对共同骨会翻倍，读数全是 0 |

---

## 5. 怎么跑

### 命令行（不经 Blender）

```bash
Unity.exe -batchmode -quit -projectPath <SDK> \
  -executeMethod GakumasSdk.ModBuilder.Build -gmiJob job.json
```

**不要加 `-nographics`**——那连图形设备都不创建，预览图渲不出来。批处理照样无窗口。

`job.json`（除 `kind`/`fbx` 外全部可选）：

```json
{
  "kind": "body",
  "target": "mdl_chr_hmsz-cstm-0059_body",
  "fbx": "…/source.fbx",
  "outputDirectory": "…/out",
  "keepMeshes": ["Body"],
  "materials": [{ "name": "m_bdy", "role": "cloth", "bareSkin": true }],
  "chains":    [{ "root": "Bone_SkirtA01_L", "category": "skirt" }],
  "twist":     [{ "bone": "+UpperArmTwist L A01", "role": "LeftArm_Roll_H" }],
  "stockJointRig": false
}
```

`chains`/`twist` 是**覆盖**，留空走自动识别。产出 `report.json`（`ok` + 一句话一条的 findings）。
失败退出码非 0。

### 出包体检

```bash
python tools/audit_body_bundle.py <bundle>
```

### 无头验证（改完代码先跑这两个）

```bash
blender --background --factory-startup --python <冒烟脚本> -- --fbx <模型>
Unity.exe -batchmode -quit -nographics -projectPath GakumasAvatarSdk \
  -executeMethod GakumasSdk.AvatarBench.RunFromArgs -logFile bench.log
```

---

## 6. 闸门清单（每条都在坏包上验过会报）

| 闸门 | 判据 | 坏包实测 |
|---|---|---|
| 必需节点 | `REQUIRED_NODES` 全在 | 缺一个 = Burst 里无栈崩 |
| 骨缩放 | **蒙皮骨**不得带非 1 缩放 | 报 `Hips` ×100 + bindpose 868mm |
| bindpose | 与骨架偏差 | 240/257 根偏 |
| T-pose | 离标准 T ≤20° | 静止偏几度动画就偏几度 |
| 手指伸直 | 0°，拇指 45° | 握剑姿势 → 手散 |
| 骨坐标系 | **肌肉/驱动器直接读坐标系的骨**（8 根肢体 + 双手 + 30 根手指 + 认领的扭转骨）与原版一致 | 报 39 根，实机手被拧 360° |
| 组件重叠 | 摇物骨不得再挂 QuartzDriver | 报 18 根骨，实机 2.6 秒硬崩 |
| 衣物链 | 垂到胯下、没人驱动的权重 = 0 | 报 4.4%（裙子焊死） |
| 几何覆盖 | **有权重**的肢体骨必须有被绘制的几何 | 整段材质被丢 |
| 骨在动画树里 | **有权重的骨必须在 `Reference` 子树内** | 报 17 根；实机表现＝人一走，腰/小腹/大腿根的皮留在原地 |
| 顶点 COLOR | 非纯白 | 没描边 |

---

## 7. 已经证伪的结论（别再走回去）

- ❌ **"T-pose 出包后游戏转回垂手会塌肩，所以需要矫正骨"** —— 机制不存在，§3.1
- ❌ **"肩半宽 17.4→12.6cm"** —— 错误取样量的，作废
- ❌ **反解补偿**（按源姿势预畸变网格）—— 一个姿势精确、离开就近似，必须切部位边界，
  每条边界都在跨界几何上折（先裙子后手腕）。已删
- ⚠️ **"骨轴向对齐只有挂驱动器的骨才需要"** —— **2026-08-15 修正为：方向被吸收，滚转不被吸收**。
  重定向吸收的是骨**指向**（所以烘 T-pose 就够、`RestPoseNormalizer` 该死）；但指向相同、
  绕自身轴差 180° 的两根骨，同一条肌肉会**反号**作用。所以双手 + 30 根手指 + 四肢都要对齐，
  哪怕它们一个驱动器都不挂。证据：实机重放 1061 → 339 个爆裂三角，作者确认手不拧了。
  当初按"只有驱动器"收窄了闸门，于是坏包一路全绿
- ❌ **按材质名丢整段** —— rip 的 "Hair" 图集常装着整条腿
- ❌ **「把扭转骨按弯曲角的系数反转一下」当成驱动器的模拟** —— 两个尺子都这么写过。
  驱动器读的是 **MuscleHandle（Arm Twist In-Out）**，弯曲工况下那个肌肉是 0，骨随臂刚体走。
  按弯曲轴反转会把骨从臂轴上拖开，`measure_rig_gap.py` 因此报出 +60%～+166% 的"更饱满"。已改

---

## 8. 没做的 / 已知边界

1. **发型的贴图语义（t1/t4）没验过 —— 而且离线量不了**。离线的发型库
   （`assetstudio-hair-json`，379 套）只有网格，没有材质也没有贴图；要验必须先把原版 hair 包
   按 `all_body` 那样落到本地。报告里明说了这一条。
   **顶点 COLOR 那一半已经量完并落地**（2026-08-15，`inventory_hair_colors.py` / 379 套）：
   发型是和身体不同的 population —— LUT 行 **99.6% 是 0**（身体摊在 0/3/6/9/12/15），
   rim **只有 0 和 9 两个值**（发型 58%、发饰 74% 取 9），描边宽度**没有原版常量**（0–15 摊平，
   身体则 49.5% 压在 15）。据此给了 `SurfacePresets.Hair = (0,0,15,144)`，发型路径过去
   一个字节都不写、直接把源模型的外来 COLOR 带进包（＝霓虹描边）。
   顺带旁证了 0.7.4 那个 `A=0` 的发型预设是产品防护 fallback、不是 shader 语义。
2. **源模型没有的骨补不出来**。这副 rip 没有大腿扭转骨和 `Hand_H`，`UpLeg_H`/`UpLeg_Roll_H`/
   `Hand_H` 六个角色空着，对应部位大角度扭转会剪切。要修就在 Blender 里加骨。
   **现在会进 `report.json`**（warn 级，点名是哪几根），不再只躺在 Unity 日志里。
3. ~~**胸部驱动**没接~~ —— **2026-08-15 接上了**。`BreastRigger.Claim()` 认领源模型自己的胸骨
   （`bust`/`breast`/`胸`/`乳`，且父骨必须是脊椎，避免抓到 MMD 的胸饰），转到原版静止坐标系、
   改名 `*Bust1_S`、补一根 `*Bust2_S_End`。尖端骨位置是从 30 个原版包量的：
   局部 **(−0.1025, 0, 0)、单位旋转，60/60 一致**（骨前方 10.25cm、下俯 5°）；
   原版静止坐标系 forward=(1,0,0) up=(0,0.9962,0.0872)，40 套一致，**左右不镜像**（和手臂不同）。
   摇物那边改成问 `Claim()` 而不是认 `Bust` 这个词，因为改名发生在摇物装配之后。
   实测：`+Breast L/R A01 → Left/RightBust1_S`，链数 26 / 骨 76 不变，体检全过。
4. **关节矫正 rig 默认关**（`stockJointRig: false`），**现在有数字了**（见 §9）：
   - 弯曲工况下矫正 rig 的收益是 **0.0%**，22 套原版 114 段全为 0 —— 因为那 10 根是扭转分配骨，
     弯曲时肌肉值为 0、随臂刚体走。原版自己带着全套矫正骨，肩部一样塌 −19.5%。
   - 扭转工况下收益是真的：同一个包 60° 上臂扭转，**有扭转骨肩部 −0.5%，没有则 −8.7%**。
   - 但这份收益**已经由 `TwistAdopter` 以纯加法拿到了**（认领源模型自带的骨，不改权重）。
     `stockJointRig` 唯一多出来的只有「源模型压根没有那根骨」的情况，代价是重写作者权重。
   结论：保持默认关；缺骨走 §8.2 的报告项，让作者在 DCC 里加骨。
5. **形态键**：Blender 不允许在带形态键的网格上应用骨架修改器。「摆 T-pose」会点名要求先删掉。
6. **孤立单骨**：层 0 是锚定层，一根骨的装饰在游戏里不会动。检查里报出来，作者各加一根尾骨。

---

## 9. 实测基线（回归时对照）

Genshin `Avatar_Girl_Claymore_MarionetteNew` → `mdl_chr_external_body`：

```
Blender:  摆 T-pose 55.5° → 5.9°       骨名打乱后拓扑识别 22 根全对 0 错
Unity:    蒙皮骨 257，顶点 42066，子网格 5
          摇物 26 条链 / 76 根骨（sleeve 4, ribbon 22, skirt 50）/ 30 个静态碰撞体
          扭转骨认领 6 根，轴向对齐 6 根
          胸部骨认领 2 根（+Breast L/R A01 → Left/RightBust1_S）
体检:     全部检查通过（bindpose 0/172，T-pose 2.6°，衣物链 0.00%）
```

对照包 `mdl_chr_chs-sucu-00_body`（实机验证过的那套）同样全过。

上臂扭转 60°，`probe_joint_collapse.py`（**同一个包开关驱动器**，其余一切不变）：

| | 肩部一段 (0.05) | 最严重的一段 |
|---|---|---|
| 本包，有扭转骨 | −0.5% | −5.1% |
| 本包，`--rig=off` | **−8.7%** | −8.7% |
| 原版 sucu，有扭转骨 | −0.5% | −3.8% |

有骨的剖面形状和原版同型（剪切摊开在整条臂上），没骨的是肩部一个尖坑。
弯曲工况（`--motion=bend`）原版自己也塌 −22.5%，装不装矫正骨一样 —— 那不是这套骨管的事。

---

## 10. 相关文档

| 文档 | 内容 |
|---|---|
| `docs/blender-unity-workflow.md` | 工作流细节、三个坑、三条自动化 |
| `docs/corrective-helper-rig.md` | 矫正骨的数据与实测（注意开头的翻案说明） |
| `docs/rest-pose-dead-end.md` | 为什么静止姿势必须是 T（clip 绑定证据） |
| `docs/body-component-inventory.md` | 530 套组件/材质闭合清查 |
| `P0-STATUS.md` | 时间序的会话交接记录 |
