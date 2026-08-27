# GakumasMI Blender 插件更新日志

版本号见 [`gakumas_mi/__init__.py`](gakumas_mi/__init__.py) 的 `bl_info["version"]`。
发布包用 `python tools/package_blender_addon.py` 生成（代码版不含 Body JSON 资源库；
加 `--with-body-lib` 可一并打包）。本地包不提交到公开仓库。

> ⚠ **0.9.0 里各条的验证程度不一样。**（下面这段写于 2026-07-27 的发布冻结之前；
> 冻结期的 RC 闭环之后，骨骼映射表单、承重关节闸门、三步 UI、校色 t0 和刚性/跟裙摆装饰
> 策略已转为实机实证；自建摇物链当时只有建链日志（**2026-08-11 已画面级确认**）。逐项见
> `research/current-status-and-roadmap.md`（已于 2026-08-22 删除）。）
>
> **实机验证过（2026-07-26，星仪·大国主 PMX → `fktn-othr-0002`，进游戏确认）**：
> `.L/.R` 折叠、MMD D 骨、`手捩→ForeArm`（肘部撕裂修复）、t1/t4 纯黑修复。
>
> **只过了离线测试，没进游戏、也没有人在真 Blender 面板里点过**：骨骼映射表单、承重关节闸门、
> 装饰骨策略列、逐张表打分选表、`mmd_edge_scale`/`mmd_vertex_order` 自动忽略、
> 移除 3DMigoto 与 UI 收三步。这些有 `pytest` / Blender headless（4.2.7 与 4.5.3 上
> 安装、UI、材质烘焙、导出闭环四套全绿）/ 真模型 geojson 数值分析背书，
> 但**新包没被安装使用过**。
>
> **贴图结果实机验证过、但面板没人点过**：肤色对齐原版（2026-07-31，千咲泳装
> `atbm-cstm-0140`）。校准输出与实机确认的那版贴图逐像素相同，所以颜色是对的；
> 算子已接进烘焙流程并有 Blender headless 冒烟背书，但 Blender 内的按钮路径未实测。
>
> **纯按公开命名规范写的，连对应模型都没拿到过**：VRM/VRoid、3ds Max Biped、Auto-Rig Pro、
> 英文 Humanoid 四张预设表。表里名字若拼错，表现是那几行不预填、要手动选（有闸门兜着不会
> 静默出废品），但不能宣称"支持"。

## 1.4.0（测试版）— 闸门重新瞄准 + 修好坐标约定（**破坏性**）

### ⚠ 坐标约定 v1 → v2：外部模型不再需要手动镜像

`core._to_unity` 从建仓第一天（2026-06-23，早于 1.1.0 两个月）就是 `(x, z, -y)` ——
只换了 Y/Z 两轴，**行列式 +1，是纯旋转**。而 Unity 是左手系、Blender 是右手系，两者之间
的转换**必须含一次反射**（行列式 -1）。数值对得上，手性没转过来。

后果：游戏骨架进 Blender 后左右是反的（实测 `LeftFoot` 落在 -X，而 Blender 里朝 -Y 的
角色解剖学左侧是 +X）。因为导入导出用同一个矩阵，round trip 自洽，两个月没暴露；只有从
**外部标准导入器**（mmd_tools / FBX / rip）进来的模型才和它对不上 —— 那些导入器是对的。
「每个外部模型都要手动镜像一次」就是这么来的，不是 MMD 的毛病，也不是游戏模型的毛病。

改法：`_to_unity` 改成 `(-x, z, -y)`，新增 `_from_unity`；导入侧四处 `(x,-z,y)` 一并改；
`C_UNITY` 矩阵同步（用它做**共轭** `C @ M @ C⁻¹` 时行列式抵消，旋转仍是正常旋转）。
**反射会翻面绕序**，所以导入和导出两侧的三角形索引都要反过来（`core.flip_winding`），
否则整个模型在游戏里面朝里。实测校验：我们导出的网格与游戏原版 mesh 在 Unity 空间的
有符号体积**同号**。

迁移（`core.COORDINATE_CONVENTION = 2`）：
- **新做的模型**：mmd_tools / FBX 导进来直接用，不用镜像。实测未镜像的 MMD 源现在全部闸门通过；
- **以前做的 .blend**：当初手动镜像过一次，现在方向反了 → 左右装反闸门会拦下并点名这种情况，
  用「沿 X 镜像整个模型」镜像回去；参照体还要回阶段 1 重新导入（旧参照体的左右和现在相反，
  劈权重和跨节过渡带都拿它当基线）。参照体上打了约定戳，旧的会在导出时报黄条；
- **已发布的 mod 包不受影响**：那些已经是 Unity 空间的绝对坐标。

### 新增「沿 X 镜像整个模型」按钮

直接改数据，不用物体缩放 —— 作者网格通常是骨架的子物体，「选中两个 → S X -1 → 应用缩放」
父子互相抵消，做偶数次等于没做（实测作者手动做了三次，净效果为零）。自定义拆分法线按
`(面号, 顶点号)` 对号写回，不按 loop 顺序（`flip_normals()` 会反转面内 loop 顺序，
按旧顺序写回 = 每个角的法线安到别的角上，91092 个共享顶点全裂 → 整片三角面阴影）。
形态键一起镜像。约定改完之后这个按钮主要用于迁移老文件。

## 1.4.0 的其余部分 — 闸门重新瞄准：从"数据自洽"转到"几何与权重"

> ⚠ **测试版，未经实机验证。** 本版的判据全部来自 2026-08-27 一次完整的 MMD → 学马仕
> 换装实战（归溟幽灵鲨 → `mdl_chr_hrnm-casl-0002_body`），每一条都写明了实测数字。
> 那次换装最终放弃，但六轮进游戏暴露出的问题都在这里。

**结论先写在前面**：1.1.0→1.3.0 那批闸门不是太严，是**瞄错了地方**。它们几乎全在查
"数据自洽性"（骨名映射齐不齐、参数字段全不全、有没有目标骨）——都是导出侧看得见的东西。
而那次真正致命的三件事全在**几何和权重**上：面朝向、权重过渡带、结构组作用域。
**一个数据完全自洽的包照样能在游戏里撕成条。**

### 新增闸门（原来静默出废品）

- **面朝里**（硬拦）：导出前算网格有符号体积，为负就拦。`S X -1` + 应用缩放会反转全部面的
  绕序；带自定义拆分法线的模型（MMD 几乎都带）点 `Shift+N`「重算外侧」修不干净，得用
  `Alt+N`「翻转」。实测 −0.4118 m³，进游戏是带尖角的破碎片、能看穿——**烧掉两轮才发现，
  而离线一次积分就够**；
- **左右装反**（硬拦）：比 5 对 L/R 骨在 Unity 空间的 X 符号。MMD 的 `.L` 在 +X、游戏的
  `Left` 在 −X，没做镜像就按名字映射 = 每根 L/R 骨绑到对侧。它躲得过现有每一把尺子（身体
  左右对称，位置差照样是正常量级），却让下游两道闸门报出一堆症状：脚尖劈不出权重、静止
  朝向整片 175~177°。排在那两道**之前**，报根因不报症状；
- **子树被外来物理拽走**（硬拦）：源骨并进游戏衣物骨、子骨却还留在 mod 骨架里 → 整支子树
  被重挂到那根原版骨下面。实测 4 根裙骨被并掉，第 2/13 列从上到下挂在原版裙骨上，
  三分之一的裙面飞出去，而所有现有闸门全绿（骨有目标、权重归一、静止正常）；
- **一行横跨多件衣服还下了物理指令**（硬拦）：结构组按骨架拓扑分，一组装得下互不相干的
  两件衣服（实测一行 177 根 = 大半条裙子 + 全部经文）。判据是**横跨几个骨族**不是行有多大
  ——整条裙子 192 根同族骨下一个指令完全正常，按大小拦就是误伤；
- **点了原版布料驱动器却一根都没挂上**（硬拦）：以前会静默退回摇物，日志全绿。

### 新增尺子（有数才能修）

- **衣物链的跨节权重过渡带**（黄条）：这是那次撕裙子的**唯一真凶**，而现有尺子一个都看不见
  ——`CROSS_JOINT_BANDS` 只列了肩肘腕膝，衣物链一根没有。实测 MMD 裙 **1.2%**、原版同部位
  **79.4%**（差 66 倍）。MMD 是一根骨一条硬边带，靠 MMD 自己的刚体+关节拴住相邻裙板；
  搬到摇物链/驱动器上，接缝没有权重拉着，一动就撕开。**静止画面看不出来是结构性的**：
  静止时每根骨的当前变换×bindPose=单位阵，再烂的权重都精确复原。有场景参考体就现算基线。

### 闸门降级 / 判据修正（原来会拦好模型）

- **静止朝向：红只留给单子骨链**，子骨 ≥2 根的降黄条 + 留痕。肩差 172° 那个实机坏样本就是
  单子骨；多子骨时中位数判据已能自我校验，剩下的偏差多半是某根子骨自己的位置差；
- **朝向按中位子骨判，不按最差**（子骨 ≥3 根时）：手有五个人形子骨，实测四个 0.3~3.3°、
  拇指 20°（MMD 拇指根比游戏往外 15mm）。取最差 = 把子骨的**位置**差记到父骨的**朝向**上，
  把一只量得好好的手判红，作者只能去搬拇指迁就一个量错的数；
- **朝向不再量退化的参考向量**（低于游戏侧长度 25% 直接跳过）：MMD 有 44 根源骨映射到
  `Hips`，按目标骨建字典后写覆盖，赢的那根离 `Spine` 源骨只有 3.5mm、游戏侧 75.1mm ——
  3.5mm 的向量量出来的方向是噪声，判出 35° 假阳性拦住一个没毛病的模型；
- **4 骨截断警告阈值 1% → 0.1%**，并按占总权重的百分比报。

### 同批的早期条目（原「未发布」节）

- **新增「左右装反」硬闸门**：源模型没做镜像就按名字映射（MMD 的 `.L` 在 +X、游戏的 `Left`
  在 −X）时，每根 L/R 骨都绑到对侧游戏骨上。这个错误躲得过现有每一把尺子——身体左右对称，
  位置差照样是正常量级，静止截图也看不出——但进游戏一动四肢就交叉。闸门排在承重关节和静止
  朝向两道**之前**，因为那两道报出来的都是它的症状（脚尖劈权重一个顶点都动不了、朝向整片
  175~177°），先撞上哪道作者就去修哪道，修的全是错地方；
- **静止朝向不再量退化的参考向量**：源骨和子骨挤在一起时（MMD 有 44 根源骨映射到 `Hips`，
  按目标骨建字典后写覆盖，赢的那根离 `Spine` 源骨只有 3.5mm、游戏侧 75.1mm）方向全是噪声，
  过去会判出 35° 假阳性拦住一个没毛病的模型。现在低于游戏侧长度 25% 的参考直接跳过；全部
  子骨都退化则报「量不了」，不判红；
- **静止朝向按中位子骨判，不按最差**（子骨 ≥3 根时）：手有五个人形子骨，实测四个 0.3~3.3°、
  拇指 20°（MMD 的拇指根比游戏往外 15mm）。取最差等于把子骨自己的**位置**差记到父骨的
  **朝向**上，把一只量得好好的手判红，作者只能去搬拇指迁就一个量错的数。父骨真转了的话所有
  子骨会一起偏，中位数照样报红；1~2 个子骨保持取最差（肩差 172° 那条实测坏样本就是单子骨）；
- **绑定体检在 MMD 源上不再静默失效**：`tools/simulate_ab_skinning.py` 的分区按主导顶点组
  判归属，而 MMD 导入器给**每一个**顶点都写了权重 1.0 的 `mmd_edge_scale` —— 它赢下全部
  顶点，于是每个区都是空的，体检只剩一句「无法评估」。现在按 `NON_BONE_GROUPS` 过滤后再选
  主导骨。修好后立刻在真模型上抓到 fingers 1.74x（阈值 1.5）。

### 修好本来就是坏的功能

