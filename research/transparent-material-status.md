# 透明材质：当前状态与结论（截至 2026-06-30）

> **2026-06-30 路线收敛（branch `native-co-only`）**：自建的 **镂空 `ALPHA_CLIP`** 与
> **半透明 `ALPHA_BLEND`** 两条路径已从插件**整体移除**。`渲染材质` 现在只剩
> **不透明 `OPAQUE`** 与 **原生co `NATIVE_CO`** 两档。下文 §2、§3 描述的自建 pass 仅作
> 历史记录保留；当前唯一的透明实现是 §0–§1 的「借用游戏原生第二材质段 m_bdyco」。
> 被删两条路径的完整作用/效果/参数(`gmi_alpha_cutoff`、`shadercache_dir`)/弃用理由见
> [`archive/selfbuilt-cutout-and-blend-removed-20260630.md`](archive/selfbuilt-cutout-and-blend-removed-20260630.md)。
>
> 本文是结论性总览，整合自两份已归档的过程记录：
> [`archive/transparent-pass-status-and-planB-20260628.md`](archive/transparent-pass-status-and-planB-20260628.md)（逐步踩坑全程）
> 与 [`archive/alpha-transparency-frameanalysis-20260628.md`](archive/alpha-transparency-frameanalysis-20260628.md)（抓帧证据）。
> 需要完整实验链路时查归档；日常以本文为准。

## −1. 抓帧复核：m_bdyco 确是同一 body mesh 的第二材质段（2026-06-30 实测确认）

对 `FrameAnalysis-2026-06-30-045108` + `mdl_chr_fktn-cstm-0001_body` 逐 draw 核对，确认
第二材质段与主 body **共用同一套缓冲**、只是 submesh 范围不同（不是独立 buffer 的尾部配件）：

| 资源 | 000003（第二段） | 000006（主 body） |
|---|---|---|
| IB | `625a05af` | `625a05af` |
| VB0 | `deccfd71` | `deccfd71` |
| VB1 | `daa6a018` | `daa6a018` |
| 范围 | first=69534, count=4932 | first=0, count=69534 |

且 body（IB `625a05af`）在一帧里被 **5 个 VS pass** 绘制，第二段出现在其中 4 个：
`436f9c16`/`221c5733`（阴影/镜像）、`5b7fff8e`（深度预通道 000187 + G-buffer 000192）、
`fe50b7a8`（000232，PS `7a9af11e` 即原生镂空 PS）。因此 NativeCo override 必须对这 5 个 VS
**全部** `checktextureoverride = ib` 才能在每个 pass 都替换——生成的 `mod.ini` 已确认做到。
若某 pass 的 VS 未登记，该 pass 仍画原始第二段几何（换鞋形后投影/阴影会对不上，是后续需单独
对深度 RT 复核的疑点）。

## 0. m_bdyco 结论：游戏用第二材质段实现透明/镂空

这次 `fktn-cstm-001` 的关键发现是：游戏不是把主 `m_bdy` 材质改成透明，而是在同一个
`Geo_Body` / 同一组运行时 body IB/VB 里创建第二个材质 `m_bdyco`，对应一个独立 submesh
index range。

资产侧证据：

- `C:/Users/10725/Desktop/fktn-cstm-001/Material/m_bdyco.json` 使用 `t_chr_fktn-cstm-0001_bdyco_col_alp`、
  `t_chr_fktn-cstm-0001_bdyco_def`、`t_chr_fktn-cstm-0001_bdyco_sdw`。
- `m_bdyco` 的 `_ShaderType = 1`、`_Cull = 0`；但 `_Surface = 0`、`_ZWrite = 1`、
  `_SrcBlend = 1`、`_DstBlend = 0`，所以它不是 Unity 常规 alpha-blend 材质，而是
  opaque/depth-write 状态下由 shader 分支读取 alpha/mask。
- `C:/Users/10725/Desktop/assetstudio-body-json/mdl_chr_fktn-cstm-0001_body/Geo_Body.json`
  有两个 submesh：主 body `indexCount = 69534`，第二段 `firstByte = 139068`，
  即 `firstIndex = 69534`、`indexCount = 4932`。

