# 透明材质渲染：当前状态与 Plan B（前向透明通道）— 2026-06-28

实战对象：`D:\Games\gakumas\Mods\fuyuko`（GakumasMI「导出贴图模组」/inverse-skin GPU 模组，3Dmigoto）。
目标：让换装里的透明/镂空材质（`m_wingopacity` / `m_wingopacity_BS_b` —— 含臂环花朵、紫色手环、薄纱裙等）在游戏里正确显示（真透明 + 正确遮挡）。

---

## 0. 当前插件策略与限制（2026-06-28 收束）

Blender 插件当前默认导出的透明路径不再承诺「完整前向半透明」。默认目标改为：

1. **全力保证投影/深度遮挡/轮廓效果与 A=0 镂空干净**。透明材质段从主 body draw 拆出，先跑 `InheritMask`，但只做深度测试、不写深度：`depth_enable=true`、`depth_func=greater_equal`、`depth_write_mask=zero`。这样保留反向 Z 遮挡与贴体观感，同时避免 A=0 padding 被写入深度后制造 AO 暗带。
2. **半透明只做有限支持**。半透明像素可以显示，但可靠范围是「背后已经有同模型/同角色其它贴图或 G-buffer coverage」的区域，例如贴在手臂、腿、衣服上的薄纱、手环、花纹。伸出角色原有轮廓外、背后是纯背景的半透明区域，仍可能被延迟合成 pass 丢弃。
3. **插件暂不默认启用前向透明 hook**。全局前向 shader hook 已实测会污染 UI/场景透明 draw，窄触发点尚未稳定。为了避免整帧错乱，当前插件优先交付可控的投影/遮挡/A=0 效果。

换句话说：当前插件能保证「透明底图看不见、贴体投影/遮挡尽量正常」；半透明效果只能在同模型已有覆盖的像素上可靠实现，不能保证真正伸出角色轮廓外的玻璃/薄纱。

---

## 1. 已确诊的根因链（按踩坑顺序，全部验证过）

GakumasMI 把整网格挂在 body 的 IB hash（`a01380f3`）上、在 body 的**不透明 draw** 里一次性画完，透明材质段也在其中。由此一连串问题：

1. **透明件渲染成实心方块/银面**：继承不透明 blend，alpha 被忽略。3Dmigoto 换贴图改不了 blend。
2. **「改 shader 没反应」最大伪装**：body 主色 PS `f872756c910a6eb7` 是 **MRT**：
   - `o0 (SV_Target0)` = 运动矢量 `.xy` + 深度 `.z` + 材质 ID `.w`
   - `o1 (SV_Target1)` = 颜色（HDR）
   我们的自定义透明 PS 只写 `o0` → **颜色写进了运动矢量目标 → 触发动态模糊 → 一坨糊白拖影，且改颜色/blend/深度全无效**。判据：只有 `clip(-1)` 丢弃能让目标干净消失。
3. **F10 不重编译同名 .hlsl**：必须换新文件名或彻底重启游戏（`cache_shaders=0` 也救不了）。调试一律用新文件名。
4. **白件 bloom 冲淡**：白纱 opacity 贴图 RGB≈(238,239,246)，平涂输出过亮（材质 `_BloomThreshold≈0.01` 极易触发）→ HDR bloom 糊成发光白团。
5. **透视/see-through**：`o0.z`（深度）、`o0.w`（ID）写 0 → 合成 pass 把这些像素当背景。
6. **多层薄纱/背面穿透**：见第 3 节，深度遮挡根本失效（Plan B 的核心动机）。

VS 顶点变换实测与原版 body VS 一致（不是位置 bug）：
```
world.xyz = cb1[0].xyz*pos.x + cb1[1].xyz*pos.y + cb1[2].xyz*pos.z + cb1[3].xyz;
SV_Position = cb0[77]*world.x + cb0[78]*world.y + cb0[79]*world.z + cb0[80];
```

---

## 2. 当前可用配置（Plan A：单层配件 OK，复杂裙穿帮）

文件：`D:\Games\gakumas\Mods\fuyuko\mod.ini` + `Shaders\GMIMrt6.hlsl`。

