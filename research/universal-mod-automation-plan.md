# 通用 AB 换装自动化：问题模型与架构

> 目标读者：接手把 GakumasMI 的 AB 导出做成「通用、少懂骨」流程的开发者。
> 本文 = 问题模型 + 架构 + 算法规格 + 诚实边界。核心原型证据来自 2026-07-24 起对
> fuyuko(SCSP)→`hmsz-cstm-0059` 的多轮实机调试。
>
> **进度不在这里。**当前完成度、验证等级和后续计划只有一个出处：
> [`current-status-and-roadmap.md`](current-status-and-roadmap.md)。
> 本文 2026-08-02 砍掉了与它重复的状态段和逐日进度时间线（git 历史里有）。
>
> 关联：[`lessons-learned.md`](lessons-learned.md)（为什么不走 3DMigoto / IL2CPP）、
> [`ab-route-notes.md`](ab-route-notes.md)（运行时机制与物理骨规范）。

## 0. 一句话目标

作者的理想流程:

```
导入 mod 模型  →  导入学马目标(body JSON/抓帧)  →  设贴图  →  选基准 bundle 模板  →  导出
```

中间所有「骨」的事(对照、清理、分类、物理继承)全部内置自动。

> **2026-07-27 的现实校准**：「全部内置自动」这个目标要分两层看，混在一起谈会得出错误的
> 优先级（本文档此前就把两层混着写）：
>
> | 层 | 现状 | 性质 |
> |---|---|---|
> | 身体骨对照 | 八家预设自动 + 表单点选兜底可人工闭环；MMD 与 SCSP 有 A 样本，另六家属于 C 级纸面范围 | 入口已完成，首发不以六家 C 级实机回归为条件 |
> | 装饰骨物理归属 | 默认源父骨 + 胸/Bust 名称规则；RC1 样本已实机确认，异常件仍可 override | **命名和源层级不能覆盖所有怪异绑定，保留人工覆盖** |
> | 对齐 / 删头 / 图集 | 零支持，每 mod 写脚本 | **作者基本功，插件不代做**（明确排除出范围） |
>
> 也就是说：身体骨对照和首发样本的装饰物理已不再是主要开发瓶颈；端到端一键化的拦路虎是
> 对齐，而那被划到作者侧。

---

## 1. 背景:核心问题模型(接手前必读)

### 1.1 换装 = 让游戏引擎穿上你的网格

AB 路线把 mod 网格作为真正的 Unity Mesh 交给 chinosk6 插件,`set_sharedMesh` 塞回原(学马活体)renderer。
网格的顶点/法线/UV/**colors32(描边)**/submesh 插件**不动**;它只改 bindpose(空间校正)、boneWeights(骨序 remap)、贴图。
→ 描边/透明/物理由引擎原生正确。详见 runtime-mechanism.md。

### 1.2 「翻译」vs「整搬」——一切麻烦的根源

- **翻译(remap/对照表)**:把源骨一根根映射到游戏骨。身体适用。
- **整搬(无损新骨)**:游戏没有的源专属骨(发/裙/缎带),当场新建 Transform、按源 localTRS 摆好、挂到正确父骨下。装饰适用。
- **铁律**:模型要跟游戏动画动,身体骨**必须**接到游戏活体骨(翻译);装饰骨才整搬。硬把装饰骨也翻译 → 缎带黏裙、蝴蝶结裂开(fuyuko 实测教训)。

### 1.3 权重:换标签保留 ≠ 邻近重刷

| 做法 | 机制 | 结果 |
|---|---|---|
| **换标签(保留)** | 读源顶点组权重原样,只把骨**名**映射到目标骨索引(`gmi_bone_remap_file` + `source_rig_weights=True`) | 权重值一字不变。fuyuko 全程用此,已验证 `Spine2_1:0.745→Spine2:0.745` |
| **邻近重刷(丢弃)** | 从游戏 body 按 `POLYINTERP_NEAREST` 重算(`GMI_OT` 三条传递权重算子,`mix_mode=REPLACE`) | 源权重丢弃 |

**只要能建立「源骨↔游戏骨」对应,就换标签保留;建不出对应才被迫重刷。** 对应关系 = 对照表 = 唯一的作者工作量。

### 1.4 物理的跨引擎现实

- scsp/偶像荣耀与学马**同 QualiArts ActorSwing 框架**(偶像荣耀已核实类名逐字相同;**SCSP 未核实,待验**),摆动参数**可从源提取**。
- MMD(刚体+关节)、Blender(通常无)**与学马是不同物理系统,参数搬不过来** → 新骨挂学马原生 ActorSwing + **默认/手调/蹭** 参数。
- 物理生效前提(P4 findings):sidecar 必须补①每骨摆动参数 ②每条链**链尾 tip 骨**(无权重、不在 m_Bones,单列 `extraSwingBones`),缺一不摆。

