# 通用 AB 换装自动化开发计划

> 目标读者:接手把 GakumasMI 的 AB 导出做成「通用、少懂骨」流程的开发者。
> 本文档 = 需求 + 已验证原型 + 架构 + 分阶段落地 + 边界 + 问题记录 + 验收清单。
> 核心原型证据来自 2026-07-24 起对 fuyuko(SCSP)→hmsz-cstm-0059 的多轮实机调试。

关联:[3dmigoto-vs-ab-route.md](3dmigoto-vs-ab-route.md)、[bundle-route-roadmap.md](bundle-route-roadmap.md)、
[../ab-route-handoff/docs/lossless-full-skeleton-plan.md](../ab-route-handoff/docs/lossless-full-skeleton-plan.md)、
[../ab-route-handoff/docs/runtime-mechanism.md](../ab-route-handoff/docs/runtime-mechanism.md)。

---

## 先读这个：现在是什么状态（2026-07-27）

**AB 核心链路已实机贯通，0.9.0 候选包已生成。** 加载、蒙皮、贴图、运行时建骨、摇物链构建、
描边和透明都有实机样本，装饰物理的最终视觉效果仍待逐件验收，见 §6.7。本分支已删除
3DMigoto **反向蒙皮导出路线**，插件只保留 AB 导出；3DMigoto 抓帧依赖仍保留。

> ⚠ **看状态先看「验证等级」那一列。** 本文档此前把"代码写完 + 测试通过"和"实机验证过"混着
> 写成 ✅，这是错的。三个等级：
>
> - **A 实证** = 有人在真实 Blender UI 或游戏里跑过并看到结果；
> - **B 离线** = 过了 `pytest` / Blender headless / 真模型 geojson 数值分析，但**没进游戏、
>   也没有人在真 Blender UI 里点过**；
> - **C 纸面** = 按公开规范写的数据，连对应的模型文件都没拿到过。
>
> B 和 C 都可能有"只在我构造的场景下成立"的问题。

| 环节 | 状态 | 验证等级 | 说明 |
|---|---|---|---|
| 身体骨架 / 权重 / 材质合并 | ✅ 核心链路 | **A 实机** | 身体承重骨映射到游戏原骨，作者权重原样保留只换骨索引；服装装饰骨可由 sidecar 驱动运行时新建 |
| 身体骨对照（MMD 两种写法） | ✅ | **A 实机** | 2026-07-26 星仪·大国主 → `fktn-othr-0002`：`.L/.R` 折叠 + D 骨 + `手捩→ForeArm` 进游戏确认（手臂跟编舞、肘部不撕裂）|
| 身体骨对照（SCSP / QualiArts） | ✅ | **A 实机** | fuyuko → `hmsz-cstm-0059` 重导后手部跟随大动作正常；本轮两套 Mod 已完成新版链路实机测试 |
| 身体骨对照（另六家预设） | ✅ | **C 纸面** | VRM / Biped / ARP / 英文 Humanoid 四家按各自公开命名规范写表，**没有对应模型试过**；Mixamo / Rigify 沿用旧表未回归实机 |
| 逐张表打分选表 | ✅ | **B 离线** | 替掉旧的探针嗅探；只有 `pytest` 断言，没有真模型走过新选表逻辑 |
| 骨骼映射表（UI 表单） | ✅ 真 UI 已走通 | **A 实证** | 0.9.0 ZIP 全新安装后，真面板完成扫描、修改并导出；配置档保存/加载已执行，证据归档待补 |
| 出门闸门（14 承重关节） | ✅ 真作者会话已拦截并放行 | **A 实证** | 故意把 `Spine` 改成无权重/错误映射时被拦，恢复后放行；提示点名 `Spine` |
| 装饰骨策略列 | ✅ 已翻转并完成两套 Mod 实机 | **A 实证** | 默认跟源父骨；胸/Bust 走 `Bust*_S`；两套当前 Mod 已进游戏验证加载与动作，物理细节证据需归档 |
| t1/t4 不再导成纯黑 | ✅ | **A 实机** | 2026-07-26 重导后 t4 从 78KB(纯黑) 变 3.4MB，游戏内颜色分层正确 |
| 肤色校正（t4.A mask 取值 + UV 足迹校色） | ✅ 已随两套 Mod 实机确认 | **A 实证** | 数值对到 G/B 差 0.5% 以内；两套当前 Mod 已进游戏确认无明显材质异常，截图/日志待归档 |
| 移除 3DMigoto 导出路线 / UI 收三步 | ✅ 真 UI→导出→实机已走通 | **A 实证** | 新 ZIP 已安装并重启 Blender；真面板走过映射、闸门和 AB 导出；旧入口反向断言仍由测试守住 |
| 打包 | ✅ 免 Unity | **A 实机** | R32 模板 + UnityPy 补丁，多个 mod 进游戏验证过 |
| 对齐 / 删头 / 图集 | ❌ 不做 | — | **作者基本功，明确排除出插件范围**；这是端到端一键化真正的拦路虎 |
| 插件分发 | ❌ 阻塞 | — | 迁移已在本地分支提交；远端推送因 HTTPS 认证失败，仍不可供别人安装（§6.7 风险 1） |

**RC1 真实闭环已经执行，不需要因为旧 Mod 的历史协议问题重做当前闭环。** 当前需要做的是把
真实 Blender 操作、闸门结果、两套 Mod 的游戏画面、核包输出、DLL/ZIP/bundle hash 和对应日志
整理成一份可复核证据；旧资产的协议迁移另记为兼容性工作，不是 RC1 的下一步。

本轮已完成发布冻结中的离线实现（主仓库 commit `7937341`，插件 runtime commit `c130c8b`）：
默认装饰策略翻转；sidecar/manifest 写入
`runtimeProtocol=1` 与确定性 `buildId`；插件 runtime 对缺失/不匹配协议明确报错并打印 buildId；
README 已写明通用性边界；`tools/verify_ab_package.py` 已生成且 Python 测试 26/26 通过。
插件 `Release|x64` 已用 Visual Studio 编译通过（0 警告/0 错误）。RC1 真 UI/实机验证已经补上，
剩余是证据归档、Gate A 合并和 Gate B 分发前置，不再把已完成的 UI/实机项目列为未验证。

### RC1 真实闭环当前结果（2026-07-27）

