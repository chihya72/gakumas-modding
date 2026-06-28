# GakumasMI Blender 插件 0.6.0

当前状态：开发预览版。建配置档已收敛为**一键流程**：填「抓帧目录」+
「Body JSON资源库」，点 `一键生成完整配置档（注入+结构+逆算子）` 即可一次产出
**①注入信息 + ②结构数据 + ③逆算子** 的完整配置档。

- 自动按顶点+索引数从资源库匹配 `Geo_Body.json`，同拓扑服装按 bind pose 自动判等价；
- 仅有 Mesh、没有 Unity 骨架的 body：从 `m_BoneNameHashes` + `m_BindPose`
  **合成骨架**，因此资源库里 500+ 套都能一键匹配（不再只限有骨架的样本）；
- 自动构建逆算子并标出不可观测骨；
- 移除了手/颈拆件等已排除路线；`从配置档传递权重` 增加了对齐守卫。

底层仍保留分步入口(`仅生成注入信息` 等)与 `更新配置档抓帧源` 校验。

项目仍处于 HSKI Body 单配置档验证阶段，不是面向普通作者的一键正式版。详见
[`research/current-status-and-roadmap.md`](../research/current-status-and-roadmap.md)。

目标环境：Blender 4.2 LTS。

## 安装

在 Blender 中打开：

`编辑 > 偏好设置 > 插件 > 从磁盘安装`

选择本地构建生成的 0.6.0 插件 ZIP。公开仓库不直接提交包含配置档资产的发布包。

启用 **GakumasMI** 后，面板位于：

`3D 视图 > 右侧边栏 > GakumasMI`

如果仍看到旧英文按钮，请卸载旧版插件、关闭 Blender、重新打开后再安装新版 ZIP。

## 当前主要工作流

### 1. 提取对象（一键生成完整配置档）

主流程只要两个输入 + 一个按钮：

- 选项 1：填 `抓帧目录`（FrameAnalysis-*）；
- 选项 2：填 `Body JSON资源库`（AssetStudio 导出的 geo.json 资源包）；
- 点击 **`一键生成完整配置档（注入+结构+逆算子）`**。

它会一次完成：

1. **① 注入信息**：扫描抓帧，识别 Body 的 Draw / IB·VB hash / stride / 贴图槽；
2. **② 结构数据**：按顶点+索引数从资源库匹配到对应 `Geo_Body.json` + 骨架，复制进配置档 `Reference/`；
3. **③ 逆算子**：由 bind pose + 四权重构建 `Buffers/InverseOperator.R32_FLOAT.buf`，并写入
   `skinning.inverseSkin`（含自动标出的不可观测骨）。

完成后 `配置档目录` 自动指向新配置档，可直接进入「导入对象 → 蒙皮转权 → 导出」。

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
- 导出 3DMigoto 模组时需要生成的配置。

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
导出的原模型 JSON 与骨架 JSON，作为蒙皮转权来源。

命令行也可以独立生成配置档：

```powershell
python tools\extract_frame_profile.py D:\Games\gakumas\FrameAnalysis-2026-06-22-105210 `
  D:\GIT\gakumas-modding\profiles\generated-body --component body
```

如果自动选择错了，可按 3DMigoto 顶部显示的 Draw 编号强制指定：

```powershell
python tools\extract_frame_profile.py <FrameAnalysis目录> <输出目录> --component body --draw 335
```

#### 批量导出所有 Body 的原模型 JSON / 骨架 JSON

把游戏缓存里的 body AB 文件放到仓库根目录 `all_body/` 后，可以用：

```powershell
python tools\export_all_body_json.py
```

默认参数：

- 输入目录：`all_body/`
- 输出目录：`build/assetstudio-body-json/`
- AssetStudio CLI：`D:\GIT\AssetStudio-net10.0-win\AssetStudio.CLI.exe`
- Unity 版本：`6000.0.67f1`

输出会按 body 资源名分目录，避免所有 Mesh 都叫 `Geo_Body.json` 时互相覆盖。
这些目录整体就是插件使用的 `Body JSON资源库`：

```text
build/assetstudio-body-json/
  mdl_chr_hski-cstm-0000_body/
    Geo_Body.json
    Geo_Body.skeleton.json
