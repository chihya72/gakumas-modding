# GakumasMI Blender 插件 1.3.0

面向《学园偶像大师》的作者侧 Blender 插件：导入参考模型、对骨名、准备贴图、导出成品
AssetBundle。**只做 AB（原生蒙皮）路线**，3DMigoto 逆蒙皮的传权与导出已整体移除——作者
模型自带的权重原样保留，插件只把骨名换成游戏骨名，由游戏引擎自己蒙皮，**没有传权这一步**。

面板按五阶段排列：**1 目标与参照 → 2 作者模型 → 3 材质与贴图 → 4 骨架与物理 →
5 检查与导出**。界面一次只显示当前阶段，作者只出
base/mask/shade 三张贴图，**永不碰 PS hash 或寄存器槽位**——AB 路线的贴图由运行时按
`rendererName + materialSlot + property` 语义替换，新场景/服装/角色自动覆盖。

目标环境：Blender 4.2 LTS（4.5 LTS 也有 CI 覆盖）。当前状态：正式稳定版。

## 安装

```text
编辑 > 偏好设置 > 插件 > 从磁盘安装
```

选当前版本的插件 ZIP，启用 **GakumasMI**，面板出现在 `3D 视图 > 右侧边栏（N）> GakumasMI`。

看到旧英文按钮说明装的是旧版：**卸载 → 关闭 Blender → 重开 → 再装新 ZIP**。

打包 bundle 那一步还需要一个**你自己装的 Python 3.10+**（`pip install UnityPy Pillow`），
不能用 Blender 自带的那个。

## 怎么用

逐步操作、每个字段填什么、报错怎么办，都在作者手册里，这里不重复：

| 你要做的事 | 看哪页 |
|---|---|
| 安装插件、资源库、打包器和 Runtime | [1-安装与资源](https://github.com/chihya72/gakumas-modding/blob/main/docs/wiki/1-安装与资源.md) |
| 搞懂配置档、作者模型和骨名映射的边界 | [2-插件负责什么](https://github.com/chihya72/gakumas-modding/blob/main/docs/wiki/2-插件负责什么.md) |
| 跑通第一个 body Mod | [3-快速上手-body](https://github.com/chihya72/gakumas-modding/blob/main/docs/wiki/3-快速上手-body.md) |
| 阶段 1：目标与参照 | [4-阶段1-目标与参照](https://github.com/chihya72/gakumas-modding/blob/main/docs/wiki/4-阶段1-目标与参照.md) |
| 阶段 2：作者模型 | [5-阶段2-作者模型](https://github.com/chihya72/gakumas-modding/blob/main/docs/wiki/5-阶段2-作者模型.md) |
| 阶段 3：材质与贴图 | [6-阶段3-材质与贴图](https://github.com/chihya72/gakumas-modding/blob/main/docs/wiki/6-阶段3-材质与贴图.md) |
| 阶段 4：骨架与物理 | [7-阶段4-骨架与物理](https://github.com/chihya72/gakumas-modding/blob/main/docs/wiki/7-阶段4-骨架与物理.md) |
| 阶段 5：检查与导出 | [8-阶段5-检查与导出](https://github.com/chihya72/gakumas-modding/blob/main/docs/wiki/8-阶段5-检查与导出.md) |
| 发型与配套发饰 | [9-发型与发饰](https://github.com/chihya72/gakumas-modding/blob/main/docs/wiki/9-发型与发饰.md) |
| 镂空与透明路线 | [10-透明材质](https://github.com/chihya72/gakumas-modding/blob/main/docs/wiki/10-透明材质.md) |
| 报错、没描边、颜色错乱 | [11-常见问题与排错](https://github.com/chihya72/gakumas-modding/blob/main/docs/wiki/11-常见问题与排错.md) |
| 从 PMX、FBX、VRM 等外部模型做起 | [12-外部模型转换](https://github.com/chihya72/gakumas-modding/blob/main/docs/wiki/12-外部模型转换.md) |

## 两种 JSON 的区别

面板「网格 JSON 资源库」指向的目录里，每套资源有两个文件，作用不同：

- **原模型 JSON**（`Geo_Body.json` / `Geo_Hair.json`）是**网格数据**：顶点位置、法线、切线、
  UV、顶点色、三角面、逐顶点的骨骼权重索引与权重值、Mesh 自带的 BindPose 数组。
  它回答「这个网格长什么样，每个顶点受哪些骨骼影响」。
- **骨架 JSON**（`*.skeleton.json`）是**骨架语义数据**：骨骼名、父子层级、节点变换，以及
  weighted bone 编号与骨骼名的对应关系。它回答「权重编号到底对应哪根骨头」。

插件导入带权重参考模型时两者都要。骨架 JSON 缺失时（记为 `mesh-only`）会从
`m_BoneNameHashes` + `m_BindPose` 合成骨架，条目仍然可用。它同时是发型描边取色和导出前
绑定体检的数据源。绑定体检量的是 fingers / forearm 的形变比值，**只对 body 跑**——发型、
发饰上没有这些区域，跑了必然“无法评估”，那是假警报。

## 通用性边界

本插件面向**已完成对齐、删头、图集/材质准备且带有效权重**的作者模型，目标是对齐之后的
一键 AB 导出。**不承诺**自动完成任意外部模型的建模对齐、删头、权重修复或图集烘焙——那些
是作者基本功。身体骨名由八家预设和面板映射表兜底，装饰物理按源父骨/语义规则默认处理，
异常件用覆盖表修正。

**装饰物理的当前边界（1.3.0）**：「跟裙摆」（蹭游戏自带裙摆骨）和「刚性跟父骨」
可用；「自建摇物链」已于 2026-08-11 用 `hmsz-fuyuko-icu` 取得第一个画面级成功案例，但
幅度与穿插仍需逐件目视验收。详见
[target-rig 现行架构](https://github.com/chihya72/gakumas-modding/blob/main/research/ab-target-rig-architecture.md)
的「运行时与物理边界」。

成品 `.bundle` + `mod.json` 放进 Mod Runtime 的 `gakumas-mod/mods/<id>/`
（chinosk6 的 `gkms-localify-dmm` 用的是它自己的 `gakumas-local/local-files/mods/<id>/`）。

target-rig 当前边界见
[现行架构](https://github.com/chihya72/gakumas-modding/blob/main/research/ab-target-rig-architecture.md)；
已排除路线与被推翻结论见
[已证伪结论](https://github.com/chihya72/gakumas-modding/blob/main/research/lessons-learned.md)；版本历史见
[CHANGELOG](https://github.com/chihya72/gakumas-modding/blob/main/CHANGELOG.md)；
运行时机制与新增物理骨规范见 [AB 路线笔记](https://github.com/chihya72/gakumas-modding/blob/main/research/ab-route-notes.md)。

## 版本与打包

各版本变更见 [CHANGELOG](https://github.com/chihya72/gakumas-modding/blob/main/CHANGELOG.md)。发布包用
`python tools/package_blender_addon.py` 生成（代码版不含资源库；加 `--with-body-lib`
可一并打包）。本地包不提交到公开仓库。
