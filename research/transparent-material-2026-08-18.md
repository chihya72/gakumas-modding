# 学马半透明材质：从零到 VL 原生通路（2026-08-18）

**这份文档管什么**：把「给学马加真半透明材质」这件事的全部实测结论、已建成的基础设施、
试过的每条路线和失败原因、以及当前卡点交代清楚。接手的人看完就能继续，不用重跑实验。

**一句话现状（2026-08-19 收尾）**：真 alpha 混合早就做出来了；
「压背景时糊」的根因也查到底了 —— **景深读的 RT0.z 由一趟全屏 resolve 从「深度预pass 结束时的
快照」重算，我们的部件写得比快照晚**（5.14）。修它只有两条路，代价都是结构性的：
要么把部件变成不透明件（遮住身体），要么抢走像素但供不上颜色（变白）。
**在 G-buffer 里解决它**是延迟渲染定义决定的二选一（5.15）。
但**绕开 G-buffer** 有两条已经验证到「机制成立」的路（5.17/5.18），
两条卡在同一个具体问题上（5.19：注入的 `DrawRenderer` 姿势不对），不是死路。
可用画面随时能回到兜底档（前向透明 queue 3000）。

---

## 0. 五分钟上手（新接手的人先看这节）

### 0.1 现在能用的是什么

**兜底档**：部件走前向透明队列 3000，真 alpha、不白、不抖、跟随动画、遮挡正确。
唯一缺点是压在背景上时被景深虚化（根因见 5.14，不是 bug 是延迟渲染的结构约束）。
把 `mod.json` 的 `transparentMaterials[]` 配成这样、把 `gakumas-mod/*.on` 开关文件全删掉，就是它：

```json
{ "rendererName": "Geo_Body", "materialSlot": 2,
  "asset": "…_t0.png", "defMap": "…_t1.png", "shadeMap": "…_t4.png",
  "alpha": 0.45, "cull": 0.0, "zwrite": 0.0, "renderQueue": 3000,
  "props": { "_ForwardEnable": 1.0,
             "_ActorTransparentEnable": 0.0, "_ZPrePassEnable": 0.0,
             "_DepthClaimEnable": 0.0, "_StencilWriteMask": 0.0,
             "_SelfBlendEnable": 0.0, "_SceneColorDebug": 0.0 } }
```

> `props` 是任意 shader 属性直通。**shader 的每个 pass 都被一个开关 clip 着**
> （见 0.4），配错就是「画了但什么都看不见」——踩过两次。

### 0.2 代码在哪

| 东西 | 路径 |
|---|---|
| shader | `gakumas-mod-runtime/packaging/shaders/GmiTransparent.shader` |
| shader 工程 | `.local/gmi-shaders-proj`（Unity **6000.0.77f1**，必须和游戏同版本） |
| runtime | `gakumas-mod-runtime/src/runtime/ModRuntime.cpp`（VL 相关全在文件末尾的探针区） |
| 本文档的离线量图脚本 | 见 7 节，直接拷 |

### 0.3 编译 + 部署（两条命令）

```bash
# runtime DLL（游戏在跑时会占用文件，先关游戏）
"C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe" gakumas-mod-runtime/build/gakumas_mod_runtime.sln /t:gakumas_mod_runtime /p:Configuration=Release /p:Platform=x64 /m /v:minimal && cp gakumas-mod-runtime/build/bin/x64/Release/xinput1_3.dll "D:/Games/gakumas/xinput1_3.dll"
```

```bash
# shader bundle（改了 .shader 才需要）
cp gakumas-mod-runtime/packaging/shaders/GmiTransparent.shader .local/gmi-shaders-proj/Assets/Gmi/ && cd .local/gmi-shaders-proj && "D:/GIT/gakumas-modding/.local/Unity6000.0.77f1/Editor/Unity.exe" -batchmode -quit -nographics -projectPath . -executeMethod GmiBuild.Build -logFile build.log && cp out/gmi_shaders "D:/Games/gakumas/gakumas-mod/gmi_shaders.bundle"
```

改 `mod.json` 的 `alpha` / `props` / `renderQueue` **不用重编任何东西**，重启游戏即可。

### 0.4 shader 的 pass 索引（`DrawRenderer` 要用，别数错）

| # | Name | LightMode | 被哪个 prop 门控 | 用途 |
|---|---|---|---|---|
| 0 | `GmiActorTransparentZPrePass` | `VLActorTransparentZPrePass` | `_ZPrePassEnable` | ColorMask 0，只写深度 |
| 1 | `GmiActorTransparent` | `VLActorTransparent` | `_ActorTransparentEnable` | VL 原生角色半透明那趟的颜色 |
| 2 | `GmiTransparentForward` | `UniversalForwardOnly` | `_ForwardEnable` | **兜底档用的就是它** |
| 3 | `GmiGBufferTransparent` | `GmiGBufferTransparent`（runtime 改写 `_forwardTagId` 认领） | 无 | 中间件 `ExecuteTransparent` 那趟 |
| 4 | `GmiActorDepthClaim` | `UniversalGBufferActor` | `_DepthClaimEnable` | 只写 RT0.B 的深度认领 |

### 0.5 出坏相怎么恢复

**删掉 `<游戏目录>/gakumas-mod/` 下所有 `*.on` 文件再重启** —— 所有实验性 hook 一律带文件开关，
不装即恢复。改渲染流程出错是硬崩，删个文件比重装 DLL 快得多。

### 0.6 唯一还活着的技术任务

**5.19**：从注入的 CommandBuffer 里 `cmd.DrawRenderer(SkinnedMeshRenderer, …)` 画出来的几何，
位置/姿势不是当前帧的。查通它，5.17 和 5.18 两条路同时活，其中 5.18 是最干净的解法。
**已排除的假设列在 5.17 的表里，别重来。**

### 0.7 怎么读这份文档

- **1–4 节**是结论和事实，可以直接信。
- **5 节是按时间排的调查日志**，前面的小节有若干**后来被推翻的结论**（都在原地标了推翻说明，
  保留是为了当反面教材）。**别从 5.1 顺着读到 5.19 当教程用** —— 要结论看 4 节的路线表和 5.19。
- **7 节**是可复跑的调试手册（抓帧怎么读、离线怎么量）。
- **8 节**是教训，每一条都对应本轮踩过的具体坑。

---

## 1. 目标与硬约束

目标：让 mod 的部件（飘带、薄纱等）以**连续 alpha** 渲染，观感与原生服装一致。

三条从抓帧得到的硬约束，两两冲突：

| 要求 | 必须满足 |
|---|---|
| 不被景深虚化 | 必须在 G-buffer RT0 里有**完整**记录（只写一个通道，光照/合成会拿到半成品） |
| 混合结果正确 | 混合时目标缓冲里必须已经有背景；角色专用颜色缓冲**在角色开画前被清屏** |
| 不被合成贴白 | 一旦写了 RT0 的材质 ID，就必须把对应的角色颜色缓冲也写对 |

前两条直接打架：RT0 完整 ⇒ 你是不透明表面 ⇒ 颜色要写进被清屏的缓冲 ⇒ 混不到背景。
**这不是学马的实现问题，是延迟渲染的定义**（一个像素只能存一个表面）。
游戏自己没有半透明服装，正是因为要付同样的代价。

---

## 2. 管线事实（3Dmigoto 抓帧实测，可复跑）

抓帧目录：`D:/Games/gakumas/FrameAnalysis-2026-08-18-*`（换装间，角色在场）。
`d3dx.ini` 已开 `export_shaders=1` / `export_hlsl=2` / `dump_usage=1`，
`analyse_options` 含 `dump_rt dump_depth`；dump 出的 HLSL 在
`D:/Games/gakumas/ShaderCache/<hash>-ps_replace.txt`。

> ⚠️ 别把 dump 出来的文件拷进 `ShaderFixes` —— 那里只该有 9 个原装文件，多一个就静默顶替
> 游戏的 shader，之后所有渲染诡异都会指向错的方向。

