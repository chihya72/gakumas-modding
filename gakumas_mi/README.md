# GakumasMI Blender 插件 0.9.0

当前状态：开发预览版。材质槽位已改为**运行时靠全局 body 地标贴图自动判布局**
（0.7.2，弃用 0.7.1 的逐 PS `slotVariants` 枚举），作者只出 base/mask/shade 三张贴图、
永不碰 PS hash，新场景/服装/角色自动覆盖。建配置档已收敛为**一键流程**：选择制作目标，
填「抓帧目录」+ 对应「网格 JSON 资源库」，点 `生成完整配置档` 即可一次产出
**①注入信息 + ②结构数据 + ③逆算子** 的完整配置档。

- 自动按顶点+索引数从资源库匹配 `Geo_Body.json`、`Geo_Hair.json` 或 `Geo_HairProp.json`，同拓扑资源按 bind pose 自动判等价；
- 仅有 Mesh、没有 Unity 骨架的 body：从 `m_BoneNameHashes` + `m_BindPose`
  **合成骨架**，因此资源库里 500+ 套都能一键匹配（不再只限有骨架的样本）；
- 自动构建逆算子并标出不可观测骨；

底层仍保留分步入口(`仅生成注入信息` 等)与 `更新配置档抓帧源` 校验。

**通用性边界**：本插件面向“已完成对齐、删头、图集/材质准备且带有效权重”的作者模型，
目标是对齐后的一键 AB 导出；不承诺自动完成任意外部模型的建模对齐、删头、权重修复或图集烘焙。
身体骨名由预设和面板映射表兜底，装饰物理按源父骨/语义规则默认处理，异常件用覆盖表修正。

本分支只做 **AB bundle（原生蒙皮）** 路线，3DMigoto 逆蒙皮的传权与导出已整体移除。
页面按 **① 准备配置档 → ② 准备材质 → ③ 导出 AB bundle** 排列：作者模型自带的权重原样保留，
插件只把骨名换成游戏骨名，**没有传权这一步**；骨名认不出来去步骤③的「骨骼映射表」点选（见 §4）。
身体/发型及其配套组件均在下文说明。当前能力边界见
[`research/current-status-and-roadmap.md`](../research/current-status-and-roadmap.md)。

目标环境：Blender 4.2 LTS。

## 安装

在 Blender 中打开：

`编辑 > 偏好设置 > 插件 > 从磁盘安装`

选择本地构建生成的当前版本插件 ZIP。公开仓库不直接提交包含配置档资产的发布包。

启用 **GakumasMI** 后，面板位于：

`3D 视图 > 右侧边栏 > GakumasMI`

如果仍看到旧英文按钮，请卸载旧版插件、关闭 Blender、重新打开后再安装新版 ZIP。

## 当前主要工作流

> **发型道具 = 发型 + 配套发饰两个部件。** 游戏内只有「发型」选择，没有单独的发饰选择；
> 每个 `mdl_chr_*_hair` 资源包同时含发型网格 `Geo_Hair` 与发饰网格 `Geo_HairProp`，
> 装备发型即两者一起渲染。它们是两个独立 drawcall（不同于 body 的 `m_bdyco`
> 同网格第二材质段），但由**同一个发型 profile 和同一套三步 UI** 管理。顶层始终只选择
> 「发型」；插件自动导入/处理 `Geo_HairProp` 并记录精确 selector。作者可以只替换发型，
> 也可以同时提供发饰网格，不再把发型和发饰作为两个制作目标。
> 两个 JSON 资源也来自同一批 `_hair` 包（`--mesh-name Geo_Hair` /
> `--mesh-name Geo_HairProp`）。

### 1. 准备配置档（一键生成并导入参考）

主流程只要两个输入 + 一个按钮：

- 选项 1：填 `抓帧目录`（FrameAnalysis-*）；
- 选项 2：填对应的 `网格 JSON 资源库`（body 含 `Geo_Body`；发型库同时含 `Geo_Hair` 与 `Geo_HairProp`）；
- 点击 **`生成完整配置档`**，再点击 **`导入参考模型与骨架`**。

