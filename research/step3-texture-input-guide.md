# 步骤②贴图输入指南：Body / Hair / HairProp

更新：2026-07-14
适用：GakumasMI 0.9.x 步骤②「准备材质」。
（0.7.x 里贴图填在四步 UI 的步骤③，0.9.0 收成三步后改到步骤②；文件名 `step3-` 是历史遗留，
为不打断既有链接保留。）

这份文档只说明**作者模型需要准备哪些图像、在 Blender 哪个路径填写**。这些路径不是游戏原始文件路径，而是作者自己制作的 PNG/DDS 文件路径。

## 1. 先记住三张主贴图

每个被替换的组件都按同一套主槽位填写：

| Blender 字段 | 游戏槽位 | 作用 | 是否必填 |
|---|---|---|---|
| 基础色 t0 | `ps-t0` | 角色最终显示的基础颜色 | 是 |
| 混合遮罩 t1 | `ps-t1` | 阴影阈值、光滑度、金属度、镜面/间接光门控 | 可选 |
| 暗面材质 t4/sdw | `ps-t4` | 卡通暗面使用的颜色与材质分支 | 可选 |

填写 t0 后，如果没有现成 t1/t4，应使用「按材质生成 t1/t4 并校准肤色」；如果只想先测试颜色，可以开启「中性 t1/t4」。不要让插件沿用目标角色原来的 t1/t4，否则新 UV 会采到旧衣服或旧发型的颜色块。

推荐目录：

```text
MyMod/
├─ textures/
│  ├─ body_t0.png
│  ├─ body_t1.png
│  ├─ body_t4.png
│  ├─ hair_t0.png
│  ├─ hair_t1.png
│  ├─ hair_t4.png
│  ├─ hairprop_t0.png
│  ├─ hairprop_t1.png
│  └─ hairprop_t4.png
└─ ...
```

PNG 可以直接填，插件会在导出时转换为 DDS；已有 DDS 也可以直接填。三张图必须是正方形，并且同一组件的 t0/t1/t4 使用同一 UV 布局和尺寸。

## 2. Body（身体/服装）要填什么

在步骤②激活 Body 作者网格后填写：

| Blender 路径 | 文件示例 | 图像要求 |
|---|---|---|
| `基础色 t0` | `textures/body_t0.png` | 身体、脸、衣服、配件的基础色；RGB 是颜色，A 通常不是普通透明度 |
| `混合遮罩 t1` | `textures/body_t1.png` | 线性 RGBA PackedMask；通道语义见下表 |
| `暗面材质 t4/sdw` | `textures/body_t4.png` | 与 t0 同 UV 的暗色版本；不是动态投影阴影图 |

Body t1 通道：

| 通道 | 作用 | 常见作者输入 |
|---|---|---|
| R | 卡通阴影阈值；越低通常暗面越大 | toon mask / shadow threshold |
| G | 光滑度 | smoothness/roughness 转换图 |
| B | 金属度 | metallic 图 |
| A | AO、镜面与间接光可见性门控 | AO 或材质可见性图 |

如果只准备了一张 t0：

1. 把 t0 填到 `基础色 t0`；
2. 保持「中性 t1/t4」开启，或点「按材质生成 t1/t4 并校准肤色」；
3. 不要把普通 AO 直接当成完整 t1，除非它已经被放入正确的 A 通道。

### Body 的原生 co（透明/镂空部件）

只有在上方材质槽的「渲染材质」选择「原生 co」时，才填写下面三项：

| Blender 路径 | 文件示例 | 要求 |
|---|---|---|
| `co 基础色 t0 / m_bdyco` | `textures/body_co_t0.png` | 透明/镂空部件自己的 RGBA；A 用于镂空，透明区 RGB 要外扩 |
| `co 混合遮罩 t1` | `textures/body_co_t1.png` | co 部件自己的 PackedMask，不共用身体 t1 |
| `co 暗面材质 t4/sdw` | `textures/body_co_t4.png` | co 部件自己的暗面图，不共用身体 t4 |

如果没有选择「原生 co」，这三项必须留空。co 图不能拿身体主 t0/t1/t4 代替。

## 3. Hair（头发主体）要填什么

在步骤②选择「发型（hair）」并激活 Hair 作者网格后填写：

| Blender 路径 | 文件示例 | 图像要求 |
|---|---|---|
| `基础色 t0` | `textures/hair_t0.png` | 发丝基础色；RGB 是发色，A 是特殊 hair coverage，不是普通透明度 |
| `混合遮罩 t1` | `textures/hair_t1.png` | R 阴影阈值、G 光滑度、B 金属度、A 镜面/间接光/HHL 门控 |
| `暗面材质 t4/sdw` | `textures/hair_t4.png` | 发丝暗面 RGB；通常与 t0 同 UV，A 通常为 0 |