---

## 2. 目标 UX(作者视角每步背后做了什么)

| 作者动作 | 背后自动 |
|---|---|
| 导入 mod 模型 | 读顶点组、逐张预设表打分选表（八家命名规范），表外的列进「骨骼映射表」等作者点选 |
| 导入学马目标 | 从 body JSON/抓帧得目标骨架 + 材质段数 + 目标摆动骨集 |
| 设贴图 | t0 直用;t1/t4 按材质预设生成（DDS→PNG 已有导出侧支持） |
| 选基准 bundle | R32 模板(每 body 一份,一次性产) |
| 导出 | 自动:建对照表→清理→分类→物理继承→新骨嫁接→保留权重→打包 |

---

## 3. 已验证的原型(fuyuko 这次,即自动化的规格来源)

这次**手动**跑通、且**全部确定性可脚本化**的步骤,就是要内置的算法:

1. 诊断源顶点组 vs 目标骨集(298 组 → 50 直接对上、248 需处理)。
2. `_1` 链识别与去后缀(scsp 合并残留;真权重在 `*_1` 上,58.5%)。
3. 空组补齐(125 个零权重组映射到父骨,只为过 `Unmapped` 校验)。
4. 装饰骨父链解析(`parent_resolve`:strip `_1` → 沿源骨架父链找第一个目标骨 → Hips 兜底)。
5. 裙摆按位置**逐段**就近到目标裙摆骨(继承物理)。
6. 悬挂装饰(缎带/蝴蝶结)**整组挂一根**(按组质心就近目标摆动骨;逐段会散架坍缩——已踩坑)。
7. rootBone 认对(合成骨架 bug 修复,见 §7)。
8. 全程**换标签保留权重**,geojson 实测 0 泄漏、Hips 分布符合预期。

产物验收:bundle mesh verts/bindpose/submesh 与 geojson 一致、boneWeights 分布逐字节穿过打包、SMR rootBone=Hips。

---

## 4. 架构:两轨自动化

```
                    ┌─ Track A 身体骨:对照表换标签(保留权重)─────────────┐
mod 顶点组 ──分类──┤                                                      ├─→ sidecar + geojson ─→ 打包
                    └─ Track B 装饰骨:无损新骨嫁接(+物理)──────────────┘
```

- **Track A(身体)**:源骨 → 目标骨对应表 → 换标签。对应表来源:scsp 自动 / MMD·标准 rig 预设 / 自定义手指。
- **Track B(装饰)**:游戏没有的源专属骨。两种子策略:
  - **蹭**(目标有相似摆动部件,如裙摆):按位置就近继承目标物理。**首选**。
  - **新骨**(目标无对应,如独立缎带):整搬源骨 + 挂物理。**同引擎源可搬参数;跨引擎源用默认/手调。**

---

## 5. 自动化管线(阶段 · 算法规格 · 验收 · 边界)

### P0. 源 rig 识别 ✅
- **不再嗅探"这是哪种模型"**：逐张预设表试算命中数、取最高的那张（嗅探只用于打平手）。
  此前靠几个探针骨名判家族，探针没命中就整张表空转。
- 当前八家：MMD 準標準（两种写法）/ SCSP-QualiArts / Mixamo / Rigify / VRM-VRoid /
  3ds Max Biped / Auto-Rig Pro / 英文 Humanoid 同义词。支持一种新命名规范＝**纯加一张表**。
- **边界**:表外的骨架 → 作者在「骨骼映射表」点选（陌生骨架实测约 21 行），不再是"引导手工"
  而是正式入口，因此可以人工闭环；自动覆盖率仍需按真实模型逐家验收。

### P1. 建对照表(Track A 核心)
算法(规格 = 本次 `gen_remap_*` 脚本):
1. 源骨名 ∈ 目标骨集 → 直接对应。
2. 否则 strip `_1` 后 ∈ 目标 → 去后缀对应。
3. 预设映射(MMD `左腕`→`LeftArm` 等)。⚠**查表前必须把 `.L/.R` 折回 `左/右`**：mmd_tools
   一律把 `右腕` 导成 `腕.R`，不折就整张 mmd 表空转（修复前 87 组只中 5 组）。
3b. 作者在「骨骼映射表」填过的行**优先级最高**，盖过预设与外部 JSON。
4. 仍无 → 沿源骨架父链找第一个目标骨(装饰骨走 Track B,不在此)。
5. 零权重空组 → 父骨兜底(仅过校验)。
- **验收**:导出无 `Unmapped weighted bones`;权重值与源逐点相等(抽样);**21 个承重关节都拿到
  权重**（闸门，缺任一根拒绝导出并点名）。