它会一次完成：

1. **① 注入信息**：扫描抓帧，识别 Body 的 Draw / IB·VB hash / stride / 贴图槽；
2. **② 结构数据**：按顶点+索引数从资源库匹配到对应 `Geo_Body.json` + 骨架，复制进配置档 `Reference/`；
3. **③ 网格统计**：数顶点/骨数、算每根骨的权重总和，写入 `skinning.inverseSkin`
   （含自动标出的低权重「不可观测骨」）。

> 0.9.0 前这一步还会解一个最小二乘、写出约 40 MB 的 `Buffers/InverseOperator.R32_FLOAT.buf`。
> 那个算子只服务 3DMigoto 重蒙皮，路线移除后没有任何读者，已一并删除——生成配置档因此快了不少，
> 每档也少 40 MB。`skinning.inverseSkin` 这个键名是历史遗留，现在只装 Mesh/骨架路径与统计。

完成后 `配置档目录` 自动指向新配置档，可直接进入「② 准备材质」。

> 同拓扑的多套服装（同一基础身体、仅贴图不同）会按 bind pose 自动判定为等价并任取其一；
> 若匹配到 bind pose 不一致的多个候选，会提示在 `target.bodyResource` 指定具体 Body。
> 仅有 Mesh、没有骨架的条目也支持：缺骨架时从 `m_BoneNameHashes` + `m_BindPose` 合成骨架。

`高级 / 分步` 折叠区保留了 `仅生成注入信息`、`匹配资源库`、`更新抓帧源`、`导入配置档对象`
等单步按钮，供排错使用。

#### 配置档目录是什么？

配置档是插件认识一个游戏对象的“规格说明书”。它不是模型本身，而是把
3DMigoto 抓帧数据和 AssetStudio 原始资源连接起来的桥。

配置档主要记录：

- 目标角色、服装和组件，例如 `hski / cstm-0000 / body`；
- 游戏内 drawcall、IB hash、VB hash、顶点数、索引数和 stride；
- 贴图槽位，例如身体 `t0/t1/t4`；
- 原始网格、骨架、BindPose 和权重来源；
- 导出 AB bundle 时需要的骨架、bind pose 与贴图槽信息。

因此，没有配置档时，插件不知道应该替换哪个游戏对象，也不知道导出的 buffer
应该符合什么格式。

#### 抓帧目录有什么用？

抓帧目录通常是 3DMigoto 生成的 `FrameAnalysis-*` 文件夹。插件可以用它来校验
当前配置档是否还能匹配游戏内实际 drawcall：

- 是否存在目标 IB；
- 是否存在目标 VB0/VB1；
- 是否存在身体贴图 `t0/t1/t4`；
- 当 3DMigoto 文件名省略 VB0 hash 时，是否能通过 draw 编号回退匹配。

0.3.5 开始可以从未知抓帧目录自动生成 runtime-only 配置档。它能从帧里确认：

- Body 候选 Draw；
- IB hash、索引数；
- VB0/VB1 文件、stride、顶点数；
- 同一 Body 的多 pass，例如主 pass、阴影/深度 pass、描边/辅助 pass；
- 抓帧中可见的 `ps-t*` 贴图槽位。

注意：帧数据不能单独还原完整 Unity 骨架名、权重和 BindPose。插件会把这类配置档标记为
`runtime-only-frame-extracted`；之后会通过 `Body JSON资源库` 自动匹配 AssetStudio
导出的原模型 JSON 与骨架 JSON，作为骨架与 bind pose 的来源。

命令行也可以独立生成配置档：

```powershell
python tools\extract_frame_profile.py <FrameAnalysis目录> profiles\generated-body --component body
```

如果自动选择错了，可按 3DMigoto 顶部显示的 Draw 编号强制指定：

```powershell
python tools\extract_frame_profile.py <FrameAnalysis目录> <输出目录> --component body --draw 335
```

#### 批量导出所有 Body 的原模型 JSON / 骨架 JSON

