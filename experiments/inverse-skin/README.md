# 逆蒙皮 GPU 算子（3DMigoto 路线，已退役）

3DMigoto 逆蒙皮路线的两个 compute shader。该路线已于 0.9.0 从插件整体移除
（见 [`../../CHANGELOG.md`](../../CHANGELOG.md)），这里作为已验证探索保留，**不再随插件发布**。

| 文件 | 作用 |
|---|---|
| `RecoverMatricesCS.hlsl` | 从每帧已蒙皮的 `VB0` 反解出 152 个骨骼矩阵 |
| `SkinSourceCS.hlsl` | 用反解出的矩阵把作者网格重蒙皮回游戏的顶点格式 |

数学依据与实机误差（动态 `VB0` 逐字节对照，RMS ≈ 1e-6）见
[`../../research/inverse-skin-matrix-recovery.md`](../../research/retired-routes.md)。

## 为什么退役

AB 路线把作者网格作为真正的 Unity 资产交给引擎原生蒙皮，**保留作者自带的权重**；
逆蒙皮路线必须先传权，两者并存会让作者用猜的权重盖掉手刷的权重。

3DMigoto 本身仍然保留——做配置档必须用它抓帧，只是不再走注入与重蒙皮。

## 变体说明

插件里曾另有一份 `RecoverMatricesCS.hlsl`（`t0` 声明为 `StructuredBuffer<uint>`
而非这里的 `Buffer<uint>`）与配套的 `SkinCustomCS.hlsl`，随路线移除一并删除，
需要时从 git 历史取。