### P2. 身体/装饰分类 ✅
- 装饰判据:命名关键词(Skirt/Bow/Streamer/Hair/…) **或** 「目标骨集里没有」。
- ⚠这个判据的固有缺陷：**没被预设认出来的身体骨也会落进"装饰"**。所以判"导出对不对"不能靠
  这个分类，要靠 P1 验收里那个只看游戏侧的承重关节闸门。
- **边界**:命名不规范的源需作者在映射表里复核/override 一次。

### P3. 装饰物理继承(Track B-蹭)
- 目标摆动骨集 = `_S` 结尾 + `Cloth` + `bone_<hash>`(启发式;`bone_<hash>` 物理不确定,需实机确认)。
- **裙摆类**(与目标裙摆骨密集重合):逐段就近。
- **悬挂类**(普通缎带/蝴蝶结):**整组按质心就近一根**,阈值(~18cm)外 → 刚性父骨。**禁止逐段**(散架)。源服装自带 `Spine*_Bow`/`Streamer`/`SStreamer`/`Lace` 链例外：保留整条源父子链，转 P4 新骨。
- **对称件(蝴蝶结左右半)**:同组映一根,别分两根(否则裂开)。
- **边界**:目标无合适摆动骨的件 → 转 Track B-新骨,或接受刚性。

### P4. 无损新骨嫁接(Track B-新骨)
- sidecar 发射源专属骨:name/parentName(解析到目标活体骨)/localTRS。
- 摆动参数:同引擎源从源 bundle 提;跨引擎源用默认；当前 GakumasMI 路径使用默认参数。
- 补每链 tip 骨到 `extraSwingBones`；runtime 支持 `newBones` 与 tip 按 `parentName` 建链。
- **依赖**:游戏侧插件运行时建新骨物理，当前插件仓库 Release x64 编译已通过。
- **当前完成范围**:sidecar/runtime 已通；P5 已补齐 bundle skeleton/bindpose/`m_Skin` 索引闭环。
- **已验证**:插件 Release x64 编译、sidecar 解析契约、离线导出回归。
- **实机验收证据**：`atbm-0140` 日志为 `matchedBones=56 createdBones=288 bones=344 boneWeights=170292 droppedInfluences=0 fallbackVertices=0`、`meshApplied=1`，并建出 5 组 `ChainInfo`（7/8/9/10/11 层）；`ActorSwing colliders applied: 288/288`。`active=0` 是刚建链/LOD 阶段的正常状态，不判失败；持续自摆仍需人工观察。
- ⚠️ **2026-08-04 更新：画面级观察的结果是「不摆」。** dress-2219（`hmsz-cstm-0059`）修完
  0.9.3 的四项 sidecar 写入约定后，日志同样全绿（`createdBones=26 swingPrepared=36`、链尾齐全、
  3 条链注册），装饰件在游戏里维持静止姿态。**所以 P4 的实机验收目前只到"链建出来了"，
  不到"它会摆"**；成品用刚性/跟裙摆绕开。排查现场与下一步见
  [`current-status-and-roadmap.md`](current-status-and-roadmap.md) 的「未解决：自建摇物链」。

### P5. 权重导出(换标签,不刷)
- 现有路径:`_inverse_skin_export_data(source_rig_weights=True)` 原样读顶点组 + 按对照表映射骨索引。
- 已补齐：新增 `newBones` 进入 bundle skeleton/bindpose/`m_Skin` 的索引闭环，并保留源权重值。
- **不得**触发邻近重刷分支；验收为抽样顶点的权重值与源逐点相等，且 `droppedInfluences=0`。

### P6. 打包
- `write_bundle_source` → `patch_unity_bundle.py`(UnityPy 模板补丁,无 Unity)→ 成品 bundle。
- 一键算子 `GMI_OT_export_bundle_source(also_patch=True)`。
- **P6.1–P6.3 ✅ 已完成（Unity 6 加载崩溃已根治）**：崩溃根因＝**UnityPy 向 bundle 新增（合成）
  GameObject/Transform，Unity 6 原生反序列化就崩**，与骨数/AABB/悬空指针都无关（都排除过）。
  修法＝**不内嵌合成对象**，改由运行时按 sidecar 建骨：导出侧删掉 `_ensure_template_bones`
  合成路径、模板缺失的新骨名回退到 root transform；运行时删掉那条冗余的
  `modBones[i].name == sidecar[i].name` 前置校验（真正干活的 `BuildHybridBoneArray`
  根本不读 mod SMR 骨名）。fuyuko 实机加载成功 + 网格/蒙皮/贴图正确 + graft 通过。
  证据链见附录 A。