把游戏缓存里的 body AB 文件放到 `../mod-workspace/libraries/all_body/`（仓库外）后，可以用：

```powershell
python tools\export_all_body_json.py --assetstudio "<AssetStudio.CLI.exe>"
```

默认参数：

- 输入目录：`../mod-workspace/libraries/all_body/`
- 输出目录：`../mod-workspace/libraries/assetstudio-body-json/`（库有数 GB，在仓库外）
- AssetStudio CLI：通过命令行参数指定本机的 `AssetStudio.CLI.exe`
- Unity 版本：`6000.0.67f1`

输出会按 body 资源名分目录，避免所有 Mesh 都叫 `Geo_Body.json` 时互相覆盖。
这些目录整体就是插件使用的 `Body JSON资源库`：

```text
../mod-workspace/libraries/assetstudio-body-json/
  mdl_chr_<角色>-cstm-<编号>_body/
    Geo_Body.json
    Geo_Body.skeleton.json
```

只导出 Mesh JSON：

```powershell
python tools\export_all_body_json.py --assetstudio "<AssetStudio.CLI.exe>"
```

同时生成骨架 JSON：

```powershell
python tools\export_all_body_json.py --assetstudio "<AssetStudio.CLI.exe>" --skeleton
```

注意：`Geo_Body.json`（Mesh，含 bind pose / 权重 / bindpose / 骨骼 hash）会**始终保留**，
作为对外发布的资源包；逆解链不依赖骨架层级。`Geo_Body.skeleton.json` 只在严格可读时
生成（`m_Bones` 为空或骨骼 Transform 指向未加载依赖时跳过，状态记为 `mesh-only`，但 Mesh 保留）。
**仅 Mesh 的条目也能一键匹配**：缺骨架时从 `m_BoneNameHashes` + `m_BindPose` 合成骨架，
因此 500+ 套全部可用。

`Body JSON资源库`（约 4.5 GB）作为**单独资源包**发布，不打进插件 zip。开发环境默认指向
仓库外的 `../mod-workspace/libraries/assetstudio-body-json/`（与 `templates/unity` 同级）；
实际使用时把资源包目录路径填进插件「选项2」即可。

调试前几个文件：

```powershell
python tools\export_all_body_json.py --assetstudio "<AssetStudio.CLI.exe>" --limit 5 --force --skeleton
```

### 2. 导入对象

- 在步骤①选择已生成的完整 `配置档目录`；
- 点击 `导入参考模型与骨架`；
- `匹配网格 JSON 资源库` 与完整排错导入位于“高级 / 分步 / 排错”。

#### 原模型 JSON 和骨架 JSON 的区别

两者都来自离线资源分析，但用途不同。

`原模型 JSON` 是网格数据，主要包含：

- 顶点位置、法线、切线；
- UV0/UV1；
- 顶点色；
- 三角面；
- 每个顶点的骨骼权重索引和权重值；
- Mesh 自带的 BindPose 数组。

它回答的是：“这个身体网格本身长什么样，每个顶点受哪些骨骼影响？”

`骨架 JSON` 是骨架语义数据，主要包含：

- 骨骼名字；
- 父子层级；
- 节点变换；
- weighted bone 编号和骨骼名之间的对应关系；
- 绑定姿势与骨骼层级的辅助信息。

它回答的是：“权重编号到底对应哪根骨头，骨架结构是什么？”

插件需要两者一起导入带权重参考模型。它是发型描边取色和导出前绑定体检的数据源。

### 3. 导出 AB bundle

把 mod 网格作为真正的 Unity 资产交给 chinosk6 插件，让引擎原生蒙皮，于是描边/透明/贴图/物理
**由引擎正确**，还能带新物理骨。代价是多一个打包环节，且游戏侧用 chinosk6 插件而不是 3Dmigoto。
与已移除的 3Dmigoto 路线的历史对比见
[`research/3dmigoto-vs-ab-route.md`](../research/3dmigoto-vs-ab-route.md)。

**前置**（缺一不可）：

