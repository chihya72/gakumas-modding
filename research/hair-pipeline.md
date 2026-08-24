# 发型与发饰（hair / hairprop）

> 合并自 `hair-replacement.md` 与 `hair-shader-analysis.md`（2026-08-02）。
> `step3-hair-texture-improvement.md` 已删除：它提的默认值改动 0.7.8 已实现，
> 而它自己的主结论（hair `t0.A` 默认清零）后来被推翻——清零会关闭刘海覆盖、
> 让眉毛和眼睛透不出来，现在默认保留作者 Alpha。
>
> 作者操作步骤看 [`../docs/wiki/9-发型与发饰.md`](../docs/wiki/9-发型与发饰.md)；
> 本文是它背后的资产事实与逆向证据。

**第一部分 制作**：资产结构、共享 hair 的精确选择、流程、踩坑总表。
**第二部分 shader 逆向证据**：pass 结构、t0–t7 逐通道、顶点 COLOR 位布局、描边原理。

---

# 第一部分：制作

更新时间：2026-07-14 · 状态：**路线已实机验证**（hski 兔耳换色/换网格 + 圆香花饰移植 hmsz 均通过）

> **发饰替换与 body 替换同构**：同一条导出链，只是组件与资源库不同，发型本体
> （`Geo_Hair`）与发饰（`Geo_HairProp`）都已实机验证。hair 组件的贴图/顶点色语义与 body
> 不同，见 §4 与第二部分。

## 1. 资产组织（实测事实，2026-07-13 修订）

- **一个 `_hair` bundle = 一个游戏内「发型」道具 = 两个独立部件**：发型网格 `Geo_Hair`
  （组件 `hair`）+ 发饰网格 `Geo_HairProp`（组件 `hairprop`）。378/378 个 `_hair` 包
  都同时含两者。从 octo 解密缓存获取（`Gakuen-idolmaster-ab-decrypt` 的
  `output/asset_bundle/other/`）。
- **游戏内只有「发型」选择，没有单独的「发饰」选择**——装备一个发型道具即同时渲染
  它的 Geo_Hair 与 Geo_HairProp 两个 drawcall。
- 同一角色不同 `hair-NNNN` 包的 `Geo_Hair` 不保证相同：
  hski 系列确实同拓扑（16345v/67410idx 跨包一致）但顶点位置逐包微调（pos md5 不同）；
  hmsz 系列连拓扑都不同（hair-0021: 12413v / 0023: 11459v / 0029: 12471v）。
  「官方换发饰只换 Prop」只是 hski 这类系列的近似现象，不是通则。
- **与 body/bodyco 的结构区别**：`m_bdyco` 是同一 body 网格的第二材质段（共用 VB/IB）；
  hair 与 hairprop 是**两个独立网格、各自 IB/VB、权重与贴图**，因此内部保留两个 component
  和两套 draw override，但由同一个发型 profile 与 UI 流程管理；发布时应合并为一个完整
  发型包，避免 hair 无条件覆盖其它发型。
- `cstm-NNNN_hair` 包 = 服装专属发型（同样是 Geo_Hair + Geo_HairProp 结构）。
  部分服装（如 ttmr-cstm-0111）没有专属 `_hair` 包，进游戏实穿才能确定实际用哪个发型包。
- **`Geo_HairProp` 的范围经常比"头顶挂件"大**：hski 兔耳 Prop 除耳朵外还包含编进头发的
  挑染发丝（包围盒覆盖整个头部 y 1.13–1.63）。**替换 = 整个 Prop 网格被替换**，
  自定义发饰若不带这些发丝件，原发丝会一并消失——作者必须知情。

### 1.1 多个发型共享同一基础 hair

多款发型可能共用同一个 `Geo_Hair` 基础网格，只有蒙皮骨架不同。AB 路线在**配置档匹配阶段**
用同帧 `Geo_HairProp` 的顶点数消歧（`core.py` 的 `_disambiguate_hair_by_hairprop`）；两套发型
若基础网格与发饰特征都相同则无法区分，这时要在「目标资源」填完整资源名。

> 原先记录在这里的「按 hairprop `IB hash + firstIndex` 做帧内 latch」是 3DMigoto 时代的
> 做法，已随该路线移除。