| 检查项 | 当前结果 | 证据 |
|---|---|---|
| 新版插件安装 | 已完成 | `dist/gakumas_mi-0.9.0-code-20260727-151540.zip` 全新安装并彻底重启 Blender |
| 真面板骨骼映射 | 已完成 | 扫描、修改、保存/加载、导出均已执行；配置档往返截图/日志待归档 |
| 承重骨闸门 | 已完成 | 故意破坏 `Spine` 映射时拦截；修正后重新导出放行 |
| 核包工具 | 已完成 | `author.hski.my-mod`：`PASS`, `buildId=b01fdd1629112716`, `files=6`；`fuyuko-super`：`PASS`, `buildId=ea2bbcfb74aca8e6`, `files=9` |
| 新 DLL | 已完成 | `runtimeProtocol=1`、buildId 校验生效；当前 DLL SHA-256=`A10EC34756618A4B7DD50AFB591B06412C7A8092478CDD763D8BA621323DD1EA` |
| 游戏实机 | 已完成首轮 | 两套当前 Mod 已测试，游戏内未见本轮链路问题；身体/手部/裙摆/飘带/t0 的截图与对应日志待集中归档 |
| RC 产物 hash | 部分完成 | ZIP SHA-256=`953917C69A79AB93F526A6D2AAC354C8F6F45256217713AB53CC5B599D2E1037`；当前 fuyuko bundle SHA-256=`35E5F9DD9A03019FFB00500E48ACB3046D9DFDC6EAAF420428170A57A72D85A1` |

**已知但不阻塞 RC1 的旧资产问题**：旧的 fuyuko/atbm 包没有 `runtimeProtocol=1` sidecar 时，
新版 DLL 会按设计拒绝应用并在 `mod-plugin.log` 报 exporter/runtime mismatch；重新导出后的
fuyuko 已以 `meshApplied=1` 成功加载。这是版本协议生效的兼容性结果，不是要求当前开发线继续
修旧包，也不应拿旧包失败日志覆盖最新 RC1 结论。

**下一步 = 完成 RC1 证据归档，再进入 Gate A（2026-07-27）**

技术风险基本还完了，**剩下全是交付风险，而最急的一条是落盘**。

**当前能力已落盘到可恢复 checkpoint。** 主仓库已提交并推送 `32db982`；插件仓库迁移已在
本地分支 `codex/checkpoint-modruntime-20260727` 提交 `aba41a4`，但远端 HTTPS 认证失败，
所以“别人能安装”仍未完成。随后冻结期改动（策略翻转、版本协议/buildId、README、核包工具）
正在本轮单独提交。

**插件仓库更重，别照 `ModRuntime.cpp` 一个文件去想**：`gkms-localify-dmm` 共 **340 项变化
（330 个删除、6 个修改、4 个 untracked 目录，其中包括整个 `src/GakumasModPlugin/`）**。
删除里有 `deps/rapidjson/*`、`conanfile.txt` 这类，**大概率是目录迁移而不是真删**。
已判定为旧目录迁移到 `src/GakumasModPlugin/` 的大批删除/新增，先以可恢复 checkpoint 落盘；
正式上游提交仍需认证恢复后再拆分/复核。

冻结期允许的改动：装饰策略翻转、**runtime 版本协议 + buildId**、README 边界声明、
**最小离线核包工具**、闭环里查出的验收修复。**不新增功能，不产生新的 B 级项。**

1. **理清两个仓库边界，拆分并提交到可恢复分支**（先落盘，暂不分发；不占作者时间，可并行）。
2. **装饰骨默认策略翻转**：位置匹配退出默认路径，默认改成跟源父骨，加 `胸`→`Bust*_S`
   名字规则（实测旧逻辑 1/3 → 预期 3/3）。代码已完成，需在 RC 前用真实服装验收，因为它改变导出结果。
3. **最小 runtime 版本协议 + `buildId`**。版本校验是硬依赖的安全措施，**必须在 RC1 之前完成，
   否则 RC1 还不是最终协议**；`buildId` 由导出器写进 bundle/manifest、runtime 在日志里原样
   打印——只存文件 hash 无法证明某份日志对应哪个 bundle。
4. **README 写死「通用性」边界**（§12 那句）。对内止血：定义不写死，"再加一张骨骼预设表"
   就永远看着像在推进。
5. **最小离线核包工具**（见下）。
6. **冻结，从确切 commit 打 RC1。**（当前已具备候选产物，待证据包命名/归档。）
7. **走一次真实 UI → 导出 → 实机验收**，一次清掉全部发布关键 B 项（当前已执行，待集中留档）。
8. **任何会改变 ZIP / DLL / bundle / sidecar 的修复，一律出 RC2 并重跑全流程**，
   不许在 RC 上原地打补丁——否则发出去的包和"验收通过"的包不是同一个。
   README 错字、验收记录补充不属此列，不必重跑。
9. **证据包通过后，插件提交推到可访问仓库**，再合并 main、**ZIP 与 DLL 一起分发**。
10. 恢复其余开发（装饰物理逐件目视、C 级预设回归等，都不是瓶颈）。

> **最小离线核包工具**：不是产品功能，是验收工具，买的是唯一稀缺资源——作者的人肉验收带宽。
> 读 bundle 直接报：t4 是否 MB 级、`m_Colors` nibble 分布（掉通道计数）、承重关节权重、
> `buildId`、以及**骨名归属核对**。
> ⚠ 判据要写准：`boneWeights` 里只有索引，而**合法的新装饰骨本来就会保留源骨名**，
> 所以不能笼统查"源骨名泄漏"；sidecar 还包含目标模板中未被当前服装使用的 `*_H`/`*_S`/辅助骨。
> 正确判据是：**源骨名若实际出现在 sidecar 中，必须是目标映射结果或合法 `newBone`；新骨有合法父级
> 与物理策略**。§10 那张清单现在全靠人对照，脚本化后闭环里人只需要看画面。

> **"插件分发"与"B 级堆积"是两个不同的阻塞，别互相否定**：前者是**对外可用性**阻塞
> （不解决则能力对外为零），后者是**发布质量**阻塞。提交边界必须先整理，但真正分发
> 必须在 B 清理之后。B→A 的通道目前只有作者一人手动验收，这是当前最大的产能瓶颈——
> 代码还在往前跑并持续生产新的 B 级项。

**已证伪，别再走（每条都实测过，细节见 §6.8 与附录 A）**

- ❌ 用源骨架 bindpose 覆盖游戏 bindpose（治"一动就变形"）→ **静止直接崩**，顶点已在游戏空间。
- ❌ 传递权重救坏绑定（反距离/重心两种实现）→ 更糟，p99 2.99→6.96。
- ❌ 逐顶点乘 `gameRest·sourceRest⁻¹` retarget 几何 → 手指扭烂。
- ❌ 自动对齐 → 两次都产废品，已放弃；对齐交作者、代码只留尺子（§6.8）。
- ❌ 向 bundle 内嵌合成 GameObject/Transform → Unity 6 加载崩，改运行时建骨（附录 A）。

