# 2026-06-28 透明材质抓帧记录

来源抓帧：

- `D:\Games\gakumas\FrameAnalysis-2026-06-28-082021`
- profile：`D:\Games\gakumas\FrameAnalysis-2026-06-28-082021\GakumasMI-profile`
- 目标：`ttmr / cstm-0136 / mdl_chr_ttmr-cstm-0136_body`

## 主身体材质不读取 baseColor alpha

profile 中主身体 draw 为 `000191`：

- `body.baseColor`: `000191-ps-t0=42394864...dds`
- 格式：`BC7_UNORM_SRGB`
- 像素 shader：`cf02c2d50d3f2230`

该 shader 对 `t0` 的基础色采样只读取 RGB：

```hlsl
r6.xyz = t0.SampleBias(s1_s, v0.xy, r0.w).xyz;
```

最终输出 alpha 写死为 1：

```hlsl
o0.w = 1;
```

结论：主身体材质的 `body.baseColor` 即使是 RGBA DDS，A 通道也不会自动让模型透明。透明效果必须走单独的透明 pass 或原版透明 shader。

## 透明 pass 的实际 alpha 处理

`000310` 是透明/遮罩相关 draw：

- `ps-t0`: `A8_UNORM`
- 像素 shader：`0186d4c1702ef7a0`

该 shader 会读取 alpha/mask 并执行 discard：

```hlsl
r0.xyzw = t0.Sample(s2_s, v2.xy).xyzw;
if (r0.x != 0) discard;
```

反汇编里能看到 `discard_nz`。这说明原版对硬镂空区域会真正丢弃像素，而不是仅输出 `alpha=0`。

`000335` 之后的透明/合成 draw 会绑定屏幕颜色和深度：

- `ps-t0`: `BC7_UNORM_SRGB`
- `ps-t1`: `R8G8B8A8_TYPELESS`, `shader_resource render_target`
- `ps-t3`: `R16G16_TYPELESS`, `shader_resource render_target`
- `ps-t4`: `R32G8X24_TYPELESS`, `shader_resource depth_stencil`

这类 pass 不是单张 RGBA 贴图直接输出，而是会参考已渲染颜色/深度进行合成。

## 半透明 shader 使用预乘 alpha

多个透明 shader 的输出形式都是预乘 alpha，而不是 straight alpha：

`b9ff5b23549943cd` / `f15da1dcea6644dc`：

```hlsl
o0.xyz = r0.xyz * r0.www;
o0.w = r0.w;
```

`0197209b8f429444` 会先读取屏幕颜色，再把透明颜色按 alpha 混入：

```hlsl
o0.w = r0.w;
o0.xyz = r1.xyz * r0.www + r0.xyz;
```

结论：插件自定义透明 pass 不能简单使用 `output = rgba` + `SRC_ALPHA/INV_SRC_ALPHA` 作为最终模型。更接近原版的基础方案是：

```hlsl
float4 color = baseColor.Sample(sampler, uv);
clip(color.a - epsilon);
color.rgb *= color.a;
output = color;
```

并使用预乘 alpha blend：

```ini
blend = ADD ONE INV_SRC_ALPHA
```

## 插件实现原则

- 主 body draw 继续绘制不透明材质段。
- 透明材质段从主 body draw 中排除，交给 `CustomShader...InheritMaskN` + `CustomShader...AlphaBlendN` 两段绘制。
- `InheritMaskN` 只测深度、不写深度：`depth_write_mask=zero`、`depth_func=greater_equal`。目标是保留反向 Z 遮挡和投影/轮廓效果，同时避免 A=0 padding 写深度后产生 AO 暗带。
- `AlphaBlendN` 使用 MRT 版 `GMIFinal.hlsl`：`o0` 写运动/深度/ID，`o1` 写预乘颜色；RT1 使用 `ADD ONE INV_SRC_ALPHA`。
- `ALPHA_BLEND` / `ALPHA_CLIP` 在当前插件里都归入这条保守透明路径；插件优先保证 A=0 干净和贴体投影，半透明只保证在同模型已有 coverage 的像素上可靠显示。
- 真正伸出角色轮廓外的前向半透明仍未作为默认导出实现；全局前向 shader hook 已实测会污染场景/UI，必须等角色专属窄触发点确认后再启用。
- DDS 格式不是核心问题。抓帧里主 baseColor 多为 `BC7_UNORM_SRGB`，但 3Dmigoto 也能加载 `R8G8B8A8_UNORM_SRGB`。关键是当前 pass 的 shader 是否读取 alpha，以及 blend 是否匹配预乘 alpha。
