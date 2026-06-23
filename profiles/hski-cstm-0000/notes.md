# hski / cstm-0000 Profile 研究记录

## 首帧结论

首个 Frame Analysis 抓取成功，目录为：

```text
D:\Games\gakumas\FrameAnalysis-2026-06-21-105931
```

共 388 个 draw、2405 个文件、290,743,345 字节。包含 801 组 `.buf` / `.dsc`，803 个 `.txt`，以及 `log.txt` 和 `ShaderUsage.txt`。

角色主绘制集中在 draw `331–354`。按位置包围盒、顶点规模、脚本资源声明和重复 pass 关系，得到：

| 语义 | IB Hash | VB0 Hash | 顶点数 | 索引数 | 置信度 |
| --- | --- | --- | ---: | ---: | --- |
| Body | `4d5dfe7b` | `e189fd22` | 17,615 | 74,664 | 已验证 |
| Face | `298f5be3` | `8c3cc86d` | 5,227 | 多子网格 | 已验证 |
| Hair Main | `548ce056` | `acf9638c` | 16,345 | 67,410 | 已验证 |
| Hair Accessory | `672c0ca7` | `701768c3` | 1,414 | 4,374 | 已验证 |

Body 的 Y 范围约为 1.32，Face 位于角色头部高度 `1.27–1.48`，两组 Hair 均为以头部局部原点为中心的范围，支持上述语义分类。

## 实机验证

- [x] Body：IB `4d5dfe7b`，成功隐藏；
- [x] Face：IB `298f5be3`，成功隐藏；
- [x] Hair Main：IB `548ce056`，成功隐藏；
- [x] Hair Accessory：IB `672c0ca7`，确认是独立发饰并成功隐藏。

直接声明 Buffer `TextureOverride` 不会自动触发；必须在相关 ShaderOverride 中显式执行 `checktextureoverride = ib`。当前已覆盖阴影、主材质和描边 VS。

第二次定向贴图抓帧完成。Body `ps-t0` 的 `950989c5` 已通过青色换色 PoC 确认为 Base Color；`ps-t1` 为打包数据图，通道语义待拆分；`ps-t4` 高置信度为阴影色图。

Body 索引缓冲替换已实机验证。退化 1,040 个手臂区域三角面后缺面符合预期，角色动画仍正常。当前 Draw 输入的 VB0 是游戏每帧更新的预变形动态缓冲，不包含 Bone Index / Bone Weight；新增带权重顶点仍需继续定位上游 skinning 数据。

已从本机 Octo 缓存中的 Asset ID `A16006` 提取 `mdl_chr_hski-cstm-0000_body.unity3d`。原始 `Geo_Body` 含 17,615 顶点、74,664 索引、152 组 Bind Pose/Bone Hash，以及每顶点四骨骼权重；SkinnedMeshRenderer 层级恢复为 167 个节点。Blender 插件 0.2 已验证能建立 152 根加权骨骼和对应顶点组。

`FrameAnalysis-2026-06-22-025949` 已定向导出 Body Draw 的全部 VS 常量缓冲。`cb0/cb1/cb2/cb3` 分别为 2,576 / 1,024 / 288 / 368 字节；内容对应全局相机/光照、对象变换、材质变换和屏幕投影，均不包含 152 根骨骼矩阵。四权重骨架即便按每骨 3x4 float 存储也至少需要 7,296 字节。整帧仅有 12 次游戏 Compute Dispatch，线程组规模均不匹配 17,615 顶点蒙皮；Body Draw 附近也没有游戏 Compute Dispatch。由此排除 GIMI/WWMI/SRMI 所依赖的 Draw 前 GPU 骨骼矩阵/Compute Skinning 路径。

## 待验证

- 确认 Body skip 后阴影与描边是否同时消失；
- 定位 Face / Hair 各主 pass 的贴图语义；
- 确认动态表情时 Face VB Hash 是否稳定；
- 在相同脚本重进后进行第二次抓帧，核对 Hash 稳定性；
- 已证明可由最终动画 VB0、原 Bind 顶点和四权重反解每帧有效骨骼矩阵；详见
  `research/inverse-skin-matrix-recovery.md`。下一步用两个 3Dmigoto Compute
  Shader 完成“恢复矩阵 → 重新蒙皮原 Body”的游戏内同形闭环。