- **P6.4 ✅ 已完成**：模板侧 44 个 `bone_<hash>` 占位骨已按 `m_BoneNameHashes` 修复；
  `patch_unity_bundle.py` 现在会拒绝仍含 `bone_*` 的模板，不会再静默产出
  `matchedBones=112 / createdBones=44 / ChainInfo=44x1` 这种坏包。
- **P6.5 ⚠ 已修的隐性 bug**：`_export_bundle_png` 的 colorspace 赋值顺序会让 t1/t4 导出成
  纯黑（影响此前所有 AB mod，游戏里表现为"整身发暗"），见附录 A。验收时看 t4 是不是 MB 级。

---

## 6. 三个诚实边界(要在 UI/文档里明确标给作者)

1. **冷门自定义 rig**:八家标准命名预设全自动;乱捏骨架需在「骨骼映射表」**点选一次**
   （约 21 行，可存成 JSON 复用）。这条边界已经从"可能做不了"降级成"多花几分钟"。
2. **跨引擎装饰物理**:MMD/Blender 物理参数**搬不过来**,新骨只能默认/手调/蹭——能摆但非源手感。同引擎(scsp/偶像荣耀)才可搬。
3. **前置基础设施**(一次性,非每 mod):模板 bundle 库 + 游戏侧插件新骨支持；P6 还需要能承载新增骨的模板结构。见 §7。

---

## 6.5 一键化的复杂度边界与泛用解方向(2026-07-24 定调)

**结论:把复杂度分两类,别混为一谈**
- **一次性基建**(崩溃修复、运行时 ActorSwing 三修、swing 参数自动合并):埋在插件/运行时里,开发者一键导出时白嫖,**不给每个 mod 增加任何操作**。是"从跑不起来→能跑",不是"变难"。
- **每 mod 启发式**(骨分类、蹭 vs 整搬、花边挂腿这类):这才是可能让一键变脆的地方。但每修一个边角(如花边→按名蹭裙摆)都是**对启发式的永久加固**,未来同类 mod 白嫖。fuyuko 是压力测试样本(SCSP 未核实源 + 左右不对称 + 花边绑腿 + bow 拆链),不是常态。

**诚实边界:没有启发式能 100% 猜对源模型的怪异绑骨。** 硬堆启发式去猜一切 = 把事情做复杂(ponytail 反模式)。正解 = **自动兜 90% + 傻瓜 override 兜 10%**:开发者不懂骨,只在画面明显不对时说一句"这块跟着那块动"。

**泛用解已落地(2026-07-27):`build_accessory_physics_remap` 采用三层分类** —— **override(作者显式) > 语义/名称规则 > 源父骨兜底**。策略:`integrate`(自己物理,飘带/蝴蝶结)/`follow_skirt`(蹭最近裙摆,花边)/`follow:<骨>`(蹭指定)/`rigid`(无物理跟源父骨)。未显式要求时不再按位置猜；包含 `胸`/`Bust`/`Chest` 的组按最近的 `Bust*_S`，其余装饰跟源父骨映射。`gmi_physics_override_file` 仍支持最长前缀覆盖；位置最近只能用 `follow_nearest` override 显式启用。当前为 B：契约测试通过，翻转后的策略尚未实机验收。

**设计:装饰骨物理 = 两个正交决策,别耦合**
1. **挂哪(parent)**:解析到某游戏骨。源父骨好就用源父骨;源父骨可疑(如花边网格在裙摆、骨却绑在大腿)才 override。
2. **怎么动(physics)**:三选一 —— ①**蹭**(权重共享游戏摇物骨,精确同步,给"和某游戏件物理连续"的镶边/花边);②**整搬**(建新骨+自己的 ActorSwing,给自由悬垂的飘带/蝴蝶结);③**刚性**(无物理,跟父骨)。
- **默认应偏「整搬/信任源」而非「位置蹭」**:位置蹭是脆弱来源(花边挂腿正是位置匹配被源绑骨误导)。把位置蹭**降级为 override-only**,默认忠实保留源层级+源物理,能去掉一大半会踩坑的启发式代码(ponytail 化简)。
- **但「直接新建/整搬」不解花边**:见 §6.6——因为源把花边绑在大腿,整搬会忠实保留"花边跟腿",还是错。花边要精确跟裙摆只有 蹭 或 改源/override。

## 6.6 「不绑骨直接新建」为什么不解花边(2026-07-24)