## 2. 注入与材质（兔耳抓帧 FrameAnalysis-2026-07-12-041807 验证）

| 项 | 事实 | 与 body 对比 |
|---|---|---|
| VB 布局 | VB0 stride 40 + VB1 stride 12 | **完全一致** |
| 主 VS | `fe50b7a82b0f37be` | **同一个** |
| 阴影 VS | `221c573337491c78` / `436f9c16af3b54cf` | 同族 |
| 镜子 pass | VS `5b7fff8ecccaf579`，精简 PS、不绑全局贴图 | 同 body 降级行为 |
| 材质槽（主 PS） | t0=底色 / t1=打包遮罩 / t4=暗面色（512² BC7） | **布局 A 逐槽同构** |
| 布局探测 | 全局地标 `0ff26bed` 落 ps-t2 | **0.7.2 运行时探测直接适用** |
| 额外槽 | t5=ramp（1024×4，沿用原版）、t6=hhl 占位（4×4 dummy） | 作者仍只出 3 张图 |
| 贴图族命名 | `t_chr_<id>_hir_col_alp / hir_def / hir_sdw / hir_hhl / rmp` + `hirco_*` | 对应 bdy 系 |

## 3. 制作流程

作者操作看 [`../docs/wiki/9-发型与发饰.md`](../docs/wiki/9-发型与发饰.md)。原先写在这里的
是 3DMigoto 逆解链（抓帧 → 逆算子 → compute 重蒙皮 → draw override → `mod.ini`），
已随该路线整体移除。

## 4. 发型替换踩坑总表：插件已自动处理 vs 需作者手动（2026-07-13 全程复盘）

以 scsp 圆香波波头 + 三件发饰 → hmsz-hair-0023 全程实机迭代为准。

### 4.1 插件已自动处理（gakumas_mi 0.7.4 起，作者无感）

| 坑 | 症状（修复前） | 0.7.4 处理方式 |
|---|---|---|
| hair t1.A 打开旧 HHL | A=255 允许错误 UV 采到未替换的原版 t6 → 异色高光 | 当前只替换三图，故「头发」材质预设用 (0.263, 0.125, 0, **A=0**) 屏蔽旧 HHL；以后 t6 与 A mask 必须成对开放 |
| hair t1 光滑度过高 | G≈153 以黄绿色漏进阴影 | 同上，预设 G=0.125 |
| t1 被存成 sRGB DDS | 阈值被 GPU 二次解码（0.45→0.056），整体暗沉 | PNG→DDS 按语义选格式：t0/t4=sRGB(29)、t1=线性(28) |
| hair 缺少独立 t4 | 阴影色相不对 | 缺图 fallback 用 hmsz 冷阴影 `linearMul=(0.378,0.367,0.474)`；高保真应单独绘制 t4 |
| hair 描边逐顶点错误合成 | 暗部量化塌成 (0,1,0) → 绿边 | 安全模式用全网格色档；参考拷贝保留 G低/B低/A高等独立 nibble，不能把 B/A 整字节改写 |
| hairprop 描边同病 | 黑蝴蝶结绿边 | 按材质槽类型写常量：metal=(3,3,3)+A144、其余=(0,0,0)+A0、B=8 |

### 4.2 需作者手动（流程/判断题，插件管不了）