- **`native_driver`（原版布料驱动器）三处连着断，从来就走不通**：`build_accessory_physics_remap`
  只认 `integrate` 要新建骨，`native_driver` 掉到「蹭最近摇物骨」被并掉（192 根裙骨并掉 182
  根，骨架 373→191）；`bone_side` 对外语骨名判不出左右 → `build_driver_block` 静默返回
  None → 退回摇物（新增 `side_from_world_x`，按世界 X 量，Unity 空间角色左侧是 −X）；
  驱动器骨还照样建 `ActorSwingChain` 和带 swing 的链尾，运行时 INV-1 会**拒绝挂驱动器**；
- **驱动器系数按链节数缩回原版量级**（`scale_driver_coefficients`）。依据是 il2cpp 源码：
  `ActorAnimationQuartzDriverSkirtBone.Calc(initialReferenceRotation, currentReferenceRotation,
  …)` 入参里**没有父骨状态**，每根骨只按参考骨那一个转角 delta 算自己的局部旋转；骨骼是
  层级的，串 N 根就叠 N 倍。预设是从 530 套原版量的、原版裙链 5 节，套到 12 节的 MMD 裙上
  累积 2.4 倍 = "动一下布料到处乱飞"。基准从**目标服装自己的骨架**数出来，不写死；
- **绑定体检在 MMD 源上从来没真的跑过**：`simulate_ab_skinning.region_vertices` 按主导顶点组
  分区，而 MMD 给**每个**顶点都写权重 1.0 的 `mmd_edge_scale` —— 它赢下全部 55108 个顶点的
  主导票，每个区都是空的，体检只剩一句"无法评估"。修好后立刻抓到 fingers 1.74x；
- **`verify_ab_package.py` 认得 driver 骨**：否则挂了驱动器的包一律判 FAIL（"摇物骨缺少物理参数"）。

## 1.3.0 — 五阶段作者工作流与跨游戏模型防错

- **界面按制作顺序重构为五阶段单页工作流**：目标与参照 → 作者模型 → 材质与贴图 →
  骨架与物理 → 检查与导出。必经内容常驻，高级/诊断项折叠；正常状态不画标记，只把阻断项标红；
  材质槽和骨组都改成「列表 + 当前项详情」，窄侧栏不再横塞多列控件；
- **明确作者模型对象**：后续材质、骨架、体检与导出围绕同一个网格工作，不再依赖点击按钮时
  碰巧激活了哪个对象；
- **跨游戏源模型防错补齐**：Mesh JSON 的 UV 不再错误翻转；描边新增「沿用源模型顶点色」并在
  缺少 COLOR 时硬拦；自建骨与目标骨架重名时拒绝导出；链尾朝向改由主导几何决定；
- **骨架队列更可处理**：链长 ±1 分组不再多米诺式合并，部件类型按链判断；增加「只看未决定」
  和「几何全在链根」提示，作者决定优先于按名字碰巧命中的目标骨；
- **AB 路线收口**：删除未发布的 Unity SDK 旁路、过期研究页和零引用的一次性工具；运行时日志
  阅读器不再把已经删除的 300 帧探针当成发布判据。

### target-rig 批次 2–7：参考资产、闸门、打包内置 UnityPy、物理作用域

现行架构与闸门清单见
[`research/ab-target-rig-architecture.md`](research/ab-target-rig-architecture.md)。批次 1 见下一节。

**批次 2 — 参考资产（P1）**

- **参考骨架的朝向照搬原版 + 无权重节点也建骨。** `_create_armature` 改成写 `EditBone.matrix`；
  `Reference` / `Pelvis` / 链锚点 `*_A` `*_O` / 链根 `*_S` 共 18 根旧版整批丢掉，它们没有 bindPose，
  位置从最近的带权重祖先按**完整 local 矩阵**合成（只累加 `localPosition` 会让带旋转的关节以下全错：
  151 个节点里 57 个带非单位 `localRotation`）。验收 `tests/blender_reference_rig_smoke.py`：
  逐骨位置 `0.00008 mm`、朝向 `0.000000°`。

**批次 3 — 权重映射与闸门（P3 + P4）**

- **新增「从相邻骨劈权重」（`gmi.split_weight_from_neighbours`）**：MMD/Biped 没有锁骨那一档的施工方案。
  只在作者和原版都认的骨之间重分、总量守恒、剩下的按作者自己的比例分回捐赠骨。验收把**原版自己身体**
  的 `LeftShoulder` 整组删掉再劈回来：864 个顶点最差差 `5.96e-08`；
- **新增硬闸门：全部 `direct` 映射骨的静止朝向差 ≥15° 拒绝导出。** 这会拦下一些以前能导出的包
  （A-pose 没烘的源，Claymore 那副 rip 肩差 172.5°）—— 不是回归，是这条路线的契约；
- **`bake` / `reject` 补上算子和闸门**（批次 1 只立了词汇）：`gmi.bake_rest_offset`；标了 `bake` 却没烘、
  或标了 `reject`，导出都会被拦；
- 权重截断量（第 5 个影响骨起被丢）从内部变量提成告警。

**批次 4 — 打包（P5）**

- **插件自带 UnityPy 与 Pillow**（`tools/package_blender_addon.py --with-unitypy`），装上就能一键打包，
  不用作者自己配外部 Python；老路一行没删，自带的 import 不了才回退。**版本钉死 `UnityPy==1.10.18`**
  （1.25 会在 `TextAsset.text` 上直接炸）；
- **修：`unity_route.py` / `topology_map.py` / `driver_presets.json` 没入库**，而打包只收 git 跟踪的文件 →
  打出来的 zip 缺模块、**插件整个装不上**。已入库，并给打包脚本加了通用闸门：`__init__.py` 顶层
  import 的每个模块都必须真进 zip；
- 验收 `tests/blender_vendored_pack_smoke.py`：产物与已发布实机验证过的 `chisaki-swimsuit.bundle`
  11 个对象逐项一致（容器字节不同是两边 lz4 版本不同，判据是比对象不是比 hash）。

**批次 5 — Runtime 收严（P6）** 改在 `gakumas-mod-runtime` 仓（`AddComponent` 预检 fail-closed、
失败即回滚、驱动器挂不上不静默替换成摇物），不属于本插件的更新日志。

**批次 6 — 物理（P7）**

- **`collisionMask` 预设改成逐档众数**（`tools/scan_vanilla_swing_bones.py --collision-mask vanilla --install`，
  48292 根原版摇物骨扫出来）。值以 `gakumas_mi/swing_presets.json` 的 `_collisionMask` 注为准；
  **这是实机实验档，画面判定还欠一次**；
- **`native_driver` 作用域化**：导出器以前收的是**类别集合** —— 作者在一行上选了裙，全模型每一根
  skirt 类别的新骨都跟着改走驱动器。现在收 `{骨名: 类别}`（`tests/test_swing_params.py` 钉住重导逐字节一样）；
- **置灰做对**：运行时只实现 Skirt / Frill / HumanoidSleeve 三类驱动器，选了「原版布料驱动器」而类别落在
  ribbon 时表单当场标 ERROR、导出拦下并说清怎么改。以前这种组合导出后那几根骨**既没驱动器也没摇物**
  = 不会动的哑骨，而日志全绿。

**批次 7 实机（dress-2219 / hmsz-cstm-0059）打出来的四个修复**

- **闸门 9：`undecided` 默认拦下导出**（`40819e4`），显式放行必须留痕，`undecided {count, allowed}`
  写进 sidecar 和权重报告。以前"还没决定"的骨可以静默进包；
- **内置名字规则不再泄漏到同组邻居**（`25c0457`）：`Leg_pendant_R` 与 `Lace_R` 恰好同锚点同链长被并成一组，
  lace 的 `follow_skirt` 带着腿上的挂坠一起去蹭裙摆末端摇物骨 —— 左右不对称就是它的指纹
  （`verify_ab_package` 那条 `Left=31 Right=34` 的 WARN 被当成"源模型本来就不对称"放过去过一次）；
- **物理指令按链算，不按结构组**（`cf12f94`）：结构分组在这个模型上一组装下 **57** 根骨（整条下半身），
  "整组一个指令"让整条裙子被误判成自建摇物，作者的 `follow_skirt` 一直被同组吞掉。
  自建骨 `69 → 18` 根，左右分布 `31/34 → 9/9`；
- **「链根自己摆」改成逐行开关 + 空摇物链硬拦**（`2109371` / `9bc92cb` / `c6fbcd2`）：链根是惰性锚，
  几何全长在链根上的短链（靴口花边）装了摇物也不动；空摇物链（垂到胯下、没人驱动的衣物链，
  原版此类 0.00%）现在直接拦下导出。

样本 2a 已定版收口（buildId `1375a006a8fc685f`，作者确认画面可接受）。逐次实验的叉点、量测和
失败尝试见路线文档 §A–§G；定版导出脚本在那个 mod 自己的工作目录里
（`mod-workspace/mods/work/hmsz-cstm-0059_body_dress-2219-TEST/export-final-2026-08-19.py`）。

### target-rig 批次 1：两把尺子 + 一行一组

现行路线见 [`research/ab-target-rig-architecture.md`](research/ab-target-rig-architecture.md)，
契约见 [`research/ab-target-rig-contract.md`](research/ab-target-rig-contract.md)。

- **新增「对齐体检」按钮（`gmi.report_rig_alignment`）：逐骨报关节位置差 + 静止朝向差。**
  朝向是作者唯一自查不到的东西 —— 静止截图完全正常，转身之后手臂转到身后、手指拉成面条
  （实机三次坐实，肩差 172°），而且它在肩和手指，不在头/手/脚/根骨这几个容易抽查的位置上。
  **朝向的定义是「本骨 → 人形子骨」的位移方向**：拿原版自己的身体标定过 —— 按骨自身坐标系的
  整体转角判，104 根里 69 根报 180°（Blender 侧根本没保留绕骨轴的 roll），原版自己全红；
  按方向判 104 根全绿 0.00°。位置差按**骨长比例**判且**最高只判黄** —— lossless 蒙皮把静止
  位置差当重定向吸收，会炸的是朝向；
- **同一个按钮报跨关节权重带**，与原版逐关节对比：场景里有带权重参考体就现算基线，
  拿不到才用扫出来的真值表（肩 13.3% / 肘 3.9% / 腕 6.2% / 膝 9.5%，两者复核逐项相同）。
  这是唯一能**预判**「肩膀会不会崩」的数字 —— Claymore 那副 rip 复量报肩 3.6%（原版 13.3%）。
  带宽**随"没映射的源骨怎么解析"变化**（同一网格：丢掉扭转骨报肩 0.0%、按导出解析报 3.6%），
  所以面板用的是与导出**同一份**解析；
- **骨骼映射表单改成一行一组。** 装饰骨按**结构**并组，一个骨名都不读：锚点（沿父链第一根
  身体骨）+ 链（分叉即断）+ 链长 ±1。原来一行一根骨，chisaki 那条 MMD 裙子作者手点了几十次；
  原来的分组正则剥 `left/right`，日语/中文/乱码骨名全废。行上的决定落到组内每一根骨，
  要逐根不同就按行尾的「拆开这一组」。chisaki 实测：**347 根带权重骨 → 75 行**（老版本 347 行），
  其中 280 根装饰骨并成 6 组、裙子那 260 根骨并成 1 行；
- **新增五档状态列**（`direct` / `merge` / `helper` / `bake` / `reject` / 未决定）。
  现在 72 根静默塌 `Hips` 的骨和真映射在表单里长得一模一样，排错只能去 dump JSON。
  `bake` / `reject` 还没有算子，先立词汇不给假开关（硬闸门在批次 3）；
- **报警语义改。** 装饰骨没有目标骨是**正常状态**（原版的飘带裙摆也没有），底部那句
  「还有 N 个骨没指定目标」改成「还有 N 组没决定怎么处理」；
- **修：外语命名的一圈裙摆全绑到同一根摇物骨。** `build_accessory_physics_remap` 里
  「逐骨蹭最近 / 按整组质心蹭」从 skirt/dress/cloth 词表改成看**链数** —— 一组多条链
  （一圈裙摆、一圈花边）逐骨蹭自己那边最近的，只有一条链才按质心。原来外语名字落进
  按质心那一档，40 根骨挤一根摇物骨；