问:装饰件不做映射,直接当新骨建(整搬)行不行?
- **对自由悬垂件(飘带/蝴蝶结)**:行,而且这本就是现在的做法(`is_source_chain`→`new_source_chain`),是最 robust 的路,不需要任何位置匹配。
- **对花边**:不行,而且和"建 vs 蹭"无关,问题在**源绑骨**。源模型把 `Lace_R` 的骨绑在 `RightLeg`(大腿),但花边**网格**在裙摆最底边。整搬会忠实保留"花边骨=腿的子级"→花边跟着腿动,还是错。
- 而且用户要的是花边**和裙摆分毫不差**("不应该自己乱动")。整搬=独立物理=和裙摆近似而非精确同步,天然做不到"分毫不差"。只有**蹭**(花边顶点权重共享裙摆骨)才精确跟随。
- **根上三条路**:①导出侧按语义(名字含 Lace)强制蹭裙摆(已做,`build_accessory_physics_remap`);②回 Blender 把花边骨从大腿改挂裙摆(源头修,连蹭都不用猜);③给 override 入口让作者点"花边→跟随裙摆"。

---

## 6.7 AB 路线可行度评估(2026-07-25 从头评估)

### 已验证样本(实机)
| 样本 | 源类型 | 结果 |
|---|---|---|
| hmsz-0000-ruinurs | QualiArts 同骨架 | ✅ 完好 |
| pm.ttmr.madoka-swimsuit | QualiArts(65796 顶点 / 9 材质归并) | ✅ 完好 |
| qa-madoka-ttmr-hair-0002-2b | hair + hairprop | ✅ meshApplied=2 |
| **atbm-0140-chisaki** | **MMD 外部源**(45 材质) | ✅ createdBones=288、多层 ChainInfo、物理 |
| fuyuko-super (dress_2219) | SCSP 镜像源 | ✅ RC1 已完整通过：**原始 `dress_2219` 手指动就炸已确认是 prep 坏绑定**；重新导出后 fuyuko 加载、graft、手部和装饰物理均完成实机确认。→ 它证明"手指失败不是 AB 架构问题"，不能把旧 prep 失败算作当前 AB 缺陷 |

**关键**:`atbm-0140` 证明**外部源(MMD)→ AB 能成**,前提是 prep 按 [`../docs/wiki/10-外部模型转换实战规范.md`](../docs/wiki/10-外部模型转换实战规范.md) 做到位。

### 能力边界:AB 比 3Dmigoto 严格
| | 蒙皮 | 对 prep 的容错 |
|---|---|---|
| 3Dmigoto | `Σw·游戏帧矩阵·**逐影响 BoneCorrection**·v` | **容错**:显式把源 bind 空间映射到游戏空间 |
| AB | `Σw·游戏骨·bindpose·v`(标准 LBS) | **不容错**:几何必须已在游戏关节上,权重引用的骨必须在几何内 |

→ 同源 3Dmigoto 能动、AB 炸,**不是 AB 的 bug,是 AB 把 prep 质量要求提前了**。

### 分源类型可行度
- **QualiArts 同骨架**(IP / 学马自有服装):**生产可用**,3 样本验证,几乎零 prep。
- **MMD / 外部源 + 完整 prep**:**可行(已验证 1 例)**,成本在 prep。
- **镜像源(SCSP 这类)**:**未验证**,唯一尝试失败于 prep;需重做 prep 才能判定。

### 剩余风险(按严重度)
1. **插件依赖没上游(最大产品化风险)**:`gkms-localify-dmm` 当前整个插件改动树都只在本地；无损骨架 graft、ActorSwing 新骨、本轮 4 处修复**全都只在本地**。社区装的发布版没有这些。分发要么上游合并,要么自带 DLL。
2. **AB 不容错 → prep 是硬门槛**(见上)。
3. **装饰物理需逐件调**:三层分类 + override 已落地,复杂服装仍要看画面。
4. Unity 版本锁 `6000.0.67f1`(bundle 头写死)。
5. **新骨物理画面级已证伪一次**:dress-2219 上链建出来了、日志全绿,装饰件不摆(2026-08-04)。
   在查清之前,自建摇物链不是可交付能力,装饰件走刚性/跟裙摆。

### 已付的一次性成本(不再是风险)
模板库备齐(**1817 个文件 / ~908 body 模板,全 R32**,作者只选不建)、免 Unity 的 UnityPy 补丁链、一键导出入插件、崩溃类已根治(不内嵌合成对象,改运行时建骨)。

### 结论
**路线成立;对「同骨架 + 规范 prep 的外部源」已是生产可用状态。** 换来原生蒙皮/描边/透明/物理(蹭游戏已有摆动骨;**新骨自建摆动当前不生效**)、免逆蒙皮算子、免 Unity。代价是**把容错从运行时挪到了 prep**。要成为可推广产品,优先级:①解决插件分发 ②prep 工具化并加代码闸门 ③装饰物理 override UI。