---

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
> | 身体骨对照 | 八家预设自动 + 表单点选兜底可人工闭环；MMD 与 SCSP 有 A 样本，另六家仍是 B/C | 入口已完成，泛化待验收 |
> | 装饰骨物理归属 | 默认源父骨 + 胸/Bust 名称规则；异常件靠 override | **命名和源层级仍不能覆盖所有怪异绑定，保留人工覆盖** |
> | 对齐 / 删头 / 图集 | 零支持，每 mod 写脚本 | **作者基本功，插件不代做**（明确排除出范围） |
>
> 也就是说：身体骨对照已不再是主要开发瓶颈；装饰骨物理仍需作者确认。端到端一键化的拦路虎是
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
- **验收**:导出无 `Unmapped weighted bones`;权重值与源逐点相等(抽样);**14 个承重关节都拿到
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
| fuyuko-super (dress_2219) | SCSP 镜像源 | ⚠ 部分：**原始 `dress_2219` 手指动就炸已确认是 prep 坏绑定**；此后 fuyuko 已能加载、graft，手部动作恢复正常；**装饰骨归属与最终物理观感仍是 B**。→ 它证明"手指失败不是 AB 架构问题"，但**不能算完整通过，也不能简化成"唯一失败且全因 prep"** |

**关键**:`atbm-0140` 证明**外部源(MMD)→ AB 能成**,前提是 prep 按 `ai-model-workspace/external-model-conversion-workflow.md` 做到位。

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
5. 新骨物理"持续自摆"仅日志通过,画面级仍需目视。

### 已付的一次性成本(不再是风险)
模板库备齐(**1817 个文件 / ~908 body 模板,全 R32**,作者只选不建)、免 Unity 的 UnityPy 补丁链、一键导出入插件、崩溃类已根治(不内嵌合成对象,改运行时建骨)。

### 结论
**路线成立;对「同骨架 + 规范 prep 的外部源」已是生产可用状态。** 换来原生蒙皮/描边/透明/物理(含新骨摆动)、免逆蒙皮算子、免 Unity。代价是**把容错从运行时挪到了 prep**。要成为可推广产品,优先级:①解决插件分发 ②prep 工具化并加代码闸门 ③装饰物理 override UI。

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
- ❌ **②(自动对齐模块)已放弃(2026-07-25)**。原计划把三份重复对齐脚本收成插件里的自动对齐。放弃理由:①对齐本质是**建模判断**(怎么变形同时保住形状),实测两次自动化尝试都产出废品——逐顶点乘 `gameRest·sourceRest⁻¹` 把手指绕自身轴扭烂、pose 摆骨在绑定不健康时把网格越带越偏;②作者手工做(整体平移+沿指向缩放+比例编辑)结果明显更好,而且本来就是他熟悉的操作;③**有了①的闸门,手工对齐足够安全**——对没对齐有数可查(手指肉偏差 vs 参考体、p99 vs 基线),不会再出现"改到第 8 版才发现绑定早坏了"。**结论:不要为人做得更好的事写自动化,只要留一把尺子。** 对齐规范与手法留在 `ai-model-workspace/external-model-conversion-workflow.md` §2。
- ③语义输入的交互 UI(装饰件归属表单)。**优先级提高**:实测按名字猜语义不可靠——`lace` 既可能是裙摆镶边、也可能是靴口花边(fuyuko 的 `Lace_R` 在靴口 z=181~228mm),猜错就整件乱抽。所以 `follow_skirt` 这类语义规则应降级为**候选建议**,由作者在表单里确认,而不是当默认。

## 7. 前置基础设施 & 问题状态

### 基础设施
- **R32 模板库**:每个目标 body 一个 `template_mdl_chr_<id>_body.bundle`,工具作者一次性产(Unity 2A 或 `tools/build_phase3_templates.py`)。作者只选不建。
- **游戏侧插件**:需支持运行时建新骨 + 挂 ActorSwing 物理(P4)。当前 `D:\GIT\git.chinosk6.cn\gkms-localify-dmm` 的 `ModRuntime.cpp` 已支持，Release x64 已本地部署并有实机日志；但整个插件改动仍未整理成可上游/分发的提交。
- **模板结构**:普通 R32 模板可覆盖同骨和新增装饰骨换装。UnityPy **不得插入合成 GameObject/Transform**；模板缺失的新骨槽临时指向 root，游戏侧插件再按 sidecar 创建真实骨并替换整组 `m_Bones`。

### 问题状态（2026-07-27）
1. **`_bundle_root_bone` 合成骨架认错根骨** ✅：合成骨架跳过不可信的 `weightedIndex==0`，回退到 `Hips`；测试覆盖 `Finger(weightedIndex=0) + Hips` 场景。
2. **`_export_bundle_png` 读不了插件自写的烘焙 DDS** ✅：`core.read_rgba8_dds` 读取 DX10 RGBA8 后由导出器写入 Blender PNG，覆盖 148 字节头 + top-down raw RGBA 路径。
3. **`Unmapped weighted bones` 校验拦空组** ✅：只把真实带正权重的顶点组加入 unresolved 校验，零权重空组不再阻塞导出。
4. **mesh-only skeleton 的 `bone_<hash>` 退化 ✅**：资源目录只有 `Geo_Body.json` 时，未命中的服装专属 hash 曾退回 `bone_<hash>`，44 根错误骨全部挂到 `Hips`，导致上半身/裙摆/蝴蝶结扭曲。现在模板修复工具按目标 profile 补真实名称，模板构建和 bundle patch 都拒绝未解析占位名。这里修的是**错误占位骨归零**；合法装饰骨仍会让运行时 `createdBones>0`。
5. **SCSP 手臂主体骨被猜到服装骨 ✅**：`*_rot/Elbow/Clavicle` 等源骨不能交给装饰骨最近点匹配；SCSP/IP/QualiArts 预设现覆盖躯干、四肢、手指和脚趾，且装饰映射不得覆盖身体 preset。重导后手部实机动作已正常。
6. **源飘带被目标摆动骨吞并 ⚠️**：导出和运行时建链已修，明确的源悬挂链会保留父子关系并生成 `newBones/extraSwingBones`。最新实机日志为 `Chain tips attached: 10/10`、`createdBones=26`、`swingPrepared=36`，并成功建立 3/4/5 层链；装饰物理归属和最终摆动观感仍是 B 级待验收。
7. **Unity 6 加载新增骨 bundle 崩溃 ✅**：AABB 数量不一致曾被修复，但不是最终根因。真正根因是 UnityPy 向 bundle 合成 GameObject/Transform；现已删除合成路径，缺失骨槽回退 root，由运行时按 sidecar 建骨。fuyuko 已能加载、graft、替换网格和贴图。