- **参考骨架的朝向照搬原版。** 「导入参考模型与骨架」旧版只按 head→tail 摆骨、roll 留默认值 ——
  实测 104 根里 69 根（镜像那一侧）与原版差整整 180°，作者拿这副骨架对齐时看到的轴向是错的。
  现在一次写 `EditBone.matrix`，head / 方向 / roll 全按原版静止坐标系；
- **参考骨架补上无权重节点**：`Reference`、`Pelvis`、动态链锚点 `*_A`/`*_O`、摇物链根 `*_S`
  （atbm-cstm-0140 是 18 根），旧版整批丢掉。它们没有 bindPose，位置从最近的带权重祖先按
  **完整 local 矩阵**合成 —— 只累加 `localPosition` 会让带旋转的关节以下全错（151 个节点里
  57 个带非单位 `localRotation`）；
  **已存盘的 blend 里那副参考骨架不会自己变** —— 要拿到修好的朝向和补上的锚点，重新点一次
  「导入参考模型与骨架」；
- **新增 `tests/blender_reference_rig_smoke.py`（已进 CI）：参考骨架与原版逐骨 diff 为零。**
  查位置、朝向、父子关系、节点覆盖。实测仓内 profile 132 根 0.000119mm/0.000000°，
  资源库真骨架 150 根（无权重 18）0.000080mm/0.000000°；
- **新增「从相邻骨劈权重」（`gmi.split_weight_from_neighbours`）：给源模型没有的承重关节
  （锁骨/脖子/脚尖）劈出权重。** MMD/Biped 常见 Spine2 直接接 UpperArm、Head 直接挂 Spine2，
  这类骨在表单里永远找不到，只能从旁边那圈骨里劈。按原版身体在同一位置的权重分布分，三条规矩：
  只在作者和原版都认的骨之间重分（作者有、原版在那点没有的骨原样不动）；族内**总量守恒**，
  不重绘全身；原版只决定"分给缺骨多少"，剩下的按**作者自己的比例**分回去。
  验收是把原版自己身体的 `LeftShoulder` 整组删掉再劈回来，864 个顶点最差差 5.96e-08；
- **新增硬闸门：静止朝向差 ≥15° 拒绝导出。** 这个角度会 1:1 显示在游戏里 —— 静止截图正常，
  转身之后那块几何整个转过去（实机三次坐实，肩差 172° → 手臂到身后、手指拉成面条）。
  **A-pose 没烘、朝向差太大的源现在会被拦下**，报错点名是哪几根骨、差多少度、对哪根子骨；
  位置差不拦（lossless 蒙皮把它当重定向吸收）。hair/hairprop 不适用；
- **权重报告：按五档给权重占比**（直接保留 / 合并 / 辅助骨 / 未决定），画在「对齐体检」框里。
  让"尽可能保留源权重"变成数字，而不是凭画面猜；
- **导出多两条告警**：第 5 个影响骨起被截断的权重量（以前只在内部变量里，作者看不到，
  而截断后还会重新归一化 → 形变与 Blender 里看到的不完全一致）；承重关节/未映射骨的报错
  文案补上**两三条出路**（去表单指定 / 选装饰物理策略 / 从相邻骨劈），
  以前只写"去表单指定"，而源模型压根没有那根骨时作者去表单里永远找不到，卡死；
- **插件可以自带打包器：作者不用再装 Python / 装 UnityPy / 配 PATH。**
  Blender 自带的就是标准 CPython（4.2 与 4.5.3 都是 3.11.7），所以 PyPI 现成的 cp311 wheel
  直接能用。发布时 `tools/package_blender_addon.py --with-unitypy "<Blender>/4.2/python/bin/python.exe"`
  把 `UnityPy==1.10.18` + Pillow 装进插件的 `vendor/`，zip 10.8 MiB，装上就能一键打包；
  有自带的就同进程跑（不起子进程），没有才回退到「外部 Python」那条老路（老路一行没删）。
  **版本是钉死的** —— 补丁脚本按 UnityPy 1.10.x 的 API 写，pip 装最新的 1.25 会直接炸，
  让作者自己 pip install 就是版本轮盘赌。一份 zip 覆盖 4.2 与 4.5.3；Windows 之外没验；
- **修：发布 zip 缺模块，插件整个装不上。** `gakumas_mi/unity_route.py`、`topology_map.py`、
  `driver_presets.json` 没入库，而打包只收 git 跟踪的文件 → 打出来的 zip 一装就报
  `ImportError: cannot import name 'unity_route'`。三个文件已入库，并给打包脚本加了通用闸门：
  `__init__.py` 顶层 import 的每个模块都必须真的进 zip，缺一个就打包失败（以前只护着两个 JSON）。
  `driver_presets.json` 也补进了"运行时无条件读取"的必需列表；
- **修：「原版布料驱动器」的全局类别泄漏。** 以前导出器收的是"部件类别集合" —— 作者在表单
  一行上选了裙，**全模型每一根裙类别的新骨都跟着改走驱动器**，他点的是一条链、拿到的是整件
  衣服。现在按骨名限定（一行=一组=一条链）。默认不点名 = 完全不碰这条路径，现有成品重导逐字节一样；
- **「原版布料驱动器」选到没有驱动器的类别时不再静默出哑骨。** 运行时只实现三类
  （裙→Skirt、披挂→Frill、袖→HumanoidSleeve）；落在飘带类时，以前导出后那几根骨**既没有
  驱动器也没有摇物**，在游戏里根本不会动，而日志全绿。现在表单当场标红、导出直接拦下并
  说清怎么改（改类别或换「自建摇物链」），也**不偷偷替换成摇物**；
- `tools/scan_vanilla_swing_bones.py` 新增 `--collision-mask vanilla`：按原版逐档众数写
  `collisionMask`（skirt 1 / cloth 64 / sleeve 0 / ribbon 256，48292 根实测）。
  **默认仍是统一 -1**，等一次只改这一项的实机定性（窄裙看贴不贴腿）后再定案；
- **五档补齐 `bake` / `reject` 两档，不再只有词汇。** `reject`=这根骨处理不了，点导出直接拦下
  并点名；`bake`=先把静止形变烘进网格再像刚性一样并到父骨，标了没烘就导出也会被拦。
  烘焙是破坏性的，所以做到可见/可关/可量化/可撤销：按钮旁边永远摆着「回退烘焙」，
  改网格前把要动的顶点原坐标存在对象上，报告里给位移的最大值和平均值。
  两档只能**追加在枚举末尾** —— 老 .blend 存的是枚举整数下标，插在中间会把已有工程的策略整排错位；
- **量出来一件反直觉的事**：装饰骨自己偏多少，与"把它并到父骨"造成的静止形变**无关** ——
  并过去之后那些顶点按父目标骨摆，公式里根本没有装饰骨的变换（给它加 5cm 静止偏移，实测仍是
  0.000mm）。所以 bake 真正要处理的是**当前姿势**：导出器读的是静止网格，作者在视图里看到的是
  摆过姿势的样子，摆了姿势直接导出，出包的是没摆的那个形状 —— 这才是这条路线里真实存在的
  "静止形变"，现在会被量出来并烘进网格；
- **按几何判部件类型正式进生产**（`swing_category_by_geometry` 以前只有测试在调）：锚点（沿父链
  第一根身体骨）+ 同锚点链数 + 垂向，一个骨名都不读，判不出来才退回词表。按名字判只对恰好用
  本作命名习惯的源有效 —— 原神 rip 的 `Bone_HemA01_L`、MMD 的 `スカート` 词表都不认，整条裙摆
  会拿到最保守的飘带档（不建链），环形碰撞和限位全丢。作者点过的行永远优先；
- **节数不同的塌链现在会被标出来**（§7.3 档 3）：源 4 节手指塌进游戏 3 节这种，每根骨都有目标、
  权重也归一，**闸门永远抓不到**，只能标给人看。「对齐体检」里列出目标骨、源骨和权重占比；
- **新增 `tools/read_runtime_log.py`：把实机日志量成数字。** graft / droppedInfluences /
  swingDynamicBones / 300 帧动了几根 / 预检拒绝 / 空引用 / error，退出码非 0 就打印
  "不合格：<键名>"；它自己有 6 个自检（坏日志必须报、好日志不许误报）。
  实机一次成本高，所以"该看什么"提前写死，回来只跑一次这个脚本；
- 修：`tools/read_runtime_log.py` 自己的两个静默通过 —— `error` 写着"期望 0"、实测命中 2 行却
  照样打印"全部判据通过"（判定规则手抄的键名清单漏了它，现在规则必须恰好覆盖判据表，
  漏一项直接断言失败）；以及日志**跨会话追加**导致上一次跑的报错被算到这次头上
  （现在默认只判最后一个 `[BOOT]` 之后的内容，`--all` 才看整个文件）。两条都补了回归用例；
- 修：`tests/blender_ui_smoke.py` 的策略枚举断言从 `native_driver` 加进来之后就没更新过，
  这套 UI 回归一直是红的。
- **验证收口（2026-08-18）**：`112` 个 pytest 与 `5` 套 Blender 冒烟（4.2 / 4.5.3）全绿；
  下一次实机只剩批次 6 的 `collisionMask` 定性。

## 1.1.0 — 自建摇物骨：参数取自原版基准，飘带不再建链

- **新增 `gakumas_mi/swing_presets.json`：学马原生摆动参数基准表。** 由
  `tools/scan_vanilla_swing_bones.py` 扫 530 套原版 body bundle 得出（bundle 内嵌 typetree，
  字段按名字读，不是按偏移猜）。4 档部件（ribbon / cloth / sleeve / skirt）× 3 个链上角色
  （链根锚 / 中段 / 链尾）的 median 做默认值、min/max 备作导出闸门区间；
- **摆动参数写全。** 此前只写 `damping/stiffness/spring/mass/rootWeight/pendulum` 六项，
  其余交给运行时 `SetDefaultValues`。对照原版实测那是错的：`pendulumRange` **84.6% 取 1.0**
  （它是 pendulum 的作用范围，留 0 等于把重力项乘没了）、`wind` 84.6% 取 1.0、`useLimit` 88.3%
  是 1 且带真实角度限位。少这几项时骨在数据上"参数齐全"，实际既不下垂也不受风；
- **飘带 / 蝴蝶结不再建 `ActorSwingChain`。** 原版实测裙类 94% 挂链、披风类 54%，而飘带绳结类
  只有 2.6%——它们本来就是裸 `ActorSwingDynamicBone`，链是裙摆专用的环形碰撞解算。
  sidecar 新增 `swingChains` 段，宿主骨与按链长的分组在导出器离线算好，运行时照单执行；
- **骨骼映射表单新增「部件类型」列**：飘带蝴蝶结 / 披风褶边 / 袖口 / 裙裤下摆四档，决定取
  哪一档原版参数和建不建链；只在策略选了「自建摇物链」时可点。默认「自动」按骨名猜，认不
  出来按飘带处理（自由悬垂、不建链，最保守）。**点名链上任意一根即对整条链生效**——否则同
  一条链会混用两档参数。随骨映射 JSON 一起存读（新增 `swingCategories` 段，schemaVersion 2）；
- 试过做「摆动幅度」弱/标准/强三档，**实测证否后撤销**：把 `damping`/`stiffness`/`spring`/
  `mass`/`pendulum` 从原版分布一端拉到另一端，摆幅只动 ±35% 且方向与预期相反，它们不是决定
  幅度的主因。只保留标准档（原版中位数）。经过与下次该怎么查见
  [`research/ab-route-notes.md`](research/ab-route-notes.md) §12；
- **角度限位默认关闭。** 限位是按骨轴授权的：原版摇物骨的子骨一律在 local −X（X=扭转轴，
  所以锁成 `[0,0]`），而 MMD 源的子骨在 local −Z。照搬等于锁死一条真·摆动轴、再把另一条夹到
  ±30° —— 参数全对却纹丝不动。不做主轴置换（作者 rig 的骨轴可能任意斜向，猜错代价就是这种
  最难查的故障）；源模型显式给了 `useLimit` 的照它的来；