## 6.8 prep 能否自动执行(2026-07-25 判断)

**目标**:作者一键出 mod,prep 由程序执行,而不是照文档手动做。**结论:可达,但要分三类,且第一步不是合并脚本而是加闸门。**

**① 纯确定性 → 可全自动(已是代码,只是没收口)**
镜像(网格+骨骼+法线+shape key)、身高 fit、手臂链/手指点追踪对齐(`segment_affine`)、`inherit_scale` 处理、烘网格+`armature_apply`、遮挡皮肤射线删除、图集 UV 仿射重映射、镂空件按 UV 足迹分类、t1/t4 烘焙、DDS。
**现状**:以每项目复制一份的形式存在——`chisaki/scripts/03_align.py`(339 行)、`fktn-cstm-0119-miku/scripts/02_align_full_skeleton.py`(457 行)、`madoka/scripts/01_prep_align.py`(424 行)几乎重复、只有常量不同,无共享模块。**这是纯工程整合(参数化 + 骨名映射来自 `bone_remap_presets.json`),不是研究问题。**

**② 需一次性语义输入 → 预设 + 交互兜住,做不到零输入**
哪些材质算「头」、冷门 rig 的骨名映射、露肤度决定要不要贴合目标体型。**目标是"点几下、不用懂骨"而非零输入。**

**③ 必须人眼 → 只能闸门 + 复核**
颜色、比例、装饰件物理手感。

### 真正的瓶颈:没有闸门,不是没有自动化
fuyuko 的失败性质不是"某步没自动",而是**坏数据静默通过导出**——导出侧只校验包围盒重叠([`operators.py:628`](../gakumas_mi/operators.py))。规范里写了闸门(workflow §2 步骤 6 / §0-3b),但**闸门也在文档里靠人执行**。

→ **自动化第一步 = 把闸门做成导出侧强制代码**,而不是先合并 prep 脚本。没闸门的自动化只会更快地产出错误;有闸门,即使 prep 半手动也不会再出现"改 8 版才发现绑定早坏了"。

### 闸门该用什么判据(2026-07-25 实测,两个想当然的都被证伪)
- ❌ **结构性绝对阈值不可用**。「骨到其主导顶点质心距离 ÷ 骨长 > 1.0」在健康且实机能跑的模型里很常见(madoka max 2.74、miku max 4.66/35 根超标),因为 `*_rot`/`*_H` 捻骨骨长极短却天生驱动远处几何。「主导骨是否为最近骨」同样不可用(SCSP `_1` 双链同位置互相竞争,坏绑定 top1=43% 反而高于健康的 31%)。
- ✅ **功能性判据可用,且跨模型**:[`tools/simulate_ab_skinning.py`](../tools/simulate_ab_skinning.py) —— pose 游戏骨架弯手指,按 AB 公式蒙皮,量手指区 edge-stretch,**以场景里的 `GMI_*_带权重参考`(游戏原生身体+权重)作已知正确基线**。实测:fuyuko MOD p99=2.99/max=7.12 vs 基线 1.62/4.07 → 判坏;而且它**正确否掉了两个错误修法**(两种传权 p99→6.96)。⚠相对 rest 的指标,rest 本身被改坏会假性变好,须配目视。
- ✅ **同模型前后回归**(prep 每步复量,只允许变小):dress_2219 手指 16.0mm → 50.5mm、p95 1.18 → 2.16,区分清晰。适合 prep 脚本内部,不适合导出侧(导出侧没有基线)。

**落地顺序**:
- ✅ **①已完成(2026-07-25)**:姿势模拟已通用化并接进导出侧。[`tools/simulate_ab_skinning.py`](../tools/simulate_ab_skinning.py) 现在从场景自动发现 mesh/参考体/游戏骨架(`gmi_weighted_reference` 或 `GMI_*参考*`),给三态判决 **OK / FAIL(超基线 `FAIL_RATIO`=1.5x)/ UNKNOWN(没有可测顶点——绝不当通过)**;`operators._bind_sanity_report` 在 bundle 导出时跑它,结果进导出报告 `bind_sanity` 并 `report({'WARNING'})`(坏绑定导出侧补不了,所以只警告 + 指回 prep,不静默)。脚本已 vendor 进插件包。
  **验证(带标签样本)**:dress_2219 work(实机炸手指)→ **FAIL fingers 1.85x**;madoka(实机能跑)→ **OK 0.98x**;chisaki 不传 remap → **UNKNOWN**(修掉了"没测到=通过"这个危险失效模式)。