当前 Python 全套测试为 `24 passed`；0.9.0 插件代码已安装且文件与工作树一致，但安装后的真 Blender 面板操作和最新 UI→导出→实机闭环尚未完成。`atbm-0140` 与 fuyuko 日志已通过结构、权重和多层物理链构建检查，持续摆动的视觉效果仍需人工确认。两个工作树均有大量未提交变更，尤其插件仓库不是只有 `ModRuntime.cpp`：当前还包含目录迁移及大量删除，接手时必须先整理提交边界。

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

## 9. 建议执行顺序(Phase)

1. **Phase 1 — 收口现有 bug**(§7 三项)。让 scsp/偶像荣耀(同引擎、对照自动)全自动跑通,是最小可用。
2. **Phase 2 — 对照表引擎 + 预设**(§5 P1-P2 + §8)。上 MMD/Mixamo/Rigify 预设,覆盖普适身体。
3. **Phase 3 — 装饰物理自动**(§5 P3 蹭)。位置就近继承目标物理,内置对称件/悬挂件规则。
4. **Phase 4 — 无损新骨 + 跨引擎物理**(§5 P4)。sidecar/runtime 与实机建链已完成，最终摆动观感仍待逐件验收。
5. **Phase 5 — UI 收敛** ✅ 已完成(2026-07-27)。移除 3DMigoto 路线后面板收成**三步**
   「① 准备配置档 → ② 准备材质 → ③ 导出 AB bundle」——比原计划的 5 步更短，因为"导入 mod 模型"
   和"对齐"都在插件之外（作者基本功）。

6. **Phase 6 — 闸门 + 交互**(§6.8)。①导出侧绑定闸门 ✅ 已完成 ②自动对齐 ❌ 已放弃(理由见 §6.8)
   ③装饰件归属表单 ✅ 已完成(2026-07-27，见「先读这个」)——骨骼映射表的第二列即是，
   同时把身体骨也纳进来，所以 P0/P1 的"未知 rig 引导手工对照"从"引导"变成了正式入口。

当前接手顺序（2026-07-27 修订）：**Phase 1–6 的代码实现已完成，A/B/C 验收状态以开头表格为准**。下一步不在这份 Phase 列表里，
见「先读这个」的下一步三条——第一条是**插件上游/分发**（§6.7 风险 1，整个插件改动尚未
整理成可上游提交，别人装不上就等于没有），第二条是**装饰骨默认策略翻转**（唯一还没做的启发式改动，
属行为变更需先确认）。

每 Phase 独立可用、可实机验收,不必等全部完成。

---

## 9.5 发布冻结：两道闸门(2026-07-27)

**两道闸门，别混成一道。** Gate A 管"能不能接进 main"，Gate B 管"能不能给别人用"。

### Gate A — 合并进 main
理由：这次合并会删掉 3DMigoto 导出路线。**Git 层面当然可恢复，这里说的是发布层面的
破坏性兼容变更**——合并后 main 就是别人拿到的东西，所以要求完整验收。

- [x] 两个仓库提交边界已落盘，工作树当前干净；插件仓库仍未能推送到远端（HTTPS 认证阻塞）
- [x] `pytest` + Blender headless 回归已通过；CI/远端可见性仍待插件仓库认证恢复
- [x] 装饰策略翻转已落地；runtime 版本协议 + `buildId` 已生效；README 边界已写
- [x] **RC 已完成一次真实 UI → 导出 → 实机闭环**，发布关键 B 项已完成实测转 A；证据尚待集中归档
- [x] 开头状态表已按最新实测更新；剩余 B 项均不是首发阻塞
- [ ] **插件提交已推到可访问仓库**（合并 main 与分发同批进行，见「下一步」第 9 条）

### Gate B — 对外分发
- [ ] Gate A 全过（当前卡在插件仓库远端推送与证据归档）
- [ ] **游戏侧插件已上游合并，或自带 DLL 一并分发**（bundle 对改版 ModRuntime 是硬依赖，
      只发 Blender 插件等于没发）
- [x] 导出器 ↔ runtime **版本校验实机确认**：当前协议包成功加载；旧 sidecar 缺协议时明确拒绝并报 exporter/runtime mismatch
      （协议本身在 RC1 之前就要完成，见「下一步」第 3 条）
- [x] 两类源各一个走完新流程的 A 样本：**QualiArts 同骨架** + **MMD 外部源**
- [ ] ZIP / DLL / bundle 的 hash **与 `buildId`** 及对应日志集中留档（hash 已取得）

### RC 闭环必须一次清掉的 B 项（照单执行）
1. [x] 从 **ZIP 全新安装**插件并**彻底重启 Blender**（不是覆盖文件——安装路径是拷贝不是软链）
2. [x] 真面板**扫描、修改、保存、加载**骨骼映射表（操作已完成，证据待归档）
3. [x] **故意制造缺失承重骨**，确认闸门拦下并点名；修正后确认放行
4. [x] 用**翻转后的装饰策略**导出
5. [x] 游戏内确认：加载、身体动作、手部、裙摆/飘带物理（两套当前 Mod 已测试）
6. [x] 确认**校色后的 t0**（两套当前 Mod 已测试）
7. [ ] 保存 **ZIP / DLL / bundle 的 hash、`buildId` 与对应日志**，避免以后不知道测的是哪个包（hash 已取得，尚未集中归档）

### 明确不作为发布条件
- 装饰物理"手感"完美 —— 逐件目视永远做不完，属 Gate B 之后
- 六家 C 级预设（VRM/Biped/ARP/Rigify 等）—— 有映射表兜底就够，不卡发布
- 材质/物理默认参数继续调优 —— 核包脚本只能量化资源结构和参数契约；物理手感仍需人工，且不作为首个发布阻塞

---

### 9.6 B→A 清单与排序（发布冻结期间）

以下列出原 B 级项及其当前状态；排序按“对首个可交付版本的阻塞程度”排列，难度和可实现性是
在现有代码、现有 Blender/游戏环境下的估计。A 级必须有真实 Blender 或游戏证据，离线测试不能替代。

