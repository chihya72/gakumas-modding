# 透明材质：当前状态与结论

更新：2026-07-13

> 镂空/cutout（原生 `m_bdyco`/`NATIVE_CO`）已验证完成；玻璃/薄纱级连续半透明
> 不在当前支持范围。

## 0. 唯一当前路线

透明/镂空材质当前只保留一条正式路线：

**借用游戏原生 `m_bdyco` 第二材质段。**

插件层面的材质模式只应保留：

| 模式 | 含义 |
|---|---|
| `OPAQUE` | 使用主 body 材质段 `m_bdy` |
| `NATIVE_CO` | 使用游戏原生第二材质段 `m_bdyco` |

自建 `ALPHA_CLIP`、自建 `ALPHA_BLEND`、运行时模拟 cutout 材质、几何侧 alpha 裁切都不作为当前方案。

## 1. 关键事实

`fktn-cstm-001` 证明游戏的 body 透明/镂空不是“主材质读 baseColor alpha”，而是：

- 同一个 `Geo_Body`；
- 同一套 body IB/VB；
- 两个材质段；
- `m_bdy` 绘制不透明主体；
- `m_bdyco` 绘制第二 submesh/index range；
- `m_bdyco` 使用自己的 base/def/shade 贴图，其中 base 是 `*_bdyco_col_alp`。

资产侧：

| Material | `_BaseMap` | 关键状态 |
|---|---|---|
| `m_bdy` | `t_chr_fktn-cstm-0001_bdy_col` | `_ShaderType=0`, `_Cull=2` |
| `m_bdyco` | `t_chr_fktn-cstm-0001_bdyco_col_alp` | `_ShaderType=1`, `_Cull=0` |

抓帧侧：

- 主 body 与 body-co 使用同一 IB/VB。
- body-co 是独立 `firstIndex / indexCount` 的 material section。
- body-co 绑定独立贴图槽，使用游戏原生 co shader/state。
- 导出时 `m_bdy` 的基础色 t0 与 `m_bdyco` 的透明材质 t0 必须分开绑定；两者各走各自 UV，
  不能用主 `m_bdy` baseColor 回退填充 `m_bdyco`。

结论：

**透明效果来自游戏原生 `m_bdyco` 材质段，而不是 `m_bdy` 上的 alpha。**

## 2. 正式 3DMigoto 实现（已验证成功）

3DMigoto 正式路线已经采用并验证了这套 `m_bdyco` 实现，效果正常：

1. Profile 提取阶段记录同一 body IB/VB 下的全部 material sections。
2. 对含 `m_bdyco` 的服装，记录 co section 的 `firstIndex`、`indexCount`、draw、VS/PS、贴图槽。
3. Blender 材质标为 `NATIVE_CO` 时，把该材质段导出到原生 co section。
4. `mod.ini` 在 co section 上使用 `match_first_index`，并绑定该段自己的 `ps-t0/t1/t4`。
5. co draw 必须同样能获得当前帧蒙皮结果；不能只依赖主 body draw 的时序。

这个路线的核心价值是：**保留游戏当前版本的原生 shader/state/draw 上下文**。这样透明行为、描边、
投影和遮挡更接近原版，也避免自写 shader 随游戏更新老化。

## 3. `m_bdyco` alpha 行为实测：cutout 而非连续半透明

后续用 `dress_2271` 的 atlas 做了中间 alpha 实机验证：

- 原始透明 padding 区域叠加从上到下的渐变 A 通道后，部分像素已不再是 `A=0`，例如约
  `A=65/255`、`A=80/255`、`A=84/255`。
- 这些低 alpha 区域在游戏里仍然完全透明，说明 `m_bdyco` 不是按 `A>0` 即绘制。
- 把低 alpha 测试性抬到 `A=128/255` 后，原本透明 padding 整块通过并显示为黑块。

结论：

**当前已验证的 body `m_bdyco` 路线更接近 alpha test/cutout：低于阈值的像素 discard，
高于阈值的像素按其 RGB 绘制；不能把中间 alpha 当作真正的连续半透明混合。**

这也解释了为什么把透明 padding 的 alpha 抬高后会出现黑块：该区域的 RGB 本来就是黑色；
`A=128` 只让像素通过裁切，并不会让它按 50% 透明与背景混合。

因此当前结论需要更精确地表述为：`NATIVE_CO / m_bdyco` 是正式的 body 透明/镂空路线，
但已实测更适合 **镂空/cutout**，不能保证薄纱、玻璃等真半透明效果。游戏管线中可能存在其它
前向/合成透明 draw，但尚未找到可安全复用为角色 body 材质的专属路线。

## 4. IL2CPP 实验反证

PC IL2CPP `.gmim` 实验进一步验证了同一结论。

失败现象：

- `yuika_atlas.png` 本身确实有 alpha。
- 只把它塞到 `m_bdy._BaseMap` 时，透明区显示黑底。
- 原因是 `m_bdy` 的 shader 路径没有按 `_BaseMap.a` discard。

成功条件：

```text
sharedMaterials[0] = m_bdy
sharedMaterials[1] = m_bdyco
opaque submesh -> m_bdy
native-co submesh -> m_bdyco
atlasBase=1
atlasCutout=1
```

实机日志确认：

```text
[mesh] using Geo_Body material slot[0]=... name='m_bdy (Instance)' (opaque m_bdy)
[mesh] using Geo_Body material slot[1]=... name='m_bdyco (Instance)' (real m_bdyco)
[mesh] build sharedMaterials: 2 -> 11 (... cutoutSubs=6 atlasBase=1 atlasCutout=1)
```

这说明 IL2CPP 支线的结果与 3DMigoto 已验证成功的正式路线一致：
**透明必须走原生 `m_bdyco`**。

## 5. 已排除路线

| 路线 | 结果 | 结论 |
|---|---|---|
| 主 body `m_bdy` 直接使用带 alpha 的 baseColor | 透明区域显示黑底 | `m_bdy` 不按 alpha 透明 |
| 将 `m_bdyco` 当作连续半透明 blend 使用 | 中间 alpha 低值被裁切；抬高到 128 后 padding 以黑块显示 | `m_bdyco` 当前更接近 cutout，不是真半透明 |
| 自写 `ALPHA_CLIP` pass | 与游戏原生状态不一致，维护成本高 | 已移除 |
| 自写 `ALPHA_BLEND` pass | 延迟合成 coverage 与背景半透明冲突 | 已移除 |
| 全局前向透明 shader hook | 污染 UI/场景透明 draw | 不可作为默认方案 |
| 运行时手动模拟 `m_bdyco` 状态 | 透明行为不等价 | 不可行 |
| 几何侧 alpha 裁切 | 破坏几何，只能处理局部全透明三角 | 不可作为透明方案 |

## 6. 当前约束

- 没有原生 `m_bdyco` section 的 profile，不能导出 `NATIVE_CO` 材质。
- 若作者需要透明/镂空，应使用包含 body-co section 的服装生成配置档。
- 若目标服装没有 `m_bdyco`，该材质必须改回 `OPAQUE`，或更换/重建 profile。
- 只要有材质槽设为 `NATIVE_CO`，就必须提供单独的 `m_bdyco` t0；缺失时应停止导出，
  不能回退到 `m_bdy` 的基础色 t0。
- `m_bdyco` 当前按 cutout 使用最可靠；不要把中间 alpha 视作可连续混合的半透明。

最终原则：

**不要自造透明；body 镂空/cutout 复用游戏已经存在的 `m_bdyco`。**
