# Blender + Unity 两下点击的 mod 工作流

作者只开 Blender。Unity 无头跑在后台，不露面。

## 分工

判据是「这一步改的是作者的东西，还是学马的东西」：

| | Blender | Unity（无头） |
|---|---|---|
| 摆 T-pose、权重、贴图、删头 | ✅ 作者看得见 | |
| 骨名映射建议（8 张预设表） | ✅ | 拓扑兜底 |
| 补必需节点、材质语义、顶点 COLOR | | ✅ |
| 摇物几何分类、扭转驱动器 | | ✅ |
| 打 AB 包、体检 | | ✅ |

## 作者的两个按钮

面板：`3D 视图 > 侧边栏(N) > GakumasMI > Unity 路线`

1. **摆 T-pose** —— 按 530 套原版实测的静止姿势摆好并应用为静止姿势
2. **适配检查** —— 人形骨、姿势、材质、孤立装饰骨，每条带下一步
3. **导出 mod** —— 导 FBX + `job.json`，调无头 Unity，回读报告

## 交接格式

`job.json`，除 `kind`/`fbx` 外全部可选，缺省由 Unity 侧自动识别：

```json
{
  "kind": "body",
  "target": "mdl_chr_hmsz-cstm-0059_body",
  "fbx": "…/source.fbx",
  "outputDirectory": "…/out",
  "keepMeshes": ["Body"],
  "materials": [{ "name": "m_bdy", "role": "cloth", "bareSkin": true }],
  "chains":    [{ "root": "Bone_SkirtA01_L", "category": "skirt" }],
  "twist":     [{ "bone": "+UpperArmTwist L A01", "role": "LeftArm_Roll_H" }]
}
```

`chains` / `twist` 是**覆盖**，不是必填——留空就走几何分类和角色认领。

命令行等价：

```bash
Unity.exe -batchmode -quit -nographics -projectPath <SDK> \
  -executeMethod GakumasSdk.ModBuilder.Build -gmiJob job.json
```

产出 `report.json`（`ok` + 一句话一条的 findings）和 `<target>.bundle`。失败时退出码非 0。

## 踩过的三个坑（都已修 + 加闸门）

**① Blender 导出的单位换算写进了节点缩放。** `apply_scale_options` 默认那档把米→厘米写成
`Armature`/`Hips`/`Geo_Body` 上的 ×100 缩放，网格只有 1.6cm 高，bindpose 240/257 根偏、最大 868mm。
导出必须带 `apply_scale_options="FBX_SCALE_UNITS"`。闸门：**蒙皮骨不得带非 1 缩放**
（只判蒙皮骨——AO 代理骨天生带缩放且不变形任何东西，一起判会把真信号埋掉）。

**② T-pose 探针不能写死方向。** FBX 的上轴和左右手性各家不同：这副原神模型在 Blender 的骨架
局部空间是 Y-up 且左右与 Unity 相反，硬编码 `(±1,0,0)` 读出 124.7° 的假偏差。改成**从骨架自己
量一组基**（上＝Hips→Head，左＝Right→LeftUpLeg，前＝叉积），任何导入约定都成立。
另外 `pose_bone.head` 与 `bone.head_local` 同在骨架物体空间，中间**不要乘 matrix_world**——
那里面正好有 FBX 导入留下的 90°，腿会被整整转歪 90°。

**③ 作者列了 `keepMeshes` 就别再按材质名过滤。** 一副 rip 的 "Hair" 图集常常装着整条腿；
作者已经删过头，再按名字猜一次会把所有子网格丢光。

## 三条自动化，都不看名字

**拓扑自动映射**（`gakumas_mi/topology_map.py`）：八张预设表覆盖不到的骨架，用结构认人形骨——
胯 = 挂着两条向下长链的那根，腿 = 向下的两条，脊椎 = 向上的，手臂 = 从胸椎横着分出去的两条，
左右 = 沿左轴的正负，脖子 = 胸椎上朝上**且有子骨**的那根，头 = 直接子骨最多的那根。
**把这副模型全部骨名打乱成 `bone_NNN` 后实测：22 根全对、0 错。**

两处判据踩过坑，都写在代码注释里：① 方向不能用 `bone.tail`——FBX 按原轴导入时叶子骨的 tail
全是同一个默认长度，`Bip001 Neck` 读出来朝下、胸骨读出来朝上 dot=+0.98；② 也不能用「最深链的
终点」——头发往下垂，会把整条脖子滤掉，还会把 Head 认到蝴蝶结上。**一律用子骨的位置量。**

**发型**（`Editor/HairBuilder.cs`，`kind: "hair"`）：原版发型骨架是 `Head_Hair` + 一堆 `*_S` 发丝，
一根人形骨都没有，所以身体那条路整条不成立（不建 Humanoid、不摆 T-pose、不装 IK/Pelvis/胸驱/扭转骨）。
成立的只有发丝摇物和材质。**发型的贴图语义还没在这个 SDK 里验过**，报告里明说，别让它假装成立。

**预览图**（`Editor/PreviewRenderer.cs`）：构建完直接渲正面/侧面两张 PNG 回传，面板画出来。
调 Unity **不能带 `-nographics`**（那连图形设备都不创建），批处理照样无窗口。

## 已知边界

- **形态键**：Blender 不允许在带形态键的网格上应用骨架修改器。学马身体不用形态键（表情走骨），
  「摆 T-pose」会点名要求先删掉这些网格，而不是半途应用。
- **孤立单骨**：层 0 是锚定层，一根骨的飘带在游戏里不会动。检查里报出来，作者各加一根尾骨即可。
- **源模型没有的骨补不出来**：这副 rip 没有大腿扭转骨，`UpLeg_H`/`UpLeg_Roll_H` 两个角色空着，
  大腿内旋会剪切。要修就在 Blender 里加骨。
