# 2026-07-01 学马 Mod 材质 / t1 通道排查记录

本文件整理本轮对话中所有与学马 Mod、GakumasMI 插件、`dress_2609_full` 外部衣装材质相关的结论、文件、改动和后续策略。

## 1. 初始现象

用户在导出 mod 后看到衣服和手部附近出现异常彩色阴影 / 色块：

- 手部投影呈绿色。
- 裙子上出现绿色阴影块。
- 另一张图中手部阴影带绿色和蓝色同心圆。
- 即使关闭描边宽度仍存在。
- 使用普通传权后阴影也错。
- 选择“实验：智能传递权重 + 颜色”时尤其容易出现。

当时导出日志里有：

```text
实验智能传权完成；置信 14820/15222，inpaint 402，法线改写 3730；需复核 1206 个顶点，p95 0.0262 m，最大 0.1399 m
```

后续判断：法线朝向本身不是主要问题；异常主要来自材质贴图槽位、`t1` 通道解释，以及后续发现的 `t4/sdw` 语义误判。

## 2. ps-t2 / ps-t4 槽位问题

检查 `C:\Users\10725\Desktop\mltd` 后发现：

- `mod.ini` 原本绑定了 `ps-t2 = ResourceMltdShadecolor`。
- `manifest.json` 里 `body.shadeColor.slot = ps-t2`。
- 实际可见 body pass 里，真正的 `ShadeColor` 是 `ps-t4`。
- `ps-t2` 在可见 pass 里是 64x64 cube / 环境光类资源，不是阴影色图。

已对用户桌面 `mltd` 包做过修正：

```text
C:\Users\10725\Desktop\mltd\mod.ini
  ps-t2 = ResourceMltdShadecolor
  -> ps-t4 = ResourceMltdShadecolor

C:\Users\10725\Desktop\mltd\manifest.json
  body.shadeColor.slot = ps-t2
  -> body.shadeColor.slot = ps-t4
```

插件代码也修正了 texture semantic 映射：

```text
ps-t0 -> baseColor
ps-t1 -> packedMask
ps-t4 -> shadeColor
ps-t5 -> ramp
ps-t7 -> rampAdd
ps-t2 -> t2
ps-t3 -> t3
ps-t6 -> t6
```

关键结论：`ps-t2` 不是当前 body 可见 pass 的 `ShadeColor`，不能再全局映射成 shadeColor。

## 3. 抓帧 / AB 原始数据分析

分析对象：

```text
Frame dump:
D:\Games\gakumas\FrameAnalysis-2026-07-01-033404

AB export:
C:\Users\10725\Desktop\mdl_chr_ttmr-cstm-0119_body
```

AB `Material/m_bdy.json` 有效纹理：

```text
_BaseMap    -> t_chr_ttmr-cstm-0119_bdy_col
_DefMap     -> t_chr_ttmr-cstm-0119_bdy_def
_ShadeMap   -> t_chr_ttmr-cstm-0119_bdy_sdw
_RampMap    -> t_chr_ttmr-base-0000_rmp
_RampAddMap -> t_chr_ttmr-cstm-0119_bdy_rma
```

AB `m_bdyco.json`：

```text
_BaseMap    -> bdyco_col_alp
_DefMap     -> bdyco_def
_ShadeMap   -> bdyco_sdw
_RampMap    -> base-0000_rmp
_RampAddMap -> bdy_rma
```

AB `m_bdytrs.json`：

```text
_BaseMap    -> bdyco_col_alp
_DefMap     -> bdyco_def
_ShadeMap   -> bdyco_sdw
_RampMap    -> base-0000_rmp
_RampAddMap -> null
```

可见 body pass 的高置信贴图槽位：

```text
ps-t0 = baseColor / col
ps-t1 = packedMask / def
ps-t2 = environment cube / t2
ps-t3 = depth-ish / t3
ps-t4 = shadeColor / sdw
ps-t5 = ramp
ps-t6 = 4x4 black
ps-t7 = rampAdd
```

