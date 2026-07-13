# Blender 步骤③：Hair / HairProp 贴图改进方案

更新：2026-07-14 · 状态：**0.7.8 已修正 t0.A 默认策略；HHL / HairProp 多 section 待后续证据**

> 重要校正：`ceshi` 与可正常显示眉眼的 `hmsz.hair23.madoka-complete` 对比证明，Hair
> `t0.A=0` 会关闭刘海覆盖，导致眉毛和眼睛无法透出。本文原先把“默认清零”当成通用安全方案，
> 该结论不再成立。步骤③字段、路径和作者准备要求以
> [`step3-texture-input-guide.md`](step3-texture-input-guide.md) 为准；0.7.8 默认已改为保留作者 Alpha。

本文把 [`hair-shader-analysis.md`](hair-shader-analysis.md) 的逆向结论转换为 Blender 插件
步骤③的最小产品改动。原则是保留已经稳定的三图流程，只修正错误默认值，并把真正缺失的
HHL 作为成对的高级功能；不把 t0–t7 全部暴露给作者。

## 1. 目标界面

```text
发型基础材质（默认安全）
├─ 基础色 t0 / BaseColor
├─ [x] 使用 t0.A 发丝覆盖率       默认保留作者 Alpha
├─ 混合遮罩 t1 / PackedMask
├─ 暗面颜色 t4 / ShadeColor
└─ 生成安全 t1 + t4 fallback

高级：原生发丝高光 HHL
├─ [ ] 启用 HHL
├─ 发丝高光 t6
└─ t1.A 高光可见性 mask

发饰材质
├─ 发饰 t0（保留 Alpha）
├─ 发饰 t1
├─ 发饰 t4
└─ 提示：渲染方式继承目标 HairProp section
```

## 2. 立即修正现有 t0/t1/t4

当前 UI 中“t1.A 必须 0；t4=基础色×冷阴影乘数”的说明不再成立，应改为：

- t0 RGB 是基础色；t0.A 是发丝 coverage，不是普通透明度。需要眉眼透出的刘海区域必须保留非零 Alpha；
  全图 A=255 只能作为测试或临时方案，不能代替按区域绘制的 coverage mask。
- t1 R/G/B/A 分别是阴影阈值、光滑度、金属度、镜面/间接/HHL 可见性。
- t4 RGB 是独立暗面颜色；t4.A 选择暗面公式分支，不是透明度。
- 未启用 HHL 时，插件将 hair t1.A 安全归零，以屏蔽未替换的原生 t6。
- 自动生成的 hair t4 使用 hmsz 冷阴影乘数，只是缺图 fallback；高保真作者应提供独立 t4。

高级 t1 单通道栏复用现有 `gmi_t1_a_file`，只根据制作目标动态改标签：

- body：`t1.A AO / 间接光可见性`；
- hair：`t1.A HHL / 镜面可见性`；
- hairprop：`t1.A 材质可见性（通常为 0）`。

不增加第二个 A mask 属性。

## 3. hair t0.A 的实际策略

当前三个原版 Hair 样本的 t0.A 为零像素比例分别是 99.214%、97.560%、94.892%，说明 coverage
通常只画在少量发片区域；但 `Hair21_D.png` 这类作者图可能全图 A=255，并且确实可以恢复眉眼透出。

新增一个 hair 专用开关：

```text
使用 t0.A 发丝覆盖率：按作者 Alpha/目标效果决定
```

导出行为：

| 输入 | 默认关闭 | 开启 |
|---|---|---|
| hair PNG | 转 DDS 时强制 A=0 | 默认保留作者 Alpha |
| hair DDS | 不改字节，显示确认 Alpha 的提示 | 原样使用 |
| HairProp PNG/DDS | 始终保留 Alpha | 不适用 |

实现上仍通过 `_png_to_dds(alpha_override=0)` 支持关闭选项后的清零路径；默认不传 override，
保留作者 Alpha。不新建转换器，也不尝试重编码作者提供的 BC7 DDS。

## 4. t6 HHL 必须与 t1.A 成对开放

新增一个路径属性：

```text
gmi_hair_highlight_file  # t6 / hir_hhl，sRGB
```

已有 `gmi_t1_a_file` 继续作为 HHL 可见性 mask。规则如下：