两个透明段从主 drawindexed 移除，改 `run = CustomShaderFuyukoAlphaBlend0/1`。每段 CustomShader：
```ini
vs = Shaders\GMIMrt6.hlsl
ps = Shaders\GMIMrt6.hlsl
topology = triangle_list
cull = back
blend[0] = disable                  ; RT0(运动/深度/ID)精确写
blend[1] = ADD ONE INV_SRC_ALPHA    ; RT1(颜色)预乘 alpha 混合
alpha[1] = ADD ONE INV_SRC_ALPHA
depth_enable = true
depth_write_mask = all
depth_func = less_equal
vb0 = ResourceFuyukoSkinnedVBIA
vb1 = ResourceFuyukoVB1
vb3 = ResourceFuyukoSkinnedVBIA
ib  = ResourceFuyukoIB
ps-t0 = ResourceFuyukoOpacityBaseColor   ; 带真 alpha 的颜色图
ps-t1 = ResourceFuyukoPackedmask
ps-t4 = ResourceFuyukoShadecolor
drawindexed = 8028, 84762, 0        ; 段0 m_wingopacity(2676面)
; 段1: drawindexed = 210, 92790, 0  m_wingopacity_BS_b(70面)
```

GMIMrt6.hlsl 关键逻辑（PS）：
```hlsl
float4 base = t0.Sample(uv);
clip(base.a - 0.02);                              // 只丢全透明像素
float4 pm = t1.Sample(uv);  float4 sc = t4.Sample(uv);
float3 col = base.rgb;
col = lerp(col, col*sc.rgb, sc.a);                // 阴影色
col *= lerp(1.0, 1.0-pm.a, 0.4);                  // AO 压暗
col *= 0.90;                                       // 整体压暗
float m = max(col.r,max(col.g,col.b));
if (m > 0.70) col *= 0.70/m;                       // 高光封顶，防 bloom
o0 = float4(0, 0, 16376.0*sqrt(saturate(i.pos.z)), 256.0); // 运动0+深度+ID
o1 = float4(col*base.a, base.a);                   // 预乘颜色
```
VS 里可选深度偏移 `pos.z += BIAS*pos.w`（实测正负都救不了穿透，已设 0）。

**效果**：臂环花朵、紫色手环（孤立单层、贴体表）显示正确（真彩色、半透明、镂空、无拖影）。**复杂多层薄纱裙穿帮**：见下。

---

## 3. 为什么深度遮挡失效（Plan B 的根本动机）

Gakumas 是**延迟渲染**：
1. 先有**深度预通道**写不透明几何的深度；
2. body 的 **G-buffer 通道**（=我们 hook 的 MRT draw）对照预通道深度，**自身不建立可遮挡新几何的深度**；
3. 合成。

我们把 wing 当**新几何**塞进 G-buffer 通道，**深度预通道里没有 wing** → wing 无论推到多前/多后都测不到正确遮挡 → **永远穿透**（臂环贴手臂背面也可见、元素沉到裙后仍可见）。`depth_func`、`depth_bias` 都改不了，因为要比对的深度缓冲里压根没它该被谁挡的信息。**结论：不是参数问题，是画错了渲染阶段。**

---

## 4. Plan B：改到前向透明通道（与原版一致）

原版透明件（渔网/薄纱）在**合成之后的前向透明通道**里画：单 RT、`o0=颜色`、**采样整张场景深度图做遮挡**。

关键证据（研究文档 `alpha-transparency-frameanalysis-20260628.md` + ShaderCache）：
- 透明 PS（如 `0186d4c1702ef7a0` / `b9ff5b23549943cd` / `f15da1dcea6644dc`）**只输出 o0（单 RT）**，做 `discard` 或预乘 alpha。
- 合成/透明 draw（`000335+`）绑定屏幕颜色 + 深度：`ps-t1=R8G8B8A8 render_target`、`ps-t4=R32G8X24 depth_stencil`，参考已渲染颜色/深度合成。
- 原版透明用**预乘 alpha** + `blend = ADD ONE INV_SRC_ALPHA`。