- **修 `useWindGlobalForce` 写成整数**：运行时 nlohmann 按 bool 读会抛 `type_error.302`，
  而那一抛是**整份 sidecar 作废、骨架 graft 整个跳过** —— 表现是网格根本没换、只有贴图生效。
  导出侧出真 bool，运行时两种都收；
- **不建分叉链**：`UpdateChainInfo` 只沿第一个子节点建层，一根骨带两个子分支时另一支永远
  进不了链层，而导出器却会按"最深那支"报一个链长 —— 静默建条只覆盖一半的链。检测到分叉
  直接不建（那些骨照样逐骨模拟，只是少了环形碰撞，安全降级）；
- **分类词表与扫描器同步**：`Gown`/`Shirt`/`Inner` 曾在扫描器算 cloth、在插件落 ribbon，
  于是自动模式用错参数还不建链。新增契约测试直接读扫描器源码比对，再分叉会当场红；
- 修一批评审指出的问题：托管引用写入走 GC write barrier（裸指针直写会绕过增量 GC 的写屏障，
  长时间运行可能丢引用）；骨复用改为**按归属作用域**（key = `modId | sidecar 指纹 | source`；
  同一角色层级下 body 包和 hair 包、乃至先后换同一部位的两个 mod，同名自定义骨都不再被后来者
  直接复用、跳过自己的父级与参数）；分类规则**顺序**也与扫描器对齐
  （`BeltChain`/`CapeRibbon`/`CollarBow` 这类两边词表都命中的名字，先判哪个就归哪类）；
  打包器缺必需数据文件时直接失败（此前缺文件仍会打出"成功"的 ZIP）；`swing_presets.json`
  与扫描脚本入库；
- 包验证器：摇物骨要写全 12 项参数（含碰撞体三项）；**`extraSwingBones`/`newBones` 也查**
  （链尾同样会被运行时建成动态骨，缺参数照样落默认值，此前只查 `bones[]` 会零告警放行）；
  新增 `swingChains` 契约检查（宿主/链根存在性、链根重复认领、链根的父必须是宿主、分叉拓扑）；
- 包验证器的两个类型漏洞：`chainLength: "2"` 此前被静默跳过整段比对（运行时按整数读），
  现在报错；`bones: 7` 此前让核包工具自己抛 `TypeError`，现在在唯一入口归一化成一条可读错误；
- 扫描器 `--limit N` 调试模式修复：局部样本不保证四档齐全，`build_plugin_presets` 缺档跳过
  而不是 `KeyError`；同时**缺档时拒绝 `--install`**，生产基线只能来自全量扫描。

### 运行时（gakumas-mod-runtime）

- **建骨建链搬到 graft 时（prefab 上）**，删掉 `RegisterBones` 里的列表追加和 SEH 兜底。
  `initialTransforms` 与 `swingDynamicBones` 是按下标并行的两张表，只往后者追加会让
  `RegisterBones` 取下标越界、整个注册中途夭折；而 `ActorSwingDynamicBone`/`ActorSwingChain`
  都实现 `IActorAnimationBone`，游戏自己的 `CampusActorAnimation.Initialize()` 会收走它们并
  保证两表同长；
- **新建的链要自己建层再补授权字段**：prefab 上 `AddComponent` 的链只有 `rootBones`，
  `OnEnable` 不建层（游戏自己的链在 bundle 里就带着序列化好的 layers）。现在在 hook 里调
  `UpdateChainInfo`，再按 1539 条原版链的实测补 `active`（layer>0 置 1）和 `radius`
  （0.010→0.015→0.025→0.030→0.033 逐层递增）。此前这两项停在 `ChainLayerInfo()` 默认值
  `active=0`/`radius=0.05`，等于链不参与模拟；
- 新增 `pendulumRange`/`wind`/`dynamicType`/`limitInfo`/collider 写入；
- **碰撞体与限位改在 graft 时自己 `new` 出来再写**，删掉整趟活体补写和那张全局
  `骨名 → 参数` 表。旧做法两个 mod 用了同名骨就互相覆盖参数、碰巧和原版骨同名还会去改
  原版的碰撞体。`UnityResolve::Class::address` 就是 `Il2CppClass*`，可以直接
  `il2cpp_object_new`。**2026-08-11 实机确认**：活体读回 `colliderRadius=0.0200` 与 sidecar 一致；
- **一根链根都没挂上的链会被销毁**：空链照样被 `Initialize()` 收进 rigData 然后什么都不驱动；
- 链层诊断日志按"这个角色有没有 mod 骨"门控 —— 未改装角色一行不打（此前每次
  `RegisterBones` 都遍历并记录该角色全部原版链）；
- 兼容 `manifest-v2.md` 里写过的嵌套碰撞写法 `swing.collider.{radius,type,collisionMask}`，
  只认平铺的话按旧文档产出的包会**静默丢掉整套碰撞体配置**；
- 新增诊断：`registration coverage`（mod 骨有没有进 `swingDynamicBones`、两张并行表是否同长）、
  `live bone`（活体字段读回）、`chain layer`（逐层 active/around/radius，游戏自己的链在同一份
  输出里天然是对照组）；
- **混合骨数组缓存改按 `modId | sidecar 全文指纹 | source` 判命中**。按 modId + 骨名比对不够：
  同一个 mod 原地更新、骨名一字未改而 TRS/摆动参数/`swingChains` 全变了，照样命中旧缓存；
- **锁只圈共享容器**。`BuildHybridBoneArray` 此前从缓存查询一直持锁到函数返回，把建 GameObject、
  `AddComponent`、建链这些托管调用全包在里面（堵住 `RegisterBones` 热路径，托管侧若同步重入
  相关 hook 还会死锁）；`BuildLayersForModChains` 则反过来，裸读全局骨名集合与后台 graft 的写
  构成数据竞争，现在先抄一份快照再调 `UpdateChainInfo`；
- **关闭与卸载会清理建骨状态**：`SetSessionModEnabled(off)` 丢掉该 mod 的混合骨缓存（renderer
  的骨数组已被还原，留着等于下次 ON 命中旧构建）；`Shutdown()` 释放骨 GC 句柄并清空骨归属、
  骨名与缓存三张表。骨归属记录在 OFF 时**故意保留**——key 里带 modId 与指纹，别的 mod 撞不上，
  清掉反而会让 ON→OFF→ON 每轮重建一套同名骨；已销毁的骨由复用处的存活检查兜；
- **修复管理页 ON 后回主页仍不生效、必须先进换装页的问题**：当前无目标 Renderer 时按
  `modId + source` 排队，`RegisterBones` / Renderer 材质生命周期到来后重试；原 Mesh 身份改为
  保留有界的近期多代记录，并排除 Runtime 自己的克隆。**2026-08-12 实机确认**：
  `hmsz-fuyuko-icu` 先写 `hotInstances=0`，返回主页后资源路径完成替换，再由
  `alreadyPatched=1` 正常清队列；无异常或重复应用。`atbm-cstm-0140` 的同分支尚未单独复验；
- 活体热 ON 只刷新现有角色的 Mesh、材质、骨绑定与碰撞体；新增摇物骨/链仍需重新进入场景，
  因为它们只在 prefab graft 与角色初始化阶段进入 Animation Rig；
- **`swingChains` 写了但不是数组 = 报错**（此前静默当作"没有链"，而导出侧验证器判它是 error，
  于是坏包在实机上看起来只是"不摆"）；反过来 `chainLength` 类型错不再作废整份 sidecar——它只
  进日志，由验证器在导出期拦；
- **资源装载那几张表补上锁**：`g_bundleMutex` 声明了却一次没用过，而它该保护的 bundle 句柄、
  已加载资源句柄、已变换网格、原生链已挂根四张表全在裸读写——资源装载会离开主线程，
  并发插入触发 rehash 就是随机崩溃。锁只圈表本身，绝不跨过托管装载调用（那会重入自己的 hook）；
- **卡住的热重载不再把全场景扫描摊到每一帧**：重试挂在 `Renderer.SetPropertyBlock` 这种逐帧
  逐 renderer 的调用上，而每次重试都要 `FindObjectsByType`。在主页开一个当前不在场景里的
  mod 就会让队列一直挂着——这是最常见的用法。现在节流到 250ms 一次，在飞标志也改成 RAII
  （中途 return 会把它永久留在 true，之后再也不重试）；
- **进程退出不再做收尾**：`DllMain` 的 `DLL_PROCESS_DETACH` 此前忽略 `lpReserved`，进程退出时
  仍去 `il2cpp_gchandle_free` 和写日志，而那时别的线程已被强杀、可能正死在 GC 锁或日志锁里 →
  退出期挂死/崩溃。只有 `FreeLibrary` 卸载才真收尾；
- **`InstallHooks` 的 else 挂错了 if**：属性块方法解析失败时没有 else，四个贴图覆盖 hook 被
  静默跳过且 `hooksOk` 仍是 1（表现是贴图覆盖全失效而日志全绿）；而 `set_materials` 缺失时
  报的却是属性块的错误信息。两边各自归位；
- **`AssetBundleRequest` 记名字改成覆盖写**：`emplace` 遇到已存在的 key 不写，而 request 指针
  会被复用——上一条没被消费的记录会让新请求顶着旧资源名走替换；
- **`Shutdown()` 补齐**：bundle / 已加载资源 / 网格克隆三批 GC 句柄，加载历史、已变换网格、
  原生链根三张表，以及热重载队列和它的两个原子标志（`inFlight` 停在 true 会让重新
  `Initialize` 之后的重试永久失效）；
- **`mod.json` 的 `runtimeProtocol` 现在会校验**：sidecar 一直是硬校验，manifest 却照单全收，
  而导出器写它、验证器把不等于 1 判成 error。写了就必须对得上；没写的老包照常放行。

## 1.0.0 — 首个正式稳定版

- 将插件从开发预览提升为正式稳定版，固定 AB bundle 单路线和三步作者流程；
- 7 个成品（6 body + 1 hair）全部完成导出、安装和游戏实测，workspace 的作者来源、发布包、
  buildId、哈希和资源数量同步为同一发布基线；
- 当前回归基线为 35 项 pytest、4 个纯 Python 冒烟/回归脚本及 Blender 4.2/4.5 闭环；
- 包验证器现在正确接受 release 包目录或 `bundle-src` 目录；
- 正式发布包附带项目许可证、第三方许可说明和 3DMigoto 修改补丁来源说明；
- 明确能力边界：刚性跟父骨与跟裙摆可交付；自建摇物链尚无稳定画面级成功案例，作为
  1.0.0 之后的下一个开发重点，不再用建链日志替代可见效果证据。

## 0.9.3 — 卡住实际制作的五个修复

> 这一版的每条都来自真实作者会话：dress-2219（`hmsz-cstm-0059`）和 mltd-stage
> （`ttmr-cstm-0119`）。7 个成品 mod（6 body + 1 hair）在本版下全部实机确认；
> 仍未解决的是**自建摇物链的装饰件在游戏里不动**，见
> `research/current-status-and-roadmap.md`（已于 2026-08-22 删除） 的「未解决：自建摇物链」。

### 新增骨的四个约定错误（装饰件先炸成黑刺、再坍缩、最后锁死不摆）

源专属装饰骨（SCSP 的蝴蝶结、缎带等）由运行时按 sidecar 现场新建。这条路 0.9.0 起就在，
但此前没有任何一个 mod 真正用过——之前的做法是把装饰件刚性绑到身体骨上，那 26 根骨权重为 0，
错误数据挂在没人引用的骨上，自然看不出来。dress-2219 是第一个真正给它们刷权重的 mod，
四个约定错误一次性全暴露：

**① bindPose 写反了（转置）**

`_matrix_json()` 按 `M<行><列>` 写，而 `_bind_pose_matrix()` 和 `patch_unity_bundle` 都按
AssetStudio 约定的 `M<列><行>` 读（平移在 M30..M32）——**写入端是转置的**。

游戏原始骨的 bindPose 直接来自 Mesh JSON，不经这个函数，所以身体一切正常；只有**插件自己
新增的源专属骨**中招。dress-2219 实测：26 根装饰骨（胸口/背后蝴蝶结、缎带）的绑定姿势全错，
顶点被拉离约 1 米，画面上是一堆贯穿角色的长条黑刺。走刚性映射到身体骨的装饰件（如鞋花
映射到 LeftFoot）不受影响。