- 当前对象已走完 ①准备配置档 → ②准备材质，**并且网格自带顶点组权重**
  （作者模型原本的权重就行，**不需要也不应该跑传权**；没有任何顶点组时
  「导出 bundle 源」按钮为灰、下方提示「bundle 源需要作者模型顶点组权重」）；
- 作者模型已按游戏骨架**对齐并烘成 rest 姿势**（镜像 / 缩放 / A→T retarget 属作者
  基本功，插件不代做）；
- 目标 body/hair 的 **R32 模板 bundle**（工作区默认库：
  `../mod-workspace/templates/unity`；由 `tools/build_phase3_templates.py` 批量生成）；
- 游戏侧装 **chinosk6 插件**（`gkms-localify-dmm`）替代 3Dmigoto，**一次性**。

**作者流程**：

1. 在「导出 AB bundle」区填两栏：

   - **`R32 模板 bundle`** —— 目标 body/hair 对应的模板文件。留空则只出 `bundle-src/`，不打成品；
   - **`外部 Python`** —— 跑模板补丁的解释器。要求 **Python 3.10+**（推荐 3.11/3.12，下限由
     Pillow 决定），并 `pip install UnityPy Pillow`。默认值 `python` 走 PATH，够用就不用改；
     不在 PATH / 多版本 / 虚拟环境时填绝对路径，例如
     `C:\Program Files\Python\Python312\python.exe`。查路径：
     `python -c "import sys;print(sys.executable)"`。

   > **不能填 Blender 自带的 Python**（`...\Blender 4.2\4.2\python\bin\python.exe`）——
   > 插件本体确实跑在它上面（4.2 是 3.11.7、4.5 是 3.11.11），但它没有也不该装 UnityPy。
   > Windows 上还要留意 `...\Microsoft\WindowsApps\python.exe` 可能只是应用商店占位程序。
2. 点 **`导出并打包 bundle（一键）`**：插件先导出 bundle 源，再自动调外部 Python 跑模板
   补丁，直接产出成品 `.bundle` 和同级 `mod.json`（写到 `<输出目录>/<id>/`）。
   **无需 Unity、无需手敲命令行，也无需再从 `bundle-src` 手动移动 `mod.json`。**
   - 只想要中间产物时，点 `导出 bundle 源`（不打包），再自行跑
     `python tools/patch_unity_bundle.py --template <模板.bundle> --mod-root <bundle源目录> --output <成品.bundle>`。
3. 把成品 `.bundle` + `mod.json` 放进 chinosk6 插件的
   `gakumas-local/local-files/mods/<id>/` 目录。
4. 进游戏换装验证；插件日志 `mod-plugin.log` 有 `meshApplied` / `textureApplied` /
   `matchedBones` / `droppedInfluences` 诊断行可对照排错。

> 带新物理骨的服装（听诊器/裙摆/缎带摆动）也已跑通，靠导出侧补齐链尾 tip 骨与每骨摆动
> 参数——这部分由 bundle 源与模板保证，作者无需手动干预。机制与完整分步路线图见
> [`ab-route-handoff/docs/bundle-route-roadmap.md`](../ab-route-handoff/docs/bundle-route-roadmap.md)。

### 4. 骨骼映射表（源骨 → 游戏骨）

AB 路线保留作者模型自带的权重，只把**骨名**换成游戏骨名。骨名认得出来就全自动，认不出来
就在这张表里点选——所以覆盖率不取决于插件认识多少种命名规范。

> ⚠ **这一节的功能是 2026-07-27 新加的，还没有人在实际制作中用过。** 表单绘制、映射生效、
> 闸门拦停、JSON 往返都过了自动测试，但没有由它产出过进游戏的 mod。用的时候如果行为和下面
> 描述不一致，以实际为准并反馈。另外表里 VRM/Biped/Auto-Rig Pro/英文 Humanoid 四家预设是按
> 各自公开命名规范写的，**没有对应模型试过**——名字若拼错，表现是那几行不预填、需要手动选。

**大多数人一行都不用碰。** 预设已覆盖八个命名家族，扫描后自动预填，直接导出即可：