**Plan B 待办**：
1. 在抓帧 `D:\Games\gakumas\FrameAnalysis-2026-06-28-082021` 里定位**前向透明通道**的代表 draw（单 RT、绑场景深度图、做 alpha 合成的角色透明 draw），拿到它的 VS/PS hash、输入布局、绑定的深度图资源。
2. 确认能否在该阶段 hook：用 `[ShaderOverride...]` 或一个晚于合成的 `[TextureOverride...]` 触发点，把 wing 的 `drawindexed`（复用已蒙皮的 `ResourceFuyukoSkinnedVBIA`/IB）插进去。
3. 写一版**单 RT、采样场景深度做软遮挡**的透明 shader：`o0 = 预乘颜色`，先 `clip` 全透明，再 `深度 = SampleSceneDepth(screenUV)`，`if (pixelDepth > sceneDepth) discard;`（或 alpha 衰减）；保留 toon 压暗 + 高光封顶。
4. blend：`ADD ONE INV_SRC_ALPHA`，`cull=back`，深度对照场景深度图而非 DSV。

**风险/未知**：
- 蒙皮 VB（`ResourceFuyukoSkinnedVBIA`）由我们的 compute 在 body draw 时算出；前向透明阶段它是否还在/可复用？可能要把蒙皮 compute 也提到透明阶段前，或把蒙皮结果存成持久 Resource。
- 前向透明 draw 的 cb0/cb1（投影/世界矩阵）在该阶段是否仍是角色的？需核对。
- 多层自重叠仍是 OIT：场景深度遮挡能解决「被不透明件挡」，但同为透明的多层之间仍无排序（可接受，原版也靠画序）。

---

## 5. 调试工具备忘
- 改 shader 必须换新文件名或重启（F10 不重编同名）。
- 诊断「我们的 ps 是否在跑」：ps 输出 `clip(-1)`，目标干净消失=在跑。
- `D:\Games\gakumas\ShaderCache\<hash>-ps_replace.txt` / `-vs_replace.txt` 有反编译 HLSL。
- 抓帧 `.dsc` 看每个 draw 绑的资源（贴图格式、render_target、depth_stencil）。
- 段索引核对：面数×3=索引数（m_wingopacity 2676→8028，BS_b 70→210）。

备份：`mod.ini.bak`（最初手补）/`mod.ini.blend_bak`（0.5.50 原导出）。

---

## 6. 突破：反向 Z + 深度遮挡（2026-06-28 续，Plan B 实测结论）

`copy oD` 拷出的深度**有效**（GMIDepthDbg3 可视化：wing 像素 sceneZ 为中间值，非清空），所以 **DSV/oD 里本来就有真实的不透明身体深度**，根本不需要手动采样 —— 之前「深度怎么调都没用」是**深度比较方向错了**。

**关键诊断（决定性）**：用 `cull=back + greater_equal` 时「看到的是背面、正面被剔除」；用 `cull=none + less_equal` 时「正面花环不显示、只有当背后有身体挡住时整圈才显示（其实显示的是背面）」。两者都指向：**游戏是反向 Z（near=1, far=0），且这个网格绕序导致 cull 不能干净分正反面**。

**正解组合（不透明件 100% 正常）**：
```ini
cull = none                 ; 不靠 cull 分面
depth_func = greater_equal  ; 反向 Z：近(z大)的画，远(z小)的被挡
depth_write_mask = zero     ; （见下，半透明问题与此有关）
blend[0] = disable
blend[1] = ADD ONE INV_SRC_ALPHA
alpha[1] = ADD ONE INV_SRC_ALPHA
```
PS=GMIFinal.hlsl（toon 压暗 + 高光封顶 + clip 全透明 + MRT：o0=运动0/深度/ID256，o1=预乘颜色）。
- 不透明件（臂环花朵）：完全正常显示。
- A=0 全透明（环带洞、花朵间隙）：正确不显示。
- 身后绕到背面的件：被身体深度正确挡掉，不穿透。

`copy oD` + `ps-t5` 手动深度那套**已不需要**（DSV 测试足够），可清理。

## 7. 仅剩问题：半透明件「只在遮挡身体时可见，背景上不可见」

现象：半透明素材（紫色手环、薄纱）当它**前方挡着身体**时显示；当它**前方是背景/手臂边缘外**时不显示。不透明件没这问题。