部分非可见 / shadow / depth pass 会出现槽位偏移，例如 shade 可能临时在 `ps-t2`。插件不应从这些 pass 推导用户替换材质槽位，应优先使用可见 representative pass。

## 4. 游戏 `t1 / DefMap / PackedMask` 通道语义

本轮确认并沿用的 `t1` 通道语义：

```text
t1.R = 阴影阈值 / Toon Mask / 进阴影范围
t1.G = 光滑度 / Smoothness
t1.B = 金属度 / Metallic
t1.A = AO / 环境遮蔽 / indirect contribution
```

重要区别：

```text
t1.R 决定哪里进入暗面 / 卡通阴影区
t4 / ShadeMap 的 RGB 是暗面材质颜色，也就是 t0/baseColor 的暗化版
ramp 决定明暗阶调和过渡风格
```

## 4.1 原生 `sdw / t4` 通道补正

用户后续对比原生 `t_chr_ttmr-cstm-0119_bdy_sdw.png`、抓帧 `ps-t4` 与插件生成的 `gmi_baked_shadeColor.dds` 后确认：

```text
原生 sdw.RGB:
  基本是 baseColor / col 的受控暗色版，UV 与 t0 对齐。
  它不是投影阴影本身带图案，而是材质进入暗面时仍需要显示服装自身花纹、布料纹理和颜色。

原生 sdw.A:
  更接近二值材质遮罩。皮肤区域多为 255，衣服/饰品大多为 0；
  不是 0.12、0.20、0.60 这种连续“阴影色强度”。
```

因此此前把 `t4.A` 当成阴影色混合强度是错误的。更准确的材质语义是：

```text
t4.RGB = 从 t0 派生暗色版
t4.A   = 近似二值：皮肤预设 255，非皮肤预设 0
不再提供手动 t4.A 微调；作者只选择材质类型，插件按预设写入二值 A
```

这也解释了为什么原生 `sdw` 明明是彩色却不会怪：它的 RGB 与自己的 baseColor 对齐，等价于“同一件衣服的暗面版本”。真正的投影 / 遮挡阴影仍是标量或 ramp 因子，不携带衣服图案；最终暗部看见图案，是因为暗面材质颜色采样了 `t4.rgb`。

异常情况的判定标准：

```text
正常: t0 与 t4 同一 UV、同一服装内容；t4.rgb 只是 t0.rgb 的暗化/偏色版。
异常: t0 已换成外部衣服，但 t4 仍是原角色/旧服装的 sdw，暗面就会采样到不属于当前衣服的彩色图案。
```

因此外部衣装的阴影图 / Rmask 不能当完整 `t1` 使用，只能进入 `t1.R`。

错误做法：

```text
t1.R = rmask
t1.G = rmask
t1.B = rmask
t1.A = rmask
```

这样会让光滑度、金属度、AO 全被阴影图污染，产生怪反光、脏阴影和彩色块。

正确做法：

```text
先按材质预设生成完整 t1
再只用外部阴影阈值图覆盖 t1.R
t1.G/B/A 继续来自材质预设、原生 def 或 SPmap 辅助估算
```

## 5. 原生 `bdy_def.R` 规律

用户提供：

```text
C:\Users\10725\Desktop\mdl_chr_ttmr-cstm-0119_body\Texture2D\t_chr_ttmr-cstm-0119_bdy_def.png
C:\Users\10725\Desktop\mdl_chr_ttmr-cstm-0119_body\Texture2D\t_chr_ttmr-cstm-0119_bdy_col.png
```

对原生 `bdy_def.R` 的数值统计：

```text
整体中位数: 106
常见亮部: 120-128
暗部 / 褶皱: 0-100
局部暗纹平均: 约 84
局部亮部平均: 约 104
```

结论：

```text
t1.R 低值 = 更容易进入阴影 / 更暗
t1.R 高值 = 更不容易进入阴影 / 更亮
```

所以如果外部 `rmask` 也是“黑=阴影，白=亮部/无阴影”，就不应该反相。