### Hair t0.A 必须特别处理

Hair 的 t0.A 会被特殊 Coverage Pass 使用：

- `A=0`：头发主体保持不透明，眉毛和眼睛不能透过刘海；
- `A>0`：允许视角相关的发丝覆盖，眉眼可在适当区域透出；
- 它不是 PNG 普通透明度，也不是把整张图做成半透明。

因此：

- 如果作者明确绘制了刘海覆盖 Alpha，勾选「使用 t0.A 发丝覆盖率」并保留该 Alpha；
- `Hair21_D.png` 这类全图 A=255 的图可以用于恢复眉眼透出，但它会让整顶头发启用 Coverage，最好后续把 Alpha 改成只覆盖前额/眉眼区域；
- 不要把「普通 PNG 默认 A=255」误认为原版 coverage mask。通用发型不应盲目把所有区域设为 255。

Hair 的 t1.A 当前通常建议为 0，因为插件主流程不替换 t6 发丝高光图；如果把 t1.A 写高，换过 UV 的新发型可能错误采到原角色 t6，产生蓝紫色斑纹或旧发色泄漏。

## 4. HairProp（发饰）要填什么

只有在同时替换发饰网格 `Geo_HairProp` 时，才填写发饰三项：

| Blender 路径 | 文件示例 | 图像要求 |
|---|---|---|
| `发饰基础色 t0` | `textures/hairprop_t0.png` | 发夹、蝴蝶结、花饰等发饰自己的基础色 |
| `发饰混合遮罩 t1` | `textures/hairprop_t1.png` | 发饰自己的 PackedMask；金属、布料可使用不同材质槽参数 |
| `发饰暗面材质 t4/sdw` | `textures/hairprop_t4.png` | 发饰自己的暗面颜色 |

发饰路径不能复用 Hair 路径：

- Hair 做了、HairProp 没做：发饰三项全部留空，游戏保留原发饰；
- HairProp 做了：三项都应填写，至少必须有发饰 t0，否则颜色会沿用原发饰；
- HairProp 的贴图必须按发饰自己的 UV 制作，不能按 Hair 的 UV atlas 绘制；
- HairProp 的 t0.A 是否用于 cutout/coverage 取决于原始材质 section，不能把整张发饰 Alpha 强行当普通透明度。

「按材质生成 t1/t4 并校准肤色」必须分别激活 Hair 和 HairProp 作者网格执行。两者使用不同的临时输出，不会互相覆盖。

## 5. 可选的 t1 单通道输入

步骤②还可以只给某个 t1 通道一张图：

| Blender 路径 | 写入通道 | 适用情况 |
|---|---|---|
| `t1.R 阴影阈值` | t1.R | 你有独立 toon/shadow mask |
| `t1.G 光滑度` | t1.G | 你有 smoothness/roughness 图 |
| `t1.B 金属度` | t1.B | 你有 metallic 图 |
| `t1.A AO` | t1.A | 你明确知道 AO/间接光门控的位置 |

只填部分通道时，插件会先按材质类型生成完整 t1，再覆盖有内容的通道。四个通道都填时，插件把它们视为完整 PackedMask。通道图必须与对应组件 t0 使用同一尺寸、同一 UV 方向。

## 6. 不需要作者准备的槽位

通常不需要准备以下图像：

- `t2`：全局环境立方图，由游戏场景提供；
- `t3`：动态阴影深度图，由游戏实时生成；
- `t5`：Ramp，由目标 shader/材质提供；
- `t6`：发丝高光图，当前主流程不替换；
- `t7`：RampAdd，通常由目标材质提供。

## 7. 导出前最小检查表

- Body：至少有 `body t0`；若不想使用旧材质，启用中性 t1/t4 或生成 t1/t4；
- Hair：至少有 `hair t0`；需要眉眼透出时确认 t0.A 和 coverage 选项；
- HairProp：只有替换发饰才填写 `hairprop t0/t1/t4`；
- 同一组件的三张图尺寸、UV、上下方向一致；
- t1 是线性数据，不能套 sRGB；t0/t4 是颜色数据；
- 不要把 t4 当动态阴影图，也不要把 t0.A 当普通透明度；
- 每次「按材质生成 t1/t4 并校准肤色」后确认激活的是正确组件网格；
- 路径指向作者自己的 PNG/DDS，而不是 `FrameAnalysis` 中的原始槽位文件。