| 排序 | 项目 | 当前状态 | 转 A 的最小证据 | 优先级 | 难度 | 可实现性 | 依赖 / 备注 |
|---:|---|---|---|---|---|---|---|
| 1 | 真 Blender 面板的骨骼映射表 | **A 实证；证据待归档** | 从 RC ZIP 全新安装；扫描、修改、保存、加载；用表单产出一个进游戏的 mod | P0 | 中 | 高 | 本轮已执行，与整条 UI→导出→实机闭环合并验收 |
| 2 | 14 承重关节闸门 | **A 实证** | 真作者会话中故意缺映射时被拦，补齐后放行，并确认提示准确 | P0 | 低 | 高 | 本轮已故意破坏 `Spine` 并恢复放行 |
| 3 | 装饰策略与物理归属 | **A 实证；细节待归档** | 先完成“跟源父骨”默认策略翻转，再用真实服装确认飘带/蝴蝶结/裙摆不乱挂 | P0 | 中 | 中 | 两套当前 Mod 已进游戏；不要求手感完美 |
| 4 | 新骨链的最低限度实机行为 | **A 实证；细节待归档** | 游戏中确认加载不崩、链条被注册、左右件有基本摆动；保留“手感未调完” | P0 | 中 | 中 | 当前日志有 `createdBones`/`swingPrepared`；画面证据仍需集中整理 |
| 5 | 校色后的 t0 | **A 实证；证据待归档** | 用 RC 导出并进游戏确认肤色，不只看离线 G/B 数值 | P1 | 低 | 高 | 两套当前 Mod 已测试 |
| 6 | 逐张表打分选表 | **B 离线，非首发阻塞** | 用至少一个真实模型跑完整选表逻辑，并保存命中/误选记录 | P1 | 中 | 中 | 表外模型仍有 UI 兜底；发布后再补真实模型记录 |
| 7 | 移除 3DMigoto 后的三步 UI | **A 实证** | 新包安装、重启 Blender，完整走“配置档→材质→AB 导出”，确认没有旧入口和旧路径依赖 | P1 | 低 | 高 | 本轮已作为 RC 外壳走通，不另起长期开发线 |

**不属于 B→A 的项目**：六家未实机预设是 C 级；插件提交/版本协议/`buildId` 是 Gate A/B 的交付前置；
对齐、删头、图集是作者 prep 范围；装饰物理“手感完美”是持续调优，不是首个版本条件。

**冻结期执行原则**：先翻转策略和完成版本协议，再从确切 commit 打 RC；闭环中任何改变 ZIP、DLL、
bundle 或 sidecar 的修复都必须生成新 RC 并重跑，不在已验收 RC 上打补丁。

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

游戏 `mod-plugin.log`:
- `matchedBones=… droppedInfluences=0 fallbackVertices=0 meshApplied=1`。
- 新骨:`createdBones=N`、`ChainInfo.layers>1`、`Applied lossless IP skeleton graft`。已实机达成（`atbm-0140` 建出 5 组 7/8/9/10/11 层链），继续按此对照即可。
- 贴图:`Applied material texture _BaseMap/_DefMap/_ShadeMap`。
- 几何炸但日志干净 → bindpose/坐标空间;整体暗 → t1 色彩空间。

---

## 11. 接手入口

- GakumasMI 仓库：`D:\GIT\gakumas-modding`
- 游戏侧插件仓库：`D:\GIT\git.chinosk6.cn\gkms-localify-dmm`
- **主回归（最常用）**：`python -m pytest tests/ -q`（当前 24 passed）
- Blender 导出回归：`blender --background --factory-startup --python-exit-code 1 --python tests/blender_smoke.py`
- Blender UI 回归：`blender --background --factory-startup --python-exit-code 1 --python tests/blender_ui_smoke.py`
- 插件 Release 编译：`MSBuild build\\gakumas_mod_plugin.sln /p:Configuration=Release /p:Platform=x64`
- 插件运行日志：游戏目录下 `gakumas-local/mod-plugin.log`
- **崩溃二分已完成、结论见「进度」段(不内嵌合成对象)**，该任务作废，别再重做。
- 离线量化闸门：`blender --background <blend> --python tools/simulate_ab_skinning.py -- <remap.json>`（pose 游戏骨架弯手指，量手指区 edge-stretch，参考体为已知正确基线）。**改法先离线量再让作者导出。**⚠该指标相对 rest，若 rest 本身被改坏它会假性变好，必须同时看几何/目视。
- prep 侧闸门与教训见 `ai-model-workspace/external-model-conversion-workflow.md` §0-3b / §2-6 / §5（⭐v3 条目）。
- CI 里还会跑 5 个纯 core 脚本（`tests/material_bake_smoke.py` 等，见 `.github/workflows/ci.yml`）。
  移除 3DMigoto 后 `mod_ini_contract.py` / `weight_transfer_smart.py` 两组已删。
- 模板工具：新目标模板 `tools/repair_template_bone_names.py --mode index`，已导出成品用 `--mode hash`。插件包用 `dist/` 下最新 `gakumas_mi-0.9.0-code-*.zip`。
- ⚠**装完新插件必须彻底重启 Blender**（内存里的旧模块不会自动重载；另注意 `gmi_bone_remap_file` 的显式映射优先于自动分类）。

主仓库基础 checkpoint 已提交并推送；当前冻结期改动与插件 runtime 改动会在本轮单独提交，接手时不要
`reset --hard` 或覆盖已有变更。插件仓库的远端推送仍受 HTTPS 认证阻塞。

## 12. 一句话给接手人

**接手顺序固定为：先落盘 → 翻转 → 版本协议 → README → 核包工具 → RC → B→A → 分发。**
前五项已完成并提交；RC1 的新版 ZIP 安装、真 UI 映射、闸门拦截/放行、核包、新 DLL 和两套
Mod 实机测试也已完成。**当前唯一下一步是把 hash、buildId、真 UI 操作和游戏日志集中归档，
据此关闭 RC1；随后处理插件仓库远端推送、Gate A 合并和 Gate B 分发。**
旧的无协议 Mod 被新版 DLL 拒绝属于版本校验的预期兼容性行为，不是当前 RC1 的重导任务。
装饰默认已从"位置蹭"翻成"跟源父骨"，另有 `胸`→`Bust*_S` 规则；物理手感完美仍不是首发条件。
对齐/删头/图集明确不在插件范围内，是作者基本功。

---

## 附录 A. 进度时间线（证据留档，日常不必读）

上面各节写的是**结论**；这里是得出结论的过程，含实机日志、崩溃二分、被证伪的尝试。
排查同类问题时再翻。

<details><summary><b>2026-07-27 · MMD→AB 实战（星仪·大国主 → fktn-othr-0002）+ 移除 3DMigoto 路线</b></summary>