**根因分析（待验证）**：延迟渲染的**合成 pass 用 DSV 深度判定「哪里是角色」**，只把角色像素的 G-buffer 颜色合成到场景上。我们设了 `depth_write_mask=zero` → **半透明 wing 不写 DSV 深度** → 在「身后没有其它角色几何」的地方（伸出身体轮廓外、纯背景），合成 pass 认为「这里没有角色」→ 丢弃 wing 的 o1 颜色 → 不显示。而当 wing 前方/同位置有身体（身体写了 DSV 深度），合成认得是角色 → wing 的混合色随之显示。不透明件多数贴在手臂（手臂已写 DSV）所以正常。

**候选解法**：
1. **`depth_write_mask = all`**：让 wing 写 DSV 深度 → 合成 pass 认得这些像素是角色 → 半透明在背景上也显示。风险：半透明写满深度会全遮挡其后（多层半透明只显最前层）；但配 `greater_equal` 应能正确挡背面、自身多层取最前。**最可能的解，优先试。**
2. 若 1 导致多层半透明丢层：半透明可改 `depth_write=all` 但只对 A≥某阈值写深度（shader 里 `clip` 控制），或接受只显最前层。
3. 若合成 pass 不是靠 DSV 而是靠 o0.w(ID) 判定角色：那 o0.w=256 可能不被认作有效角色 ID，需 dump 身体像素真实 o0.w 值填对。

下一步：先试解法 1（`depth_write_mask=all`），观察半透明是否在背景上显示、是否引入新穿帮。

---

## 8. 新假设：coverage 可能是 RT1 alpha，而不是 stencil（2026-06-28 续）

`depth_write_mask=all` 未解决「身体轮廓外不显示」，因此 DSV 深度资格基本降级。一个更贴合现象的解释是：合成 pass 使用 MRT 颜色目标 `o1.a` 作为角色 coverage/有效像素标记。

当前透明颜色 pass 使用预乘 alpha：

```hlsl
o1 = float4(col * base.a, base.a);
```

并且 RT1 blend 是：

```ini
blend[1] = ADD ONE INV_SRC_ALPHA
alpha[1] = ADD ONE INV_SRC_ALPHA
```

于是：

- 有身体在后方时，RT1 目标原本 `dst.a=1`，混合后仍为 `1`，合成认作角色像素；
- 纯背景处，RT1 目标原本 `dst.a=0`，混合后为 `base.a`，半透明像素可能不满足 coverage 条件，被合成丢弃；
- 这能解释「贴身体显示，伸出身体轮廓不显示」，且不依赖 DSV。

已在 `D:\Games\gakumas\Mods\fuyuko` 做实验版：

1. 新增 `Shaders\GMICoverageMaskA.hlsl`。
2. 每个透明 range 先跑 coverage-only pass，再跑原 `GMIFinal.hlsl` 颜色 pass。
3. coverage-only pass：
   - `clip(alpha - 0.02)`；
   - RT0/RT1 RGB 用 `blend = ADD ZERO ONE` 保持不变；
   - RT1 alpha 用 `alpha[1] = ADD ONE ZERO` 写成 1；
   - 原颜色 pass 仍输出 `o1=float4(col*base.a, base.a)`，所以 RGB 透明混合不被 `o1.a=1` 破坏。

备份：`D:\Games\gakumas\Mods\fuyuko\mod.ini.coverage_test_bak`。

待进游戏验证：如果身体轮廓外出现，说明 coverage 是 RT1 alpha；若仍不出现，再回到 stencil/前向透明方案。

### 实测反馈

coverage-only pass 后，身体轮廓外仍不出现；但裙底颜色从红色恢复为白色。这说明：

- 新 pass 确实执行；
- RT1 alpha/coverage 影响最终颜色或材质合成；
- 但它不是「轮廓外是否被丢弃」的唯一门槛，stencil/更早的角色 mask 仍然可疑。

追加实验：新增 `Shaders\GMIInheritMaskA.hlsl` 和 `CustomShaderFuyukoInheritMask0/1`，放在透明颜色 pass 之前、`copy oD` 之前执行。该 pass：

- `clip(alpha - 0.02)`；
- RGB/alpha blend 全部保持目标不变；
- **不声明** `depth_enable` / `depth_func` / `depth_write_mask`，避免 3Dmigoto 生成新的 depth-stencil state，尽量继承原 body pass 的 stencil 状态。