| 事项 | 要点 |
|---|---|
| 选对源资产 | 同角色多款发型（scsp 圆香有 001/002/005/010），枚举后按骨链特征区分（如 `HAIR_Side_Tail`=马尾）并渲染预览确认，别只看编号 |
| 空间对齐 | 用**发根骨→`Head_Hair` 锚点映射 + 统一缩放**（scsp→Gakumas 实测 ×1.0557），别用原点缩放；**发型与发饰必须用同一套变换**，否则相对位置漂移 |
| 解剖差异微调 | 头骨形状差异锚点管不住（圆香耳位比莉波低 → 耳环单独 +15mm），按实机截图毫米级手动偏移部件 |
| 发饰材质类型标注 | 金属件材质槽标 `metal` → 灰描边+A高 rim mask；亮色布件（白花等）想要灰描边也标 metal；不标默认黑描边 |
| 暗环境金属发乌 | metal 预设 metallic=0.75 大量混入环境立方图，室内昏暗时小饰品会发乌——饰品建议用布料 t1 参数（或单独提亮该件暗面图） |
| 双 draw | hair 与 hairprop 需各自 draw override，但发布时合并为一个完整发型包；hair 用 hairprop selector 限定 |
| 合包在 AB 路线的落地 | 2026-08-04 前导出器只写一个 renderer，「合并成一个包」只是结论没有实现，实际只能产出半截包（只带 `Geo_HairProp` 的包实测 `pairs=1`，发型退回原版）。现在 `write_bundle_source(extra_components=...)` 支持多 renderer，副 renderer 用 `{source}__Geo_HairProp` 命名 geojson/sidecar；作者侧操作是「激活发型 + 选发饰对象」，单独导发饰会被拒绝 |
| 开发环境 | 无头脚本跑导出前，确认 Blender 已安装的 gakumas_mi 与仓库同步（枚举缺项报 `enum not found` 即版本落后） |

---

# 第二部分：shader 逆向证据

更新：2026-07-14 · 状态：**主可见 pass、t0–t7、顶点 COLOR 与描边机制已闭环**

本文记录现有游戏抓帧、反编译 shader、`Geo_Hair` / `Geo_HairProp` 和原始贴图之间能互相
验证的结论。目标不是只得到一组“看起来差不多”的预设，而是像 body 一样，从资源名、绑定、
指令数据流、逐通道实验和原始资产五个方向证明每项语义。

### 1. 结论摘要

- hair 与 body 共用同一套卡通/PBR 主光照框架；hair 的差异主要是材质类型 8 的 `hir_hhl`
  发丝高光、一个输出角度覆盖率的额外 surface pass，以及不同的顶点 COLOR 分布。
- 主可见布局 A 中，`t0=BaseColor`、`t1=Def/PackedMask`、`t2=全局环境立方图`、
  `t3=动态阴影深度图`、`t4=ShadeColor`。只有 t0/t1/t4 是每个资产自己的作者贴图。
- t1 的 RGBA 算法在 body/hair 间没有换定义：R=卡通阴影阈值、G=光滑度、B=金属度、
  A=镜面/环境/HHL 可见性门控。原版 hair 把 A 大面积写 0，只在需要原生 HHL 的小块写高；
  当前插件不能替换 t6，故自定义 UV 的安全预设仍是 A=0。
- t4.A 不是透明度或阴影强度，而是在两套暗面着色公式间选择。hair 样本几乎全为 0；
  hmsz 的 `(0.378, 0.367, 0.474)` 只是一个安全合成预设，不是 shader 的固定系数。
- COLOR 是四个 UNORM8 字节，每个字节再拆成高/低 4 bit。描边 RGB 用 `R高/R低/G高`，
  描边宽度只用 `B低`；`G低` 选择可选 t7 LUT 行，`A高` 控制主材质的边缘/背光项。
- 描边是 inverted hull：专用 VS 沿自定义的 `TANGENT.xyz` 外扩，专用 PS 不采样贴图。
  仅把 B 低 nibble 清零即可关闭宽度，不能清掉整个 B/A 字节。
- `Geo_HairProp` 只是网格容器，不等于一种 shader。它的不同 submesh 可以分别走普通 hair
  surface、带描边 hair surface，或用 t0.A≈0.33 硬裁切的 `hirco` cutout。

### 2. 证据与分析方法

#### 2.1 body 已采用的方法

body 的 t0/t1/t4 结论不是从贴图外观猜出来的，而是按以下链条冻结：

1. 从 AssetBundle 材质属性名建立初始假设：`_BaseMap / _DefMap / _ShadeMap / _RampMap /
   _RampAddMap`。
2. 在 Frame Analysis 中选择完整主可见 draw，利用资源描述符区分作者 2D 图、TextureCube
   与动态 depth；阴影、镜子等精简 pass 不参与物理槽位定性。