**这一轮的样本：MMD（星仪·大国主 PMX）→ `fktn-othr-0002`，实机跑通。** 它暴露的是 P0/P1
（源 rig 识别 + 对照表）此前有多不可靠，以及"两条路线并存"本身就是个坑。

- **P0 选表机制换掉**：`auto` 原本靠几个探针骨名嗅探单一家族，探针没命中就整张表空转。改成
  **逐张预设表试算命中数、取最高**（嗅探只用于打平手）。副作用是以后支持一种新命名规范＝
  **纯加一张表**，不必再加嗅探分支。
- **P1 身体预设从 4 家扩到 8 家**：新增 VRM/VRoid（`J_Bip_*`）、3ds Max Biped（`Bip001 *`）、
  Auto-Rig Pro（`*_stretch.l`）、英文 Humanoid 同义词（`UpperArm`/`Thigh`/`Calf`…）。
  修复前实测覆盖率：VRM 0%、Biped 0%、ARP 0%、英文手搭 54%；现在八家的身体骨全 100%，
  `pytest` 断言守住。
- **⚠ 修正本文档此前的说法**："身体预设现覆盖 …MMD…" 是**名义上覆盖、实际空转**：mmd_tools
  是 PMX→Blender 的事实标准导入器，它一律把 `右腕` 导成 `腕.R`，而表里写的是 `左腕/右腕`。
  修复前 87 个加权组只有 5 个映射成功（占 23% 权重），手臂/腿/手指全部落进 P3 的位置匹配。
  修法=查表前把 `.L/.R` 折回 `左/右`。**这一条影响所有 MMD 模型，不止某一个。**
- **P1 补齐 MMD 半标准骨**：`足D/ひざD/足首D/足先EX`（占身体权重 24.6%，腿全刷在这上面）、
  `腕捩1-3`、`手捩1-3`、`腰`。另修 `手捩*` 的目标：原指 `Hand`，导致肘后 4cm 起整条小臂吃满
  手掌旋转 → **肘部拉伸扭曲**；改指 `ForeArm` 后 `Hand` 的接管点回到 |x|0.48，与游戏原版同位置。
- **P1/P3 新增「作者直接指定」入口（本文档 §6.5-6.6 的 override 正规形态）**：插件里加了
  **骨骼映射表** UIList——左列填目标游戏骨（下拉可搜），右列选装饰物理策略
  （自动/刚性跟父骨/自建摇物链/跟裙摆）。预设退化成**预填**：认得的骨架一行不用碰，
  认不出来的靠点选，实测一个完全陌生的骨架约 21 行覆盖全身。**所以骨映射这一层不再取决于
  我们认识多少种命名规范。** 出口沿用已有的 explicit/physics 通路，后端零改动；存盘时骨映射与
  装饰物理写同一份 JSON 的 `bones`/`physics` 两个键。
- **P3 的诚实账（策略已翻转）**：本次 3 组装饰骨，旧位置匹配只对了 1 组（`胸上2`→`Bust1_S`）；
  脖子缎带被蹭到夹克**袖子**摇物骨、腰部挂件被蹭到大腿皮肤摇物骨。当前代码改成「跟源父骨映射后的骨」
  并加 `胸`→`Bust*_S` 名称规则；离线契约为 3 组预期分类，但真实服装仍需进游戏确认。
- **新增硬闸门**：14 个承重关节（Hips/Spine/左右 Arm-ForeArm-Hand-UpLeg-Leg-Foot）任一没拿到
  权重就拒绝导出并点名。此前源骨名认不出来时是**导出成功、进游戏才废**（实测整只手 100% 被钉在
  `Spine1`、上臂挂在袖子摇物骨上，全程零警告）。判据只看游戏侧、与源命名无关；与目标骨架取交集，
  所以发型/发饰导出永不触发（实测交集为 0）。
- **`mmd_edge_scale`/`mmd_vertex_order` 自动忽略**：它们不是骨（每顶点权重 1.0），此前会让导出
  报错，而按 UI 提示填兜底骨 `Hips` 会把整个模型塌成刚体。
- **3DMigoto 路线在本分支整体移除**（不是加开关隐藏）：两条路线摆在同一套编号流程里，会让 AB
  作者顺着编号点进传权、用猜的权重盖掉手刷的权重——这次实战里就发生了。删掉 11 个算子、
  `weight_transfer.py`、core 的三个打包函数及 16 个随之成为孤儿的内部函数、5 个属性、3 个测试/
  脚本文件，UI 从四步变三步，净减约 1100 行。3DMigoto 仍是**抓帧工具**，这个依赖保留。
- **修掉一个影响此前所有 AB mod 的 bug**：`_export_bundle_png` 在写完像素之后才设
  `colorspace_settings.name`，赋值会重建图像缓冲、丢掉已写入的像素（**赋同一个值也丢**，
  `image.update()` 拦不住），存盘得到纯黑。t0 是 PNG 走 `copy2` 所以幸免，t1/t4 从烘焙的 DDS
  转 PNG 必中 → 游戏里 ShadeColor 全黑、整身发暗，很容易被误当成"没做肤色校正"。
- **肤色校正有了可信取值法**：游戏权威肤色＝用原版 **t4 的 A 通道（皮肤二值 mask）** 圈出图集
  皮肤纹素、再采原版 t0。本次得 sRGB (0.994, 0.898, 0.840)，与另一次独立实测重合。按几何猜皮肤
  区会被立领/袖子污染（脖子采样采出 0.879 偏灰，作废）；源侧要按 **UV 足迹光栅化**取均值，
  点采样只取顶点 UV 会漏掉贴图里画的阴影（本次差 0.09 线性）。

</details>

<details><summary><b>2026-07-24/25 · fuyuko(SCSP) 新骨 + Unity6 加载崩溃根治 + 摇物物理三连修</b></summary>

