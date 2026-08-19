# AB Runtime 源骨架代理测试版（2026-08-16）

## 1. 这轮要回答什么

只回答一个问题：

> Runtime 能不能不把同名人形骨直接换成学马骨，而是完整建立一套源骨架，让网格继续使用源权重和源 bindpose？

第一版故意不接动画、不装摇物。进游戏后模型应保持在源包的静止姿势，只随角色整体移动。这样结果很容易解释：

- 模型静止但形体正确：源骨架、源权重、源 bindpose 的闭环成立；下一步才值得做动画桥。
- 一加载就炸开或整体错位：问题在骨架重建、父级坐标或 renderer 空间转换，不应把锅甩给动画。
- 模型形体正确，但材质不理想：不影响本轮骨架结论；材质是另一条问题。

## 2. 已实现的测试 Runtime

改动位于 `gakumas-mod-runtime/src/runtime/ModRuntime.cpp`，正式协议 1 的路径不变。

新增实验协议：

```json
{
  "runtimeProtocol": 2,
  "experimentalSourceProxy": {
    "mode": "rest-only"
  }
}
```

安全边界：

1. 只有 sidecar 明确写协议 2 和 `rest-only` 才进入实验路径。
2. 正式发布版 Runtime 只认协议 1，拿到这个实验包会拒绝，不会静默退回旧的混合骨架路径。
3. 测试 sidecar 可用 `experimental-file:文件名` 从 `mod.json` 同目录读取；只允许单个文件名，不接受绝对路径、子目录或 `..`。
4. 普通协议 1 sidecar 如果误写 `experimentalSourceProxy`，测试 Runtime 也会拒绝。

实验路径的实际行为：

- 为 sidecar 中每一根渲染骨创建独立 Transform；
- 即使骨名能对应学马骨，也不复用学马 Transform；
- 骨对象使用唯一前缀，避免和游戏骨同名搜索串线；
- 按 sidecar 的源局部位置、旋转、缩放重建层级；
- 网格继续使用源 boneWeight 索引和源 bindpose；
- `SkinnedMeshRenderer.rootBone` 改为源代理的 `Hips`；
- 不创建 ActorSwing、姿势驱动器或动画桥；
- 日志统一带 `[ModAsset][EXPERIMENT]`，并明确写出 `animationBridge=0 physics=0`。

## 3. Claymore 测试包

测试包目录：

`D:\GIT\gakumas-modding\mod-workspace\experiments\source-rest-claymore-2026-08-16\runtime-test-package`

生成脚本：

`D:\GIT\gakumas-modding\mod-workspace\experiments\source-rest-claymore-2026-08-16\build_runtime_test_package.py`

它复用了 Unity SDK 已经生成的 `mdl_chr_external_body.bundle`，从其中 `Geo_Body` 的真实 SkinnedMeshRenderer 读取骨数组和静止层级，再生成协议 2 sidecar。

静态核对结果：

| 项目 | 结果 |
|---|---:|
| 顶点 | 9054 |
| 渲染骨 | 225 |
| bindpose | 225 |
| rootBone | Hips |
| 因 renderer 骨数组不含中间父骨而折叠的父级 | 5 |
| 折叠后的最大矩阵剪切残差 | 7.671645142232674e-15 |

最后一项接近浮点数值零，说明这 5 处父级折叠没有引入可见的矩阵误差。

目标资源暂时固定为：

`mdl_chr_atbm-cstm-0140_body`

这是用户明确指定的实机测试服装资源。它只是本轮测试入口，不是为该角色或该来源编写专用生产逻辑。

## 4. 重要限制：这不是原始 A-pose 直驱实验

当前测试包复用的是 Unity SDK 输出包，其中 Claymore 人形骨已经经过 T-pose 烘焙。因此本轮可以验证：

- 源骨架比例能否保留；
- 源权重能否不转移；
- 源 bindpose 和源代理骨能否在游戏 Runtime 中闭合；
- 是否真的不需要逐骨贴到学马骨长和关节位置。

本轮不能验证：

- 原始 A-pose 是否可以直接吃学马 Humanoid 动画；
- 源代理如何逐帧接收学马动作；
- Animator 后处理、表情、摇物之间的最终更新顺序；
- 225 根骨全部参与动画后的性能。

A-pose 问题的结论没有被推翻：只保留源骨架和权重，能解决“网格为什么要贴原版身体”和“为什么要转权重”；它不能自动消除源人形静止姿势与学马 Humanoid 标准姿势之间的旋转差。动画桥仍应以 T-pose 中间状态为基准。

## 5. 构建结果

Runtime：

`D:\GIT\gakumas-modding\gakumas-mod-runtime\dist\gakumas-mod-runtime-source-proxy-rest-test2.zip`

- SHA-256：`BDBCFBF06A97936D1678006FC199B2665CF74D5BA0C0B674C1861AB140B5A48B`
- Release 构建通过；`ModPresentationModelTests`、`ModRuntimeCatalogSmoke` 均通过。

测试 bundle：

- SHA-256：`A3CF8879E9645407ED4037FE434BD95DB6F0D362F1F4E973E8B64412E1F8EDB5`
- sidecar SHA-256：`A97424419400EA08C8853456FA9AEBEA875049C02CB36E5CA0342381470EA601`

## 6. 实机验收顺序

1. 备份游戏目录当前 `xinput1_3.dll` 和 Runtime 配置。
2. 暂停其他命中 `mdl_chr_atbm-cstm-0140_body` 的身体 Mod，避免优先级混淆。
3. 安装测试 Runtime zip。
4. 把 `runtime-test-package` 整个目录作为一个 Mod 放进 Mods 目录。
5. 完全重启游戏；第一版不把热开关作为验收路径。
6. 在游戏里换上 `mdl_chr_atbm-cstm-0140_body` 对应服装，观察 Claymore 身体。
7. 搜索日志：

```text
[ModAsset][EXPERIMENT] Built source proxy REST-ONLY skeleton
[ModAsset][EXPERIMENT] Applied source-proxy rest-only skinning
sourceWeights=1 sourceBindposes=1 animationBridge=0 physics=0
```

正确的第一阶段结果应是：模型形体完整、没有蒙皮爆炸，但身体停在 T-pose，不跟随学马身体动画。这个“不会动”是本版主动关闭动画桥后的预期结果，不是失败。

## 7. 通过后下一步

只有静态闭环通过后，才进入动画桥：

1. 在活体角色克隆完成后重建“学马语义骨 → 源代理骨”的映射；
2. 记录两套骨架的 T-pose 静止矩阵；
3. 在游戏 Animator 和身体修正之后，把学马骨相对静止姿势的变化写到源代理；
4. 再接表情、姿势驱动器和弹簧，逐层验证更新顺序。

这一步不能只找一个普通 `LateUpdate` 就宣布完成；必须用实机日志或反汇编确认写入时机晚于学马 Animator、早于摇物和渲染。
