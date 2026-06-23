# 由 CPU 蒙皮最终 VB 恢复骨骼矩阵

日期：2026-06-22

## 结论

学马仕 Body 的最终 40-byte VB0 虽然不携带 Bone Index/Weight，Draw 的
CB/SRV 中也没有骨骼矩阵，但它是标准线性蒙皮结果。利用 AssetStudio 导出的
Bind Pose 顶点和四权重，可以构造固定设计矩阵，并由每帧最终动画 VB 反解
152 个 4x3 有效蒙皮矩阵。

这条路线只依赖 Blender 导出数据、3Dmigoto 能读取的动态 VB 和两个 D3D11
Compute Shader，不需要 AssetBundle、Unity 编辑器或进程内 Runtime。

## 已验证数据

- Profile：`hski-cstm-0000`
- Body IB：`4d5dfe7b`
- 动态 VB0：`e189fd22`
- 顶点：17,615
- 加权骨骼：152（当前 Mesh 实际使用 147）
- 每顶点影响：4
- 动态 VB stride：40（Position/Normal/Tangent）
- 主绘制、阴影和描边三个 Draw 的 VB0 SHA-256 完全相同：
  `8FF8E93FC22797EF5C8F69732E95EF0AF9FD74E32A6CF747D7DCD2E908A4173E`

## 数学模型

对源顶点 `p_i` 和已知权重 `w_ib`：

```text
posed_i = sum_b(w_ib * [p_i.x p_i.y p_i.z 1] * M_b)
```

把 152 个 `M_b` 的四行排成系数矩阵，可写为：

```text
Y = A * M
M = P * Y
P = (A^T A + lambda I)^-1 A^T
```

`A`、`P` 仅依赖 Profile，离线生成一次；每帧 GPU 只计算 `P * Y`。

冻结参数：`lambda scale = 1e-10`。R32_FLOAT 逆算子为 42,839,680 bytes；
R16_FLOAT 会产生约 `0.002`–`0.003` RMS 位置误差，已排除。

## 离线验收结果

20% 顶点留出拟合：

- Position RMS：`1.47e-5`
- Position P95：`1.08e-5`
- Normal P95：`0.076 deg`
- Tangent P95：`0.073 deg`

冻结参数下，按真实 HLSL 256-lane 顺序累加和树形归约模拟：

- Position RMS：`1.39e-6`
- Position P95：`2.26e-6`
- Position Max：`1.80e-5`
- Normal P95：`0.0198 deg`
- Tangent P95：`0.0198 deg`

两个 Shader 已由 Windows SDK FXC 以 `cs_5_0` 成功编译：

- `experiments/inverse-skin/RecoverMatricesCS.hlsl`
- `experiments/inverse-skin/SkinSourceCS.hlsl`

## 可观测性限制

设计矩阵 588 个活跃列的数值秩为 585。唯一严重不可辨识的骨骼是
`RightFrontRibbon1_S`（weighted index 114）：它只影响 3 个源顶点，总权重
0.048。该骨骼必须在 Profile 中标记为不可供 Mod 新增权重使用，并回退到
父级/邻近可观测骨。其余活跃骨在 24 组合成刚体姿势中的矩阵误差 P95 为
`6.1e-5` 量级。

## 目标模型检查

`mdl_chr_ttmr-cstm-0119_body` 有 10,383 顶点、123 个权重组、最多 8 个影响。
其中 74 个组与当前 HSKI Profile 精确匹配，49 个是 TTMR 服装专属骨；当前
HSKI Profile 仅覆盖目标总权重约 75.7%，且 1,486 个目标顶点完全依赖 TTMR
专属骨骼。

因此首个游戏内闭环必须使用原 HSKI Body 做“恢复后再蒙皮”同形验证。
TTMR 模型最终应在其自身角色/服装场景抓取并生成 `ttmr-cstm-0119` Profile，
不能用 HSKI Profile 的裙摆结果判断算法成败。

## 游戏内验收顺序

1. 默认关闭实验，F10 后原画面必须不变。
2. 开启实验，Compute 恢复矩阵并重新蒙皮原 HSKI Body；视觉应不变。
3. 对重新蒙皮后的 VB0 做 Frame Analysis。
4. 离线比较新抓取 VB0 与游戏原动态 VB0。
5. 通过后才把同一矩阵流接到 Blender 导出的自定义顶点/权重。

## 游戏内闭环验收（2026-06-22）

抓帧：`D:\Games\gakumas\FrameAnalysis-2026-06-22-105210`。

- 动态 VB 通过显式 `StructuredBuffer<uint>`（176,150 elements，stride 4）读取。
- 逆算子视图：10,709,920 个 R32_FLOAT，抽样与磁盘文件逐位一致。
- GPU 恢复矩阵与同帧 CPU/HLSL 顺序模拟：RMS `1.55e-6`，P95 `9.54e-7`，Max `6.10e-5`。
- GPU 重建位置与游戏原动态 VB：RMS `1.14e-6`，P95 `2.18e-6`，Max `1.73e-5`。
- Compute 输出和最终 IA VB 逐字节一致。
- 开启/关闭实验的游戏画面视觉一致。

结论：不依赖 AssetBundle、Unity Runtime 或原始骨骼常量缓冲，已能从最终
CPU-skinned Body VB 在 GPU 上恢复当前姿势矩阵，并用其正确驱动同源 bind mesh。
下一阶段是把 `SkinSourceCS` 的固定 HSKI bind mesh 替换为 Blender 导出的
任意拓扑顶点、权重与索引缓冲。

## 任意拓扑与作者流程更新（2026-06-22 晚）

上述“下一阶段”已经完成技术验证：TTMR 测试 FBX 展开为 37,761 个 GPU 顶点后，
可由恢复矩阵驱动并替换 HSKI Body。由此确认任意拓扑 GPU 路线成立。

同时确认，恢复矩阵只定义 HSKI Profile 的动画空间，不会自动让 TTMR 骨架权重
兼容 HSKI。正确作者流程是先在 Blender 中将衣服蒙皮到 HSKI 参考骨架，再导出
HSKI 骨骼编号。当前最近表面权重传递能稳定驱动衣服主体，但手指串权重、颈部
几何缺失和材质 t1/t4 语义仍未解决。

失败的运行时骨名映射、bind correction、同名权重混合和手指语义最近点实验均不
进入正式架构。最新状态和后续计划见
[current-status-and-roadmap.md](current-status-and-roadmap.md)。