本轮对用户的 `rmask` 判断：不反相。真正需要的是重映射范围，避免 `0..255` 直接塞进游戏 `t1.R`。

推荐初始重映射：

```text
rmask 0..255 -> t1.R 80..128
或
rmask 0..255 -> t1.R 90..135
```

## 6. `dress_2609_full` 解包目录分析

分析目录：

```text
D:\GIT\scsp\dress_2609_full
D:\GIT\scsp\dress_2609_full\textures
```

关键贴图：

```text
Dress_2609_SHYTNY_00_col.png
Acce_02609_SHYTNY_00_col.png
00_bodyskin_00_col.png
Dress_2609_SHYTNY_00_Rmask.png
Acce_02609_SHYTNY_00_Rmask.png
Dress_2609_SHYTNY_00_SPmap.png
Acce_02609_SHYTNY_00_SPmap.png
bodyskin_Skirt_Rmask_c.png
FO_RIM1.png
white.png
dress_2609_full_col_single_atlas_4096_A255.png
dress_2609_full_rmask_atlas_4096_A255.png
```

`dress_2609_full_materials.json` 材质槽：

```text
slot 0: m_bodyskin        -> 00_bodyskin_00_col.png
slot 1: m_dress           -> Dress_2609_SHYTNY_00_col.png
slot 2: m_dress_BS_b      -> Dress_2609_SHYTNY_00_col.png
slot 3: m_headwear        -> Acce_02609_SHYTNY_00_col.png
slot 4: m_headwear_01     -> Acce_02609_SHYTNY_00_col.png
slot 5: m_mizugi_option   -> solid color
slot 6: m_neckless        -> solid color
```

`dress_2609_full_col_single_atlas_4096_A255.png`：

```text
用途: t0 / BaseColor atlas
尺寸: 4096x4096
alpha: 全 255
```

`dress_2609_full_rmask_atlas_4096_A255.png`：

```text
用途: 只可作为 t1.R / Toon Mask 输入
尺寸: 4096x4096
alpha: 全 255
```

`dress_2609_full_rmask_atlas_4096.json` placement：

```text
Dress_2609_SHYTNY_00_Rmask.png -> rect [2048, 0, 2048, 2048]
Acce_02609_SHYTNY_00_Rmask.png -> rect [2560, 2048, 256, 256]
```

这个 atlas 不覆盖 bodyskin 和 solid 材质区域，不能用黑色空白去覆盖皮肤或无贴图材质。

## 7. `dress_2609_full` 贴图应如何进入 GakumasMI

当前推荐：

```text
t0:
  D:\GIT\scsp\dress_2609_full\textures\dress_2609_full_col_single_atlas_4096_A255.png

t1.R:
  使用重映射后的学马规律图

t1.G / t1.B / t1.A:
  先留空，由插件按材质预设生成

t4:
  由插件按 t0 派生；RGB 为暗色版 baseColor，A 按材质写二值遮罩
```

对各材质：

```text
m_dress / m_dress_BS_b:
  t1.R = rmask remap
  t1.G = cloth smoothness，约 0.35-0.45
  t1.B = 0
  t1.A = 默认 AO

m_headwear / m_headwear_01:
  t1.R = rmask remap
  t1.G = accessory / plastic / metal smoothness，约 0.45-0.65
  t1.B = 默认 0，明确金属再提高
  t1.A = 默认 AO

m_bodyskin:
  不使用 rmask atlas 的黑区
  保留 skin 预设

m_mizugi_option / m_neckless:
  没贴图
  保留材质预设
```

## 8. 已为用户生成的重映射 t1.R 图

基于：

```text
D:\GIT\scsp\dress_2609_full\textures\dress_2609_full_rmask_atlas_4096.json
```

生成：

```text
D:\GIT\scsp\dress_2609_full\textures\dress_2609_full_t1R_gakumas_remap_80_128_A255.png
D:\GIT\scsp\dress_2609_full\textures\dress_2609_full_t1R_gakumas_remap_80_128_preview.png
```