### 2.1 一帧的结构

```text
① 房间/背景        → 场景色缓冲
② 角色 MRT         → RT0 (RGBA16F)  运动矢量.xy | 深度 | 材质ID
                     RT1 (R11G11B10) 角色颜色缓冲，**开画前被 ClearRenderTargetView 清屏**
③ 合成/描边        → 读 RT0，往场景色写
④ 后处理           → 从 RT0 重建深度 → 景深链 → 雾 → bloom → tonemap
⑤ 透明队列         → 直接画进场景色
```

### 2.2 RT0 的编码（原生 body PS `58352a72263d897c`）

```hlsl
o0.xy = float2(0.5,-0.5) * 运动矢量;
o0.z  = 16376 * sqrt(z);       // z = SV_Position.z（反向 Z，近处值大）
o0.w  = 256;                    // 材质 ID；背景为 0
o1.xyz = min(1000, 颜色);   o1.w = 1;
```

像素级验证：背景 `A=0 B≈3720`，角色 `A≠0 B≈4980`。

### 2.3 景深只吃 RT0.z（CoC PS `8049386f8c4ef698`，全文 20 行）

```hlsl
r0.x = t0.Sample(uv).z;              // 只采 RT0 的 B 通道
r0.x = 6.10649731e-05 * r0.x;        // = 1/16376
r0.x = r0.x * r0.x;                  // 还原 z
… → 线性深度 → 焦距/距离 → CoC
```

**「写进 RT0.z」是不糊的充要条件。** 我们不写 → CoC 取背后几何的深度 →
身体后清晰、地板后糊、拉近更糊。zwrite / stencil / TAA 与此**全部无关**（均已实测排除）。

### 2.4 队列分档（IDA + 运行时双向确认）

```text
{0, 2500}      不透明区间（VLActorGBuffer.ExecuteBase、VLActorTransparentPass 都用它）
{2501, 2700}   VLRenderQueue.GBufferTransparentRange   ← 死区：没有任何 pass 画它
{2701, 3500}   VLRenderQueue.TransparentRange          ← 普通透明
```

材质队列设成 2501 → **一个 draw 都没有**（抓帧确认），因为覆盖它的
`VLActorGBuffer.ExecuteTransparent` 在学马零调用。

---

## 3. 已建成的基础设施（与路线无关，可直接复用）

### 3.1 自建 shader 与打包

- 源码：`gakumas-mod-runtime/packaging/shaders/GmiTransparent.shader`
- 工程：`.local/gmi-shaders-proj`（Unity **6000.0.77f1**，与游戏同版本），
  `GmiBuild.Build` 打出 `gmi_shaders.bundle`，`tools/package.ps1` 已把它收进发布包
- **绝不 include URP 的 ShaderLibrary**：游戏用的是 fork 过的 URP（源码路径
  `campus-client/campus-submodule/Graphics/com.unity.render-pipelines.universal`），
  include 版本对不上就是粉屏。只用引擎自带的 `UnityCG.cginc`；蒙皮由引擎在 VS 之前完成
- toon 用项目已实测的贴图语义：`t1.r`=阴影阈值、`t1.a`=AO；`t4.rgb`=暗面色、`t4.a`=分支 mask
- **顶点色故意不采样**：mod 网格的 COLOR 是描边参数（布料预设 `(0,0,255,0)`），
  乘进来会把部件染蓝并把 alpha 干掉

### 3.2 Runtime（`gakumas-mod-runtime/src/runtime/ModRuntime.cpp`）

`mod.json` 的 `replacements[].transparentMaterials[]`：

```json
{ "rendererName": "Geo_Body", "materialSlot": 2,
  "asset": "Assets/Mods/<id>/body_slot0_t0.png",
  "defMap": "…_t1.png", "shadeMap": "…_t4.png",
  "alpha": 0.45, "toonStrength": 1.0, "shadeDarken": 0.45,
  "cull": 0.0, "zwrite": 0.0, "renderQueue": 2400,
  "props": { "任意 shader 属性": 数值 } }
```

- 加载 `gakumas-mod/gmi_shaders.bundle` → `new Material(shader)` → **把 renderer 的
  `sharedMaterials` 扩容到「声明的最大槽位 + 1」**。原版 body 只有 bdy/bdyco 两槽，
  多出来的 submesh 不扩容会被 Unity **静默丢掉**
- `props` 是任意 shader 属性直通 → **调参不用重编 shader**，改 mod.json 重启即可
- fail-closed：shader 包缺失 / 贴图缺失 / 材质建不出来 → 整体拒绝并在日志点名，不静默回落

### 3.3 插件（`gakumas_mi`）

- 材质属性「渲染材质」新增 **自建半透明** 档（`gmi_alpha_mode = GMI_TRANSPARENT`），
  配套 `gmi_transparent_alpha` / `_toon` / `_co_atlas` / `_proxy`
- `core.merge_material_groups(..., transparent_slots)`：半透明槽落在目标段数**之后**，
  不受「目标只有 N 段」限制；`core.transparent_group_map` 给出槽→段号
- `tools/patch_unity_bundle.py`：允许**材质段变多**（复制最后一段当模板），变少仍报错
- 半透明段**不另出贴图**，复用已有的 body/co 两张 t0 —— 模板里没有多余的 Texture2D 对象，
  而 UnityPy 现造对象是已知的 Unity6 加载崩溃源

### 3.4 实验性开关与 hook 清单（全部只在开关文件存在时才装）

| 开关文件（放 `<游戏目录>/gakumas-mod/`） | 文件内容 | 装了什么 | 对应小节 |
|---|---|---|---|
| `vl-transparent-pass.on` | 数字 = `RenderPassEvent`（默认 300） | 钩 `ScriptableRenderer.EnqueuePass`，在 `CampusActorRenderPass` 之后补塞一个 `VLActorTransparentPass`；钩 `OnCameraSetup` 配目标 | 5.2 / 5.3 |
| `vl-gbuffer-transparent.on` | 无（存在即可） | 钩 `VLDeferredPass.RenderActor`，改写 `_forwardTagId` 成我们自己的 tag，然后转发 `VLActorGBuffer.ExecuteTransparent`；顺带把 `_transparentFilteringSettings` 队列下界改到 2400 | 5.8 / 5.9 |
| `vl-afterdof.on` | 数字 = shader pass 索引（默认 2） | 钩 `VLPostProcessPass.SetupVLBloom`，在它之前把部件画进景深之后的颜色缓冲 | 5.17 |
| `vl-depthpatch.on` | 数字 = shader pass 索引（默认 0） | 钩 `VLDeferredPass.Execute`，在它之前把部件深度补写进 `_cameraDepthTexture` 快照 | 5.18 |

**始终安装的只读探针**（不受开关控制，只写日志、不改渲染）：

```text
VLActorGBuffer.ExecuteBase / ExecuteTransparent      VLActorTransparentPass.Execute
VLDeferredPass.Execute / RenderActor                 VLPostProcessPass.DoVLDOF / SetupVLBloom
```

**日志前缀**：`[VLProbe]` 结构与配置、`[VLPass]` 接线状态、`[VLDoF]` 后处理侧、`[VLDepth]` 深度补写。

```bash
grep -aE "VLProbe|VLPass|VLDoF|VLDepth" "D:/Games/gakumas/gakumas-mod/mod-plugin.log"
```


---

## 4. 试过的每条路线与结论

