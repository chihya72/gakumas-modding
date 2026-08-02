# GakumasMI Blender 插件更新日志

版本号见 [`gakumas_mi/__init__.py`](gakumas_mi/__init__.py) 的 `bl_info["version"]`。
发布包用 `python tools/package_blender_addon.py` 生成（代码版不含 Body JSON 资源库；
加 `--with-body-lib` 可一并打包）。本地包不提交到公开仓库。

> ⚠ **0.9.0 里各条的验证程度不一样，别当成都实机验证过了。**
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

## 0.9.0 — 只做 AB bundle：骨映射表单、承重关节闸门与肤色对齐原版

跳过 0.8.x：本版一次性合入三批改动，其中「移除 3DMigoto 路线」是不兼容的工作流变更。

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
- **硬闸门**：14 个承重关节（Hips/Spine/左右 Arm-ForeArm-Hand-UpLeg-Leg-Foot）任一没拿到
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
  [`research/transparent-material-status.md`](research/transparent-material-status.md)。
- 补充 `m_bdyco` alpha 行为实测：低 alpha 渐变区域仍被裁切，抬到 `A=128/255` 后透明 padding
  以黑块显示，确认当前 body-co 路线更接近 cutout/alpha test，不是连续半透明 blend。
- 测试：`tests/mod_ini_contract.py` 删去 cutout/alpha-blend 契约，新增「旧 alpha 值回退不透明」
  与「原生 co 缺 t0 报错」；`tests/inverse_skin_index_format_smoke.py` 移除 alpha-blend 用例。

## 0.6.0 — 透明材质保守路径 + 文档整理

- **透明材质路径固化**：材质属性新增 `渲染材质`（不透明 / 透明）。透明段从主 body
  draw 拆出，走 `InheritMask`（只测深度不写深度，反向 Z）+ `AlphaBlend`（MRT、RT1 预乘
  alpha）两段，优先保证 **A=0 镂空干净 + 投影/遮挡正常**；半透明在同模型已有 coverage
  的像素上可靠显示。随包附带 `GMIFinal.hlsl` / `GMIInheritMaskA.hlsl` / `GMIAlphaBlend.hlsl`
  / `GMIAlphaClip.hlsl`。详见 [`research/transparent-material-status.md`](research/transparent-material-status.md)。
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