| 家族 | 识别的骨名样例 |
|---|---|
| MMD 準標準（两种写法） | `腕.L` / `左腕`、`足D.L`、`手捩2.L`、`中指１.L` |
| VRM / VRoid | `J_Bip_L_UpperArm`、`J_Bip_C_Chest`（`J_Sec_*` 归装饰骨） |
| 3ds Max Biped | `Bip001 L UpperArm`、`Bip001 L Thigh`、`Bip001 L Finger0` |
| Auto-Rig Pro | `arm_stretch.l`、`thigh_stretch.l`、`spine_01.x` |
| 英文 Humanoid 同义词 | `LeftUpperArm`、`LeftLowerLeg`、`Chest`、`LeftThigh`、`LeftCalf` |
| Mixamo / Rigify / SCSP-QualiArts | `mixamorig:LeftArm` / `DEF-upper_arm.L` / `LeftArm_rot` |

「源骨架类型」保持 `自动识别` 即可——它会逐张表试算命中数、取最高的那张，不是靠几个探针名
猜家族。所以新增支持一种命名规范只是加一张表，不影响已有的识别结果。

**什么时候需要它**：导出报

> 以下承重关节没有拿到任何权重：LeftHand、RightHand、…请在导出面板「骨骼映射表」里
> 扫描并指定对应关系。

这是硬闸门，专门拦「导出成功但进游戏是废品」——源骨名没认出来时，那些部位会跟着别的骨
乱跑（实测过整只手被钉在 `Spine1` 上），而静止画面完全看不出来。VRM/VRoid（`J_Bip_*`）、
3ds Max Biped（`Bip001 *`）、Auto-Rig Pro 这些目前都没有预设，会走到这里。

**用法**：展开「骨骼映射表」→ 点 `扫描源骨骼` → 每行两列：

| 列 | 给谁用 | 说明 |
|---|---|---|
| 左：目标游戏骨 | 身体骨 | 下拉可打字搜索（如输入 `Hand`）。填了就以此为准，优先级最高 |
| 右：装饰物理 | 飘带 / 花边 / 挂件 | 自动＝跟源父骨（胸/Bust 按 Bust*_S）；**刚性跟父骨**＝不摆、最安全；自建摇物链＝自由悬垂的飘带；**跟随最近骨骼**＝跟最近的目标摇物骨（过远则回退父骨）；跟裙摆＝裙边花边 |

- 填了左列的行，右列自动置灰——那已经是确定映射；
- 一个完全陌生的骨架，实测需要点选约 **21 行**（脊椎 5 + 左右各 8）就能过闸门；
- `列出全部` 可以复核预设填的结果；`存为 JSON` / `从 JSON 读入` 换模型时复用，骨映射与
  装饰物理写在同一份文件里（`bones` / `physics` 两个键）。

**装饰骨物理为什么保留覆盖入口**：源作者常把装饰骨绑在语义无关的骨上（把腰部挂件绑在胸骨、把
裙边花边绑在大腿），单靠名字和位置都猜不准。默认跟源父骨能避免错误蹭到袖子/腿；
`刚性跟父骨` 虽然不摆，但绝不会出现「手臂一动脖子上的缎带跟着甩」这种事故。

### 5. 材质模板（步骤② 用）

HSKI Body 已验证的身体贴图语义：

- `t0`：基础色；
- `t1`：混合遮罩，R 阴影阈值 / G 光滑度 / B 金属度 / A 环境光遮蔽；
- `t4`：暗面材质 / `sdw`（RGB=基础色暗色版，A=近似二值材质遮罩；皮肤通常 255，非皮肤通常 0）。

贴图基础色可直接填 **PNG**（导出时自动转 DDS），也可填现成 DDS。只有基础色时勾
**「中性 t1/t4」**，导出会自动绑定中性遮罩与暗面图，避免游戏原版 t1/t4 叠在新贴图上。