| # | 路线 | 结果 | 定性原因 |
|---|---|---|---|
| 1 | 原生 co 段（`m_bdyco`） | 只能二值 | 游戏自己就是 alpha test；挂饰靠「周围蒙皮全透」避免黑边 |
| 2 | 自建 shader + 前向透明队列 3000 | **半透明成立**，压背景糊 | 不在 RT0 里，景深取背后几何的深度 |
| 3 | 队列 2450/2500 + `UniversalForwardOnly` | 全糊 / 白 | 落进角色 MRT 阶段，混合的是被清屏的角色缓冲 |
| 4 | 写 stencil（Ref 64 / mask 108） | 无变化 | 景深确实不读 stencil——但**结论下早了**，读 stencil 的是第 5.5 节那趟全屏 resolve |
| 5 | 队列 2501（GBufferTransparentRange） | **一个 draw 都没有** | 那段是死区，`ExecuteTransparent` 零调用 |
| 6 | G-buffer 代理段（复制几何只写 RT0） | 白 | 写了材质 ID → 合成把空的角色颜色缓冲贴上来 |
| 7 | 代理段只写 RT0.z（`ColorMask B`） | 糊+白（变量不干净） | 当时混着复制段和别的队列，未单独复测 |
| 8 | 抖动 / screen-door | 未做 | 作者明确否决 |
| 9 | Overlay 相机 | 未做 | 一定成，但不吃场景后处理，且要拆独立 renderer |
| 10 | 自采场景色、自己 lerp 后不透明写回 | 已写好未测 | shader 里有 `_SelfBlendEnable` / `_SceneColorDebug` 两个开关 |
| 11 | VL 原生角色半透明通路（`VLActorTransparentPass`） | 接通了，但 `dsv=NULL` | 颜色对、深度没有 → 透视 |
| 12 | 深度认领（`UniversalGBufferActor`，只写 RT0.B） | 压角色清晰、压背景糊 | 被 draw 96 用深度快照重算掉（5.14） |
| 13 | 深度认领 + stencil 64 | 不糊了，但**白** | 挡掉 draw 96 = 连它的场景色回填一起挡掉（5.6） |
| 14 | **中间件自带的 `ExecuteTransparent`**（转发调用 + 改写 `_forwardTagId`） | **跑通了**，颜色正确 | 但它是**前向单目标** pass，拿不到 RT0，解决不了糊（5.11） |
| 15 | 后景深绘制（钩进 `SetupVLBloom` 之前） | **确实不受景深影响** | 位置/姿势不对，见 5.17 |
| 16 | **深度快照补写**（往 `_cameraDepthTexture` 补一笔） | **机制成立**（出现无景深亮斑） | 同 15 的病，见 5.18/5.19 |

**已实测排除**的假设（别再重复）：贴图分辨率/UV 密度、TAA 缺运动矢量、
透射到的背景本身糊、「那块几何本来就在景深外」——
最后一条被「同一副几何走原生材质在任何距离都不糊」直接否掉。

---

## 5. 调查日志（按时间排，含已被推翻的结论）

> ⚠️ **这一节不是教程，是过程记录。** 前面的小节里有若干后来被推翻的结论
> （都在原地标了推翻说明，保留是为了当反面教材）。
> 要**结论**看第 4 节的路线表和 5.19；要**上手**看第 0 节。


### 5.1 中间件里有什么

`VL.Rendering.VLActorTransparentPass`（`Unity.RenderPipelines.Universal.Runtime.dll`）：

```text
_prePassTagId  = 85  VLActorTransparentZPrePass
_shaderTagIds  = 86  VLActorTransparent
                 87  VLActorCoverZPrePassTransparent
                 88  VLActorCoverTransparent
_outlineTagId  = 89  （名字未知，三次猜测未中；不影响出图）
_filteringSettings: 队列 [0, 2500]，layerMask 0xFFFFFFFF，renderingLayerMask 0xFFFFFFFF
renderPassEvent = 400（构造函数设的）
Execute() = 三趟 DrawRenderers：前置 → 颜色 → 描边
```

tag id 由**运行时反查**确认：拿候选名构造 `ShaderTagId`，撞上已注册的 id 即命中
（新名字会拿到递增的新 id，所以没撞上的一眼可辨）。
这几个 tag **全游戏只有这个 pass 用** —— 挂它们的 pass 不会被别的趟误收，
之前「白块 / 多趟同画」的坑从机制上消失。

同源的 `VLActorGBuffer`（含 `ExecuteTransparent`）在实机**零命中**——注意这是运行时探针的结论，
不是静态的：IDA 里链路是存在的

```text
VLSRPRenderer ctor 0x0A183AC0（VLDeferredPass 存在 this+0x420）
  → VLSRPRenderer.Setup 0x0A184530     配 attachments 并按条件 Enqueue
    → VLDeferredPass.Execute 0x0A1702DC → RenderActor 0x0A171778（private）
      → VLActorGBuffer.ExecuteBase 0x0A16E3D8   ShaderTagId = UniversalGBufferActor
```

但 PC 这一版整局（300+ 帧、角色在场、`VLActorTransparentPass.Execute` 有命中）
`VLActorGBuffer.ExecuteBase(probe)` 钩子**一次都没触发**（钩子确实装上了：
`Hook installed: VLActorGBuffer.ExecuteBase(probe) target=00007FFDC723AA10`；
它一触发就会打 `_actorTagId` 那一串，日志里没有）。

**唯一的残余可能**是 PC 的 AOT 把 `ExecuteBase` 内联进了 `RenderActor`，
钩子挂在独立函数体上就永远等不到。所以加了三个**内联影响不到的**上游探针（已编译部署，待一次重启）：

| 探针 | 为什么它不怕内联 |
|---|---|
| `EnqueuePass` 里打「renderer 类名 ← pass 类名」各一次 | 在调用链最上游；直接答「当前 renderer 是不是 `VLSRPRenderer`」「`VLDeferredPass` 到底排没排进去」 |
| `VLDeferredPass.Execute` | `override`，走虚表，必有独立函数体 |
| `VLDeferredPass.RenderActor` | 把「角色那一支」和整个 deferred pass 分开 |

**探针局结果（2026-08-18 23:05，已跑）**：

```text
[VLProbe] 入队 VLSRPRenderer ← DownscalePass / DownscaleTransparentPass / DownscaleApplyPass
                             / ActorShadowPass / CampusActorParameterPass / VLDecalPass
                             / GlobalWindPass / CampusActorRenderPass / RenderObjectsPass
                             / MainLightShadowCasterPass / AdditionalLightsShadowCasterPass
                             / VLPreDepthIDPass / ColorGradingComputePass / VLDeferredPass
                             / InvokeOnRenderObjectCallbackPass / VLPostProcessPass / VLCapturePass
[VLProbe] VLDeferredPass.Execute    FIRED（第 1 次 / 第 300 次）self=…2A37F960
[VLProbe] VLDeferredPass.RenderActor FIRED（第 1 次 / 第 300 次）self=…2A37F960
（VLActorGBuffer.ExecuteBase 仍然一次都没有）
```

三条判据 **1、2 成立**：当前 renderer 就是 `VLSRPRenderer`，`VLDeferredPass` 在它的队列里，
`RenderActor` 每帧都跑 —— 而且 `CampusActorRenderPass` 和 `VLDeferredPass` **挂在同一个 renderer 上**，
不是两套并行管线。IDA 那条静态链路在 PC 上是活的。

`ExecuteBase` 的钩子零命中，剩两种解释，从进程外分不开：AOT 把它内联进了 `RenderActor`，
或者 `RenderActor` 里有分支绕过它。**分不开也不用分** —— 追加的探针改从 `RenderActor` 手里取
`VLDeferredPass._actorGBuffer` 实例直接 dump，下一局会打出

```text
[VLProbe] VLDeferredPass._actorGBuffer=…
[VLProbe] _actorTagId(+0x..)=id:77 "UniversalGBufferActor"   ← 期望值
[VLProbe] _baseFilteringSettings(+0x..) queue=[…]            ← 决定 renderQueue=2400 收不收得走
```

`_baseFilteringSettings` 的队列区间是这条路真正的成败开关：2400 落在区间里，
§5.4 的深度认领就有宿主；落在外面，材质怎么配都不会被这一趟画到。

### 5.2 我们怎么接的

runtime hook `ScriptableRenderer.EnqueuePass`：游戏的 `CampusActorRenderPass` 入队之后，
把我们 `new` 出来的 `VLActorTransparentPass` 也入队一次。
**不启用整套 RendererFeature** —— 它会连 `VLActorForward` 一起来，和 Campus 那套重复画角色。

