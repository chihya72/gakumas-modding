# AB target-rig 现行架构

状态：GakumasMI 1.3.0 正式版。本文只维护当前有效的架构、流程与实现边界；已经完成的批次、
逐日实机记录和被取代的计划由 Git、[`CHANGELOG.md`](../CHANGELOG.md) 与
[`lessons-learned.md`](lessons-learned.md) 保存。

文档分工：

| 文档 | 权威范围 |
|---|---|
| **本文** | 当前 target-rig 架构、步骤、导出闸门、明确不做的路线 |
| [`ab-target-rig-contract.md`](ab-target-rig-contract.md) | 骨架、五档映射、sidecar 与阈值的硬契约 |
| [`ab-consolidated-facts-and-evidence-2026-08-16.md`](ab-consolidated-facts-and-evidence-2026-08-16.md) | 已坐实事实、实测数字、量测方法与反例 |
| [`ab-target-rig-ingame-checklist.md`](ab-target-rig-ingame-checklist.md) | 离线无法完成的实机验收 |

发生冲突时：流程与边界以本文为准，数据格式与导出约束以契约为准，事实和数字以事实文档为准。

## 产品边界

目标是让 mod 作者只使用 Blender：不要求安装 Unity、不要求手写 3DMigoto 配置，也不在运行时
猜测或重画作者的权重。3DMigoto 只负责抓帧以生成目标配置档。

现行路线只发布 AB 方案：保留目标游戏的 prefab、Animator、IK、socket 和原生人体骨组件，替换
Mesh、材质及必要的 `bones[]` / bindpose；作者模型的骨权重尽量原样保留，骨名显式映射到游戏骨名。
来源模型独有的裙、袖、飘带和发饰骨可作为带前缀的新增辅助骨 graft 到目标骨架。

这条路线接受一个明确取舍：人体关节要对齐目标骨架，因此不能完整保留来源模型的人体比例；服装
轮廓、拓扑、UV、贴图以及由辅助骨承载的动态细节仍可保留。

## 为什么使用 target-rig

| 路线 | 作者成本 | 权重/体型 | 游戏原生物理与挂点 |
|---|---|---|---|
| **target-rig（现行）** | 只用 Blender | 关节需对齐，映射后保留来源权重 | 复用目标 prefab，并支持新增辅助链 |
| 双骨架 bridge | 只用 Blender | 可保留来源人体比例 | 代理骨前缀使按骨名工作的物理、IK、socket 无法直接复用；只留特殊兼容能力 |
| whole-object | 必须由 Unity 生成带组件 prefab | 可保留完整来源对象 | 违反作者只用 Blender 的产品边界，不进入发布线 |

双骨架和 whole-object 的量测证据仍有研究价值，但不是默认产品路线。

## 制作与运行流程

1. **选目标**：加载 `profiles/<目标>/` 中的配置档和目标参考体。
2. **对齐作者模型**：在 Blender 中对齐承重关节的位置与骨静止朝向；朝向差在静止截图中不可见，
   必须使用面板仪表检查。
3. **确定骨映射**：按结构分组处理骨链，并为每根 deform bone 留下明确状态。
4. **补必需权重**：仅对来源缺失的承重骨使用「从相邻骨劈权重」；原版决定缺骨份额，捐赠骨之间
   保持作者原来的相对比例，族内总权重守恒。
5. **导出前检查**：运行对齐、覆盖率、权重、辅助骨和摇物链闸门；任何 `undecided` 或 `reject`
   不得静默进入导出。
6. **打包**：插件使用项目维护的目标模板生成 AB 和 sidecar，作者不负责 Unity 环境或模板选择。
7. **运行时应用**：在原版 prefab 上应用网格、材质、骨序和显式声明的新增骨/物理数据；运行时不修
   权重、不复制未知组件、不做来源骨架 bridge。
8. **实机验收**：按 [`ab-target-rig-ingame-checklist.md`](ab-target-rig-ingame-checklist.md)
   一次只改变一个主要变量，分别验证画面、骨映射和动态链。

## 骨映射五档

每根来源 deform bone 最终只能处于以下一种状态，状态的精确定义和 sidecar 表达见契约：

| 状态 | 含义 |
|---|---|
| `direct` | 一对一映射到目标骨 |
| `merge` | 多根来源骨合并到同一目标骨 |
| `helper` | 作为带前缀的新增辅助骨保留 |
| `bake` | 把静止形变显式烘焙后再合并 |
| `reject` | 无法安全处理，禁止导出 |

赋值以“锚点 + 连通链 + 几何影响”形成的结构组为主要粒度，作者可展开后逐骨覆盖。不能识别骨名时
允许作者明确选择；不允许把未知骨静默猜成 `Hips` 或其它人体骨。