抓帧侧证据：

- `D:/Games/gakumas/FrameAnalysis-2026-06-30-045108/000191-...txt` 是主 body：
  `first index = 0`、`index count = 69534`，PS `cf02c2d50d3f2230`。
- `000187-ib=625a05af-vs=5b7fff8ecccaf579-ps=e2fac5a6f1522625.txt` 是 `m_bdyco`
  同一 body 的第二段：`first index = 69534`、`index count = 4932`。
- `000187` 绑定 co 贴图：`ps-t0=5f7bd922`、`ps-t1=62b78053`、`ps-t2=9efcbcc8`；
  主体 `000191` 则绑定 `ps-t0=b5ce47cb`、`ps-t1=c4bd1058`、`ps-t2=da09fd9a`。
- 重新提取后的 `materialSections` 显示第二段 draws 为 `[3, 18, 187, 192, 232]`；
  其中 `000192` 紧跟主 body `000191` 之后，仍绑定 co 贴图，是比 pre-main `000187`
  更适合复用主 draw 已计算 VB 的 hook 点。
- `000232` 也是同一第二段的后续材质/辅助 pass：`firstIndex = 69534`、
  `indexCount = 4932`，PS `7a9af11e8bc01174`。

结论：`m_bdyco` 是“同 body mesh 的第二材质 section + 独立 PS/贴图集”，透明/镂空效果来自
`_ShaderType = 1` 的 shader 路径和 `col_alp`，不是主 body PS 读取 baseColor alpha，也不是
我们之前自建的延迟 alpha-blend pass。

## 1. 对 Blender 插件 + 3Dmigoto 的实现路线

近期方向改为复刻原生第二材质段，暂时放弃 `experiments/pc-il2cpp-proxy` 路线。

已落地：

- FrameAnalysis profile 提取现在会记录同一 IB/VB/顶点数下的全部材质段，写入
  `profile.json -> components[].materialSections` 和
  `drawcall_map.json -> components.body.sectionBindings`。这样 `000187/000232` 这种
  `m_bdyco` 段不会再只作为 `tailFirstIndices` 被发现却无法使用。
- Blender 材质 `渲染材质` 新增 `原生co(NATIVE_CO)`。这类材质段不会走自建
  `ALPHA_CLIP` / `ALPHA_BLEND`，而是被移到 secondary material section 的
  `TextureOverride` 中绘制。
- 生成器会把 co section 的 VS 也加入 `checktextureoverride = ib`，并且在 co draw 自己
  `copy vb0 -> RecoverMatrices -> SkinCustom`，因此 pre-main 和 post-main co draw 都有当前帧
  VB 可用，不依赖主 draw 先后顺序。
- 对 fktn 真实 profile 的离线生成结果为：
  `TextureOverride...BodyNativeCo` 使用 `hash = 625a05af`、`match_first_index = 69534`，
  `ps-t0/ps-t1/ps-t2` 分别绑定 base/packed/shade，source draws 为 `[3, 18, 187, 192, 232]`。

当前实现路线：

1. **Profile 层**：把第二材质段视作 body 的 native material section，而不是尾部配件。
   每段保存 `firstIndex`、`indexCount`、representative draw、PS 列表和自己的贴图槽。
2. **Blender 导出层**：用材质槽选择 `原生co`。导出时继续按 Blender 材质聚合面段，
   但把该材质段从主 body draw 中移出，交给 secondary section 绘制；没有原生 co section
   的 profile 会报错，需改用 `ALPHA_CLIP` / `ALPHA_BLEND` fallback。
3. **3Dmigoto 层**：hook 原游戏的 co section draw，例如 fktn 的
   `ib=625a05af + match_first_index=69534`。主 body draw 负责或参与生成已蒙皮自定义 VB/IB，
   co draw 也能自行生成当前帧 VB，并在原生 co PS/state/贴图绑定上下文里绘制自定义第二段。