实测日志（成立）：

```text
[VLPass] VLActorTransparentPass 实例已创建 … renderPassEvent=300
[VLPass] VLActorTransparentPass 已入队（第 1 次 / 第 300 次）
[VLProbe] VLActorTransparentPass.Execute FIRED —— 原生角色半透明通路是活的
```

### 5.3 卡点：这条 pass 的 draw **没有深度附件**

同一帧内的对照：

```text
我们的退路 pass（不透明段）  dsv=3bb6dc74   ← 有深度
VL pass 的两趟                dsv=NULL      ← 没有深度
```

后果：① 没有深度测试 → 正面能看到被身体挡住的部件；② 前置那趟没深度可写 → 景深照旧。

**已试且无效（别再重复）**：

- `ConfigureTarget(color, depth)` 在 `EnqueuePass` 时机 → 两个句柄都是 null（相机目标还没配）
- 同一调用挪到 `OnCameraSetup` → 句柄非空、调用成功，**dsv 仍是 NULL**
- `set_useNativeRenderPass(false)` → 无变化
- `renderPassEvent` 改 300（AfterRenderingOpaques）→ 无变化
- hook `ScriptableRenderer.Execute` 转发 → **部件直接消失**
  （`Execute` / `ExecuteFast` 同名，按名字取方法很可能挂错重载）。**这个 hook 已删，别再加**

### 5.4 当前部署的配置：两趟分工

```text
颜色  LightMode = VLActorTransparent        VL 原生那趟：真 alpha 混合，底下是完整场景
深度  LightMode = UniversalGBufferActor     角色 MRT 那趟：深度绑着，RT0 就是景深读的那张
        ColorMask B 0    只写 RT0 的深度通道 = 16376·√z
        ColorMask 0 1    角色颜色缓冲一个字节不写（否则合成贴空缓冲 → 白）
        不写材质 ID      （.w 一动，合成就来抢 → 也是白）

mod.json: renderQueue 2400
          props {_ActorTransparentEnable:1, _DepthClaimEnable:1, 其余 0}
```

同一个材质挂两个 tag、两趟各取所需，**不需要复制几何**。这一版的实测结果尚未回报。

---

### 5.5 「还是糊」的根因：一趟全屏 resolve 把深度认领刷掉了

抓帧 `FrameAnalysis-2026-08-18-231211`（换装间，2162×3840）。先按 PS 指纹认领我们的 draw：

| draw | PS | 是谁 | 输出 |
|---|---|---|---|
| 100 / 101 | `2cb5ea89ac146db5` | **我们的 `UniversalGBufferActor` 深度认领**（`o0.z=16376·√z`、`o0.xyw=0`、`o1=0`） | `o0=2b977138 o1=cda673bf **oD=3bb6dc74**` |
| 103 | `58352a72263d897c` | 原版 body G-buffer | 同上 |
| **104** | `24c7e9bfbe2d4b81` | **全屏 resolve**：`Draw(VertexCount:3)`、无 IB、**StencilRef 64**，`t0`=深度、`t1`=场景色，重新算 `o0.z=16376·√(t0.Load())`。⚠️ 这里当时写的「`t0`=真实 DSV」**是错的**，见 5.14 | 同上 |
| 106–109 | `ebb46f9a…` / `3d5d7d39…` | 我们的 VL 那两趟（ZPrePass + 颜色） | `o0=cda673bf`，**dsv=NULL** |

第一个好消息：**深度认领这趟是有 DSV 的**（`oD=3bb6dc74`），5.4 的分工在 API 层面成立。
坏消息是 draw 104 紧跟着把它刷了。逐像素量（比 RT0 的 dds，B 通道）：

```text
我们写进 RT0.B 的像素      2,538,947
  压在角色身上 (matID≠0)   1,432,624   draw104 之后存活 98.4%
  压在背景上   (matID==0)  1,106,323   draw104 之后存活  0.0%   ← 全没了
```

**存活的那 98.4% 不是我们赢了**，是原版角色在那儿写了 stencil 64、draw 104 被 stencil 挡住了而已。
API 层面直接坐实：

```text
draw 099/102/103（原版角色）  OMSetDepthStencilState(…, StencilRef:64)
draw 100/101（我们）          OMSetDepthStencilState(…, StencilRef:0)   ← 没写 stencil
draw 104（全屏 resolve）      OMSetDepthStencilState(…, StencilRef:64)
```

这正好解释了从第一天起就记着的那句「身体后清晰、地板后糊」——它一直是**同一个原因**，
不是景深参数、不是贴图、不是 TAA。

> ⚠️ **本节的「修法」在 5.14 被推翻**：`t0` 不是活的 DSV，是深度预pass 结束时拍的**快照**。
> 「压背景 0.0% 存活」的真正原因是**时机**（我们写在快照之后），不是「没写 stencil」。
> stencil 只是把 draw 104 整个挡掉，连带挡掉它的颜色回填 —— 于是有了 5.6 那片白。
> 下面这段保留原样，作为「机制成立 ≠ 结论成立」的又一个例子。

**修法**：深度认领那趟补上和原版角色一样的 stencil 写入（已改、已重编、已部署）：

```shaderlab
Stencil { Ref [_StencilRef] WriteMask [_StencilWriteMask] Comp Always Pass Replace }
```

`_StencilRef` / `_StencilWriteMask` 默认 64，走 `props` 可改，不用重编 shader。

**顺带查掉的一个风险**：draw 104 同时还写 `o1.xyz = cb0[157].xyz × 场景色`。
把自己从这趟里遮出去，等于放弃那次乘法。这一帧 `cb0[157] = (1,1,1,1)`，**乘的是 1，没有代价**；
但它是随场景变的常量，如果哪个场景曝光不为 1，压背景那半边会出现亮度缝——到时候看这一格。


### 5.6 stencil 修法的实机结果：糊变白 —— 第 1 节那个矛盾的 draw 级证据

补上 stencil 64 之后，压背景那半边**从「糊」变成「白 + 抖动」**，正是路线 6 当年那片白。
机制现在是闭合的：

```text
角色 MRT 开画前   RT1（角色颜色缓冲）被清屏
draw 099/102/103  原版角色写 RT0 + RT1，并写 stencil 64
draw 104          全屏 resolve：stencil 挡掉角色像素，把**其余像素**的
                  RT0.z（按真实 DSV 重算）和 RT1（按场景色副本回填）补齐
```

也就是说 draw 104 一趟干两件事：**补深度**和**补背景色**。
我们原先只被它刷掉深度（糊）；写了 stencil 之后两件一起躲开了 ——
深度保住了，RT1 却停在清屏值上，于是那片白。

**所以第 1 节那条「前两条要求直接打架」不是理论推导，是 draw 级事实**：
在这条管线里，**认领一个像素的深度 = 认领它的颜色**，两者由同一趟、同一个 stencil 位决定，
不存在只要深度不要颜色的配法。

> ⚠️ 注意抓帧里的 RT hash 是**按描述符**算的，不是按资源身份：
> `cda673bf` 同时出现在 draw 68–90 的 o3/o4、91–98 的 o0、99–104 的 o1 上，
> 它们是几张同规格的 R11G11B10，不是同一张。之前据此判断「RT1 就是场景色、不会被清屏」是错的。

**当前处置**：`mod.json` 的两个半透明槽都加了 `_StencilWriteMask: 0`，
stencil 写入关掉、回到 5.5 之前（压背景糊、但不白）。shader 里的 Stencil 块保留，
改 `props` 就能再开，不用重编。

**要往下走只有两条**，都得同时供 RT1：