3. 反编译 PS，追踪每次 `Sample` 的 swizzle、参与的公式和最终输出。
4. 实机逐张/逐通道替换，观察阈值、光泽、金属、暗面颜色和遮蔽的独立变化。
5. 把结果与原始 DDS 的直方图、UV 采样和运行时 VB1/AssetStudio Geo 数据交叉核对。
6. 最后才把稳定语义写入插件的材质预设和回归测试。

本次 hair 完整复用了这套方法。额外加入两项：比较同一网格的普通 surface/覆盖 surface/描边
draw，以及逐顶点验证 `Geo_Hair*.json` 与抓帧 VB1 的 UV、COLOR 是否完全一致。

#### 2.2 已核对样本

| 抓帧 | 资产判定 | Geo 规模 | 代表性可见 draw |
|---|---|---:|---|
| `FrameAnalysis-2026-07-13-192715` | ttmr `hair-0002` | Hair 17511v/69258i；Prop 3634v/8784i | Hair 222/224，outline 225；Prop 223 |
| `FrameAnalysis-2026-07-14-011920` | jsna `cstm-0012/0024`（两者 Geo 相同） | Hair 18304v/77103i；Prop 1140v | Hair 236/238/239，outline 241；Prop cutout 237 |
| `FrameAnalysis-2026-07-14-011958` | fktn `cstm-0045` | Hair 15479v/64734i；Prop 3766v/13170i | Hair 241/243/246；Prop 242/244/245 |
| `profiles/hmsz-hair-0023-hair` | hmsz `hair-0023` | Hair 11459v/46758i；Prop 5394v/20289i | Hair 244/247；Prop 分 hair/cutout 两段 |

资产归属不是只靠文件名：IB hash、顶点/索引数、submesh 的 `firstIndex/indexCount`、VB1
顶点色共同核对。fktn 0045/0046 顶点数相同，但 HairProp VB1 有 206 个 COLOR 差异，最终能
精确排除 0046。运行时 VB1 与选中 Geo 的 COLOR 逐顶点相等，UV 最大误差约 `2.5e-8`，所以
下面的顶点通道结论可以直接用于作者数据。

#### 2.3 置信度边界

- **已证明**：纹理逻辑语义、t1/t4 各通道公式、t0.A 在各 pass 的用途、COLOR nibble 解码、
  outline 外扩方向/宽度、HairProp 分段差异。
- **高置信推断**：普通 surface 与 hair coverage 两个 draw 的组合方式。抓帧证明它们使用不同
  state，且 coverage PS 输出角度相关 alpha；但现有 Frame Analysis 没有保存完整 D3D blend
  state 描述符，因此本文不虚构具体 blend factor 名称。
- **尚未命名**：部分 Unity cbuffer/property 的原始符号名。编译产物没有调试符号，但不影响
  槽位和公式的功能定性。

### 3. Pass 结构

同一 Hair 会在一帧里多次绘制。必须先分清 pass，不能把某个精简 pass 的物理槽号当成全局
材质定义。

| pass | 代表 shader | 行为 |
|---|---|---|
| 深度/阴影，不透明 | VS `436f9c...` / `221c57...` + PS `a04da6...` | PS 输出 0；几何写深度/阴影 |
| 深度/阴影，cutout | 同族 VS + PS `df3c41...` | 采 t0.A，导数抗锯齿后约在 0.33 裁切 |
| 镜子/反射精简 | VS `5b7fff...` + PS `cf02c2...` 等 | 使用压缩槽布局，不绑主场景 cube/depth |
| 标准主 surface | VS `fe50b7...` + PS `f87275...` / `10fc39...` | 完整光照；输出 alpha=1 |
| hair coverage/material | VS `fe50b7...` + PS `306c29...` / `b41a...` | 同一主光照，输出受 t0.A 和视角影响的覆盖 alpha |
| outline | VS `e0ceaa...` + PS `58352a...` | 沿 tangent 外扩的 inverted hull；不采纹理 |

body 常只需要标准主 surface；hair 样本会连续出现标准 surface 与 coverage/material surface。
两者最终颜色主体相同，主要区别在第二 MRT 的 RGB/alpha 是否乘入 hair 覆盖项。depth/cutout、
surface、outline 是否存在由原材质 section 和原 draw 序列决定，写一个 COLOR 值不能凭空创建
原本不存在的 pass。