1. 没有启用 HHL：生成的 t1.A 保持 0。
2. 启用 HHL：必须同时提供 t6 和 `gmi_t1_a_file`。
3. 只提供其中之一时阻止导出，避免 t6 完全不可见或旧 HHL 泄漏。
4. t6 与 t0 共用 UV，尺寸按 profile 中 `hair.t6` 的描述符校验。
5. PNG 自动转 sRGB DDS；t1.A 仍按线性数据合入 t1。

现有 profile 已记录 `hair.t6`，无需引入新 schema 或新的纹理语义注册系统。现有 package writer
也能复制任意 profile 纹理资源，只需在运行时材质绑定块增加 HHL 槽位。

### 4.1 布局边界

已有抓帧只证明主布局 A 的 HHL 位于 ps-t6。尚未抓到 hair 布局 B 的对应槽位，因此第一版：

- layout A：绑定自定义 HHL 到 ps-t6；
- layout B/C：不绑定 HHL，继续沿用 t1.A=0 的安全结果；
- 取得一份 layout B hair 抓帧后，再按证据补槽位，不能直接假设为 ps-t7。

这样不会为了高保真功能破坏暗光/未知布局。

## 5. HairProp 不增加假的透明模式

不能照搬 body 的“不透明/原生 co”下拉框。HairProp 的 hair-like、cutout 和 outline pass 由
目标原生 section 决定，改一个 UI 枚举无法创建原本不存在的 shader/state/pass。

当前步骤③只做以下诚实处理：

- HairProp t0 永远保留作者 Alpha。
- UI 提示 cutout 有效区需要 t0.A 大于约 0.33，并注意透明区 RGB 外扩。
- hair-like section 的 t0.A 不当作普通透明度；没有特殊 coverage 时可安全为 0。
- 作者 HairProp 继承 profile 主 section 的渲染方式。
- 一个 HairProp 内混合 hair-like 与 cutout 的逐材质支持暂不伪装成已支持。

只有 exporter 能把作者材质槽分别路由到原生 `materialSections` 后，才增加 per-slot
`hair-like / hirco cutout` 选择。届时还必须同步 section 的 firstIndex、pass 序列和 outline
存在性，不能只切换 t0.A。

## 6. 明确不开放的槽位

步骤③不提供以下输入：

| 槽位 | 原因 |
|---|---|
| t2 | 全局 HDR 环境 TextureCube，不是作者资源 |
| t3 | 当前帧动态阴影深度图，不是作者资源 |
| t5 | 原角色 toon ramp，当前继续继承即可 |
| t7 | 可选 RampAdd LUT，需同时解决逐顶点 G低 band，当前无必要 |

不新增材质节点系统、PS hash 白名单或通用 t0–tN 编辑器。

## 7. 最小改动范围

| 文件 | 改动 |
|---|---|
| `gakumas_mi/__init__.py` | 修正说明；增加 t0.A 开关和一个 HHL 路径属性 |
| `gakumas_mi/ui.py` | hair 专用标签、HHL 高级折叠区、HairProp Alpha 提示 |
| `gakumas_mi/operators.py` | PNG Alpha override、HHL 成对校验、传入 `hair.t6` |
| `gakumas_mi/core.py` | layout A 的 ps-t6 绑定；B/C 安全跳过 |
| `tests/material_bake_blender_smoke.py` | 验证默认 hair PNG 输出 A=0 |
| `tests/mod_ini_contract.py` | 验证 HHL 只在 layout A 绑定 ps-t6 |

不改 profile schema、逆蒙皮、权重、描边和包合并架构。

## 8. 实施顺序与完成条件

1. **P0（0.7.7 已完成）：语义与 Alpha 安全**——组件独立烘焙文件；修正文案；默认
   hair PNG 的 t0.A=0；两版 Blender 回归通过。
2. **P1：布局 A HHL**——t6+t1.A 成对校验和绑定；layout B/C 不污染。
3. **P2：补抓 layout B hair**——确认 HHL 物理槽后扩展运行时地标分支。
4. **P3：HairProp 多 section**——只有出现实际需要混合 hair-like/cutout 的作者样本时实施。

完成 P0/P1 即可解决当前步骤③的错误默认值并恢复主场景发丝高光；P2/P3 不应阻塞前两项。