1. **路线 10（自采场景色）真正实现**——现在只有 `_SelfBlendEnable` / `_SceneColorDebug`
   两个属性和一个 `sampler2D _CameraOpaqueTexture` 声明，**任何 pass 里都没用到**，
   文档之前记的「已写好未测」不成立。要做就是：深度认领那趟同时写
   `RT1 = lerp(采到的背景色, 我们的颜色, alpha)`，配 stencil 64 一起认领整个像素。
   **先要解决的问题**：draw 104 的 `t1` 是引擎绑的场景色副本，
   我们这边 `_CameraOpaqueTexture` 到底有没有值，没验过。一次 `_SceneColorDebug=1` 就能看出来
   （部件上显示出背后的房间 = 有值）。
2. **放弃在 G-buffer 里认领**，回第 6 节的兜底（队列 3000 前向透明，压背景近景偏软）
   或 Overlay 相机。

### 5.7 路线 10 死在「拿不到场景色」（IDA + 入队清单，不用重启）

路线 10 要的是「自采场景色、自己 lerp」。查了两头，两头都不通：

- **`_CameraOpaqueTexture` 永远是空的**：URP 只在 `CopyColorPass` 跑过之后才填它，
  而 5.1 那份**入队清单里没有 `CopyColorPass`**（VLSRPRenderer 的 17 个 pass 一个都不是）。
- **VL 自己的场景色不是全局贴图**：`VLSRPRenderer.m_LitColorTexture`（`VLCameraBufferSystem`，+0x3B0）
  配 `GetLitColorTexture(cameraHash)` / `MarkLitColorTextureAsRendered(cameraHash)`。
  IDA 查 `GetLitColorTexture`（`0x0A187494`）的 xref：**只有一个调用者**，
  `VLDeferredPass.Execute`（`0x0A1702DC`），取到的 RTHandle 被 `memmove` 进 subpass 的附件描述里
  ——它是**附件**，不是 `SetGlobalTexture`。draw 104 的 `t1` 就是它。

所以 shader 侧没有任何一个名字能采到场景色。要走通只剩一条：
**我们自己的 runtime 拿 `m_LitColorTexture` 调 `Shader.SetGlobalTexture` 绑成全局**——能做，
但要在正确时机拿 cameraHash、把 RTHandle 解成 Texture、再保证绑定发生在我们那趟之前，
是个工程，不是一行。

**结论**：G-buffer 认领这条路，在不做上面那个工程的前提下**到此为止**。

### 5.8 中间件自带的「G-buffer 半透明」通路：接线，不是发明

`VLActorGBuffer` 里整套东西是齐的，缺的只是没人调 `ExecuteTransparent`：

```text
ShaderTagId  _actorTagId 0x10 / _hairTagId 0x14 / _outlineTagId 0x18 / _forwardTagId 0x1C
FilteringSettings _base 0x20 / _hair 0x40 / _all 0x60 / _transparent 0x80
ExecuteBase / ExecuteHair / ExecuteTransparent
```

**实机读到的值**（PC，本轮探针）：

```text
_actorTagId=77 "UniversalGBufferActor"   _hairTagId=78   _outlineTagId=79   _forwardTagId=60 ← 名字待认领
_baseFilteringSettings        queue=[0,2500]     layerMask=0xB800  renderingLayerMask=0xB000
_transparentFilteringSettings queue=[2501,5000]  layerMask=0xB800  renderingLayerMask=0xF000
VLRenderQueue.GBufferTransparentRange = [2501, 2700]
```

`GBufferTransparentRange` **在 iOS 3.2.3 里不存在**（那一版 `VLRenderQueue` 只有
`MotionVectorRangeBefore/After`、`TransparentRange`、`DownscaleTransparentRange`），是这一版新加的；
而 `TransparentRange` 从 2701 才开始，那 200 格是特意让出来的。`VLActorGBuffer` 的字段布局两版一致。

**接法要换一个落点**：原计划是 hook `ExecuteBase` 再转发一次 `ExecuteTransparent`，
但 PC 这一版 **`ExecuteBase` 的钩子零命中**（见 5.1），挂不上去。
改挂 `VLDeferredPass.RenderActor` —— 它每帧都跑，参数
`(context, ref renderingData)` 和 `ExecuteTransparent` 一模一样，`_actorGBuffer` 实例就在
`VLDeferredPass` 的字段里（探针已经在读了）。此刻 RT 还绑着角色 MRT、深度也在。

已实现并部署，**默认关**：开关文件 `<游戏目录>/gakumas-mod/vl-gbuffer-transparent.on`
存在才转发，删掉重启即恢复。

**下一步是两次重启，别合并**：

1. **不建开关文件**先重启一次：候选名表里补了 8 个候选，日志会打出 `id:60` 到底叫什么。
   `ExecuteTransparent` 用的多半就是这个 tag，配 shader pass 之前先把它钉死。
2. 拿到名字后再加对应 `LightMode` 的 pass、`renderQueue` 设进 2501–2700、建开关文件重启。

### 5.9 `_forwardTagId` 的名字查不到 —— 改成我们自己定

第一次探针局的结果：8 个候选**全部拿到新 id（93–100）**，没有一个是 `id:60`。
而且日志里还有一行关键的：

```text
[ModAsset] Optional method absent (有降级路径): UnityEngine.Rendering::ShaderTagId.get_name
```

`ShaderTagId.get_name` 在这一版**被裁了** —— 所以 id → 名字根本反查不了，只能靠撞。
又从 PC 的 `global-metadata.dat` 里把字面量表捞出来对了一遍，`LightMode` 相关的真实字符串只有：

```text
Universal2D / UniversalForward / UniversalForwardOnly / UniversalForwardOutline
UniversalForwardPerformance / UniversalGBuffer / UniversalGBufferActor
UniversalGBufferActorHair / UniversalGBufferOutline / UniversalGBufferPreDepth
UniversalGBufferVirtualEffect / UniversalGBufferVirtualHair / UniversalGBufferVirtualOutline
UniversalMaterialType
VLActor / VLActorCover / VLActorCoverAlphaFillPass / VLActorCoverTransparent
VLActorCoverZPrePass / VLActorCoverZPrePassTransparent / VLActorTransparent / VLActorTransparentZPrePass
```

（顺带证否：`VLActorOutline`、`VLActorCoverOutline`、`VLActorTransparentOutline`、`VLActorForward`
**在字面量表里根本不存在**，之前拿它们去撞 `id:89` 当然撞不上。）

**与其继续撞，不如直接改写**：`_forwardTagId` 这个字段本来就没人用
（`ExecuteTransparent` 零调用），转发之前把它写成我们自己造的
`ShaderTagId("GmiGBufferTransparent")`，名字叫什么由我们定，`id:60` 是什么就不重要了。
字段按名字解析（不写死 0x1C）。

### 5.10 当前部署（等一次重启）

```text
runtime   VLDeferredPass.RenderActor 钩子 → 改写 _forwardTagId → 转发 ExecuteTransparent
shader    新增 pass "GmiGBufferTransparent"：Blend 0 One Zero / Blend 1 SrcAlpha OneMinusSrcAlpha
          RT0 = (0, 0, 16376·√z, _MaterialId=256)   RT1 = toon 颜色 + alpha
mod.json  renderQueue = 2600（落进 GBufferTransparentRange=[2501,2700]）
          _DepthClaimEnable / _ActorTransparentEnable / _ZPrePassEnable / _ForwardEnable 全 0
开关      gakumas-mod/vl-gbuffer-transparent.on 已建
          gakumas-mod/vl-transparent-pass.on   已删（少一个变量）
```

三种可能的结果，各自的下一步：

| 现象 | 说明 | 下一步 |
|---|---|---|
| 部件正常半透明 | 中间件那条路通了 | 收工，把参数固化 |
| 一个 draw 都没有 | `ExecuteTransparent` 用的不是 `_forwardTagId`，或队列/layerMask 不收 | 抓帧看；改试 `_allFilteringSettings` 那几个字段 |
| 画了但不对（白/黑/位置错） | 合成规则不是预乘 alpha，或缺前置 RT | 抓帧比对 RT0/RT1 的实际写入 |

出任何坏相：删 `vl-gbuffer-transparent.on` 重启即恢复。

### 5.11 中间件通路实机跑通（2026-08-19）

