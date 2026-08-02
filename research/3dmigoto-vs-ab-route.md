# 两条换装路线对比:3Dmigoto 逆蒙皮 vs AB bundle 原生

> **状态（2026-07-27）：本文档转为历史记录。** 分支 `research/ab-route-swing-physics` 已把
> 3Dmigoto 逆蒙皮路线从插件里整体删除，不再是"两条路线按需选"。保留本文是因为它记录了**为什么**
> 选 AB——下面对 3Dmigoto 代价的分析仍然是那个决定的依据。3Dmigoto 保留的唯一角色是抓帧工具。

同一个目标(把 IP 服装换进学马),两种实现,**在渲染管线的两个不同位置拦截**。这一个分叉决定了后面所有差异、所有代价。

- 3Dmigoto 路线:已在 main 完成并大量实机验证(GakumasMI 插件 + 3dmigoto-gkms)。
- AB bundle 路线:本仓研究中,机制见 [../ab-route-handoff/docs/bundle-route-roadmap.md](../ab-route-handoff/docs/bundle-route-roadmap.md)、[../ab-route-handoff/docs/runtime-mechanism.md](../ab-route-handoff/docs/runtime-mechanism.md)。

## 拦截点:根本分叉

| | 3Dmigoto 路线 | AB bundle 路线 |
|---|---|---|
| 拦截层 | **DirectX 11 绘制调用**(引擎之后、GPU 之前) | **Unity Mesh 资产**(引擎之前) |
| 手段 | 3Dmigoto DLL hook 绘制,按 buffer hash 换 VB/IB/贴图 | chinosk6 插件 `set_sharedMesh` 把 mod 网格塞回原活体 renderer |
| 谁做蒙皮 | **没人——网格是逆蒙皮烘死的几何** | **Unity 自己做**,用学马活体骨驱动 |

3Dmigoto 换的是「已经蒙好皮的最终几何」,AB 换的是「引擎的蒙皮输入」。所有代价都从这里派生。

## 逐项对比

### ① 蒙皮 / 骨架 / 物理
- **3Dmigoto**:必须**逆蒙皮**——把网格预烘到游戏当前姿势,3Dmigoto 只做几何替换、不碰骨。无引擎骨架访问 → **新增物理骨不可能**,摆动只能蹭原网格烘死的动作。逆蒙皮矩阵恢复本身是一整套逆向工程(见 [inverse-skin-matrix-recovery.md](inverse-skin-matrix-recovery.md))。
- **AB**:Unity 原生蒙皮。共享骨按名自动 retarget 到学马体型(`skinnedV = Σ wᵢ · 学马活体骨ᵢ · IP_bindposeᵢ · v`,root 同名 Hips 走 useModBindposes),**不需要 Blender 预烘对齐**。新增专属骨可做(lossless 方案 + 已跑通的 ActorSwing 物理:翅膀/裙摆/缎带/听诊器真摆)。

### ② 描边(顶点 COLOR)
- **3Dmigoto**:新网格缺顶点 COLOR 被默认白色冲掉 → 没描边,得手动传递权重+颜色(memory `gakumas-color-drives-outline`)。
- **AB**:COLOR 在 JSON→Mesh 阶段写对,插件 clone 时**不动 colors32** → 原生描边直接对。

### ③ 透明件
- **3Dmigoto**:透明区 RGB 纯黑被双线性渗色,得 alpha-bleed + 带 alpha 的 DDS 格式;一度自建镂空/半透明后又全删,只留原生 co(memory `transparent-route-native-co-only`)。
- **AB**:走引擎原生材质段,透明是引擎本职,无 hack。

### ④ 贴图槽(最脆的一处)
- **3Dmigoto**:按**寄存器 t0/t1/t4 硬绑**。shader 变体一换,槽位重排 → 暗光全身颜色错乱(memory `dark-scene-ps-slot-repack`),要靠运行时全局布局探测才根治。**天生脆,跟着游戏 shader 变。**
- **AB**:按 `rendererName + materialSlot + property`(_BaseMap/_DefMap/_ShadeMap)语义覆盖,不吃寄存器重排。

## 各自的代价

### 3Dmigoto 的代价:能力债 + 脆性债
- 逆蒙皮工程量大,且**吃游戏 shader 变体**——每个新场景/变体都可能重排槽位炸一次,得追着修(FLIP swapchain resize、暗光槽、透明黑,都是这条线的坑)。
- 能力天花板硬:**新物理骨做不了**,描边/透明全靠 hack 兜。
- 换来的好处:**开发者侧零 Unity**,3Dmigoto 通用、不锁引擎版本,装好即用。

### AB 的代价:前置门槛 + 正确性责任
- **bindpose 正确性由你的 bundle 保证**,插件不修——转置/非法直接蒙皮爆炸。从「逆向游戏」换成「喂对数据」。
- **锁 Unity 6000.0.67f1**(bundle 头写死,必须匹配游戏运行时);打包这一步绕不开 Unity——已用「工具作者一次性产模板 + 开发者跑 UnityPy 补丁」把 Unity 从开发者路径上摘掉(免 Unity 2B 链已端到端跑通)。
- 换 3Dmigoto 为 chinosk6 插件(一次性)。
- 换来的好处:描边/透明/贴图/物理**全部由引擎原生正确**,3Dmigoto 追着修的脆性坑从根上消失,并解锁新物理骨。

## 底线

- **3Dmigoto = 骗过 GPU**:通用、免 Unity、装好即用,但要逆蒙皮、追着 shader 变体修、能力封顶。
- **AB = 喂对引擎**:把脆性坑从根上换成一次性的打包门槛和 bindpose 正确性责任,拿回原生蒙皮/描边/透明/物理和新骨能力。

一句话:**AB 用「前置打包成本 + 引擎版本锁」换掉了 3Dmigoto「逆蒙皮工程 + 无穷尽的 shader 变体维护 + 能力天花板」。** 长期出高质量换装(尤其带物理)→ AB 划算;图省事的一次性小改 → 3Dmigoto 仍更轻。