### 4. 槽位布局：先区分“逻辑纹理”和“物理 tN”

#### 4.1 主可见布局 A

当前 hair 主样本都命中布局 A。fktn Hair draw 243 的实际绑定为：

| 槽 | 格式/尺寸 | 逻辑资源 |
|---|---|---|
| t0 | 2048² BC7 sRGB | `hir_col_alp` / BaseColor |
| t1 | 2048² BC7 UNORM | `hir_def` / PackedMask |
| t2 | 64²×6 R9G9B9E5 | 全局 HDR 环境 TextureCube |
| t3 | 2048² R16 typeless | 当前帧阴影深度比较图 |
| t4 | 2048² BC7 sRGB | `hir_sdw` / ShadeColor |
| t5 | 1024×4 RGBA8 sRGB | 角色 toon ramp |
| t6 | 2048² BC7 sRGB | `hir_hhl` / hair highlight |
| t7 | 128×8 RGBA8 sRGB | 可选 RampAdd LUT |

#### 4.2 布局 B 与精简布局

主 shader 还存在布局 B。插件用全局 cube hash `0ff26bed` 作为运行时地标：

- cube 在 t2：布局 A，Base/Def/Shade = t0/t1/t4；
- cube 在 t3：布局 B，Base/Def/Shade = t1/t2/t5；
- 两处都没命中：保守布局 C，至少替换 t0/t1。

镜子 PS 又会把逻辑资源紧缩为如 Base=t0、Def=t1、Shade=t2、Ramp=t3、HHL=t4、
RampAdd=t5。由此可见，“作者应替换 t0/t1/t4”只是在主布局 A 下的说法；真正稳定的是
Base/Def/Shade 的逻辑角色。现有运行时地标探测比维护 PS hash 白名单更可靠。

### 5. t0–t4 与每个颜色通道

#### 5.1 t0：BaseColor / `*_hir_col_alp`

格式为 sRGB；与 t1/t4 共用 UV0。

| 通道 | 作用 |
|---|---|
| R/G/B | 线性化后的基础反照率。三个通道都是颜色，不各自承担独立 mask。材质类型为 hair 时，后续可与 t6 HHL 颜色做角度混合。 |
| A | 标准不透明 surface 不把它当普通透明度，输出仍为 1；hair coverage pass 把它变换为视角/边缘覆盖率；`hirco` cutout pass 还会以约 0.33 阈值硬裁切。 |

这解释了“原版 hair t0.A 大量为 0，但头发仍完整可见”：主体来自标准不透明 surface，不是
alpha blending。t0.A 只有在 coverage 或 cutout 材质段才改变覆盖行为，因此不能把 hair、
hairprop cutout、普通 body 的 alpha 经验混为一谈。

三个当前 Hair 样本的全图 Alpha 统计进一步说明安全默认值应为 0：ttmr 有 99.214% 像素为
0，jsna 有 97.560%，fktn 有 94.892%。非零值只集中在少量发片/条带区域；普通 RGB PNG
隐式带入的 A=255 不等价于原生 hair。插件步骤②的具体处理方案见
[`hair-pipeline.md`](hair-pipeline.md)。

#### 5.2 t1：Def / PackedMask

t1 是线性 UNORM；shader 采样后做 `.xzyw` 重排只是寄存器排列，回到 DDS 实际通道的语义如下：

| 通道 | 公式作用 | 视觉结果 |
|---|---|---|
| R | `2R-1` 平移 toon 的 `N·L` 分界；还进入部分边缘光门控 | 高值通常让受光区更大/更亮，低值让暗面铺得更多 |
| G | smoothness；内部粗糙度参数近似 `α=(1-G)^2` | 高值产生更尖的直接高光，并选择更清晰的 cube mip |
| B | metallic | 漫反射乘 `1-B`；镜面 F0 从约 0.04 向 t0 基色过渡 |
| A | specular / indirect / HHL visibility gate | 与阴影可见度夹取后，缩放 cube 环境、直接镜面以及 t6 发丝高光 |

因此旧结论“body A=AO，hair A 不是 AO”需要精确化：**shader 算法没有给 hair 换一套 A
定义**，差别来自贴图的作者用法。body 常把 A 当 AO/间接光可见性；原版 hair 的 A 大部分为
0，只在少量 HHL 岛上写高，以允许 t6 高光出现。

