# GakumasMI Blender 插件 0.3.5

当前状态：开发预览版。0.3.5 新增 `从抓帧生成配置档`：可以扫描
`FrameAnalysis-*` 抓帧目录，自动识别任意 Body 候选 Draw、IB、VB0/VB1、stride
和可见贴图槽位，生成 runtime-only 配置档：

- `profile.json`
- `drawcall_map.json`
- `texture_map.json`
- `material_map.json`
- `extraction-report.json`

同时保留 `更新配置档抓帧源`：用于校验已有配置档是否匹配当前抓帧。

项目仍处于 HSKI Body 单配置档验证阶段，不是面向普通作者的一键正式版。详见
[`research/current-status-and-roadmap.md`](../research/current-status-and-roadmap.md)。

目标环境：Blender 4.2 LTS。

## 安装

在 Blender 中打开：

`编辑 > 偏好设置 > 插件 > 从磁盘安装`

选择本地构建生成的 0.3.5 插件 ZIP。公开仓库不直接提交包含配置档资产的发布包。

启用 **GakumasMI** 后，面板位于：

`3D 视图 > 右侧边栏 > GakumasMI`

如果仍看到旧英文按钮，请卸载旧版插件、关闭 Blender、重新打开后再安装新版 ZIP。

## 当前主要工作流

### 1. 提取对象

- 选择 `配置档目录`；
- 可选选择 `抓帧目录`；
- 如果是未知 Body，先设置 `新配置档输出`，点击 `从抓帧生成配置档`；
- 点击 `更新配置档抓帧源`；
- 点击 `导入配置档对象` 或 `导入抓帧参考模型`。

#### 配置档目录是什么？

配置档是插件认识一个游戏对象的“规格说明书”。它不是模型本身，而是把
3DMigoto 抓帧数据和 AssetStudio 原始资源连接起来的桥。

配置档主要记录：

- 目标角色、服装和组件，例如 `hski / cstm-0000 / body`；
- 游戏内 drawcall、IB hash、VB hash、顶点数、索引数和 stride；
- 贴图槽位，例如身体 `t0/t1/t4`；
- 原始网格、骨架、BindPose 和权重来源；
- 手部、颈部等原生身体保留区域；
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
`runtime-only-frame-extracted`；之后仍应通过 `导入原模型 / 权重参考` 绑定
AssetStudio 导出的原模型 JSON 与骨架 JSON，作为蒙皮转权来源。

命令行也可以独立生成配置档：

```powershell
python tools\extract_frame_profile.py D:\Games\gakumas\FrameAnalysis-2026-06-22-105210 `
  D:\GIT\gakumas-modding\profiles\generated-body --component body
```

如果自动选择错了，可按 3DMigoto 顶部显示的 Draw 编号强制指定：

```powershell
python tools\extract_frame_profile.py <FrameAnalysis目录> <输出目录> --component body --draw 335
```

### 2. 导入对象

- 导入原始 Unity 网格 JSON；
- 导入骨架 JSON；
- 点击 `导入带权重参考模型`；
- 可生成 `原生手部 / 颈部选择集` 供后续保留和复核。

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

- 选择作者模型；
- 点击 `从配置档传递权重`；
- 检查 `GMI_WEIGHT_RISK` 和 `GMI_REVIEW_HIGH_RISK`；
- 手指、颈部、宽袖、裙摆等区域仍需要人工复核或精修。

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
- `t1`：混合遮罩，R 阴影 / G 光滑度 / B 金属度 / A 环境光遮蔽；
- `t4`：阴影色。

当前插件可创建身体材质模板并打包已有 DDS；PNG/TGA 自动转换仍待实现。

## 当前版本

插件源码版本：0.3.5。

本地发布包不会提交到公开仓库；需要时从当前源码重新打包安装。
