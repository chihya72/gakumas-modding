# 自建镂空(ALPHA_CLIP)/半透明(ALPHA_BLEND)路径 —— 退役归档（2026-06-30）

> 归档原因：分支 `native-co-only` 把这两条自建透明路径从插件**整体删除**，`渲染材质` 只剩
> `不透明(OPAQUE)` 与 `原生co(NATIVE_CO)`。本文完整记录被删路径的作用、效果、参数与弃用理由，
> 供日后回溯或在原生 co 失效时参考重建。代码可在该删除提交之前的历史里找回。
>
> 关联：[`../transparent-material-status.md`](../transparent-material-status.md)（当前结论）、
> [[transparent-route-native-co-only]]（决策记忆）、
> [`transparent-pass-status-and-planB-20260628.md`](transparent-pass-status-and-planB-20260628.md)（踩坑全程）。

## 0. 三条路径速览

| 模式 | 枚举值 | 机制 | 供着色器? | 版本老化风险 |
|---|---|---|---|---|
| 镂空（删） | `ALPHA_CLIP` | 复用游戏原生镂空 PS 的**冻结拷贝**，只覆盖 ps+贴图，继承主 body VS/状态 | 是（冻结 PS） | **有**（独有） |
| 半透明（删） | `ALPHA_BLEND` | 自建 `InheritMask`+`AlphaBlend` 两段延迟混合 | 是（自写 PS） | 有（自写简化打光） |
| 原生co（留） | `NATIVE_CO` | `TextureOverride` hook 游戏原生第二材质段 draw，只换 IB/VB/贴图 | **否** | **无**（跟版本走） |

## 1. 镂空 ALPHA_CLIP

**作用**：处理二值 alpha 的镂空件（花纹、镂空裙、贴花）。绝大多数「透明」换装件其实是这一类，
不需要真混合。

**机制**：把镂空材质段从主 body draw 拆出，生成 `[CustomShader…AlphaClip{n}]`，里面
`ps = Shaders\GMINativeClip{n}.hlsl`，**只覆盖 ps + 贴图槽**（ps-t0 基色 / ps-t1 packed /
ps-t4 阴影色），不声明 vs / depth / stencil / blend —— 全部继承主 body draw 的管线状态：
- 继承原生 body VS → 原生 PS 拿到正确插值（法线/切线/灯光坐标）；
- 继承 cb0–cb3 → 原生 toon 打光正确，颜色/亮度与原版逐像素一致；
- 继承 depth/stencil → 拿回 body 的 coverage（伸出轮廓外也显示）+ 反向 Z 遮挡；
- A=0 的洞交给原生 PS 的 alpha-to-coverage discard。

`GMINativeClip.hlsl` 是游戏延迟镂空 PS（hash **`7a9af11e8bc01174`**）的反编译拷贝。

**效果**：背景上可见、遮挡正确、A=0 干净、无 AO 暗带、颜色与原版逐像素一致。这是三条里
视觉最贴原版的镂空方案。

**`gmi_alpha_cutoff`（镂空阈值）参数**：`FloatProperty` 默认 `0.33`（=游戏原生阈值），范围
0–1。导出时把 `GMINativeClip.hlsl` 里的常量 `0.330000013` 替换成材质设定值（`f"{cutoff:.9f}"`），
得到 `GMINativeClip{n}.hlsl`。提高阈值可削掉 mip/双线性渗进的低 alpha 脏边。该参数**只服务
ALPHA_CLIP**，随路径一并删除。

**`shadercache_dir` 参数**：`write_inverse_skin_package(..., shadercache_dir=None)`。导出时若指向
本机 3Dmigoto `ShaderCache`，且存在 `7a9af11e8bc01174-ps_replace.txt`，则**优先用本机当前版本**
的镂空 PS（自动跟游戏版本走），插件内置 `GMINativeClip.hlsl` 拷贝只当离线兜底。这是为缓解下面
那个老化风险预留的钩子，**当时没接 UI**。随路径一并删除。

## 2. 半透明 ALPHA_BLEND

**作用**：真半透明（薄纱、玻璃、渔网）的预乘 alpha 混合。

**机制**：拆出后跑两段，运行顺序 `InheritMask → copy oD → AlphaBlend`：
- `[CustomShader…InheritMask{n}]`（`GMIInheritMaskA.hlsl`）：只测深度不写深度
  （`depth_write_mask=zero`、`depth_func=greater_equal` 反向 Z、`blend=ADD ZERO ONE`），
  保留遮挡又不让 A=0 padding 写深度造成 AO 暗带；
- `Resource…SceneDepth = copy oD`：透明色 pass 前抓一份场景深度；
- `[CustomShader…AlphaBlend{n}]`（`GMIFinal.hlsl`，MRT）：`blend[1]=ADD ONE INV_SRC_ALPHA`
  预乘 alpha 混到 RT1，`o0=运动/深度/ID`、`o1=预乘颜色`，clip 全透明像素。