当前导出只替换 t0/t1/t4，不替换 t6。自定义模型通常还换了 UV，如果把 t1.A 写高，就可能
在错误 UV 位置采到原角色 t6，出现“漏出旧发色/蓝紫块”。所以 **A=0 仍是当前产品的正确
安全预设**；它是对未替换 t6 的防护，不是“hair shader 中 A 没有意义”。未来若增加 t6 替换，
t1.A 应恢复为可绘制的 HHL/镜面可见性 mask。

现行头发预设 `(67,32,0,0)` 对应 R≈0.263、G≈0.125、B=0、A=0，是 hmsz 原生样本验证过
的安全中性值，不代表所有原版 hair 的 t1 都是全图常量。

#### 5.3 t2：全局 HDR 环境 TextureCube

| 通道 | 作用 |
|---|---|
| R/G/B | 环境辐射亮度；沿 `reflect(-V,N)` 采样，LOD 由 t1.G 的 roughness/smoothness 决定，再进入 GGX IBL/镜面项 |
| A | R9G9B9E5 格式没有独立 alpha 语义 |

它是所有材质共享的场景资源，不是 hair 资产图，不应被 mod 替换。hash `0ff26bed` 的稳定性
使它适合作为布局地标，而不是作为作者贴图。

#### 5.4 t3：动态主光阴影深度图

t3 是 R16 typeless 的深度 SRV/DSV，只有一个有效深度通道，没有 RGBA 材质含义。主 PS 用
`SampleCmp` 做 4 tap PCF，叠加深度 bias 与距离淡出，得到主光/阴影可见性。它决定场景物体
投下的动态阴影，和 t4 的“材质暗面颜色”完全不是一回事，也不应被替换。

#### 5.5 t4：ShadeColor / `*_hir_sdw`

t4 是 sRGB，与 t0 共用 UV0。

| 通道 | 作用 |
|---|---|
| R/G/B | 作者绘制的暗侧反照率/图案。三个通道都是颜色，可独立偏色，不是 shadow projection 或三张 mask。 |
| A | 在“t4 暗色分支”和“t0×ramp 分支”之间选择，通常近二值；不是 opacity，也不是连续阴影强度。 |

主干可近似写成：

```text
base          = sample(t0) + optionalRampAdd(t7)
shade         = sample(t4) + optionalRampAdd(t7)
candidateSdw  = lerp(base, shade * materialTint, materialStrength * ramp.a)
rampBase      = base * ramp.rgbVariant
darkAlbedo    = lerp(candidateSdw, rampBase, t4.a)
```

之后 `darkAlbedo` 才进入饱和度、toon 明暗混合和 PBR 光照。原版 hair 的 t4.A 在本批样本中
几乎都为 0，所以直接使用作者 t4 RGB 暗色分支。

hmsz 预设 `t4_linear = t0_linear × (0.378,0.367,0.474)` 是从该角色采样出的实用 fallback，
不是 shader 公式。用当前 Geo UV 对原图取样得到的线性空间 t4/t0 中位数已经明显不同：

| 样本 | R | G | B |
|---|---:|---:|---:|
| ttmr | 0.399 | 0.408 | 0.585 |
| jsna | 0.891 | 0.532 | 0.523 |
| fktn | 0.630 | 0.388 | 0.416 |

所以高保真作者流程应允许单独绘制 t4；自动乘数只能作为缺图时的安全默认值。

### 6. t5–t7：为什么只换三张图仍能工作、又为何不是完整保真

#### t5：Toon Ramp

1024×4 的角色/材质 ramp。x 坐标来自 toon 光照因子，当前变体只取特定行；RGB 塑造亮暗
过渡的色调，A 调节 t0/t4 两套暗面公式的混合强度。它通常是角色共享资源，当前 mod 沿用
原版即可得到稳定结果。

#### t6：Hair Highlight / `hir_hhl`

仅 hair 材质类型使用的 UV 颜色图。shader 根据视线/法线角度生成条带状权重，把 t6 RGB 混入
t0；最终强度受 t1.A 和阴影可见性门控。普通发饰可能绑定 4×4 黑 dummy，原生 hair 则常是
2K 图。