学马存在而来源缺失的骨分三类：

- 21 根承重关节必须获得权重；缺骨只在对应局部使用 `core.redistribute_family_weight`。
- `Pelvis`、`Spine2` 和 `*_H` 等可选骨允许无权重；不为凑齐骨数而重画作者全身权重。
- 节数不同的手指/脊椎可以合并到最近语义骨，但必须在映射状态中可见。

## 导出硬闸门

下面是现行唯一闸门清单。实现引用只写符号名，避免代码移动后文档行号失效。

| 项 | 当前判定 | 实现锚点 |
|---|---|---|
| 21 个承重关节有权重 | 拦截；错误同时给出“指定映射”和“从相邻骨劈权重”两条出路 | `core.critical_coverage_error` |
| 未映射 deform bone / 引用不存在的骨 | 拦截 | `operators._inverse_skin_export_data` |
| 未归一化或全零权重 | 写包时归一化；全零拦截，并报告第 5 个影响骨后的截断量 | `core._bundle_skin` |
| `bones[]`、bindpose、`m_Skin` 数量和索引自洽 | 拦截 | `core._bundle_geojson`、`core._bundle_skin` |
| 目标骨 bindpose 不被来源覆盖 | 不设独立闸门；lossless 输出本来就携带来源 mesh bindpose，无法形成对原版也成立的判据 | — |
| 头、手、脚、根骨静止位置偏移 | 面板报告，不使用统一硬阈值 | `core.rest_alignment` |
| 全部 `direct` 骨的静止朝向差 | `>=15°` 拦截 | `operators._rest_orientation_error` |
| `bindpose · 骨静止世界 ≈ I` | 作废；target-rig 下会误报原版资产 | — |
| `undecided`、`reject` 或未执行的 `bake` | 拦截；显式允许 undecided 时必须在 sidecar 和报告留痕 | `core.undecided_export_error`、`operators._prepare_bundle_export_data` |
| 空摇物链 | 拦截 | `core.empty_swing_chain_error` |
| 新增骨与目标骨架重名 | 拦截 | `core.new_bone_name_collision_error` |

每个新检查必须同时证明“坏样本会报”和“正常样本不误报”。离线验证不能取代实际代码执行、蒙皮
模拟和实机观察。

权重报告按五档统计占比，并用 `core.cross_joint_bands` 对比跨关节混合带。原版基线为肩 13.3%、
肘 3.9%、腕 6.2%、膝 9.5%；数字来源和量法见事实文档。

## 运行时与物理边界

运行时职责保持薄：

- 保留目标 prefab 和原生人体骨组件，只应用 Blender 已确定的资源与 sidecar；
- sidecar 只描述新增骨、父子关系、链、driver 和已确定的参数，不包含运行时启发式权重修复；
- body、face、hair 共用骨名空间，新增骨必须带 mod 前缀且不得重名；
- 一根 Transform 只能有一个主要求解器；摇物骨不能同时挂 QuartzDriver；
- `ActorSwingChain` 是环容器，可与 driver 共骨；单根装饰骨只有锚定层，不会形成可动链；
- 静态碰撞体不挂在 `*_H` 骨，`collisionMask` 使用
  [`gakumas_mi/swing_presets.json`](../gakumas_mi/swing_presets.json) 的逐档原版基线。

诊断动态问题时，先用日志证明目标骨实际进入解算并产生局部旋转，再讨论 stiffness、碰撞和限位。

## 明确不做

- 不把 whole-object 并入发布线，也不把双骨架 bridge 设为默认路线。
- 不自动执行 A→T 烘焙或全自动关节对齐；破坏性步骤必须可见、可关、可量化、可撤销。
- 不全身重绘权重，只修来源确实缺失的承重骨。
- 不用骨名启发式猜完所有异常来源；自动结构分组负责常见情况，作者覆盖负责剩余情况。
- 不让运行时自动修权重或复制未知 MonoBehaviour。
- 不以自研 AssetBundle 序列化阻塞当前模板打包路线。

## 贯穿不变量

1. 每次实机验证只改变一个主要变量。
2. bindpose、骨序、权重索引和 Renderer 空间必须自洽。
3. 日志声称完成的操作必须能从产物或活体状态读回。
4. 共享文件、贴图、骨名和缓存必须按模型/部件限定作用域。
5. 源数据、推断结果和作者覆盖必须可区分、可追溯。
6. 文档引用代码只写稳定符号名，不维护易漂移的行号。

## 相关资料

- [`ab-route-notes.md`](ab-route-notes.md)：AB 加载、换网格、新增物理骨与材质边界。
- [`hair-pipeline.md`](hair-pipeline.md)：发型与发饰制作、shader 通道证据。
- [`lessons-learned.md`](lessons-learned.md)：已经证伪或退役的路线。