4. **时序注意**：fktn 抓帧里 co draw 既有主 body 前的 `000187`，也有主 body 后的
   `000192/000232`。如果只在主 draw 完成 compute，优先使用主 draw 后的 section pass；
   若目标服装只有主 draw 前的 co pass，则需要在 co pass 自己也能触发 compute 或改为提前
   准备持久资源。当前原型选择“co pass 自己也触发 compute”，离线结构上更稳，性能需实机观察。

这个路线的优势是避开之前延迟透明的 coverage 冲突：我们借用游戏已经为 `m_bdyco` 准备好的
角色专属 shader/state/draw 上下文，而不是在主 body G-buffer 里硬造半透明。

## 2. 镂空 vs 半透明（⚠️ 已于 2026-06-30 移除，仅存档）

「透明材质不压在身体上就消失」过去是因为插件把**所有**透明材质都塞进半透明(alpha-blend)
延迟路径，而该路径 `depth_write_mask=zero`、靠延迟合成的角色 coverage 才显示 → 伸到背景上
就被丢。**但绝大多数「透明」件其实是镂空(二值 alpha)，根本不需要混合。**

因此 `渲染材质` 拆成 **镂空(`ALPHA_CLIP`)** 与 **半透明(`ALPHA_BLEND`)** 两档：

- **镂空**：当不透明件画。PS `clip(a - cutoff)` 丢掉洞，其余像素 `depth_write_mask=all`
  正常写深度+coverage（MRT：o0=运动0/深度/ID256，o1=不透明色）。→ **背景上可见、遮挡正确、
  A=0 干净、无 AO 暗带**，绕开了下面那个架构冲突（冲突只对真混合成立）。着色器
  `GMIClipMRT.hlsl`，每段烘焙各自 cutoff 为 `GMIClip{n}.hlsl`。
- **半透明**：仍走下述保守的 InheritMask+AlphaBlend 路径，限制不变。

实现：[`../gakumas_mi/core.py`](../gakumas_mi/core.py) 发射按 `mode` 分流；回归见
`tests/mod_ini_contract.py::test_cutout_ini_contract`。

## 3. 半透明的保守策略（⚠️ 已于 2026-06-30 移除，仅存档）

Blender 插件**不默认实现完整前向半透明**。半透明材质（材质属性 `渲染材质 = 半透明`，
对应 `gmi_alpha_mode = ALPHA_BLEND`）默认走一条保守路径，目标按优先级是：

1. **A=0 镂空干净** —— 全透明像素正确不显示，且不产生 AO 暗带；
2. **投影 / 深度遮挡 / 贴体观感正常** —— 保留反向 Z 遮挡；
3. **半透明有限支持** —— 半透明像素能显示，但**可靠范围**仅限「背后已有同模型/同
   角色其它几何或 G-buffer coverage」的区域（贴在手臂、腿、衣服上的薄纱、手环、花纹）。
   伸出角色原有轮廓外、背后是纯背景的半透明，仍可能被延迟合成 pass 丢弃。

换句话说：当前插件保证「透明底图看不见、贴体投影/遮挡正常」；真正伸出轮廓外的
玻璃/薄纱**暂不保证**。

## 4. 为什么不做完整前向透明（架构结论）

- 游戏是**延迟渲染 + 反向 Z**（near=1, far=0）。body 的 G-buffer 通道（即我们 hook 的
  draw）对照深度预通道做遮挡，自身不建立可遮挡新几何的深度。把透明件当新几何塞进
  G-buffer 通道，深度预通道里没有它 → 永远穿透，`depth_func` / `depth_bias` 都改不掉。
- 延迟合成 pass 用「早期/原 body pass 继承的 stencil/coverage」判定「哪里是角色」。
  自定义透明 pass 想让「写资格的区域」精确等于「A>0 区域」时，`clip`、提高 alpha
  阈值、`SV_Coverage`、CoverageMask **全部实测无效** —— 资格写入发生在 PS discard
  能约束之前，或不受其控制。
- **完整背景半透明** 与 **A=0 干净** 在 G-buffer/延迟路径里存在架构冲突，二选一。
  插件默认选更稳的 A=0 + 投影 + 遮挡。