注意：`t4.rgb` 不是投影阴影贴图，而是进入卡通暗面时采样的材质颜色。它应该和 `t0`
同 UV、同图案，只是更暗或轻微偏色；如果只换 `t0` 不换 `t4`，暗面会继续读原服装的
`sdw`，出现不属于当前衣服的彩色图案。

### 6. 分材质烘焙 t1/t4（0.5.0 新增）

把自定义 atlas（尤其 MMD 等自带 UV、无游戏 t1/t4 来源的模型）按 **Blender 材质槽**
逐材质烘焙出贴合游戏观感的 t1/t4，比平铺「中性」更接近原作。预设数值由实机抓帧
逐材质实测得来，存放于 [`material_presets.json`](material_presets.json)。

用法：

1. 在 Blender 给模型分材质（披风 / 制服 / 皮肤 / 皮鞋…各一个材质）；
2. 填好上方「基础色 t0」（PNG）；
3. 在「分材质烘焙」区给每个材质选 **材质类型**，需要时只调每行的 **明暗**；
4. 如有外部阴影阈值 / 粗糙度等图，可在 `t1 通道输入` 只填对应通道；
5. 点 `按材质烘焙 t1/t4` → 自动写成同基础色尺寸的 DDS 并设为导出 t1/t4 → 正常校验导出。

材质类型预设（归一化 0–1）：

| 类型 | 明暗阈值 | 光滑度 | 金属度 | t1.A 门控/AO | t4.A | 适用 |
| --- | --- | --- | --- | --- | --- | --- |
| 皮肤 | 0.45 | 0.13 | 0 | 0 | 1 | 裸露皮肤 |
| 布料 | 0.38 | 0.40 | 0 | 0 | 0 | 制服/衬衫/针织袜（不分颜色） |
| 皮鞋/哑光皮革 | 0.42 | 0.38 | 0 | 0.10 | 0 | 皮鞋 |
| 皮革/塑料(亮面) | 0.50 | 0.70 | 0 | 0.54 | 0 | 漆皮/塑料件 |
| 金属 | 0.34 | 0.73 | 0.75 | 0.57 | 0 | 金属扣/饰品 |
| 头发 | 0.263 | 0.125 | 0 | 0 | 0 | 发丝（见下方 hair 语义） |
| 中性 | 1.0 | 0 | 0 | 1.0 | 0 | 等价旧「中性」 |

每个材质行只有一个手动微调（-1 = 用预设，只影响该材质）：

- **明暗**：即 t1 的 toon 阴影阈值。越低阴影越大越暗、越高受光越多越亮；控制明暗分界落在哪、阴影铺多大。
- **t4.A**：不提供手动选项。它由材质类型预设自动写入二值结果：皮肤通常 255，非皮肤通常 0；它不是透明度，也不是连续阴影强度。
- 配合用：**明暗决定暗面铺多大，t4.RGB 决定暗面材质颜色，t4.A 由材质类型固定。**

#### t1 单通道输入（0.7.0）

`t1` 是 PackedMask：

| 通道 | 作用 | 常见输入 |
|---|---|---|
| `R` | 卡通阴影阈值 / 进暗面范围 | 外部模型的 Rmask、toon mask |
| `G` | 光滑度 | roughness/smoothness 转换图 |
| `B` | 金属度 | metallic 图 |
| `A` | 镜面 / 间接光可见性门控；body 常按 AO 使用 | AO 图 |

推荐外部服装的首选流程：

1. `基础色 t0` 填单图 atlas PNG。
2. 只把外部阴影阈值图填到 `t1.R 阴影阈值`；`t1.G/B/A` 先留空。
3. 在步骤③的「材质槽设置」区选择 `皮肤 / 布料 / 皮鞋 / 金属...`；身体材质同时在这里选择
   `不透明 / 原生 co`，再点 `按材质生成 t1/t4 并校准肤色`。
4. 若暗面范围不对，先调整 `t1.R` 的黑白点 / 输出范围或材质行的 `明暗`，不要把 Rmask 直接塞满 `t1.G/B/A`。