这是当前三图方案与“完整替换 hair 材质”之间最大的剩余差距：A=0 会可靠屏蔽旧 HHL，但也
同时放弃原版式发丝高光。若要恢复，应把 t6 与 t1.A 作为一对提供，不能只开放其中一个。

#### t7：RampAdd LUT

可选的 128×8 LUT。x 来自视角/法线和阈值，y 来自顶点 COLOR 的 G 低 nibble `/15`；
`RGB×(1-A)` 会同时加到 t0 和 t4。不是所有 PS 都绑定 t7，例如 `10fc39...` 变体没有它，
`306c29...` 变体有。插件应保留参考 COLOR 的 G 低 nibble，不能为了统一描边色把整个 G 覆盖。

### 7. 顶点 COLOR 的精确位布局

输入为 `COLOR.rgba` 四个 UNORM8 字节。VS 把每字节拆成高/低 nibble：

```text
byte = high * 16 + low
decodedNibble = nibble / 15
```

主 VS `fe50b7...` 输出：

```text
COLOR0   = (R高, R低, G高, G低) / 15
TEXCOORD2 = (B高, B低, A高, A低) / 15
```

各字段在已检查 shader 家族中的用途：

| 字段 | 主 surface | outline | 当前结论 |
|---|---|---|---|
| R 高 | 未使用 | outline R | 描边红 |
| R 低 | 未使用 | outline G | 描边绿 |
| G 高 | 未使用 | outline B | 描边蓝 |
| G 低 | t7 LUT 行 | 未使用 | RampAdd 材质/区域 band |
| B 高 | 未见使用 | 未使用 | 保留/未知，不能随意清零 |
| B 低 | 未使用 | 外扩宽度 | 描边宽度 0–15 |
| A 高 | 边缘/背光附加项 mask | 未使用 | directional rim/backlight 强度 |
| A 低 | 未见使用 | 未使用 | 保留/未知 |

主材质中 A 高大致缩放一个 `min(1,2*t1.R)`、随 `(1-N·direction)^power` 增长的方向性
边缘/背光项。因此 `A=144 (0x90)` 的真实含义是 A高=9/15、A低=0，不是神秘的“hair
二值高光开关”；0x10–0x80 等中间值也是合法过渡。

同理，“B 是 0–15”也不严谨。原始 B 字节可以是 `0xF0–0xFF`，outline 只读低 4 bit；
现有 `_clear_outline_width()` 用 `B &= 0xF0` 是正确实现，既关闭描边又保留未知的 B 高 nibble。

#### 7.1 Geo 样本说明了什么

- hmsz Hair 的 R=0、G=16 基本恒定，所以描边 nibble RGB=(0,0,1)；B低在 0–15 变化，A高
  主要是 0 或 9。
- ttmr Hair 的描边 RGB 基本为 (0,0,0)。
- jsna Hair 存在多个大区域，如 (4,1,0)、(3,1,3)、(4,1,1)。
- fktn Hair 以 (4,2,1) 为主，也有 (7,3,2) 等区域；G低多数为 0，但有 130 个顶点为 15。

结论是引擎原生支持**按顶点/发片岛变化的描边色和附加 LUT band**。插件当前“全网格描边
色档”仍是新拓扑最稳的作者默认值，但它是防止错误最近邻/暗部量化的产品简化，不是 shader
限制。高保真模式可以保留或显式绘制这些 nibble。

### 8. 描边工作原理

#### 8.1 Inverted hull，而不是屏幕后处理

outline draw 使用 VS `e0ceaa...` + PS `58352a...`：

1. 使用同一网格，以不同 rasterizer/cull state 绘制外壳；
2. VS 沿每顶点的 `TANGENT.xyz` 外扩；
3. 正面被剔除，只留下比原网格稍大的背面轮廓；
4. PS 输出解码后的描边色以及延迟管线需要的 motion/depth 数据，不采样 t0–t7。

外扩可近似为：

```text
offset = TANGENT.xyz
       * 0.01
       * cameraDistanceScale(cb0[144])
       * (COLOR.B_low / 15)
```