```text
[VLPass] _forwardTagId(+0x1C) 60 → 85 (GmiGBufferTransparent)
[VLPass] 开始向 VLActorGBuffer.ExecuteTransparent 转发
[VLProbe] VLActorGBuffer.ExecuteTransparent FIRED (第 1 / 100 / 1000 次)
```

零调用的死代码每帧都在跑，部件由它画出来了。两个坑各踩一次：

1. **这趟是前向 pass，单颜色目标**。第一版按 MRT 写了 `SV_Target0/1`，
   结果 `rt0` 的 `16376·√z`（≈4500）被当成颜色直接糊上去 —— 爆亮纯蓝 + bloom 拉出的紫晕。
   改成单 `SV_Target` 返回 toon 颜色后正常。
   **这条同时也是个事实**：这趟拿不到 RT0，深度认领只能还是靠 `UniversalGBufferActor` 那趟。
2. **tag id 会随启动顺序变**。这一局 `GmiGBufferTransparent` 拿到 85，
   而之前几局 85 是 `VLActorTransparentZPrePass` —— 因为那几局有探针预先注册了 26 个候选名。
   **id 只在本次进程内有意义，别跨日志比对。**

单目标版的实机现象（作者截图）：**身体外「远清晰、近模糊」**（就是老问题，景深）；
**身体上「磨砂质感」**（新的，最可能是 `cull:0` 双面互混又没排序，只在锐利处看得见）。

### 5.12 组合解：深度认领 + 中间件供色（当前部署，等一次重启）

白的死结现在有解了 —— 之前是「写 stencil → 躲开 draw 104 的背景色回填 → RT1 停在清屏值」，
而现在**颜色有了新供给方**：中间件这趟画在 draw 104 之后（上一局那身爆亮蓝压在地板上照样可见，
证明它在 104 后面），正好盖住那片白。

```text
UniversalGBufferActor 那趟   写 RT0.z + stencil 64   → 景深不糊
GmiGBufferTransparent 那趟   在更后面写颜色           → 盖掉 stencil 造成的白
```

队列打架的解法：`_transparentFilteringSettings` 的下界从 2501 改写成 **2400**
（这个字段除了 `ExecuteTransparent` 没人用），材质挂 2400 就同时落进
`_baseFilteringSettings=[0,2500]` 和改写后的 `[2400,5000]`，两趟一起收。

```text
mod.json  renderQueue=2400  _DepthClaimEnable=1  _StencilWriteMask=64  _StencilRef=64
```

判据：**压地板那半边还糊不糊**。糊 → 深度认领仍被刷；不糊但白 → 中间件那趟在 104 之前；
不糊不白 → 成了，剩「磨砂」单独处理（先试 `cull: 2`）。

### 5.13 停下来重新归因：「糊」到底糊的是谁（2026-08-19）

5.12 那版实机结果：**磨砂 + 糊 + 白同时出现**。每修一层冒出下一层
（蓝 → 白 → 磨砂），这通常说明在跟架构对着干。

**该先分清的两件事，一整轮都没分**：

| | 现象 | 含义 | 该做什么 |
|---|---|---|---|
| A | 部件自己被景深糊了 | RT0.z 里没有部件的深度 | 深度认领（我们做的全部工作） |
| B | 部件是清晰的，糊的是**透过它看到的背景** | 没有 bug —— 焦外的地板本来就该虚 | 什么都不用做，回兜底 |

alpha=0.45 的薄纱，一个像素里 55% 是背后的地板。**地板糊是对的。**
文档第 8 节第 1 条已经记着这个项目四次把「糊」归错因，这一轮又犯了第五次：
没做 A/B 分离就直接上深度认领，结果是每加一层制造一个新伪影。

**分离方法（一次重启，不用编译）**：alpha 拉到 0.95，其他全不动。

- 部件变清晰 → **是 B**，5.4–5.12 全部作废，回兜底；
- 部件还是糊 → **是 A**，方向没错，再查 stencil 那版为什么没生效。

当前部署即为这个测试：兜底前向（`_ForwardEnable=1`，queue 3000）+ `alpha 0.95`，
其余通路全关，两个开关文件都已删除（实验 hook 一个都不装）。

### 5.14 定案：draw 96 读的是**深度快照**，不是活的 DSV（2026-08-19）

抓帧 `FrameAnalysis-2026-08-19-013117`（2160×3840，alpha 0.95，深度认领开、stencil 关）。
这一帧里我们的 draw 是 **092 / 093**（`2cb5ea89ac146db5`），全屏 resolve 是 **096**（`24c7e9bf…`）。

**① `ZWrite On` 是生效的，深度缓冲里确实有飘带**

```text
draw 91 → 93（我们那两趟）  DSV 变了 2,217,231 像素（26.73%）
DSV 里的值 0.0768..0.0808 → 16376·√z = 4539..4655   ← 和我们写进 RT0.B 的 4536..4652 一致
```

**② 但 draw 96 采的那张 `t0` 是我们画之前的快照**

```text
draw 34 的 DSV 与 draw96 的 t0 相同像素: 100.00%   ← 深度预pass 刚结束
draw 82 的 DSV 与 draw96 的 t0 相同像素: 100.00%
draw 91 的 DSV 与 draw96 的 t0 相同像素:  32.73%
draw 93 的 DSV 与 draw96 的 t0 相同像素:  26.16%   ← 我们写完之后就对不上了
```

于是 draw 96 从快照算出来的是**地板的深度**：

```text
我们写进 RT0.B        4536 .. 4652
draw96 之后的 RT0.B   1998 .. 2686   → z = 0.0149..0.0269 = draw91 时刻的地板深度
```

> ⚠️ 3Dmigoto 的资源 hash **按描述符算，不按身份**：DSV 和这张快照的 hash 都是 `fb14940a`，
> 两张同规格的深度图长得一模一样。5.5 就是被这个坑骗了一次，5.6 又被同一个坑骗了一次
> （`cda673bf` 同时是 o0/o1/o3/o4）。**看到相同 hash，先证明它们是同一张。**

**③ 所以「糊」的完整因果链是**

```text
深度预pass（draw 16–34）→ 拍快照
  我们的深度认领（92/93）写活 DSV + RT0.B    ← 快照拍完了，晚了
    原版角色（91/94/95）写 RT0，并写 stencil 64
      全屏 resolve（96）：stencil≠64 的像素，用**快照**重算 RT0.B
        → 压角色的像素被 stencil 挡住，我们的值留下（97.0%）
        → 压背景的像素被重算成地板深度（存活 0.0%）
          → 景深按地板的 CoC 糊 → 飘带跟着糊
```

**④ A/B 归因已完成**：alpha 拉到 0.95（几乎不透背景）后，同一片几何、同一次 draw，
**压腿的一半锐利、压地板的一半虚**。所以糊的是部件自己（A 类），
不是「透出来的背景本来就虚」（B 类）。这条排除掉了 5.13 提的另一半可能。

### 5.15 结论：两条出路，代价都是结构性的

| | 做法 | 效果 | 代价 |
|---|---|---|---|
| **P** | 加一个 `LightMode = UniversalGBufferPreDepth` 的 pass，把飘带写进**深度预pass** | 快照里就有我们 → draw 96 自己算出正确的 RT0.z → 不用 stencil，**也不会白** | 飘带在深度上遮挡身体：和腿重叠处腿会消失。等于把半透明件变成不透明件 |
| **S** | stencil 64 挡住 draw 96（5.5/5.6 那版） | 锐利 | draw 96 同时负责把场景色回填进角色颜色缓冲，挡掉就**白** |

两条的共同结构就是第 1 节那句话，现在有 draw 级证据：
**这条管线里，一个像素的深度和颜色由同一趟、同一个 stencil 位决定。**
P 是把我们变成不透明表面（深度对了、透明没了），S 是抢走像素但供不上颜色。
这是延迟渲染的定义，不是这一版的实现缺陷 —— 游戏自己没有半透明服装，正是因为要付同样的代价。