若这版轮廓外出现，说明之前自定义透明 pass 因显式 depth state 丢掉了原 stencil 写入；若仍不出现，则需要真正把 wing 画到原生前向透明阶段，或找到 3Dmigoto 可控的 stencil write/ref 语法。

### 实测反馈 2：InheritMask 打通轮廓，但 alpha 过宽

`GMIInheritMaskA` 后，透明件身体轮廓外全部出现，说明关键门槛就是早期/原 body pass 的继承状态（高度疑似 stencil/coverage）。但出现新问题：本应 alpha=0 的底图/padding 区域也出现阴影。

原因判断：

- `GMI_ALPHA_FLOOR=0.02` 约等于 5/255，阈值太低；
- `Body.Opacity.dds` 里存在少量低 alpha 脏值：`1-15` 约 2.3 万像素，`16-63` 约 5.8 千像素；
- mip/bilinear 也可能把邻近不透明区域的 alpha 糊进透明 padding；
- `CoverageMaskA` 对误通过像素写 `RT1.a=1`，会放大这些透明底图的合成/阴影副作用。

已切到 B 版：

- `GMIInheritMaskB.hlsl` / `GMICoverageMaskB.hlsl`：mask 阈值提高到 `0.25`，并用 `SampleLevel(..., 0)` 读 mip0 alpha 做 clip；
- `GMIFinalB.hlsl`：颜色 pass 仍保留 `0.02` 低阈值，但 clip 也改用 mip0 alpha，减少 mip bleed；
- `mod.ini` 已改为引用 B 版 shader 文件名，以确保 F10 重新编译。

待验证：透明件是否仍完整伸出轮廓外，同时 alpha=0 padding 阴影是否消失。若边缘被削太硬，可把 B 版 mask 阈值从 `0.25` 回调到 `0.12` 或 `0.08`。

### 实测反馈 3：不是阈值，clip 无法约束继承资格写入

B 版提高阈值后，透明底图仍存在；确认不是阈值问题，而是 `A=0` 区域也被显示。结论：`InheritMask` 继承到的 stencil/coverage 写入很可能发生在 PS `clip()` 能约束之前，或该资格写入不受 PS discard 控制。

追加 C 版实验：

- 新增 `GMIInheritMaskC.hlsl`；
- `InheritMask0/1` 改为引用 C 版；
- C 版不再依赖 `clip`，而是输出 `SV_Coverage`：

```hlsl
cov = (a > 0.0) ? 0xffffffff : 0;
```

目的：验证能否在 OM 阶段用 sample coverage 阻止 `A=0` 像素写 depth/stencil/coverage。若 C 版无效或编译失败，说明 3Dmigoto 自定义 pass 无法对这个继承 stencil 写入做 per-pixel alpha gate，后续应转向：

1. 透明件几何侧切 alpha（把 padding/透明面从 mesh/index range 中拆掉）；
2. 或正式改为前向透明阶段，绕过延迟合成的角色轮廓资格。

### 实测反馈 4：SV_Coverage 无效，切前向透明实验

`GMIInheritMaskC` 无任何变化，说明 `SV_Coverage` 也无法控制继承来的资格写入。结论：当前延迟路径无法同时满足「轮廓外出现」和「A=0 挖洞干净」。

已切到前向透明实验：

- 备份失败版本：`D:\Games\gakumas\Mods\fuyuko\mod.ini.inheritmask_failed_bak`；
- 主 body pass 不再 run `InheritMask` / `CoverageMask` / MRT `AlphaBlend`；
- 主 pass 只画不透明段，并保存：
  - `ResourceFuyukoSkinnedVBIA`
  - `ResourceFuyukoMainCB0 = copy vs-cb0`
  - `ResourceFuyukoMainCB1 = copy vs-cb1`
- 新增 `ShaderOverrideFuyukoForwardAlphaHook`，hook 原生前向透明 PS `b9ff5b23549943cd`；
- 新增 `CustomShaderFuyukoForwardAlpha0/1`，使用 `GMIForwardAlpha0.hlsl` 单 RT 输出预乘 alpha：

```hlsl
o0 = float4(col * base.a, base.a);
```

预期：绕开延迟合成的角色轮廓资格，A=0 区域由 forward shader 的 `clip` 正常丢弃。