`cull=none`（绕序无法干净分正反面）。

**效果（及其硬限制）**：保守策略，只保证「A=0 镂空干净 + 投影/遮挡正常」；半透明像素**只在
背后已有同模型/同角色几何或 coverage 的区域**可靠显示。**伸出角色轮廓外、背后纯背景的半透明
会被延迟合成 pass 丢弃**——这是延迟渲染+反向 Z 的架构冲突，`clip`/抬 alpha 阈值/`SV_Coverage`/
CoverageMask 实测全部无效（资格写入发生在 PS discard 能约束之前）。详见
[`../transparent-material-status.md`](../transparent-material-status.md) §4。

## 3. 为什么弃用

1. **半透明先天残**：完整背景半透明与「A=0 干净」在 G-buffer/延迟路径二选一，自建路径永远
   只能给保守版，伸出轮廓外不保证 —— 达不到原版渔网/薄纱效果。
2. **镂空有老化风险（独有）**：ALPHA_CLIP 冻结了游戏某版镂空 PS。它依赖三样继承物——原生 body
   VS 的输出插值布局、cb0–cb3 寄存器语义（哪个是灯光/阴影矩阵）、贴图槽语义。**只要游戏改的是
   渲染管线本身**（body VS 签名变、常量缓冲重排、贴图槽换位），这份冻结拷贝就读到错位数据 →
   颜色/打光不对甚至几何错乱，而且**不报错，是「画出来不对」的静默故障**。hash 变只是这种底层
   改动的信号。（反之：游戏只出新衣服/角色，管线不动 hash 不变，拷贝永远有效；核心渲染 shader
   通常几个月才动一次。）不透明件没有此风险——它不供 PS，跑游戏当前 shader 自动跟版本。
3. **维护成本**：同时养三条路径（含两份会老化的自写/冻结 shader）不划算。抓帧确认 `m_bdyco`
   就是「同一 body mesh 的第二材质段」，游戏已经为它备好角色专属 shader/state/贴图上下文，
   借用它比自造延迟透明更稳、更贴原版。决定收敛到原生 co 一条。

## 4. 现方案 NATIVE_CO 的效果

**机制**：不是 `CustomShader`，是 `TextureOverride`，hook 游戏自己那条第二材质段 draw
（`hash=<ibHash>` + `match_first_index=<第二段 firstIndex>`，fktn 为 `625a05af` + `69534`）。
**既不声明 `vs=` 也不声明 `ps=`**，只把 IB/VB（蒙皮后）和 ps-t0/t1/t2 贴图换成我们的，
`handling=skip` 跳过原 draw、用 `drawindexed` 画自定义第二段。co draw 自带
`RecoverMatrices+SkinCustom`，绕开「第二段在主体之前画」的时序依赖。

**效果与代价**：
- 跑的是**游戏当前版本的 VS+PS**，所以打光/toon/透明手法与原版一致，且**自动跟版本走、无冻结
  老化风险**（与不透明件同级）。这是相对 ALPHA_CLIP 的最大改进。
- 残留耦合只剩**匹配条件**：IB hash、`match_first_index`、body 的多个 VS hash（fktn 为 5 个，
  须全部 `checktextureoverride=ib`）。游戏重构 body mesh 才会失配 → 露原版 co 几何，这是**看得见
  的失败**，不是静默画错；且不透明段有同样的匹配依赖。
- 贴图槽语义从**每次抓帧的 texture_map 提取**，不写死代码，跟 profile 走。
- 前置条件：profile 必须来自含 secondary material section 的抓帧；否则导出报错，需把该材质槽
  改回不透明或重抓。

**抓帧验证**（`FrameAnalysis-2026-06-30-045108` + `mdl_chr_fktn-cstm-0001_body`）：第二段
(000003) 与主 body (000006) 共用 VB0=`deccfd71`/VB1=`daa6a018`/IB=`625a05af`，仅 submesh
范围不同（主体 first=0/count=69534，第二段 first=69534/count=4932）。body 一帧被 5 个 VS pass
绘制，第二段出现在其中 4 个。详见 [`../transparent-material-status.md`](../transparent-material-status.md) §−1。

**已知遗留疑点**：脚尖阴影对不上，疑似阴影 pass（VS `436f9c16`/`221c5733`）里第二段几何/alpha
投影与原版不一致，需对 000003/000006 的深度 RT 单独复核——非 NATIVE_CO 主结构问题。

## 5. 真失效时怎么救（若日后想重建镂空）

- 重抓一帧找到新的镂空 PS hash，把其 `-ps_replace.txt` 重新拷成 `GMINativeClip.hlsl`；
- 或导出时用 `shadercache_dir` 指向本机 `ShaderCache`，自动取当前版本 PS；
- 仓库历史里（本删除提交之前）有 `GMIClipMRT.hlsl`（自写、更新免疫但打光是简化版）可作降级开关。
- 这些代码均可从删除提交的父提交检出。