- ❌ **②(自动对齐模块)已放弃(2026-07-25)**。原计划把三份重复对齐脚本收成插件里的自动对齐。放弃理由:①对齐本质是**建模判断**(怎么变形同时保住形状),实测两次自动化尝试都产出废品——逐顶点乘 `gameRest·sourceRest⁻¹` 把手指绕自身轴扭烂、pose 摆骨在绑定不健康时把网格越带越偏;②作者手工做(整体平移+沿指向缩放+比例编辑)结果明显更好,而且本来就是他熟悉的操作;③**有了①的闸门,手工对齐足够安全**——对没对齐有数可查(手指肉偏差 vs 参考体、p99 vs 基线),不会再出现"改到第 8 版才发现绑定早坏了"。**结论:不要为人做得更好的事写自动化,只要留一把尺子。** 对齐规范与手法见 [`../docs/wiki/10-外部模型转换实战规范.md`](../docs/wiki/10-外部模型转换实战规范.md) §2。
- ③语义输入的交互 UI(装饰件归属表单)。**优先级提高**:实测按名字猜语义不可靠——`lace` 既可能是裙摆镶边、也可能是靴口花边(fuyuko 的 `Lace_R` 在靴口 z=181~228mm),猜错就整件乱抽。所以 `follow_skirt` 这类语义规则应降级为**候选建议**,由作者在表单里确认,而不是当默认。

## 7. 前置基础设施 & 问题状态

### 基础设施
- **R32 模板库**:每个目标 body 一个 `template_mdl_chr_<id>_body.bundle`,工具作者一次性产(Unity 2A 或 `tools/build_phase3_templates.py`)。作者只选不建。
- **游戏侧插件**:需支持运行时建新骨 + 挂 ActorSwing 物理(P4)。同级仓库 `../gakumas-mod-runtime/` 的 `src/runtime/ModRuntime.cpp` 已支持，Release x64 已部署并有实机日志。
- **模板结构**:普通 R32 模板可覆盖同骨和新增装饰骨换装。UnityPy **不得插入合成 GameObject/Transform**；模板缺失的新骨槽临时指向 root，游戏侧插件再按 sidecar 创建真实骨并替换整组 `m_Bones`。

### 问题状态

原先逐条记录的 7 个阻塞问题（合成骨架认错根骨、DDS 回读、空组误拦、`bone_<hash>` 语义、
SCSP 手臂骨被猜成服装骨、源飘带被吞并、Unity 6 加载崩溃）已全部关闭并在 0.9.0 发布。
结论已并入 [`lessons-learned.md`](lessons-learned.md)，排查过程在 git 历史里。

---

## 8. 骨预设格式(建议)

一份预设 = 源骨名 → 目标骨名 的 JSON(与 `gmi_bone_remap_file` 同构),外加分类提示:

```json
{
  "source": "mmd-standard",
  "bones": { "下半身": "Hips", "上半身": "Spine", "上半身2": "Spine2",
             "首": "Neck", "頭": "Head", "左腕": "LeftArm", "左ひじ": "LeftForeArm" },
  "accessoryPrefixes": ["髪", "スカート", "ネクタイ", "胸"],
  "twistToParent": ["左腕捩", "左手捩"]
}
```

内置至少:`mmd-standard`、`mixamo`、`rigify`。作者选来源类型即套用;不匹配的骨提示手工补。

---

## 9. 执行顺序（已完成）

原先的 Phase 1–6 列表与两道发布闸门都已走完，0.9.0 已按它发布，故删除。
当前进度与后续计划只有一个出处：
[`current-status-and-roadmap.md`](current-status-and-roadmap.md)。

---

## 10. 验收诊断清单(每次都对照)

Blender 导出侧:
- 无 `Unmapped weighted bones`;抽样顶点权重值 == 源。
- 目标身份(顶点/索引数)匹配正确 body。
- **没有「承重关节没有拿到任何权重」报错**（闸门拦下就是源骨名没映射上，去骨骼映射表点选，
  别去改兜底骨）。
- **`bundle-src/body_slot0_t4.png` 是 MB 级**；若约 78KB 且与 `t1` 字节相同 = 纯黑图（曾有
  colorspace 赋值顺序 bug，见附录 A）。

导出后离线复查（比进游戏快，四个判据；`m_BindPose` 是列主序、平移在 M30..M32，骨序用
`*_bones.json.txt` 的顺序）:
- **按 x 切片查每段几何的驱动骨**，与原版 `Reference/Geo_Body.json` 并排。手臂最灵敏：健康=
  `ForeArm` 管到 |x|0.48、`Hand` 才接手；坏=`Hand` 从 0.36 就占 84%（肘部撕裂）。
