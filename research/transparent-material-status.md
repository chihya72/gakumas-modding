# 透明材质：当前状态与结论（截至 0.6.0）

> 本文是结论性总览，整合自两份已归档的过程记录：
> [`archive/transparent-pass-status-and-planB-20260628.md`](archive/transparent-pass-status-and-planB-20260628.md)（逐步踩坑全程）
> 与 [`archive/alpha-transparency-frameanalysis-20260628.md`](archive/alpha-transparency-frameanalysis-20260628.md)（抓帧证据）。
> 需要完整实验链路时查归档；日常以本文为准。

## 1. 插件当前策略（默认导出行为）

Blender 插件**不默认实现完整前向半透明**。透明材质（材质属性 `渲染材质 = 透明`，
对应 `gmi_alpha_mode = ALPHA_BLEND`）默认走一条保守路径，目标按优先级是：

1. **A=0 镂空干净** —— 全透明像素正确不显示，且不产生 AO 暗带；
2. **投影 / 深度遮挡 / 贴体观感正常** —— 保留反向 Z 遮挡；
3. **半透明有限支持** —— 半透明像素能显示，但**可靠范围**仅限「背后已有同模型/同
   角色其它几何或 G-buffer coverage」的区域（贴在手臂、腿、衣服上的薄纱、手环、花纹）。
   伸出角色原有轮廓外、背后是纯背景的半透明，仍可能被延迟合成 pass 丢弃。

换句话说：当前插件保证「透明底图看不见、贴体投影/遮挡正常」；真正伸出轮廓外的
玻璃/薄纱**暂不保证**。

## 2. 为什么不做完整前向透明（架构结论）

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

## 3. 抓帧证据（关键事实）

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

## 4. 当前导出的 mod.ini 结构

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

## 5. 后续（要做真正的前向半透明时）

1. 在抓帧里定位**角色专属**的前向透明 draw（单 RT、绑场景深度图做合成），拿到可
   唯一识别它的窄触发点（资源 hash / draw 上下文，而非全局 PS hash）。
2. 把已蒙皮的 VB/IB 在该阶段复用（蒙皮 compute 可能要提前或把结果存成持久 Resource）。
3. 单 RT、采样场景深度做软遮挡的透明 shader：`o0 = 预乘颜色`，先 clip 全透明，再按
   场景深度衰减/丢弃；保留 toon 压暗 + 高光封顶（防 bloom）。

## 6. 调试备忘

- 改 shader 必须换新文件名或重启游戏（F10 不重编同名 .hlsl，`cache_shaders=0` 也救不了）。
- 诊断「自定义 PS 是否在跑」：输出 `clip(-1)`，目标干净消失 = 在跑。
- `ShaderCache\<hash>-ps_replace.txt` / `-vs_replace.txt` 有反编译 HLSL；抓帧 `.dsc` 看每
  个 draw 绑的资源格式 / render_target / depth_stencil。
- 段索引核对：面数 × 3 = 索引数。