风险：`vs-cb0/vs-cb1` 常量缓冲复制/绑定语法若不被当前 3Dmigoto 支持，wing 可能不显示或位置错误；若 `b9ff5b...` 当前画面不触发，则需要换 hook 点（例如 `0197209b8f429444` 或 `f15da1dcea6644dc`）。

### 实测反馈 5：全局前向 shader hook 会炸场景，已回滚

前向透明实验导致整场景/模型渲染状态错误。原因判断：`b9ff5b23549943cd` 是全局复用的原生前向透明 shader，用 `[ShaderOverride]` 按 PS hash 触发太泛，会在大量非角色透明 draw 上插入我们的自定义 draw/state，污染整帧。

已执行回滚：

```text
D:\Games\gakumas\Mods\fuyuko\mod.ini.inheritmask_failed_bak
  -> D:\Games\gakumas\Mods\fuyuko\mod.ini
```

当前生效状态回到：`InheritMask` 打通轮廓，但 `A=0` padding 仍错误参与。

后续结论：

1. 不能再用全局 shader hash hook 前向透明；
2. 若继续前向透明，必须找更窄的触发点，例如特定 `TextureOverride`/资源 hash/draw 上下文，并确保不影响原 draw；
3. 当前延迟继承 stencil 路线无法按 PS alpha 挖洞：`clip` 和 `SV_Coverage` 都无效；
4. 最可靠的修复方向是几何侧处理 alpha：拆分/重建透明件几何，让 `A=0` 区域没有可写 stencil 的三角形覆盖；或者找到 3Dmigoto 显式 stencil write/ref 且能受 alpha test 控制的语法。

---

## 9. 当前落地结论：插件优先保 A=0 与投影，半透明有限支持（2026-06-28 终）

经过完整隔离实验（逐个关 InheritMask / CoverageMask / AlphaBlend）得到的决定性结果：

| InheritMask 深度策略 | 半透明上背景 | A=0 暗带/阴影 | 当前插件采用 |
|---|---|---|---|
| 写深度（默认继承 body） | 显示 | 出现 | 否 |
| `depth_write_mask = zero` | 不稳定，只在已有角色 coverage 上显示 | 干净 | 是 |

取舍理由：

- 半透明能伸到背景上，靠的是 InheritMask 写深度让延迟合成 pass「认得这里是角色」。
- A=0 暗带来自装饰面写入了比手臂更近的深度，后续 AO/SSS 屏幕空间 pass 在透明 padding 缝隙处算出阴影。它不是贴图颜色，也不是阈值能修掉。
- `clip`、提高 alpha 阈值、`SV_Coverage`、CoverageMask 都无法让「写资格/深度的区域」精确等于「A>0 区域」。
- 因此在 G-buffer/延迟路径里，完整背景半透明与 A=0 干净存在架构冲突。插件默认选择更稳定的 A=0、投影和遮挡效果。

当前插件生成结构：

```ini
drawindexed = ... opaque material ranges ...
run = CustomShader...InheritMaskN
Resource...SceneDepth = copy oD
run = CustomShader...AlphaBlendN
handling = skip
```

`InheritMaskN`：

```ini
depth_enable = true
depth_write_mask = zero
depth_func = greater_equal
blend[0] = ADD ZERO ONE
blend[1] = ADD ZERO ONE
```

`AlphaBlendN`：

```ini
vs/ps = Shaders\GMIFinal.hlsl
blend[0] = disable
blend[1] = ADD ONE INV_SRC_ALPHA
alpha[1] = ADD ONE INV_SRC_ALPHA
depth_enable = true
depth_write_mask = zero
depth_func = greater_equal
```

仍然有效的技术备忘：

- 游戏是反向 Z（near=1, far=0）：自定义 G-buffer 绘制用 `cull=none` + `depth_func=greater_equal`。
- body 是 MRT：`o0=运动矢量.xy+深度.z+材质ID.w`，`o1=颜色`。颜色必须写 `o1`，写错会被当运动矢量导致拖影。
- 半透明目前只保证在同模型/同角色已有 coverage 的像素上可靠显示。伸出身体轮廓外的真实前向半透明，需要未来找到窄触发点的角色专属前向透明 draw 后再实现。