- 真正的前向透明阶段（原版渔网/薄纱所在）是**全局复用** shader；用 `[ShaderOverride]`
  按 PS hash hook 太泛，实测会污染整帧 UI/场景透明 draw。必须等找到**角色专属的窄
  触发点**后才能安全启用 —— 这是后续工作，不是当前默认。

## 5. 旧路线抓帧证据（关键事实）

- **主 body 不读 baseColor 的 alpha**：主身体 PS 对 `t0` 只采样 RGB，输出 `o0.w = 1`。
  即使 t0 是 RGBA DDS，A 通道也不会让模型透明 —— 透明必须走单独 pass。
- **原版硬镂空用 discard**：透明/遮罩 PS 读 mask 后 `discard_nz`，真正丢像素，而非输出
  alpha=0。
- **原版半透明用预乘 alpha**：透明 shader 输出 `o0.xyz = rgb * a; o0.w = a`，配
  `blend = ADD ONE INV_SRC_ALPHA`。自定义透明 pass 不能简单用 `rgba` + `SRC_ALPHA/
  INV_SRC_ALPHA`。
- **body 是 MRT**：`o0 = 运动矢量.xy + 深度.z + 材质ID.w`，`o1 = 颜色(HDR)`。颜色必须
  写 `o1`；写错到 `o0` 会被当运动矢量 → 触发动态模糊拖影。
- DDS 格式不是核心：主 baseColor 多为 `BC7_UNORM_SRGB`，但 3Dmigoto 也能加载
  `R8G8B8A8_UNORM_SRGB`。关键是当前 pass 的 shader 是否读 alpha、blend 是否匹配预乘 alpha。

## 6. 当前 fallback 导出的 mod.ini 结构

主 body draw 只画不透明材质段；透明段拆出，先 `InheritMask` 后 `AlphaBlend`：

```ini
drawindexed = ... opaque material ranges ...
run = CustomShader...InheritMaskN
Resource...SceneDepth = copy oD
run = CustomShader...AlphaBlendN
handling = skip
```

`InheritMaskN`（只测深度、不写深度，保留遮挡又不让 A=0 padding 写深度造成 AO 暗带）：

```ini
depth_enable = true
depth_write_mask = zero
depth_func = greater_equal
blend[0] = ADD ZERO ONE
blend[1] = ADD ZERO ONE
```

`AlphaBlendN`（MRT 版 `GMIFinal.hlsl`，RT1 预乘 alpha 混合）：

```ini
vs/ps = Shaders\GMIFinal.hlsl
blend[0] = disable
blend[1] = ADD ONE INV_SRC_ALPHA
alpha[1] = ADD ONE INV_SRC_ALPHA
depth_enable = true
depth_write_mask = zero
depth_func = greater_equal
```

自定义 G-buffer 绘制统一用 `cull = none`（绕序无法干净分正反面）+ `depth_func =
greater_equal`（反向 Z）。

## 7. 后续（要做真正的前向半透明时）

1. 在抓帧里定位**角色专属**的前向透明 draw（单 RT、绑场景深度图做合成），拿到可
   唯一识别它的窄触发点（资源 hash / draw 上下文，而非全局 PS hash）。
2. 把已蒙皮的 VB/IB 在该阶段复用（蒙皮 compute 可能要提前或把结果存成持久 Resource）。
3. 单 RT、采样场景深度做软遮挡的透明 shader：`o0 = 预乘颜色`，先 clip 全透明，再按
   场景深度衰减/丢弃；保留 toon 压暗 + 高光封顶（防 bloom）。

## 8. 调试备忘

- 改 shader 必须换新文件名或重启游戏（F10 不重编同名 .hlsl，`cache_shaders=0` 也救不了）。
- 诊断「自定义 PS 是否在跑」：输出 `clip(-1)`，目标干净消失 = 在跑。
- `ShaderCache\<hash>-ps_replace.txt` / `-vs_replace.txt` 有反编译 HLSL；抓帧 `.dsc` 看每
  个 draw 绑的资源格式 / render_target / depth_stencil。
- 段索引核对：面数 × 3 = 索引数。