- **P0–P2 已完成**：源 rig 识别、身体/装饰分类、直接/去 `_1`/预设/父链 remap 已接入导出链路；身体预设现覆盖 SCSP/IP/QualiArts、MMD、Mixamo、Rigify 的躯干、四肢、手指、脚趾。IP 与 SCSP 使用同一 QualiArts 身体命名族，不另造一套重复表。
- **P3 已完成**：目标 `_S`/`Cloth`/`bone_<hash>` 摆动骨识别；裙摆逐段最近匹配；普通悬挂件按组质心匹配；远距回退刚性父骨。源服装自带的 `Spine*_Bow`/`Streamer`/`SStreamer`/`Lace` 链改为保留源层级并走 P4 新骨，避免左右件被质心合并到同一侧或被裙摆骨吞掉。
- **P4 已完成（sidecar/runtime 契约）**：导出 `newBones`、每条链的 `extraSwingBones` tip 和默认 ActorSwing 参数；插件 runtime 支持读取并按 `parentName` 创建新骨链。插件 Release x64 已编译通过，但尚未完成实机 `ChainInfo.layers>1` 验收。
- **P5 已完成**：把源顶点组权重无损保留到导出 mesh；只替换骨骼索引，不触发邻近重刷；新增骨可进入 bundle skeleton/bindpose 与 `m_Skin` 索引闭环。
- **P6.1/P6.2 离线部分已完成**：UnityPy 可向普通模板插入缺失的 `GameObject/Transform`，补齐父子关系、SMR `m_Bones`、Mesh bindpose/AABB；UnityPy 结构检查和 atbm 新骨 bundle 回归通过，但 fuyuko 在 Unity 6 实机 `LoadAsset_Internal` 仍崩溃，因此不能宣称 P6.1/P6.2 已实机完成。
- **P6.3 实机日志已取得（2026-07-24）**：`D:\Games\gakumas\gakumas-local\mod-plugin.log` 已证明 `atbm-0140` 新骨网格替换、权重闭环和 ActorSwing 多层建链成功；视觉上的持续自摆仍需人工观察确认。
- **最新阻塞（2026-07-24，fuyuko-super）**：重新导出的 `hmsz-cstm-0059` bundle 网格替换和权重闭环成功（`meshApplied=1`、`droppedInfluences=0`），但 44 根 `bone_<hash>` 被当作新骨全部挂到 `Hips`，日志为 `createdBones=44`、`ChainInfo=44x1`，造成上半身、裙摆、蝴蝶结扭曲。
- **根因已确认**：`D:\GIT\gakumas-modding\.local\assetstudio-body-json\mdl_chr_hmsz-cstm-0059_body` 只有 `Geo_Body.json`，没有 `Geo_Body.skeleton.json`；Mesh 只有 156 个 `m_BoneNameHashes`/`m_BindPose`。合成骨架只能从其他资源 sidecar 补公共骨名，0059 独有的 44 根退回 `bone_<hash>`。游戏 profile 已证明这 156 个 hash 顺序可对应真实骨名。
- **P6.4 模板修复已完成，实机复测待做（2026-07-24）**：新增 `tools/repair_template_bone_names.py`。它按 `Geo_Body.json` 的 `m_BoneNameHashes` 与目标 profile 的 `bones[index]` 修复 R32 模板 Transform/sidecar；0059 修复结果已放回原模板文件名，SMR 156 根、sidecar 156 根、`bone_* = 0`，旧坏模板保留为 `template_mdl_chr_hmsz-cstm-0059_body.before-bone-fix.bundle`。`build_phase3_templates.py` 现在遇到 `bone_*` 会直接拒绝交付坏模板。
- **当前 fuyuko 热修状态**：`bone_<hash>` 名称热修和源飘带新骨导出均已写入当前 bundle；AABB 热修后当前文件指标为 `SMR.m_Bones=184`、`Mesh.m_BindPose=184`、`Mesh.m_BonesAABB=184`，引用缺失数为 0、骨引用重复数为 0。旧文件保留为 `fuyuko-super.before-aabb-fix.bundle`；但游戏仍在加载阶段崩溃，尚未进入 mesh graft/ActorSwing。
- **最新手部问题（2026-07-24 19:00）**：新版导出报告已显示 `preset=scsp`，但后续装饰物理位置映射用 `update` 覆盖了身体 preset，实际仍是 `LeftElbow→LeftSleeve2_S`、`RightElbow→RightSleeve1_S`、锁骨→`Spine2`，所以画面未变。已修正合并优先级：身体 preset 命中后不可被装饰映射覆盖，只有未命中的装饰骨才允许按位置匹配。旧 bundle 的错误权重已烘焙，必须用新版插件重新导出，不能只再次改名。
- **最新背部蝴蝶结/飘带物理问题（2026-07-24 19:05–19:12）**：手部已正常；但导出 sidecar 仍为 `newBones=0/extraSwingBones=0`，`Streamer_L/R` 被质心合并并映射到左侧 `LeftBackRibbon2_S/LeftBackSkirt*_S`，`Lace_R` 还落到腿部摆动骨，故出现背后乱摆、左右不对称、整根飘带不联动。已在 `build_accessory_physics_remap` 修复：`Spine*_Bow`、`Streamer`、`SStreamer`、`Lace` 源链强制保留源父子关系并进入 P4 新骨；新包为 `dist/gakumas_mi-0.8.0-code-20260724-191244.zip`，15 个 bundle contract 测试通过。旧 bundle 需重新导出后再看实机画面。
- **第一次崩溃（2026-07-24 19:19）**：使用新链 bundle 加载 mod 时游戏在 `AssetBundle.LoadAsset_Internal` 的 Unity 原生反序列化阶段崩溃（`UnityPlayer.dll`、`0xc0000005`），尚未进入 ActorSwing。发现 `Mesh.m_BindPose=184`、`Mesh.m_BonesAABB=156`，因此补了 AABB 扩容逻辑并热修当前 bundle。
- **第二次崩溃（2026-07-24 19:33）**：AABB 已补齐为 `184/184` 后，游戏仍在相同位置崩溃；`Player.log` 栈为 `AssetBundle_LoadAsset_Hook:2946 → LoadLocalModAssetFromBundle:1400 → AssetBundleRequest_get_asset_Hook:2991`，异常仍为 `UnityPlayer.dll 0xc0000005`。`mod-plugin.log` 只到 `Loaded mod asset bundle`。