```

只导出 Mesh JSON：

```powershell
python tools\export_all_body_json.py
```

同时生成骨架 JSON：

```powershell
python tools\export_all_body_json.py --skeleton
```

注意：`Geo_Body.json`（Mesh，含 bind pose / 权重 / bindpose / 骨骼 hash）会**始终保留**，
作为对外发布的资源包；逆解链不依赖骨架层级。`Geo_Body.skeleton.json` 只在严格可读时
生成（`m_Bones` 为空或骨骼 Transform 指向未加载依赖时跳过，状态记为 `mesh-only`，但 Mesh 保留）。
**仅 Mesh 的条目也能一键匹配**：缺骨架时从 `m_BoneNameHashes` + `m_BindPose` 合成骨架，
因此 500+ 套全部可用。

`Body JSON资源库`（约数 GB）作为**单独资源包**发布，不打进插件 zip。开发环境默认指向
`build/assetstudio-body-json/`；实际使用时把资源包目录路径填进插件「选项2」即可。

调试前几个文件：

```powershell
python tools\export_all_body_json.py --limit 5 --force --skeleton
```

### 2. 导入对象

- 选择或使用内置 `Body JSON资源库`；
- 点击 `匹配 Body JSON资源库`；
- 点击 `导入带权重参考模型`。

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

插件需要两者一起导入带权重参考模型。之后作者模型才能从这个参考模型上转移权重。

### 3. 蒙皮转权

**前提：作者模型必须先和参考身体空间对齐。** 逆解矩阵与逆算子都工作在参考身体的
bind 空间，导出又会烘焙 `matrix_world @ co`，所以作者模型必须：

- 摆到参考身体所在的位置、保持接近的尺寸（同为 T-pose）；
- 按 `Ctrl+A` 应用缩放 / 旋转；
- **不要去映射 / retarget 作者模型自带的骨架**——只保留几何，靠空间对齐 + 最近表面
  把参考身体的权重传过来。

操作：

- 选择作者模型；
- 点击 `从配置档传递权重`；
  - 如果模型未对齐 / 尺寸相差过大，插件会直接报错并提示如何修正；
  - 存在未应用变换时会给出警告。
- 检查 `GMI_WEIGHT_RISK` 和 `GMI_REVIEW_HIGH_RISK`；导出页的“描边宽度”默认关闭全部，用于规避/诊断新拓扑裙子、披风的描边壳异常。确认模型稳定后可改为“仅风险顶点”或“保留”；需要手动关闭描边的裙内侧/问题三角，可加入 `GMI_NO_OUTLINE` 顶点组；
- 新拓扑衣服的“顶点 COLOR”默认使用“衣物常量”，这是最稳的无斑纹/无色块方案并保留描边宽度。COLOR 是游戏打包材质参数，不是普通颜色；原版抓帧 COLOR 带有区域/拓扑假设，不能简单按材质复用；“拷原版”只适合同拓扑或非常贴身的替换；
- 手指、宽袖、裙摆等区域仍需要人工复核或精修。

### 4. 导出模组

- 推荐直接点击 `校验并导出模组`；
- 如需排错，可先点击 `校验网格`；
- 当前作者流程只暴露带权重 GPU 导出路线。

#### 网格导出按钮说明

普通作者优先使用 `校验并导出模组`。插件界面只保留当前主线导出入口，避免误用
研究阶段功能。

| 按钮 | 用途 | 推荐程度 |
|---|---|---|
| `校验并导出模组` | 先校验，再按当前对象类型选择合适导出方式 | 主流程 |
| `校验网格` | 只检查当前网格，不导出 | 排错时使用 |
| `导出带权重 GPU 模组` | 导出任意拓扑模型，使用游戏内恢复的动画矩阵驱动 | 当前主线实验出口 |

`导出带权重 GPU 模组` 是当前最接近 WWMI/EFMI/GIMI 思路的出口：作者模型需要先被转成
当前配置档兼容的骨骼权重，再由游戏内恢复的动画矩阵驱动。

### 5. 材质模板

HSKI Body 已验证的身体贴图语义：

- `t0`：基础色；
- `t1`：混合遮罩，R 阴影阈值 / G 光滑度 / B 金属度 / A 环境光遮蔽；
- `t4`：阴影色（RGB=阴影色，A=叠加强度）。

贴图基础色可直接填 **PNG**（导出时自动转 DDS），也可填现成 DDS。只有基础色时勾
**「中性 t1/t4」**，导出会自动绑定中性遮罩/阴影，避免游戏原版 t1/t4 叠在新贴图上。

### 6. 分材质烘焙 t1/t4（0.5.0 新增）

把自定义 atlas（尤其 MMD 等自带 UV、无游戏 t1/t4 来源的模型）按 **Blender 材质槽**
逐材质烘焙出贴合游戏观感的 t1/t4，比平铺「中性」更接近原作。预设数值由实机抓帧
逐材质实测得来，存放于 [`material_presets.json`](material_presets.json)。

用法：

1. 在 Blender 给模型分材质（披风 / 制服 / 皮肤 / 皮鞋…各一个材质）；
2. 填好上方「基础色 t0」（PNG）；
3. 在「分材质烘焙」区给每个材质选 **材质类型**，需要时用每行的 **明暗 / 阴影色** 微调；
4. 点 `按材质烘焙 t1/t4` → 自动写成 2048² DDS 并设为导出 t1/t4 → 正常校验导出。

材质类型预设（归一化 0–1）：

| 类型 | 明暗阈值 | 光滑度 | 金属度 | AO | 阴影色 | 适用 |
| --- | --- | --- | --- | --- | --- | --- |
| 皮肤 | 0.45 | 0.13 | 0 | 0 | 固定珊瑚·0.6 | 裸露皮肤 |
| 布料 | 0.38 | 0.40 | 0 | 0 | 派生·0.12 | 制服/衬衫/针织袜（不分颜色） |
| 皮鞋/哑光皮革 | 0.42 | 0.38 | 0 | 0.10 | 派生·0 | 皮鞋 |
| 皮革/塑料(亮面) | 0.50 | 0.70 | 0 | 0.54 | 派生·0.20 | 漆皮/塑料件 |
| 金属 | 0.34 | 0.73 | 0.75 | 0.57 | 派生·0.20 | 金属扣/饰品 |
| 头发 | 0.45 | 0.60 | 0 | 0 | 派生·0.40 | 发丝 |
| 中性 | 1.0 | 0 | 0 | 1.0 | 派生·0 | 等价旧「中性」 |

每个材质行的两个微调（-1 = 用预设，只影响该材质）：

- **明暗**：即 t1 的 toon 阴影阈值。越低阴影越大越暗、越高受光越多越亮；控制明暗分界落在哪、阴影铺多大。
- **阴影色**：即 t4 阴影色的叠加强度。越高阴影区颜色越浓、越低越淡。
- 配合用：**明暗决定阴影铺多大，阴影色决定阴影多浓。**

> 几何 AO 软化（可选，默认关）：从网格烘 AO 只对凹陷缝隙加深阴影，对光滑凸面（腿/袜）
> 无效；圆柱体的硬光影分界应用「明暗」调，而非 AO。

## 7. 透明材质

材质属性 `渲染材质` 选 **透明** 即走透明路径（`gmi_alpha_mode = ALPHA_BLEND`）。当前为
**保守路径**：优先保证 A=0 镂空干净 + 投影/遮挡正常；半透明只在「背后已有同模型/同角色
其它几何或 coverage」的像素上可靠显示，伸出角色轮廓外、背后纯背景的半透明暂不保证。
原理与边界详见 [`../research/transparent-material-status.md`](../research/transparent-material-status.md)。

## 版本与打包

各版本变更见根目录 [`../CHANGELOG.md`](../CHANGELOG.md)。发布包用
`python tools/package_blender_addon.py` 生成（代码版不含资源库；加 `--with-body-lib`
可一并打包）。本地包不提交到公开仓库。