**② localRotation 的分量顺序反了**

Unity 的 `Quaternion` 序列化顺序是 `(x,y,z,w)`，运行时按 `Quaternion(v[0],v[1],v[2],v[3])` 读；
导出端写的是 `list(matrix.to_quaternion())`，而 mathutils 迭代出来是 `(w,x,y,z)`。实测
`Spine_Bow_R_B0` 在 blend 里 w=0.3392/x=-0.184，包里写的正是 `[0.3392, -0.184, ...]`。
新增 `_quaternion_xyzw()`。

**③ 新骨链的根用了作者骨架的相对变换**

运行时把新骨挂在**游戏骨架**的父骨下，但导出写的 local 是相对**作者骨架**父骨的。两套骨架的
静止姿势并不相同——dress-2219 实测 Hips 差 38mm、Spine 差 83mm、Spine2 差 67mm——于是骨被
放到别处，而 bindPose 记的是作者世界位置，两边对不上就把装饰件拉变形（蝴蝶结坍缩成一片）。

新增 `_retarget_new_bone_roots()`：链根按 `inverse(游戏父骨静止世界矩阵) × 作者骨世界矩阵`
重算 local；链内部（父也是新骨）不动，那一段父子都按作者世界摆放，相对关系本来就自洽。

**效果**：用真实 blend 模拟导出，26 根装饰骨的运行时位置与 bindPose 的偏差从
**平均 208.2mm / 最大 572.4mm 降到 0.0mm**（模拟出的修复前数值与实际出问题的包逐位吻合）。

`tests/blender_smoke.py` 加了三条断言：bindPose 写入→读取往返、四元数 w 在末位、
链根重算后世界位置回到作者摆放处。

**④ 新骨的 swing 缺 `rootWeight` / `pendulum`**

这两项不给，运行时 `SetDefaultValues` 会留下 `1.0` / `0`——即「完全刚性跟随根骨 + 没有重力项」，
装饰件被锁死在作者摆的静止姿态上翘着不下垂。默认值改为游戏自己裙摆骨的实测值 `0.3` / `0.001`
（runtime 的 `LocalIpBoneSwing` 注释）。源模型自带 swing 参数时仍用源的，只补这两项
（`build_source_extra_bones()` 由整体替换改成 `{**默认, **源}` 合并）。

> ⚠️ 装上这四项修复后 dress-2219 重导，日志显示数据链路完全正常
> （`createdBones=26 swingPrepared=36 droppedInfluences=0`、链尾齐全、3 条链注册成功），
> **但装饰件在游戏里仍然不动**。这是 0.9.3 未解决的问题，成品当前用刚性/跟裙摆绕开，
> 排查经过与下一步见 `research/current-status-and-roadmap.md`（已于 2026-08-22 删除）。

### SCSP 预设：`_1` 后缀不再挡住预设查表，并补上脚趾

SCSP 导出的骨名是「变体名 + `_1`」。此前只有「剥掉 `_1` 后能直接命中目标骨名」这条路通，
需要再查预设表的（`*_rot` / `Elbow` / `Clavicle`）全部落空：dress-2219 上 18 根带权重的
身体骨、合计 3514 权重被误判成装饰骨。预设表里也一直没有 `Toe → ToeBase` 规则，于是脚趾
撞承重关节闸门、导出被拒。

- 新增 `_preset_lookup()`：原名查不到时剥掉 `_1` 再查一次；预设打分 `_best_preset()` 同步，
  否则整套骨名都带 `_1` 的源会让每张表都得 0 分、选表全靠嗅探碰运气；
- scsp 预设加 `LeftToe → LeftToeBase`、`RightToe → RightToeBase`。

修完 dress-2219 不填任何手写映射表，自动映射 146 条，承重关节 21/21 全覆盖。

### 「生成完整配置档」报 'operatorBytes'

点「生成完整配置档」时报一句没头没尾的 `'operatorBytes'`（Python `KeyError` 的原样输出）。
0.9.0 删掉 3DMigoto 逆蒙皮路线时，`summarize_bind_mesh()` 不再产出那个 ~40 MB 的 R32 逆算子
buffer，返回值里的 `operatorBytes` 也一并没了，但两处还在读它：
`core.complete_inverse_skin_profile()` 的返回字典、以及算子里那句「逆算子 X KB」的完成提示。