四个 t1 通道都填时，插件认为你提供了完整 PackedMask，会整图合成。只填部分通道时，插件会先按材质预设生成完整 t1，再只覆盖有有效内容的材质区域；空白 atlas 黑区不会覆盖未贴图材质。

> 几何 AO 软化（可选，默认关）：从网格烘 AO 只对凹陷缝隙加深阴影，对光滑凸面（腿/袜）
> 无效；圆柱体的硬光影分界应用「明暗」调，而非 AO。

#### 肤色对齐原版（默认开）

脸和头发用的是**原版贴图**，身体是你的，肤色不对齐脖子上就有一道色差断层。烘焙时会把材质类型
标为**皮肤**的区域整体缩放到原版身体肤色 `(254, 230, 218)`，t4 从 t0 派生所以自动跟着修正。

- **实测该肤色跨角色相同**（atbm/hmsz/fktn/jsna 共 16 套服装、58,651 个皮肤顶点，
  差异在一个量化桶内）。角色间的肤色差异走 `_RampMap`，不在 t0 上，所以没有按角色的选项。
- 缩放是**统一系数**，你画在皮肤上的阴影、腮红、渐变按比例保留，不会被抹平。
- 校准后的 t0 **另存并回填到「基础色 t0」栏，不改你的原文件**；回退把那栏改回自己的路径。
- 完成提示会打出 `肤色 [你的] → [校准后]（原版 [...]）`。若材质类型标错或皮肤 UV 没覆盖，
  会明确报「未校准」及原因，不会静默跳过、也不会把非皮肤区刷成肉色。
- **不覆盖 `co 基础色 t0`**：原生 co 是镂空装饰件，正常不含皮肤。皮肤别标成「原生co」。

#### hair 组件的贴图 / 顶点色语义（0.7.4；2026-07-14 多抓帧闭环）

hair 与 body 共用主光照框架，但原图作者规则、附加 HHL pass 和顶点参数分布不同。制作目标选
「发型（hair）」后插件使用以下**安全作者默认值**；完整逆向见
[`../research/hair-shader-analysis.md`](../research/hair-shader-analysis.md)：

- **t0 Alpha**：普通 PNG 通常隐式带 A=255，但原生 hair 大部分区域接近 0；它是刘海 coverage，
  不是普通透明度。0.7.8 默认保留作者 Alpha，需要禁用 Coverage 时再关闭「使用 t0.A 发丝覆盖率」。
  `Hair21_D.png` 这类需要眉眼透出的图应保持开启。HairProp 始终保留作者 Alpha。完整的输入路径和准备要求见
  [`research/step3-texture-input-guide.md`](../research/step3-texture-input-guide.md)。
- **t1 PackedMask**：R=toon 阈值、G=光滑度、B=金属度、A=镜面/间接/HHL 可见性门控。
  当前插件不替换 t6 发丝高光图，所以自定义 UV 用 A=0 屏蔽旧 HHL；安全中性预设为
  `(67,32,0,0)`，并不表示所有原版 hair 都是常量图。
- **t4 ShadeColor**：RGB 是独立的作者暗面颜色，A 在两套暗面公式间选择，hair 通常为 0。
  缺少独立 t4 时，插件用 hmsz 样本的线性冷阴影乘数 `(0.378,0.367,0.474)` 作 fallback；
  这是安全预设，不是 shader 固定公式。
- **顶点色 COLOR**：
  - 原版支持按顶点/发片变化的描边色；插件对任意新拓扑采用**全网格常量安全档**，避免
    错误区域映射和暗部量化塌绿。导出面板按发色明度选「发型描边色档」：
    深色发 `(0,0,1)` / 粉红发 `(1,0,0)` / 金浅色发 `(4,2,1)` / 纯黑 `(0,0,0)`；
    宁小勿大（描边宁暗勿亮）。
  - 精确字段是 `G低=t7 LUT 行`、`B低=描边宽度`、`A高=边缘/背光 mask`；B高/A低保留。
    这些字段由插件从**带权重参考网格**最近邻拷贝——导出 hair 时必须保留参考模型。