**建议收在兜底档**：前向透明（`_ForwardEnable:1`、`renderQueue:3000`、`alpha 0.45`）。
画面完全可用，代价是压背景时边缘偏软。再往下走，每一步都是在「半透明」和「遮挡正确」之间二选一。

### 5.16 对照组 SCSP：它不是可抄的作业，是另一种 renderer 配置（2026-08-19）

SCSP（シャニソン，`D:\Games\SONGforPRISM\imasscprism.exe`，**D3D12**）确实有真半透明服装件
（薄纱裙，画面确认）。RenderDoc 抓帧（服装预览场景，1280×720）之后，**它和学马根本不是一套渲染路径**：

```text
Compute Pass #1                   蒙皮/剔除
Depth-only Pass #1   26 draws
Depth-only Pass #2   26 draws
Colour Pass #1       35 draws     房间(24057) + 角色全部部件 ← 纱裙就是其中一个 draw
Colour Pass #2       20 draws     角色部件再来一遍（描边/第二材质段）
后处理               1280→640→320→160 再升回来 = bloom 金字塔
Colour Pass #4       95 draws     index 全是 6/12/54/108/216/324 = UI
Colour Pass #5       → Swapchain
```

**全帧每一次 `OMSetRenderTargets` 都只绑 1 个 RT**（逐条查过 4496 行 API 流，不是从 pass 摘要推的）。
**没有 G-buffer**。半透明纱裙就是前向颜色 pass 里一次普通的混合 draw ——
没有专属 pass、没有专属队列档，不需要任何技巧。

**两条限制说明**：
- SCSP 这一帧**没有景深**（后处理只有 bloom 金字塔，没有 CoC pass）。
  所以「它的纱裙很锐利」**不能**证明前向透明和景深能共存，只证明不走延迟就没这个问题。
- 发行版剥掉了 Unity 的 ProfilingSampler marker，全帧零 marker，看不到 VL 的 pass 名。
  但既然没有 G-buffer，`ExecuteTransparent`（往 G-buffer 阶段画的）也就无从调起。
- 旁证：SCSP 的 `OMSetStencilRef` 是 0/1，学马是 64/48 —— 两套配置。

**结论**：VL 中间件前向/延迟两条都支持，学马换装间配的是 `VLDeferredPass`，SCSP 这个场景配的是前向。
差别在作品/场景配置，不在中间件。**学马的兜底档（前向透明 queue 3000）结构上已经就是 SCSP 在做的事**，
只是学马额外压着一套延迟合成，景深读 RT0.z ——
这正是 5.14/5.15 那个二选一的来源，抄 SCSP 绕不开它。

> 抓 SCSP 的方法备查（DMM 启动的游戏）：RenderDoc 全局钩子在 **Secure Boot 开启时必然无效**
> （它靠 `AppInit_DLLs`，Win8 起被 Secure Boot 禁用）；DMM Game Player 是 Electron + 单实例，
> 直接当宿主抓子进程会卡在界面打不开。可行的是 **DMMGamePlayerFastLauncher**：
> `DMMGamePlayerFastLauncher.exe prism --type game`（`prism` 是 SCSP 的 DMM productId，
> 从 `%APPDATA%\dmmgameplayer5\dmmgame.cnf` 里查），它绕开 DMM 界面直接把游戏当子进程拉起来。
> 另外 3Dmigoto **只支持 D3D11**，对 SCSP 这种 D3D12 完全用不了。

### 5.17 后景深绘制：躲开景深成立，卡在「注入的 DrawRenderer 姿势不对」

思路：不再跟延迟管线抢 RT0.z，改成在**景深之后、bloom 之前**把部件画上去。
底下的场景已经过景深（透过薄纱看到的地板该虚还是虚，物理正确），而纱本身不进景深。

**接入点**：`DoVLDOF` 和 `SetupVLBloom` 都在 `VLPostProcessPass.Render` 的**同一次 Execute 里**，
`RenderPassEvent` 插不进去，只能钩进函数之间：

```text
VLPostProcessPass.Render(cmd, ref renderingData)        0x0A188C4C
  ├─ DoVLDOF(cmd, source, destination, ref cameraData)  0x0A18AC60  ← 实机返回 false（VL 自己那套 DOF 没启用）
  ├─ SetupVLDiffusion(...)
  ├─ SetupVLBloom(cmd, source, ...)                     0x0A192F84  ← 用这个，每帧命中，source = 景深之后的颜色缓冲
  └─ SetupVLParaffin / SetupVLVirtualEffect / RenderFinalPass
```

> 糊我们的景深不是 VL 那套，是**基类 `PostProcessPass`（URP 自带）的 DoF** —— `DoVLDOF` 每帧调但返回 false。

**结果**：部件画出来了，**确实不受景深影响**。但位置错（跑到角色右侧）、不跟随、正反着色反了。

**逐条排除**（每条都实测，别再重来）：

| 假设 | 结论 |
|---|---|
| VP 矩阵没设 | 设了（`CommandBuffer.SetViewProjectionMatrices`），画面零变化 |
| `Camera.main` 拿错相机 | 管线 `renderingData.cameraData` 里的相机**就是** `Camera.main` = `Game3DManager`，矩阵逐值相同 |
| `Camera.current` 更准 | SRP 下是 `<null>` |
| 是 VL 自研蒙皮、非 SMR | **不是**，`Geo_Body` 类型探针打出来是标准 `SkinnedMeshRenderer` |

剩下没排除的只有：**从我们自建 CommandBuffer 里发出的 `DrawRenderer`，
拿到的 `unity_ObjectToWorld` / 蒙皮缓冲不是当前帧的**。

### 5.18 深度快照补写：机制成立，同一个卡点

思路（比 5.17 更干净）：resolve 是从 `_cameraDepthTexture`（**一张独立纹理**，不是活 DSV）
重算 RT0.z 的 —— 那就只往这张快照里补一笔部件的深度，让 resolve 自己算出正确的 RT0.z。

```text
VLDeferredPass._cameraNormalsTexture  +0x280
VLDeferredPass._cameraDepthTexture    +0x288   ← 快照
VLDeferredPass._additionalInfoTexture +0x290
```

**它避开了此前每一条路线的代价**：

| 旧路线的代价 | 这条 |
|---|---|
| 写深度预pass → 部件遮住身体 | 不碰活 DSV，身体照常画 |
| stencil 挡 resolve → 白 | 不用 stencil，背景色回填照旧 |
| 后景深重画 → 5.17 那堆问题 | 在几何阶段画 |
| 颜色要自采场景色（5.7 已死） | 不动颜色，部件仍走 queue 3000 前向透明 |

**两次迭代**：

1. 插在 `RenderActor` 之后 —— 抓帧 `FrameAnalysis-2026-08-19-035841` 显示时机完美
   （draw 92/93 在原版 body 91 之后、resolve 94 之前），但输出是
   `o0=2b977138 o1=cda673bf oD=3bb6dc74` = **角色 MRT + 活 DSV，不是快照**。
   原因：那段命令插在 G-buffer 的 **native render pass 内部**，URP 在 pass 里不允许换渲染目标，
   `CoreUtils.SetRenderTarget` 被静默忽略。
   （用 `renderingData.commandBuffer` 还是自建 CommandBuffer + `context.ExecuteCommandBuffer`
   都一样 —— 后者只保证了时序，管不了 render pass 内不能换目标。）
2. 挪到 `VLDeferredPass.Execute` 开头（快照已就绪、蒙皮已就绪、还没进 render pass）——
   **画面上出现了一块没有景深的亮斑**：证明快照补写这条通路是成立的，
   但那块的形状/位置不跟裙子走 —— **和 5.17 是同一个病**。

### 5.19 现在唯一的卡点

5.17 和 5.18 都已证明结构可行（一条躲开景深、一条改掉景深的输入），并且卡在同一件事：

> **从注入的 CommandBuffer 里 `cmd.DrawRenderer(SkinnedMeshRenderer, …)` 画出来的几何，
> 位置/姿势不是当前帧的。**