生成规则：

```text
不反相
有效 rmask 区域: 0..255 -> 80..128
空白区域: 128
A = 255
```

统计：

```text
Dress_2609_SHYTNY_00_Rmask:
  input  min/mean/max = 0 / 113.85 / 255
  output min/mean/max = 80 / 101.42 / 128

Acce_02609_SHYTNY_00_Rmask:
  input  min/mean/max = 42 / 145.82 / 255
  output min/mean/max = 88 / 107.60 / 128
```

插件里应填写：

```text
t1.R 阴影阈值:
D:\GIT\scsp\dress_2609_full\textures\dress_2609_full_t1R_gakumas_remap_80_128_A255.png

t1.G / t1.B / t1.A:
留空
```

然后执行：

```text
按材质烘焙 t1/t4
```

## 9. 插件功能改动

本轮在 GakumasMI 中新增了 `t1` 四通道输入：

```text
t1.R 阴影阈值
t1.G 光滑度
t1.B 金属度
t1.A AO
```

行为：

```text
四个通道都填:
  直接整图合成完整 t1

只填 1-3 个:
  先按材质预设烘焙 t1
  再只覆盖填写的通道
  对空白 / 无内容材质区域保留预设，不用黑色覆盖
```

新增 / 修改文件：

```text
gakumas_mi/__init__.py
gakumas_mi/core.py
gakumas_mi/operators.py
gakumas_mi/ui.py
tests/material_bake_smoke.py
```

核心函数：

```text
core.apply_packed_mask_channel_overrides(...)
core.packed_mask_channel_label(...)
```

Blender 操作器读取通道图时：

```text
通过 Blender image API 读取 PNG / 图像
转 top-down RGBA8
RGB 转灰度通道
要求尺寸与基础色 atlas 一致
```

UI 位置：

```text
材质模板 -> 分材质烘焙 t1/t4 -> t1 通道输入（可选）
```

## 10. 插件打包

已打包插件：

```text
D:\GIT\gakumas-modding\dist\gakumas_mi-0.7.0-code-20260701-160015.zip
```

说明：

```text
这是代码包，不含大型 Body JSON 资源库。
可直接在 Blender 中安装测试 t1.R/G/B/A 四通道输入功能。
```

## 11. 已运行测试

本轮相关测试均通过：

```text
python tests/material_bake_smoke.py
python tests/mod_ini_contract.py
python tests/frame_profile_extract_smoke.py
python tests/export_buffers_regression.py
```

此前修 `ps-t4` 时也通过：

```text
python tests/frame_profile_extract_smoke.py
python tests/mod_ini_contract.py
```

## 12. 当前最推荐操作流程

对 `dress_2609_full`：

1. 在 Blender 插件材质模板页填写基础色：

```text
D:\GIT\scsp\dress_2609_full\textures\dress_2609_full_col_single_atlas_4096_A255.png
```

2. 在 `t1.R 阴影阈值` 填写：

```text
D:\GIT\scsp\dress_2609_full\textures\dress_2609_full_t1R_gakumas_remap_80_128_A255.png
```

3. `t1.G / t1.B / t1.A` 先留空。

4. 材质槽按大类设置：

```text
皮肤 -> skin
裙子 / 衣服 -> cloth
头饰 -> leather_plastic 或 metal，按实际材质试
```

5. 点击：

```text
按材质烘焙 t1/t4
```

6. 再导出 mod。

如果仍有彩色阴影块，优先调 `t1.R` 的输出范围，而不是反相：

```text
当前: 80..128
可试: 90..135
可试: 100..140
```

## 13. 后续插件建议

后续可继续加入：

```text
t1.R 反相开关
t1.R 输入黑白点 / 输出黑白点
t1.R 输出范围预设:
  原生保守 90..128
  布料明显 80..135
  强阴影 60..140
```

但根据原生 `bdy_def.R` 对比，本轮对 `dress_2609_full` 的首选不是反相，而是重映射。