发饰顶点色同属常量描边语义，但发饰几何与参考不重叠，
不走参考拷贝，改为**按材质槽的「材质类型」写常量**（原版发饰实测）：
`metal` → 灰描边 `(3,3,3)` + A高 rim mask 9/15；其余类型 → 黑描边 `(0,0,0)` + A高0；
宽度 B低统一 8。金属件请把材质槽类型标成 `metal`；亮色布件（白花等）想要灰描边
也可标 metal。注意暗环境下 metal 预设的高金属度会让小饰品发乌（混入环境立方图），
饰品的 t1 建议用布料参数。`Geo_HairProp` 还可能同时包含 hair-like 与 t0.A 裁切的 `hirco`
section；是否存在 cutout/outline pass 由原 section 决定，不能靠 COLOR 单独改变。

Hair 与 HairProp 的「按材质生成 t1/t4」必须分别激活对应作者网格执行。0.7.7 起两者使用
独立临时文件名，不会再因后烘焙发饰而覆盖已经生成的 Hair PackedMask/ShadeColor。

## 7. 透明材质

材质属性 `渲染材质` 有两档：

- **不透明**：普通 body 路径，投影/遮挡/描边最稳定。
- **原生co**（`NATIVE_CO`）：使用游戏原生 `m_bdyco` 第二材质段绘制，借用原版 shader/state
  实现透明/镂空。需要当前配置档来自包含 secondary material section 的抓帧，例如 fktn
  `m_bdyco` 的 `match_first_index = 69534`；没有 co section 的配置档会导出报错，请把该材质槽
  改回「不透明」或重新生成配置档。勾选原生co 后，必须在「co 基础色 t0 / m_bdyco」填入
  单独贴图；它使用透明材质自己的 t0/UV，不会回退或借用基础色 `m_bdy` 的 t0。co 的
  `t1/t4` 也有独立字段；留空时会生成 co 专属中性图，不会共用 body 的 `t1/t4`。

> `m_bdyco` 实测更接近 cutout/alpha test：低 alpha 会被裁切，抬高到阈值以上后按 RGB 绘制；
> 中间 alpha 不应视作真正半透明混合。薄纱/玻璃类连续半透明暂不属于当前正式路线。

> 自建的 **镂空 `ALPHA_CLIP`** 与 **半透明 `ALPHA_BLEND`** 两条路径已于 2026-06-30 移除，
> 改为全力打磨「借用游戏原生第二材质段」这一条路。旧工程里残留的这两个值在导出时会被当成
> **不透明**处理。

### 原生co实机测试步骤

1. 用包含 `m_bdyco` 的抓帧生成完整配置档；本次 fktn 抓帧生成后会在 `profile.json` 里出现
   `body.section1`，并在 `drawcall_map.json` 里出现 `match_first_index = 69534` 对应的 section。
2. 激活作者模型后，在材质列表里把需要走 co 的材质槽设为 **原生co**。
3. 在「不透明 body / m_bdy」里填 body 的 `t0/t1/t4`。如果有任一材质槽设为 **原生co**，
   还必须在「原生 co / m_bdyco」里填 co 的 t0；有 co 的 t1/t4 时也填到同一区块。body
   与 co 各走各自 UV、atlas 尺寸和 t1/t4，互不干涉。
4. 点 `导出并打包 bundle`，把成品 `.bundle` + `mod.json` 放进 chinosk6 插件的
   `gakumas-local/local-files/mods/<id>/`。
5. 进游戏观察：轮廓外透明/镂空是否显示、是否有原版 co 段残留、是否亮度叠加。若不正常，
   保留 `bundle-src` 与 `mod-plugin.log` 用于排查。

原理与边界详见 [`../research/transparent-material-status.md`](../research/transparent-material-status.md)。

## 版本与打包

各版本变更见根目录 [`../CHANGELOG.md`](../CHANGELOG.md)。发布包用
`python tools/package_blender_addon.py` 生成（代码版不含资源库；加 `--with-body-lib`
可一并打包）。本地包不提交到公开仓库。