已排除：VP 矩阵、相机对象、renderer 类型（见 5.17 表）。
没排除：注入点上 `unity_ObjectToWorld` 和蒙皮缓冲的绑定是否有效。

**下次开工第一件事就是查这个** —— 一旦查通，5.17 和 5.18 同时活过来，
其中 **5.18 是最干净的**：不碰颜色、不用 stencil、不遮身体、不改现有可用画面，
只是额外补一笔深度。

## 6. 怎么继续（按优先级）

这一轮把机制查干净了，剩下的是取舍，不是未知。按「先拿到可用画面」排序：

0. **查 5.19 那个卡点**（唯一还活着的技术路线，优先级最高）：注入的 `DrawRenderer`
   为什么画在错误的姿势上。查通了 5.18 就能收工 —— 它不碰颜色、不用 stencil、
   不遮身体、不改现有可用画面。已排除的假设见 5.17 的表，别重来。

1. **随时可回的兜底档**。`props` 里 `_ForwardEnable:1` + `renderQueue:3000` + `alpha:0.45`，
   其余通路全关、开关文件全删。真 alpha、不白、不抖，代价是压背景时边缘偏软。
2. **想看 P 长什么样**：加一个 `LightMode = UniversalGBufferPreDepth` 的 pass（`ColorMask 0`、
   `ZWrite On`），一次重启就知道「飘带遮腿」难看到什么程度。难看就删掉，代价只有一次重启。
3. **要完全锐利且不挑场景**：Overlay 相机（路线 9）。一定成，代价是不吃场景后处理，
   且要把部件拆成独立 SkinnedMeshRenderer（相机按 GameObject 剔除，管不到 submesh）。
4. **另一件没解决的事 —— 透视**：中间件那趟和 VLActorTransparentPass 都**没有深度附件**
   （`dsv=NULL`，见 5.3/5.11），所以飘带会从背后浮到人物正面。这和糊是两回事，
   兜底档（前向透明，在正常透明队列里、有深度）不存在这个问题。

**别再重复的**（全部实测排除，理由见正文）：贴图分辨率/UV 密度、TAA 缺运动矢量、
stencil 与景深的关系、`_CameraOpaqueTexture` 自采场景色（5.7）、
挂 `ExecuteBase` 转发（PC 上零命中，5.8）、按 id 反查 tag 名字（`get_name` 被裁，5.9）。

---

## 7. 调试手册

```bash
# 运行时日志的关键行
grep -E "VLPass|VLProbe|Applied transparent materials" "D:/Games/gakumas/gakumas-mod/mod-plugin.log"
```

**抓完帧别退游戏** —— 3Dmigoto 退出时会把目录去重成 `FrameAnalysisDeduped`，
`log.txt` 会没掉，`OMSetDepthStencilState` / draw 顺序就读不到了。

**离线量 RT / 深度**（本轮的三个结论都是这么量出来的，dds 是裸 DDS + 半精度/uint32）：

```python
def load(path):                 # 128 字节头，DX10 再 +20
    b = open(path,'rb').read(); off = 4+124
    if b[84:88] == b'DX10': off += 20
    return b[off:]
# RGBA16F 的 RT： np.frombuffer(..., np.float16).reshape(H, W, 4)
# R32G8X24 的深度：np.frombuffer(..., np.uint32).reshape(H, W, 2)[...,0].view(np.float32)
```

三个判据：① 某趟前后 RT0.B 的差集 = 它写了哪些像素；
② 按 RT0.A（材质 ID）切成「压角色 / 压背景」两组分别看存活率；
③ 把某个 draw 的 `ps-t0` 内容和各个 draw 的 `oD` 逐一比，**定位快照是什么时候拍的**。

抓帧怎么读：解析 `FrameAnalysis-*/log.txt`，按 `OMSetRenderTargets` 累计当前的
RT 列表与 DSV，遇到 `Draw*` 就记一行。找我们的 draw 用**索引数**（各段的 `indexCount`）。
关键只看两栏：`rt=[…]`（写进了哪几张）和 `dsv=…`（`NULL` 就是没有深度附件）。

- 出坏相：删 `gakumas-mod/vl-transparent-pass.on` 重启 → 实验性 hook 全不装
- 换 RenderPassEvent：往那个文件里写数字（250/300/350/400/450）重启
- 调透明度 / toon / 各 pass 开关：改 `mod.json` 的 `alpha` / `props` 重启，**不用重新打包**
- 重编 shader：`.local/gmi-shaders-proj` →
  `Unity.exe -batchmode -quit -nographics -projectPath . -executeMethod GmiBuild.Build`，
  产物 `out/gmi_shaders` 拷成 `gakumas-mod/gmi_shaders.bundle`

### 关键 hash / 地址备查

```text
原生 body G-buffer PS   58352a72263d897c      景深 CoC PS    8049386f8c4ef698
原生镂空 PS             7a9af11e8bc01174      暗光 body PS   cf02c2d50d3f2230
全屏 resolve PS         24c7e9bfbe2d4b81      我们的深度认领 PS 2cb5ea89ac146db5
我们的 VL ZPrePass PS   ebb46f9a7f179fb4      我们的 VL 颜色 PS 3d5d7d392f6b87a7
VLActorTransparentPass  ctor 0x0A16D56C   Execute 0x0A16D958         （iOS 3.2.3）
VLActorGBuffer          ctor 0x0A16DF2C   ExecuteBase 0x0A16E3D8
                        ExecuteTransparent 0x0A16E700（零调用者）
VLRenderQueue           TransparentRange 0x0A160F34   不透明 {0,2500} = sub_A447850
iOS il2cpp dump         D:/GIT/gkms-localify-ios/workspace/3.2.3/inspector/cs/il2cpp.cs
```

---

## 8. 教训

1. **机制成立 ≠ 结论成立**。这一轮先后把「糊」归因为景深深度、贴图密度、角色遮罩、材质 ID，
   四次都被一张截图推翻。项目里本就有同样的教训
   （`ab-consolidated-facts-and-evidence-2026-08-16.md` 的「近景发糊」一节，标着"保留作反面教材"），
   引用了它之后又犯了一遍。
2. **一次抓帧能回答多个问题，一次实机只能回答一个**。本轮八次改 shader、每次靠一次重启判一个变量；
   而从**一份**帧里同时读出了景深的解码公式、原生 G-buffer 的写法、RT0 的全部消费者 ——
   比前面所有实机加起来都有用。**先把要问的问题列全，再抓帧。**
3. **克隆 pass 必须保证常量布局不同**，否则编译出逐字节相同的 DXBC：开关失效、
   还会被多趟同时收走。本轮「候选 tag 全部落空」这个错误结论就是这么来的。
4. **实验性 hook 一律加文件开关**。改渲染流程出错是硬崩，删个文件能恢复比重装 DLL 强得多。
5. **3Dmigoto 的资源 hash 按描述符算，不按身份。** 同规格的两张图 hash 一样。
   本轮被这个坑骗了两次：`cda673bf` 同时是 o0/o1/o3/o4（5.6），`fb14940a` 同时是活 DSV 和它的快照（5.14）。
   两次都直接导致了错误结论。**看到相同 hash，先证明它们是同一张再往下推。**
6. **同一个症状要先做 A/B 归因，再动手修。** 「糊」有两种：部件自己被糊（A）、
   透过它看到的背景本来就虚（B）。分开只要一次重启（alpha 拉到 0.95），
   而不分开就花了整整一轮去修一个还没确认存在的问题。第 1 条说的四次归因错误，这轮又添了一次。
7. **ShaderTagId 的 id 只在本次进程内有意义**，随注册顺序变（探针注册了候选名就会挪动后面所有 id）。
   **别跨日志比对 id。** `ShaderTagId.get_name` 在这一版被裁了，反查不了名字 ——
   要认领一个 tag，要么从 `global-metadata.dat` 的字面量表里捞候选去撞，要么干脆改写字段用我们自己的名字（5.9）。