投影后还施加约 `projectedZ - viewZ*6.6667e-5` 的深度偏移，以降低与主体表面的 z-fighting。

#### 8.2 为什么必须保留 `GMI_TANGENT`

这里的 tangent 不是普通 UV 切线，而是人为平滑过的 outline extrusion direction。Geo 实测
`normal·tangent` 中位数：hmsz Hair≈0.936、fktn Hair≈0.872、两个 Prop≈0.997/0.999，说明
它接近法线但允许美术修形。如果导出器把它重算成沿 UV 的表面切线，外壳会沿表面滑开、断裂
或整圈消失。

当前导出器把按位置+材质平滑后的法线写入 `GMI_TANGENT`，适合作为任意新拓扑的安全近似；
同拓扑/高保真移植则应保留原始 tangent。

#### 8.3 描边颜色不是 COLOR 的字面值

PS 先取得 `(R高,R低,G高)/15`，再乘材质/全局参数（包括 `cb1[14]`、`cb0[137]`）。因此
顶点 nibble 是材质输入，不是最终屏幕 RGB；不同场景/材质仍可能让同一 nibble 看起来深浅不同。

同时要满足两个条件才会出现描边：原材质 section 有 outline draw，且 B低>0。某个 HairProp
section 若抓帧里没有 outline pass，单独把 COLOR.B 改成 15 也不会生成描边。

### 9. HairProp：必须按 submesh/material section 分析

`Geo_HairProp` 只表示“这个发型道具附带的第二张网格”，不保证所有 submesh 使用相同材质：

- fktn 0045 Prop：submesh0（9018 indices）走标准 hair-like surface `306c29...` 并有 outline；
  submesh1（4152 indices）走 `7a9af1...` cutout，t0.A≈0.33 裁切，本帧未见 outline。
- hmsz 0023 Prop：第一段（7989 indices）为 `0493c9...` cutout；第二段（12300 indices）走
  hair-like `306c29...` 并有 outline。
- jsna Prop 的可见段也使用 cutout `0493c9...`。

这会直接影响替换策略：

1. profile 必须保存每个 section 的 `firstIndex/indexCount` 和原 pass 序列；
2. hair-like 段可沿用 hair 的 Base/Def/Shade 规则；
3. `hirco` 段必须正确制作 t0.A，不能只看 RGB；
4. 不应给整张 HairProp 强行套一种 alpha 或 outline 规则；
5. 当前按材质槽生成常量描边是安全 fallback，不等同于复刻原 section 的全部 COLOR 参数。

### 10. 对当前插件行为的影响

#### 10.1 保留不变的安全默认

- 继续只自动替换逻辑 Base/Def/Shade，不碰全局 t2/t3。
- hair 中性 t1 保持 `(67,32,0,0)`，避免未替换 t6 泄漏。
- 缺失 t4 时可继续用 hmsz 冷阴影乘数，但 UI/文档必须标明“fallback”，不宣称原生固定公式。
- 任意新拓扑继续使用常量描边色档；关闭描边只清 B 低 nibble。
- 保持运行时 cube 地标探测，不建立逐 PS hash 列表。

#### 10.2 下一阶段的正确顺序

1. **高保真 HHL 对**：把可选 t6 和 t1.A mask 一起加入 hair 材质导出；无 t6 时仍强制/提示
   A=0。两者必须成对交付。
2. **HairProp section 语义**：profile/UI 显式区分 hair-like 与 `hirco` cutout 段，并验证各段
   的 t0.A、材质槽和 outline pass 是否保留。
3. **高级 packed COLOR**：安全默认仍用常量档；另提供“保留参考/按顶点绘制”路径，分别维护
   outline RGB、G低 band、B低宽度、A高 rim，不能再把 B/A 当成整字节二值字段。
4. **可重复的 shader 合约测试**：把布局 A/B、COLOR nibble 解码、仅清 B低、t1/t4 预设边界
   固化为纯 Python 合约；不为单个 shader hash 构建长期枚举系统。

这四步完成后，hair 才从“安全地换三张图且不漏旧材质”升级为“可以有意识地复刻原版发丝
高光、材质分段和逐岛描边”。