- **✅ 崩溃根因定位并根治（2026-07-24 晚，实机验证通过）**：崩溃 = **UnityPy 向 bundle 新增（合成）GameObject/Transform 对象 → Unity 6 原生 `LoadAsset_Internal` 反序列化崩**。二分证据链：①校验 crash bundle 对象图无悬空指针/无重复 PathID/类型表一致/字节自洽/对齐一致 → 排除常见缺陷；②对照发现 atbm-0140（能加载）的 288 根新骨是**运行时插件 AddComponent 建的，bundle 内零克隆对象**，`createdBones` 从来是运行时计数——**内嵌合成对象这条路实机从未通过**；③变体 A（删 56 个合成对象、28 个新骨槽重指向 Hips、Mesh/bindpose 逐字节不动）**实机加载不崩**，且日志出现 `createdBones=288`——决定性证明崩溃 100% 由合成对象触发。**根本原因**：运行时 `PatchModMeshSkinningLosslessly` 的前置校验（`ModRuntime.cpp:2088`）要求 `modBones[i].name == sidecar[i].name`，这是唯一逼迫导出器内嵌命名 Transform 的地方；而真正干活的 `BuildHybridBoneArray` 完全从 sidecar JSON 按名字/顺序建骨、运行时创建缺失骨，**根本不读 mod SMR 骨名**，该校验纯冗余。**修法（两仓，删代码为主）**：运行时删掉 `name != modBoneName` 条件只留 parentIndex 合法性检查；导出侧 `patch_unity_bundle.py` 删掉 `_ensure_template_bones` 合成路径，`_reorder_smr_bones` 对模板缺失的新骨名回退到 root transform（m_Bones 156→184、零合成对象）。插件 Release x64 已重编译部署，fuyuko 实机**加载成功 + 网格/蒙皮/贴图正确 + graft 通过 + 运行时成功创建缺失骨**；后续最新日志为 `matchedBones=156 createdBones=26 swingPrepared=36`。

- **✅ 摇物物理运行时修复三连（2026-07-24 晚，实机逐步收敛）**：崩溃解决后回到 ActorSwing 物理，运行时定位并修了三个真 bug（均在 `ModRuntime.cpp` RegisterBones 建链段）：
  1. **swing 参数缺失致乱摆/不摆**：sidecar 主 `bones[]` 里的新骨没有 `swing` 字段（`build_new_bones_sidecar` 只写进独立 `newBones` 数组，而 `extra_nodes` 为真时 `newBones` 不落盘），运行时 `parseSwing(bones[i])` 全返回 nullopt → `SetDefaultValues` 惰性（mass=0/spring=0）→ 被驱动就发散乱摆、不驱动就不动。**修**：导出侧 `core.py` sidecar 组装把 newBones 的 swing 按名合并进 `bones[]`；实机热补当前 bundle 后右侧开始摆动。
  2. **误把游戏裙摆链当自家链复用致截断+乱摆**：`existingHostChains` 收了 pelvisGo(Hips) 上**所有** ActorSwingChain，但游戏自己的裙摆链也挂在 Hips 上 → 被当成"我们建的链"复用，7 个 depth-3 bow 根塞进游戏 5 层裙摆链 → `UpdateChainInfo` 按最短成员截断成 3 层，既砍了游戏裙摆下摆、又让 bow 被裙摆解算器带乱。**修**：加全局 `g_createdHostChains` 只追踪自建链，`existingHostChains` 只从中筛选，绝不碰游戏链。修后 `chain[len=3]` 变 `created=1`、`registered=3`，**左侧蝴蝶结正常、游戏裙摆恢复完整**。
  3. **复用链漏注册**：swingChains 注册被 `if(createdChain)` 门控，复用链若不在 swingChains 里永不被驱动。**修**：改成扫描去重后，任何不在 swingChains 的 host 都注册。

- **剩余物理问题（导出侧分类，2026-07-24 晚未完）**：运行时已各司其职，剩下的是**导出侧装饰骨挂到哪根目标骨**的分类问题，需改导出+重导：
  - **花边 `Lace_R` 乱摆**：`Lace_R_A0` 父骨 = `RightLeg`（大腿），因 `is_source_chain` 把 lace 归为 `new_source_chain` 保留了源模型的腿部父链 → 花边挂腿上独立摆。用户要它**跟裙摆**。修向：lace 应"蹭"最近**裙摆**骨（排除腿部 `_S`），而非保留源腿父。
  - **右 bow/右裙摆弱/不摆、左右不对称**：源模型左右 bow 骨 rest 姿态/命名不对称（`SStreamer_L` vs `Streamer_R`、左右 bow x 位置疑似同号），可能需回 Blender 改源骨对称。
  - **提醒**：重新导出目前产出的 bundle 与手术版**逐字节相同**，改物理必须先改导出代码（`build_accessory_physics_remap` / sidecar 组装）再重导，不能只重导。

当前边界：**AB 新骨换装加载/蒙皮/建骨/多数摇物链实机贯通**；左蝴蝶结、游戏裙摆已正常。

- **❌ 已作废：SCSP 异骨架动态变形「改 bindpose」修法（提出 2026-07-25，同日实测证伪，别再走）**

  <details><summary>原提案（保留备查）：用源骨架 bindpose 覆盖游戏 bindpose</summary>

  SCSP 源模型手指/脚/关节**静止正常、一动就变形**。当时判断根因=AB 导出用游戏抓帧 bindpose，
  但 mesh 绑在源骨架上；参照 3Dmigoto 版冬优子的 `BoneCorrections`
  （`correction=gameRest@sourceRest⁻¹`）推出 `ABbindpose=sourceRest⁻¹`，
  修法=`operators._source_armature_bindposes` 从 Blender 源骨架逐骨算 bindpose、
  `core._bundle_geojson` 按骨名覆盖。数值上恒等式差 1e-7、round-trip=0。
  </details>

  **实测结果：这条修法实机让游戏在静止状态直接崩。** 原因是 AB 导出的顶点**已经在游戏空间**，
  再叠一次 bindpose 校正等于重复校正。该修法从未进入代码，`_source_armature_bindposes` 也
  从未实现。

  **真实根因（同日实测坐实）**：预处理阶段把手指绑定搞坏了——原始 `dress_2219_full_todo.blend`
  手指「骨→其主导顶点质心」= **16.0mm**，预处理后的工作文件 = **50.5mm**，即网格动了、手指骨
  没跟着动，权重照错位骨刷，顶点整体错约 2 个指节。四肢骨节长 150–300mm、偏差 30mm 只占
  10–20% 所以看不出；手指骨节仅 20–25mm，偏差大于骨节 → 撕碎。**导出管线没有问题，缺陷在上游
  模型 prep。** 修法=按 `ai-model-workspace/external-model-conversion-workflow.md` 从原始
  blend 重做预处理，并在每步之后复量该比值（只允许变小或不变）。

  连带证伪的还有四条，都实测过：传递权重（反距离/重心两种实现，p99 2.99→6.96）、逐顶点乘
  `gameRest·sourceRest⁻¹` retarget 几何（手指扭烂）、pose 摆源骨到游戏关节再烘（网格反而离
  关节更远 23→48mm）、「逐骨 roll 差 90–180°」（那是 Blender 骨轴约定差，无害——四肢同样差却正常）。
- 剩花边挂腿(导出分类,已 remap 兜住)、右侧 bow 不对称(疑源模型)、装饰物理逐件微调待办。

---

</details>