- **骨→其主导顶点质心的距离**，拿原版当已知正确基线。健康样本中位 16.6mm vs 原版 39.2mm；
  坏绑定样本 50mm。⚠用的骨少时 p90 天然偏大，不是缺陷。
- 每顶点影响数 1–4、权重和精确 1.0000。
- `mmd_edge_scale`/`mmd_vertex_order` 不在骨列表里（它们不是骨，已自动忽略）。

geojson/bundle 侧:
- mesh verts/submesh/bindpose 数一致；身体骨已映射；未映射名称必须出现在合法 `newBones` 中，且父级和物理策略完整。
- SMR `m_RootBone` → 目标根骨(body=Hips)。
- 核包工具额外报告 `swing` 骨总数、左右数量、父索引和物理参数完整性；fuyuko 当前为 `26 / 13 / 13`，结构层无左右不对称。

游戏 `mod-plugin.log`:
- `matchedBones=… droppedInfluences=0 fallbackVertices=0 meshApplied=1`。
- 新骨:`createdBones=N`、`ChainInfo.layers>1`、`Applied lossless IP skeleton graft`。已实机达成（`atbm-0140` 建出 5 组 7/8/9/10/11 层链），继续按此对照即可。
- 贴图:`Applied material texture _BaseMap/_DefMap/_ShadeMap`。
- 几何炸但日志干净 → bindpose/坐标空间;整体暗 → t1 色彩空间。

---

## 11. 接手入口

- 游戏侧运行时仓库：同级的 `../gakumas-mod-runtime/`（产物 `xinput1_3.dll`）
- **主回归（最常用）**：`python -m pytest tests/ -q`（当前 30 passed）
- Blender 导出回归：`blender --background --factory-startup --python-exit-code 1 --python tests/blender_smoke.py`
- Blender UI 回归：`blender --background --factory-startup --python-exit-code 1 --python tests/blender_ui_smoke.py`
- 运行时 Release 编译（在 `../gakumas-mod-runtime/`）：`.\generate.bat` 后
  `msbuild build\gakumas_mod_runtime.sln /p:Configuration=Release /p:Platform=x64`
- 插件运行日志：游戏目录下 `gakumas-mod/mod-plugin.log`
- **崩溃二分已完成、结论见「进度」段(不内嵌合成对象)**，该任务作废，别再重做。
- 离线量化闸门：`blender --background <blend> --python tools/simulate_ab_skinning.py -- <remap.json>`（pose 游戏骨架弯手指，量手指区 edge-stretch，参考体为已知正确基线）。**改法先离线量再让作者导出。**⚠该指标相对 rest，若 rest 本身被改坏它会假性变好，必须同时看几何/目视。
- prep 侧闸门与教训见 [`../docs/wiki/10-外部模型转换实战规范.md`](../docs/wiki/10-外部模型转换实战规范.md) §0-3b / §2-6 / §5（⭐v3 条目）。
- CI 里还会跑 5 个纯 core 脚本（`tests/material_bake_smoke.py` 等，见 `.github/workflows/ci.yml`）。
  移除 3DMigoto 后 `mod_ini_contract.py` / `weight_transfer_smart.py` 两组已删。
- 模板工具：新目标模板 `tools/repair_template_bone_names.py --mode index`，已导出成品用 `--mode hash`。插件包用 `dist/` 下最新 `gakumas_mi-0.9.3-code-*.zip`。
- ⚠**装完新插件必须彻底重启 Blender**（内存里的旧模块不会自动重载；另注意 `gmi_bone_remap_file` 的显式映射优先于自动分类）。

主仓库基础 checkpoint 已提交并推送；当前冻结期改动与插件 runtime 改动会在本轮单独提交，接手时不要
`reset --hard` 或覆盖已有变更。插件仓库的远端推送仍受 HTTPS 认证阻塞。

## 12. 一句话给接手人

**接手顺序固定为：先落盘 → 翻转 → 版本协议 → README → 核包工具 → RC → B→A → 分发。**
前五项已完成并提交；RC1 的新版 ZIP 安装、真 UI 映射、闸门拦截/放行、核包、新 DLL 和两套
Mod 实机测试也已完成并归档。**当前唯一外部动作是由作者手动推送插件仓库现有提交，
随后完成 Gate A 合并和 Gate B 分发；本助手不执行该推送。**
旧的无协议 Mod 被新版 DLL 拒绝属于版本校验的预期兼容性行为，不是当前 RC1 的重导任务。
装饰默认已从"位置蹭"翻成"跟源父骨"，另有 `胸`→`Bust*_S` 规则；物理手感完美仍不是首发条件。
对齐/删头/图集明确不在插件范围内，是作者基本功。

---