- **配置档其实已经写好了**：崩溃发生在 `profile.json` 落盘之后、拼提示语的时候。受影响的是
  「配置档目录」没被自动填上（body），以及发型的 hairprop 分量没被合并（hair）。
  已经踩到的人可以手动把「配置档目录」指向抓帧目录下的 `GakumasMI-profile\`，不必重跑。
- 去掉两处对 `operatorBytes` 的读取和完成提示里的「逆算子 X KB」——那个数字已经没有对应物了。
- **为什么没被测试挡住**：`tests/blender_ui_smoke.py` 里 mock 的返回值自己造了一个
  `operatorBytes: 1024`，测试喂假键、算子读假键，两边自洽地错。stub 已改成与真实返回一致，
  再出现读不存在的键会被这条冒烟拦下。

### 目标服装有 3 段时报「材质槽 1 缺少 t0 基础色贴图」

**原版 body 不止 1~2 段**：530 套 dump 里 186 套 1 段、326 套 2 段、**18 套 3 段**
（`cstm-0119` 全 13 个角色，另有 `hski-0070/0071/0074`、`kcna-0131/0132`、`fktn-0071`）。
`ttmr-cstm-0119` 的第 2、3 段是腰上一圈 128 顶点的薄环和胸前 179 顶点的小件。

导出按 `range(目标段数)` 逐段要一套 t0/t1/t4，而段 1 对 body 一律当成原生 co——于是**没做
co 部件的工程**会被一个自己根本没用到的空段拽去要「co 基础色 t0」，空着就报
`材质槽 1 缺少 t0 基础色贴图`。

改成只给**作者网格真的用到的段**出贴图（`data["materials"]` 归并后出现过的段）。空段照样
会被 `_bundle_submeshes` 造出来，但 0 面片、不可见，不出贴图条目就保留原版材质。真标了
「原生 co」的工程 `materials` 里会出现段 1，co 贴图照旧必填，行为不变。hairprop 的同款
`range(prop_slots)` 一并改掉。mltd-stage（`ttmr-cstm-0119`）已用本修复导出并实机确认。

### 工具：`export_all_body_json.py` 改走 typetree，骨架导出覆盖率 99/530 → 全部

这个 UnityPy 版本上 `SkinnedMeshRenderer.m_Bones` 用类型化的 `.read()` 取到的是空列表，
于是 530 个 body 里 **431 个被误判成「没有带骨骼的 SkinnedMeshRenderer」而跳过**——数据一直
都在，只是读法不对。全流程改成 `read_typetree()` + 按 `m_PathID` 手动解引用（`_tree()` /
`_pptr()` / `_tt_vec3()` / `_tt_quat()`），顺带把逐对象的 try/except 兜底去掉，读不到就是真读不到。

## 0.9.2 — 发型 + 发饰真正合并成一个包

### 发型和发饰现在能一次导出成一个包（实机验证通过）

此前文档写的是「同时有发饰网格 → 点一次导出自动合并成一个完整包」，但**导出器从来只写一个
renderer**，这条从未真正实现。实际做出来的只能是两个半截包：

- 只导发型 → 包里只有 `Geo_Hair`，游戏里发饰是原版；
- 只导发饰 → 包里只有 `Geo_HairProp`，游戏里**发型退回原版**（实测日志 `pairs=1`），
  而且 `part` 被写成 `body`（`"part": "body" if component_id != "hair" else "hair"`
  没考虑 `hairprop`），运行时按身体 mod 处理。

现在：

- `write_bundle_source` 新增 `extra_components`，一个包可带多个 renderer。命名对齐实机
  验证过的合包格式——副 renderer 的 source 是 `{source}__Geo_HairProp`，geojson 与
  sidecar 跟着这个名字走，主 renderer 继承顶层 `source`/`skeleton`，两份 sidecar 盖同一个
  `buildId`（runtime 是逐 renderer 读的）；
- 导出面板新增 **「发饰对象」**（hair 包时显示）：激活发型网格 + 选上发饰 = 一个完整包。
  留空则只换发型，并明确提示“发饰保持原版”；
- **单独激活发饰导出直接报错**，不再默默产出装上去只生效一半的包；
- `part` 修正：`hairprop` 归 `hair` 部位。

### 材质槽归并不再只对 body 生效

作者网格的多材质槽（发型的 `m_FrontHair` / `m_BackHair` / `m_InBack` 等）此前只有 body
会归并到目标段数，hair/hairprop 直接按原槽数导出，带着 3 个 submesh 撞进模板补丁，只报一句
`submesh count changed: template=1 input=3`。现在所有部件都归并（`co` 仍只对 body 有意义）。

### 两处误导性提示

- 绑定体检量的是 fingers / forearm，只对 body 跑。此前在发型上也跑，必然“无法评估”，
  还附一句“作者骨名可能没映射到游戏骨名”，是纯假警报；
- 模板补丁失败时不再一律先甩锅“是否装了 UnityPy/Pillow”，先亮子进程的真实异常，
  只有输出里确实出现 `ModuleNotFoundError` / `ImportError` 才提示装依赖。

## 0.9.1 — 网盘素材包上线、安装路径更正与文档整合

**只有文档和资源分发变化，插件代码行为与 0.9.0 相同**——但这两项都会直接决定你能不能做出
成品包、装进去能不能被读到，所以单独发一版。

### 拿得到模板了

打成品 `.bundle` 必需的 **R32 模板**（530 body + 378 hair）和数 GB 的**网格 JSON 资源库**
体积太大不放 GitHub，此前一直没有公开下载——没有模板，导出只能停在 `bundle-src\` 中间
产物。现在整个 `libraries` 文件夹已放上百度网盘，链接和各子目录填进面板哪一栏见
[安装与资源「下载」](docs/wiki/1-安装与资源.md)。只换装不重导 JSON 的话
`all_body/` 可以不下，省 4.6 GB。

### 安装路径更正（**装错位置就不会生效**）

换模运行时已经把根目录从 `gakumas-local\`（那是汉化插件的地盘）挪到 `gakumas-mod\`，
**没有回退**。此前所有文档、以及本发布包里的「安装说明.txt」写的都还是旧路径，照着放
根本不会被读到。现在统一为：

```text
<游戏目录>\gakumas-mod\mods\<模组标识>\
```

用 chinosk6 的 `gkms-localify-dmm` 加载则仍是它自己的 `gakumas-local\local-files\mods\`，
两个目录互不读取。日志路径同步更正为 `gakumas-mod\mod-plugin.log`。

### 文档更正（都是会让你查错方向的）

- **承重关节闸门是 21 个，不是 14 个**。此前所有页面写的 14 且名单不全，漏了 `Spine1`、
  `Neck`、`Head`、左右 `Shoulder` 和左右 `ToeBase`——被这几根拦下时，翻遍文档找不到它们
  属于闸门。发型不受影响（与发型骨架交集为 0）。
- **没描边怎么修**改对了：此前让你去选一个**已经不存在**的「衣物常量」档。实际按部件分三种
  ——body 用 `描边颜色`（默认「取自基础色」，需要步骤②先填 t0，不需要参考模型）；只有 hair
  才从带权重参考网格拷描边字段，**导出 hair 必须保留参考模型**；hairprop 按材质槽写常量。
- 贴图填写是**步骤②**，不是步骤③（0.9.0 收成三步后没跟着改）。
- 游戏内 Mod 管理 UI 已并进 `xinput1_3.dll`，不再有独立的 `xinput9_1_0.dll`。

### 仓库整理

文档从 4239 行 27 份收到 3645 行 26 份：新增「反面教训汇总」作为已排除路线、作废做法和被
推翻结论的唯一出处；插件 README 不再重抄 wiki；透明材质记录并入 AB 路线笔记。

## 0.9.0 — 只做 AB bundle：骨映射表单、承重关节闸门与肤色对齐原版

跳过 0.8.x：本版一次性合入三批改动，其中「移除 3DMigoto 路线」是不兼容的工作流变更。

### 发布方式：合并成一个包

- 插件与抓帧环境**合并为一个 `gakumas-mod-toolkit-0.9.0.zip`**，内含
  `blender-addon/gakumas_mi-0.9.0.zip` + `3dmigoto_gkms/` + 一页纸安装说明；
- 两条 tag 线（`gakumas-mi-v*` / `3dmigoto-gkms-v*`）合并成一条 **`vX.Y.Z`**，
  版本号统一跟插件走；两个 release workflow 合并成一个；
- 去掉 Inno Setup 安装向导，抓帧环境改为直接拷文件——不再需要 Windows runner 与 .NET；
- 仓库目录 `3dmigoto-gkms/` 改名 `3dmigoto_gkms/`，与发布包内的目录名一致。

### 肤色自动对齐原版

作者模型的皮肤底色几乎不会正好等于原版。脸和头发用的是**原版贴图**，身体是作者的，
不对齐脖子上就有一道明显色差断层。这一版把校准做进插件，不再需要每个 mod 写一次性脚本。

- **新增开关「肤色对齐原版」**（默认开，在「按材质槽类型处理贴图」面板）。点烘焙按钮时，
  把材质类型标为**皮肤**的区域在线性光下整体缩放，使其主色调对齐原版身体肤色。
  t4 本来就从 t0 派生，会自动跟着修正。
- **校准后的 t0 另存并回填到「基础色 t0」栏，不改作者原文件**；想回退把那栏改回自己的路径即可。
- **`core.VANILLA_SKIN_TONE = (254, 230, 218)`** —— 实测跨角色是同一个常数：atbm / hmsz /
  fktn / jsna 共 16 套服装、58,651 个皮肤顶点，4 级量化众数只在 `(254,230,218)` 与
  `(254,234,218)` 之间摆动，即一个量化桶以内。**每角色的肤色差异走 `_RampMap`
  （`t_chr_<角色>-base-0000_rmp`），不在 albedo 上**，所以不需要按角色查表。
- **用众数不用均值**（`core.dominant_tone`，4 级量化）。皮肤区里画进了阴影/AO 细节，均值会被
  拖低约 28 级：原版 atbm 皮肤众数 `(254,230,218)`，同一批采样的均值只有 `(226,206,199)`。
  按均值对齐会把整块皮肤压暗并去饱和 —— 实机试过，画面明显发灰白。测试里锁死了这一点。
- **取样与应用两个口径分离**：取样按**网格 UV**（与常数的测法同口径），应用按**光栅化皮肤区**
  （含 dilate 外扩，岛边不留色阶）。面积口径不能用来取样 —— 实测同角色不同服装能差 60 级。
- **失败明确报告不静默**：采样近黑（材质类型标错、UV 落在空白区）会打「肤色未校准（皮肤采样
  近黑 …，材质类型可能标错）」，不会把非皮肤区刷成肉色。
- 按钮 / 面板 / tooltip / 完成提示同步改名为「按材质生成 t1/t4 并校准肤色」，
  完成提示在校准生效时显示「已设为导出 **t0**/t1/t4」。
- 新增 4 组单元测试（`tests/material_bake_smoke.py`）：均值 vs 众数、只动皮肤区不碰 alpha、
  已对齐的图不动、近黑采样不炸也不刷成肉色。

**验证程度：** 千咲泳装（`atbm-cstm-0140`）实机确认过。校准输出与实机验证通过的那版贴图
**逐像素相同**（max diff 0），但**插件面板本身没有人在真 Blender 里点过**，
`blender_ui_smoke` / `material_bake_blender_smoke` 未跑。

**已知盲区：** `co 基础色 t0 / m_bdyco` 走独立的 `co_base8`，不参与校准。原生 co 是镂空装饰件，
正常不含皮肤；若把皮肤材质标成「原生co」，它不会被校准也不会报错。

### 移除 3DMigoto 路线，插件只做 AB bundle

彻底放弃 3DMigoto 逆蒙皮路线，不再是"两条路线并存、按开关切换"，而是**整体删除**。
理由：AB 路线保留作者模型自带权重，而 3DMigoto 路线必须传权，两者摆在同一套编号流程里
会让 AB 作者顺着编号点下去、用猜的权重盖掉手刷的权重（0.9.0 发布前的实战中就发生了）。
留一个用不到的路线等于把坑留在原地。

- **UI 从四步变三步**：`① 准备配置档 → ② 准备材质 → ③ 导出 AB bundle`。原「② 绑定模型」
  面板整体删除（上一版加的「输出路线」下拉一并删掉——不需要在两条路线之间选了）。
- **删除的算子**（11 个）：`transfer_profile_weights` / `transfer_profile_weights_smart` /
  `transfer_hairprop_weights` / `transfer_hairprop_weights_smart` / `bind_hairprop_rigid` /
  `select_high_risk_vertices` / `validate_mesh` / `export_mesh_mod` /
  `export_inverse_skin_mod` / `export_validated_mod` / `export_texture_mod`。
- **删除的模块与函数**：`gakumas_mi/weight_transfer.py` 整个文件；`core` 的
  `write_inverse_skin_package` / `merge_inverse_skin_packages` / `write_texture_package`
  及随之成为孤儿的 16 个内部函数（mod.ini 生成、landmark 绑定块、cover 处理、
  `validate_index_mesh` 等）。
- **删除的属性**：`gmi_cover_image`（预览图只有 3DMigoto 包需要）、`gmi_transfer_risk_distance`、
  `gmi_texture_key` / `gmi_texture_file`、`gmi_output_route`。
- **删除的测试与脚本**：`tests/mod_ini_contract.py`、`tests/weight_transfer_smart.py`、
  `tools/reweight_hski_fbx_mod.py`，CI 里对应两行也去掉；`tests/blender_smoke.py` 收敛成
  只跑 bundle 闭环，`tests/blender_ui_smoke.py` 改成**反向断言** UI 里一个 3DMigoto 入口都不剩。
- 代码净减约 1100 行。3DMigoto 仍是**抓帧工具**（做配置档必须用它抓帧），这个依赖保留。

### 骨映射表单 + 承重关节闸门

> 本条目覆盖 2026-07-26 一轮 MMD→AB 实战（星仪·大国主 PMX → `fktn-othr-0002`）暴露的问题。

**预设从 4 家扩到 8 家，选表改成打分**

- `auto` 不再靠几个探针名嗅探单一家族，改成**逐张预设表试算命中数、取最高**（嗅探只用来
  打平手）。此前探针没命中就整张表空转——我自己写测试时就中招了。副作用是以后支持一种新
  命名规范＝**纯加一张表**，不用再加嗅探分支。
- 新增 **VRM/VRoid**（`J_Bip_*`，`J_Sec_*` 归装饰骨）、**3ds Max Biped**（`Bip001 *`，
  游戏拆包最常见）、**Auto-Rig Pro**（`*_stretch.l` / `spine_0N.x`）、**英文 Humanoid
  同义词**（`UpperArm`/`LowerLeg`/`Thigh`/`Calf`/`Forearm`/`Clavicle`…）四张表。
- 八个家族的身体骨现在全部 100% 零手工映射，且都不触发承重关节闸门（`pytest` 断言守住）。
  修复前实测：VRM 0%、Biped 0%、ARP 0%、英文手搭 54%。

**覆盖率：从"赌命名规范"改成"按构造 100%"**

- 新增**骨骼映射表**（收三步后位于步骤③）：作者直接指定「哪根源骨对应哪根游戏骨」，行内下拉可打字
  搜索目标骨。预设退化成**预填**——MMD/Mixamo/Rigify/SCSP 扫描后一行都不用碰；
  VRM(`J_Bip_*`)、3ds Max Biped(`Bip001 *`)、Auto-Rig Pro 等没有预设的骨架靠点选，
  实测约 21 行覆盖全身。数据出口沿用已有的 explicit 通路，后端零改动。
- 同一张表第二列是**装饰骨物理策略**（自动/刚性跟父骨/自建摇物链/跟裙摆），替代手写
  `physics-override.json`；实测与手写 JSON 结果逐条一致。骨映射与装饰物理存在同一份
  JSON 的 `bones` / `physics` 两个键里。
- **硬闸门**：21 个承重关节（Hips/Spine/Spine1/Neck/Head、左右 Shoulder-Arm-ForeArm-Hand 与 UpLeg-Leg-Foot-ToeBase）任一没拿到
  权重就拒绝导出并点名。此前源骨名认不出来时是**导出成功、进游戏才废**（实测整只手 100%
  被钉在 `Spine1`、上臂挂在袖子摇物骨上，全程零警告）。判据只看游戏侧，与源命名无关；
  与目标骨架取交集，所以发型/发饰导出永不触发（实测交集为 0）。

**MMD 源模型：预设此前对 mmd_tools 导入的模型全程空转**

- `腕.R` 折回 `右腕` 再查表。mmd_tools 是 PMX→Blender 的事实标准导入器，它一律输出
  `.L/.R` 后缀，而表里写的是 `左腕/右腕`——修复前 87 个加权组只有 5 个映射成功（23% 权重），
  手臂、腿、手指全部落到装饰骨位置匹配上。**这条影响所有 MMD 模型，不止某一个。**
- 补齐 MMD 半标准骨：`足D/ひざD/足首D/足先EX`（占身体权重 24.6%，腿全刷在这上面）、
  `腕捩1-3`、`手捩1-3`、`腰`。
- `手捩*` 改指 `ForeArm`（原为 `Hand`）。捻骨只继承手腕转动的一部分，映射到 `Hand` 会让
  肘后 4cm 起整条小臂吃满手掌旋转 → **肘部拉伸扭曲**；改后 `Hand` 的接管点回到 |x|0.48，
  与游戏原版同位置。
- `mmd_edge_scale` / `mmd_vertex_order` 自动忽略。它们不是骨（每顶点权重 1.0），此前会让
  导出报错，而按提示填兜底骨 `Hips` 会把整个模型塌成刚体。

**文档**

- README 删掉「蒙皮转权」「导出模组」两整节，章节重编号为 ①②③ + 骨骼映射表；
  原本教 AB 作者去传权的说明（§3 全节、§4B 的「必须带配置档权重」前置）随之消失。
  传权会**用猜的权重盖掉手刷的权重**（实测某模型传权后手指区 p99 2.99 → 6.96）。

**t1/t4 导出成纯黑（影响此前所有 AB mod）**

- `_export_bundle_png` 在写完像素之后才设 `colorspace_settings.name`，赋值会重建图像缓冲、
  丢掉已写入的像素（**赋同一个值也丢**，`image.update()` 拦不住），存盘得到纯黑。t0 是 PNG
  走 `copy2` 所以幸免，t1/t4 从烘焙的 DDS 转 PNG 必中 → 游戏里 ShadeColor 全黑、整身发暗。
  改为写像素之前设 colorspace，之后不再触碰。实测导出 PNG 与烘焙 DDS 逐像素相同。

## 0.7.8 — Hair Coverage Alpha 默认修正与步骤③贴图指南

- Hair `t0.A` 默认改为保留作者 Alpha，修复刘海眉毛/眼睛无法透出的问题；仍可关闭选项将 PNG
  Alpha 清零，作为不需要 Coverage 的兼容路径。
- 新增步骤③ Body / Hair / HairProp 贴图路径、通道和准备要求文档，并链接到主页 README。
- 修正 Hair/HairProp Alpha、t1/t4 与发饰独立贴图的开发者说明。

## 0.7.7 — 发型贴图烘焙隔离与 Alpha 安全

- Hair、HairProp 与 body/co 的 t1/t4 烘焙改用组件独立临时文件名，修复完整发型制作时
  后烘焙的 HairProp 静默覆盖 Hair PackedMask/ShadeColor，导致旧 t6 蓝纹和错位灰影。
- Hair PNG t0 默认在转 DDS 时将 Alpha 归零；只有明确制作了 coverage Alpha 时才开启
  「使用 t0.A 发丝覆盖率」。HairProp 始终保留作者 Alpha。
- Hair/HairProp atlas 未覆盖区统一使用 A=0 的安全 t1，步骤③同步修正 t1.A/t4 说明。
- Blender 材质闭环新增组件文件隔离、Hair t1.A=0 与 PNG Alpha override 回归。

## 0.7.6 — 共享基础发型选择器稳定化 + 工作流面板重构

- 侧边栏按工作流重构：删除「当前步骤」下拉，① ~ ④ 改为常驻可折叠子面板，
  四步一览、随时跨步查看；步骤 ① 默认展开。
- 全部用户可见文本重写：属性名/悬停说明、面板文案、操作器名称与说明、报错提示。
  每条悬停说明讲清"是什么、哪里来、漏填/填错的后果"（t0 漏填=颜色错乱、t1/t4 的
  A 通道是数据不是透明度、风险距离顶点属正常待复核、兜底骨填 Hips 等实战踩坑
  全部写进 tooltip）；错误消息统一指向具体步骤和按钮。
- 导出面板补上一直缺失的「骨骼映射 / 未映射骨骼兜底」入口（MMD 等外部模型
  残留控制/物理骨权重时兜底骨填 Hips）。
- 导出面板在 t0 基础色留空时显式警告（漏填不会报错，而是 mod.ini 静默不生成
  ps-t0 → 游戏内颜色错乱）；发饰网格已绑定但发饰 t0 留空同样警告。
- Blender 插件的制作目标保持为「身体 / 发型」两项；发型自动读取配套 hairprop，作者可只替换
  发型，也可在同一流程中同时准备发饰并自动合并为一个完整发型包。
- 发型导出若 profile 同时包含 hairprop，会在 hair override 前匹配配套 hairprop 的
  `IB hash + firstIndex`（manifest 另记录 indexCount）；未匹配的其它发饰保持原版，不再被
  共享基础 hair 无条件覆盖。
- 完整发型包的 manifest 记录 `components: ["hair", "hairprop"]`、精确游戏资源 `targets`
  和 `runtimeSelector`；管理器显示组件组合，不再把完整包误显示成旧的 `hair.weightedMesh`。
- 当前秦谷美铃 hair-0023 圆香波波头与发饰已合并为一个完整包；旧的两个独立包已移除。
- 发型选择器改为运行时稳定实现：基础发型只在配套发饰绘制的那一帧替换。此前的实现有三处
  会失效——① 完整包导出误把 Operator 类当实例调用（`GMI_OT_...().execute()`）导致「校验并
  导出模组」直接报 `bpy_struct.__new__` 崩溃；② 合并完整包时把发饰的 `[Constants]` 整块删掉，
  发饰段引用的 `$enable_/$..._layout/$..._probe` 变量未声明，游戏内满屏 `Unrecognised
  identifier`；③ 发型选择器与发饰替换挂同一 IB hash，靠 `allow_duplicate_hash` 并存，但游戏用的
  3DMigoto 分支的 TextureOverride 不认这个键 → 两个 override 互相覆盖，选择器不触发，发型永不替换。
  现改为：选择器 `match=1` 直接注入发饰自己的那个 TextureOverride（全程唯一挂此 hash），
  每帧末由 `[Present]` 清零 latch；body landmark 不再中途清零（避免夹在发饰和发型 draw 之间导致
  主 pass 漏替换）。发饰的 `[Constants]` 声明并入发型 `[Constants]`。
- 发型多候选消歧：基础发型网格常被多套发型共用（同顶点同索引、仅蒙皮骨架不同），资源库靠顶点数
  无法区分时，改用抓帧里同时出现的配套发饰顶点数选中正确的 bundle。
- 侧边栏移除 ①~④ 步骤的「下一步：…」提示行——带右向三角图标，易与可折叠面板的折叠三角混淆。

## 0.7.5 — UI 收敛为身体 / 发型，附属组件改为默认配套组件

- 制作目标只保留「身体」「发型」：`m_bdyco` 是身体材质槽可选的透明/镂空路径，
  `Geo_HairProp` 是发型 profile 默认配套的发饰组件，不再暴露为第三个顶层目标。
- profile 的逆蒙皮配置下沉到 component；一个发型 profile 可同时保存 hair 与 hairprop
  各自的 VB/IB、drawcall、骨架、贴图和逆算子，并兼容旧单组件 profile。
- 默认 HMSZ 发型 profile 合并为 hair + hairprop 双组件；是否替换发饰由作者网格和材质决定，
  不再使用「包含配套发饰」复选框。

## 0.7.4 — hair/hairprop 语义转正：发型替换全链内建（圆香波波头实机校准）

以 scsp 圆香波波头 + 三件发饰 → hmsz-hair-0023 的全程实机迭代为校准样本
（踩坑总表见 [`research/hair-pipeline.md`](research/hair-pipeline.md) §7）：

- **「头发」材质预设按实测修正**：t1 = (0.263, 0.125, 0, **A=0**)——hair 的 t1.A 不是
  body 的 AO，写 255 会打开暗面项、漏出未替换的原版 t4（蓝紫阴影）；光滑度写高会以
  黄绿色漏进阴影。t4 改为逐通道冷阴影 `linearMul`：`t4_lin = base_lin × (0.378, 0.367,
  0.474)`，替代 body 的单一 darken。中性 t1 在 hair 组件下也自动走 A=0 常量。
- **PNG→DDS 按语义选格式**：t0/t4 = sRGB(DXGI 29)、t1 = 线性(DXGI 28)。此前 t1 一律
  sRGB 会被 GPU 二次解码（阈值 0.45→0.056），整体暗沉——该隐患对 body mod 同样存在。
- **hair 顶点色转正**：描边色 nibble `(R高,R低,G高)/15` 为全网格常量档（深色/粉红/
  金浅/纯黑），不再用 body 的逐顶点基础色曲线（暗部量化塌成绿描边）；G低（ramp 行）/
  B（0~15 细宽度）/A（144/0 高光掩码）从带权重参考网格最近邻拷贝。
- **hairprop 顶点色转正**：按材质槽「材质类型」写常量——metal = 灰 `(3,3,3)` + A=144，
  其余 = 黑 `(0,0,0)` + A=0，B=8；不再走 body 曲线（黑蝴蝶结绿边）。VB1 手动补丁流程
  全部作废。
- **文档**：发型道具 = Geo_Hair + Geo_HairProp 双组件（游戏内无单独发饰选择，完整替换
  = 同一次抓帧得到两个组件，发布时合并为一个完整包）；证伪旧「发饰包 / 跨包共用 Geo_Hair」表述；
  制作目标 tooltip 与 README 同步。
- **profiles 精简为默认两件套**：`atbm-cstm-0140`（带原生 co 第二材质段的 body 默认档，
  由已导出包离线重建，附 `rebuild_profile.py`）+ `hmsz-hair-0023-hair`（发型默认档）。插件默认配置档路径
  与测试（blender_smoke / inverse_skin_numeric / profile_contract_smoke）同步切换；
  旧 hski-cstm-0000 PoC 冻结契约随档移除，契约冒烟改锁新默认档的几何/骨架/算子/co 段。

## 0.7.3 — manifest 面向包管理器：目标显示游戏资源名 + 强制预览图

- **Blender 作者界面收敛为四步**：全局选择“身体（body）/发饰（hairprop）”，按
  `① 准备配置档 → ② 绑定模型 → ③ 准备材质 → ④ 导出模组` 操作；实验、runtime-only、
  直接 GPU 导出等入口默认折叠。发饰页把 `Head_Hair` 刚体与物理骨权重路线明确为二选一，
  hairprop 材质页不再显示 body 专用原生 co。
- **修复发饰 profile 的顶点数提示仍扫描 `Geo_Body.json`**：Blender 的完整/分步配置档入口
  现在都按组件传入 `Geo_HairProp`；新增 Blender 4.2 UI 冒烟检查覆盖目标枚举、折叠 API、
  图标与两条 profile 入口。
- **导出 manifest `targets` 改为被替换的游戏内模型资源名**（如 `mdl_chr_hski-cstm-0000_body`），
  取自 profile `target.bodyResource/hairResource/faceResource`（按组件），而非旧的
  `body.weightedMesh`。让用户在包管理器里直接看到本 mod 替换了游戏里的哪个 body/hair/face；
  profile 缺资源名时回退旧语义。`schemaVersion` 升到 2，新增 `cover` 字段。
- **导出强制附预览图**：导出面板新增「预览图」字段（`gmi_cover_image`，png/jpg/webp），
  不填直接报错取消。`core._prepare_cover` 校验存在/格式/magic 字节/≤2MB 并复制为包内
  `cover.png`；operator 侧对过大图用 Blender 自动缩到 ≤1024px 再入包（合理限制体积）。
- 测试：`tests/mod_ini_contract.py` 新增 `test_manifest_target_is_body_resource_and_cover`，
  断言 `targets` 为游戏资源名、`cover` 落盘、缺预览图报错（7→8 项，全绿）。

## 0.7.2 — 运行时全局布局自动探测（彻底弃用 PS 枚举）

- **不再枚举 pixel shader hash。** 游戏按光照把 `baseColor/packedMask/shadeColor`
  重排到不同 `ps-tN` 槽（0.7.1 靠 `slotVariants` 逐 PS 登记，新场景一冒新 PS 就漏），
  现改为**运行时靠全局 body 地标贴图 `0ff26bed` 的槽位自动判布局**：
  - 地标在 `ps-t2` → 布局 **A**：`t0/t1/t4`（含自定义 shade）
  - 地标在 `ps-t3` → 布局 **B**：`t1/t2/t5`（唯一挪动 base/mask、会导致「棋盘格全身错乱」的变体）
  - 都不中 → **C/未知**：只绑 `t0/t1`，不绑自定义 shade（安全兜底，base/mask 永远对，
    绝不错乱/消失）。
  新场景、新服装、新角色全部自动覆盖，作者只需 base/mask/shade 三张贴图，**永不碰 PS hash**。
- **导出 ini 结构变化**：`[Constants]` 加 `$gmi_<Mod>_layout` / `_probe` 全局；新增
  `[CommandList<Mod>DetectLayout]`（`checktextureoverride = ps-t2 / ps-t3` 探地标）与自包含的
  `[TextureOverride<Mod>BodyLayoutLandmark]`（`hash = 0ff26bed` + 由 IB hash 派生的
  `match_priority`，多 mod 同装不冲突）。主体段与 native co 段都改成按 `$..._layout` 的三分支绑定。
- **移除 0.7.1 的逐 PS `slotVariant` 机制**：`core.py` 删除 `_section_slot_variant_ini`、
  `_section_material_binding_block` 等 5 个函数，新增 `_landmark_layout_sections` /
  `_landmark_binding_block`。TextureOverride 的重复 hash 用 `match_priority` 消歧
  （`allow_duplicate_hash` 只对 ShaderOverride 合法，放 TextureOverride 上会告警）。
- 已在 `D:/Games/gakumas/Mods/` 的 6 个活跃 mod 上手工验证：干净重启后 3DMigoto 日志
  无 `Unrecognised entry` / `Duplicate TextureOverride` 告警，暗光/正常/镜面场景均正常。
- 测试：`tests/mod_ini_contract.py` 的 `test_pixel_shader_slot_variants_are_conditional`
  改写为 `test_body_layout_is_runtime_autodetected`，断言地标探测三分支结构（7/7 通过）。
- 详细复盘结论已收敛进当前实现与回归测试。

## 0.7.1 — body / bdyco 材质贴图彻底分离

- **修复低亮度 PS 变体贴图槽错位**：`50b619789b23bd7a` 这类低亮度 shader 中，
  `baseColor/packedMask/shadeColor` 分别改读 `ps-t1/ps-t2/ps-t5`，其中 `ps-t4` 是深度比较槽。
  profile 现在支持 `slotVariants`，导出 ini 会按当前 PS 自动切换槽位，避免暗光下把
  `shadeColor` 误塞进深度槽后出现大块彩色阴影。
- **修复原生 co 材质共用 body t1/t4 的问题**：`NATIVE_CO` 段现在绑定
  `body.section1` 自己的 `t0/t1/t4` 资源；没有填写 co 的 `t1/t4` 时生成 co 专属中性图，
  不再复用 `m_bdy` 的 PackedMask / ShadeMap，避免透明材质与身体材质叠出灰斑。
- **调整材质模板 UI**：贴图绑定拆成「不透明 body / m_bdy」与「原生 co / m_bdyco」
  两块，co 现在有独立的基础色、混合遮罩和暗面材质字段。
- **分材质烘焙按渲染材质分流**：材质槽设为 `原生co` 时，烘焙会额外输出
  `gmi_baked_co_packedMask.dds` 与 `gmi_baked_co_shadeColor.dds`，并写回 co 字段。co 会按
  `m_bdyco` 自己的 atlas 尺寸烘焙，不要求与 body atlas 同尺寸。
- **修复 UV 重叠时 co 挖空 body t1/t4**：body 与 co 现在先按材质槽过滤三角形，再分别栅格化；
  co UV 覆盖在 body 皮肤 UV 上时，不会再把 body 的 material id 覆盖成中性洞。
- **抓帧主 draw 选择支持短角色代号提示**：`gmi_body_resource` 填 `shro` 这类短代号时，
  会用 Body JSON 资源库里所有匹配 body 的顶点数集合过滤候选，避免抓帧里同屏多角色时选错
  body；完整 body 名仍走精确匹配。`tools/extract_frame_profile.py` 新增
  `--body-json-library` / `--body-resource` 参数；提示会写进 `profile.target.bodyResource`。
- **打包附带 profiles**：`tools/package_blender_addon.py` 会把仓库 `profiles/` 目录
  （含 `texture_map.json` 槽位/`slotVariants` 标注）一并打进插件 ZIP 的
  `gakumas_mi/profiles/`。
- 测试：`tests/mod_ini_contract.py` 覆盖 co 专属 t1/t4 绑定与 `slotVariants` 条件绑定契约；
  `tests/frame_profile_extract_smoke.py` 覆盖短代号顶点数提示；
  `tests/material_bake_blender_smoke.py` 更新为检查 body/co 双输出。

## 0.7.0 — t1/t4 材质语义收敛与旧 Profile 防错

- **修正 t4/sdw 语义**：`t4.rgb` 明确为 `t0/baseColor` 的暗面材质颜色版，用来在卡通暗面保留
  衣服自身花纹、布料纹理和颜色；它不是投影阴影本身带图案。`t4.a` 继续按原生 `sdw`
  近似二值材质遮罩处理，不当作透明度或连续阴影强度。
- **修复旧 Profile 槽位坑**：旧抓帧 profile 可能把 `ps-t2` 环境 cubemap 误标为
  `body.shadeColor`，真正的 `_ShadeMap/sdw` 则在 `body.t4 / ps-t4`。0.7.0 导出时会自动把
  `shadeColor` 迁移到同前缀的 `t4/ps-t4`，避免暗面继续读取原服装 `sdw`，导致新衣服暗部出现
  不属于当前服装的彩色图案。
- **新增 t1 单通道输入**：分材质烘焙时可单独填写 `t1.R/G/B/A` 图。四个通道都填时按整图合成
  完整 PackedMask；只填部分通道时，先按材质预设烘焙，再仅覆盖有有效内容的材质区域，避免
  空白 atlas 黑区污染皮肤或无贴图材质。
- **UI 文案收敛**：`t4` 在界面中改称「暗面材质 t4/sdw」。逐材质行只保留 `材质类型`、
  `渲染材质`、`明暗`；不再暴露 `t4.A` 手调项，`t4.A` 由材质类型预设自动写入二值结果。
- **原生 co 贴图绑定对齐游戏逻辑**：基础色 `t0` 对应 `m_bdy`，透明材质 `t0` 对应 `m_bdyco`，
  两者各走各自 UV，互不回退。只要有材质槽设为 `原生co/NATIVE_CO`，导出时就必须提供
  「透明材质 t0 / m_bdyco」，否则直接报错，避免把 `m_bdy` 贴图错误套到 co 材质上。
- **抓帧主 draw 选择更稳**：自动抽 profile 时优先匹配期望顶点数和可见贴图绑定数，减少选到
  shadow/depth/helper draw 后生成错误贴图槽位的风险。
- 测试：`tests/mod_ini_contract.py` 新增旧 profile `shadeColor=ps-t2` 自动迁移到 `ps-t4`
  的回归；`tests/material_bake_smoke.py` 覆盖 t1 通道覆盖和材质预设 t4.A；`tests/frame_profile_extract_smoke.py`
  覆盖可见 draw 选择与贴图槽位语义。

## 0.6.2 — 透明路线收敛到原生 co（移除自建镂空/半透明）

- **删除自建透明路径**：`渲染材质` 不再有 `镂空(ALPHA_CLIP)` / `半透明(ALPHA_BLEND)`，
  只剩 `不透明` 与 `原生co(NATIVE_CO)`。透明/镂空统一交给游戏原生第二材质段 `m_bdyco`
  的 draw 上下文绘制（借用原版 shader/state/贴图）。旧工程里残留的 `ALPHA_CLIP/ALPHA_BLEND`
  值导出时按 `不透明` 处理。
- 移除随包 shader `GMIFinal/GMIInheritMaskA/GMIAlphaBlend/GMIAlphaClip/GMIClipMRT/GMINativeClip`
  与 `镂空阈值(gmi_alpha_cutoff)` 属性；导出不再写 `GMINativeClip{n}.hlsl`。
- 抓帧复核（`FrameAnalysis-2026-06-30-045108` + `mdl_chr_fktn-cstm-0001_body`）确认 `m_bdyco`
  与主 body **共用 VB0/VB1/IB**、仅 submesh 范围不同，且第二段在 5 个 VS pass 中的 4 个出现；
  NativeCo override 对全部 5 个 VS 都 `checktextureoverride = ib`。详见
  [`research/ab-route-notes.md`](research/ab-route-notes.md) §5。
- 补充 `m_bdyco` alpha 行为实测：低 alpha 渐变区域仍被裁切，抬到 `A=128/255` 后透明 padding
  以黑块显示，确认当前 body-co 路线更接近 cutout/alpha test，不是连续半透明 blend。
- 测试：`tests/mod_ini_contract.py` 删去 cutout/alpha-blend 契约，新增「旧 alpha 值回退不透明」
  与「原生 co 缺 t0 报错」；`tests/inverse_skin_index_format_smoke.py` 移除 alpha-blend 用例。

## 0.6.0 — 透明材质保守路径 + 文档整理

- **透明材质路径固化**：材质属性新增 `渲染材质`（不透明 / 透明）。透明段从主 body
  draw 拆出，走 `InheritMask`（只测深度不写深度，反向 Z）+ `AlphaBlend`（MRT、RT1 预乘
  alpha）两段，优先保证 **A=0 镂空干净 + 投影/遮挡正常**；半透明在同模型已有 coverage
  的像素上可靠显示。随包附带 `GMIFinal.hlsl` / `GMIInheritMaskA.hlsl` / `GMIAlphaBlend.hlsl`
  / `GMIAlphaClip.hlsl`。详见 [`research/ab-route-notes.md`](research/ab-route-notes.md) §5。
- 文档全面整理：新增本 CHANGELOG，归档已排除路线与逐步实验记录到 `research/archive/`，
  透明材质合并为单一结论文档。

## 0.5.50 — 描边颜色与顶点 COLOR 预设收敛

- 新拓扑衣服顶点 COLOR 默认使用「衣物常量」安全色，避免原版区域/拓扑相关 COLOR
  串到错误几何上产生移动色块。
- 描边颜色来源可选：取自基础色 / 按材质预设 / 黑色常量。
- COLOR 的安全族结论已收敛进插件预设与回归测试：
  中性化 R/G/A，保留 B 高位 `0xf0`，仅用 B 低位作描边宽度。

## 0.5.30 — 首次导出稳定性与 UV/COLOR 防错

- 修复「第一次导出错乱、第二次正常」：UV layer 引用在 `calc_tangents()` 后按名称重取，
  不再使用失效引用。
- 移除静默 fallback UV（读不到 UV 直接停止导出，而非写 `(0,0)` 导致 VB1 大面积 `(0,1)`）。
- 增加最终 VB1 UV 校验（NaN/Inf/异常大坐标直接报错，不再钳到 fp16 `65504`）。
- 非法 UV layer 清理与报告（`export-report.json` 记录 `uvLayers.candidates` 与
  `invalidUvLayersRemoved`）。
- 系统性清理 NaN/Inf（COLOR 转 0–255、PNG/DDS 像素、原生 COLOR 合成矩阵）。
- 新增 `应用分材质 COLOR` 按钮；「校验并导出」直接调用导出 operator 的 `execute`，减少
  `bpy.ops` 套娃和状态不同步。

## 0.5.22 — 原生顶点 COLOR 与分材质控制

- 新增 `原生合成顶点 COLOR(实验)`（`gmi_enable_native_color_transfer`）：按原版 `m_Colors`、
  贴图、位置/法线/UV 等特征为 MOD 网格合成逐顶点 COLOR。
- 新增描边宽度模式（`gmi_outline_width_mode`）与顶点 COLOR 导出模式（`gmi_vertex_color_mode`）。
- 分材质烘焙 / COLOR 拆为可折叠材质模板区；`material_presets.json` 开始写入材质默认 COLOR。
- 移除 0.5.6 残留的 `gmi_semantic_correction`（手指/颈部语义修复）。

## 0.5.6 — 基础流程版本

- 完整主流程可用：导入配置档对象 / 抓帧参考 / 带权重参考；从配置档传递权重；校验并
  导出（原拓扑 / 带权重 GPU）；创建身体材质模板；按材质烘焙 t1/t4；导出贴图模组。
- 材质系统偏「t1/t4 烘焙」，COLOR/描边方案尚不完整；仍含后续废弃的手指/颈部修复选项。

## 0.5.1 — 运行时替换链修复（重要）

修复同一 body IB 被多 pass、多段绘制时的替换：

- **全 VS 触发**：profile 记录 body IB 关联的全部 VS，每个生成
  `ShaderOverride…checktextureoverride = ib`，避免只覆盖部分 VS 导致其它 pass 叠图。
- **主体段定位 + drawindexed**：用 `match_first_index = <主体偏移>` + `handling = skip`
  + `drawindexed = <索引数>, 0, 0`，跳过原 draw、从自定义 IB 的 0 画满。
- **尾部段跳过**：同 IB 尾部段（原版裙摆等配件）逐段 `handling = skip`，避免原版配件漏出。

> 旧 profile 需**重新提取**才会带上述字段。

## 0.5.0 — 分材质烘焙 t1/t4

- 单 t0 身体的 Blender → 3DMigoto → 游戏（换模 + 动画 + 贴图 + 多 mod 共存）完整闭环
  达成并发布，跨服装实机验证。
- 一键生成完整配置档（注入 + 结构 + 逆算子）；缺 Unity 骨架时从 `m_BoneNameHashes` +
  `m_BindPose` 合成骨架，资源库 500+ 套全部可用。
- 新增按 Blender 材质槽逐材质烘焙 t1/t4（皮肤珊瑚阴影、哑光皮革、织物、金属…，预设由
  实机抓帧实测），专为自定义 atlas / MMD 等无游戏 t1/t4 来源的模型还原观感。
- mod.ini 改为 IB-only 触发，多个 body mod 共存零冲突警告。

## 0.3.x — 中文化工作台与一键配置档（历史）

- 0.3.2：`导入配置档对象`、`选择高风险顶点`、`创建身体材质模板`、`校验并导出模组` 等主线入口成形。
- 0.3.3：`更新 Profile 抓帧源`，支持 3DMigoto 文件名省略 VB0 hash 时按 draw 编号回退。
- 0.3.4：面板/字段/提示全面中文化（Profile→配置档、Mod→模组、Body→身体），收敛主线出口。
- 0.3.5：`从抓帧生成配置档`（runtime-only），自动候选评分选主 Draw；新增 `tools/extract_frame_profile.py`。

## 0.1.0 – 0.2.x — 起步（历史）

- 0.1.0：Blender 4.2 LTS 上的参考 Mesh 导入、索引 Mesh 校验/导出、DDS 贴图包导出。
- 0.2.x：带权重参考导入（`Geo_Body`：152 根加权骨骼）。
