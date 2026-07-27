# RC1 验收证据（2026-07-27）

本记录对应发布冻结后的 RC1 候选产物。测试由作者在真实 Blender UI 和游戏内完成；本文件只固化
核包输出、产物 hash、runtime 日志关键行和已报告的画面结果，不把旧协议资产迁移混入 RC1。

## 1. 产物指纹

| 产物 | 路径 | SHA-256 |
|---|---|---|
| Blender 插件 ZIP | `D:\GIT\gakumas-modding\dist\gakumas_mi-0.9.0-code-20260727-151540.zip` | `953917C69A79AB93F526A6D2AAC354C8F6F45256217713AB53CC5B599D2E1037` |
| 游戏侧 DLL | `D:\Games\gakumas\xinput1_3.dll` | `A10EC34756618A4B7DD50AFB591B06412C7A8092478CDD763D8BA621323DD1EA` |
| author bundle | `C:\Users\10725\Desktop\author.hski.my-mod\author.hski.my-mod.bundle` | `0327256FFF8CE5F2B38B3B2C8958C55373F99F9884E8C5D74ECE68255F267703` |
| fuyuko bundle（源输出/部署文件相同） | `C:\Users\10725\Desktop\fuyuko-super\fuyuko-super.bundle` | `35E5F9DD9A03019FFB00500E48ACB3046D9DFDC6EAAF420428170A57A72D85A1` |

## 2. 核包工具

命令：

```text
python tools/verify_ab_package.py C:\Users\10725\Desktop\author.hski.my-mod
python tools/verify_ab_package.py C:\Users\10725\Desktop\fuyuko-super
```

结果：

```text
AB package: PASS
buildId: b01fdd1629112716
files: 6

AB package: PASS
buildId: ea2bbcfb74aca8e6
files: 9
```

## 3. RC1 操作结果

- 用 `gakumas_mi-0.9.0-code-20260727-151540.zip` 全新安装插件，并彻底重启 Blender。
- 真面板完成配置档、骨骼扫描、修改、保存/加载和 AB 导出。
- 故意破坏 `Spine` 承重映射时，闸门拦截并提示 `Spine`；恢复映射后重新导出放行。
- 翻转后的装饰骨默认策略已用于导出。
- author 与 fuyuko 两套当前 Mod 均进游戏测试；作者报告身体动作、手部、裙摆/飘带和肤色未出现本轮链路问题。

## 4. runtime 日志关键结果

日志文件：`D:\Games\gakumas\gakumas-local\mod-plugin.log`

author（MMD 外部源）：

```text
runtimeProtocol=1 buildId=b01fdd1629112716
matchedBones=122 createdBones=0 bones=122 boneWeights=57930
droppedInfluences=0 fallbackVertices=0 meshApplied=1 textureApplied=1 skippedMeshes=0
```

fuyuko（SCSP / QualiArts）：

```text
runtimeProtocol=1 buildId=ea2bbcfb74aca8e6
matchedBones=156 createdBones=26 bones=182 boneWeights=89748
swingPrepared=36 droppedInfluences=0 fallbackVertices=0 meshApplied=1 textureApplied=1 skippedMeshes=0
```

fuyuko 后续重复应用时，已存在的 182 根骨全部匹配，仍为 `meshApplied=1`、`textureApplied=1`、
`skippedMeshes=0`。

## 5. 历史兼容性记录（不属于 RC1 失败）

日志中较早的 fuyuko/atbm 记录出现：

```text
error=runtimeProtocol is required (exporter/runtime mismatch)
meshApplied=0 textureApplied=1 skippedMeshes=1
```

这些记录对应没有 `runtimeProtocol=1` sidecar 的旧资产。新版 DLL 按协议拒绝旧资产是预期行为；
fuyuko 重新导出后已用上面的 `buildId=ea2bbcfb74aca8e6` 成功加载。不要用这些历史记录覆盖最新
RC1 结论，也不要求当前开发线继续重导旧 Mod。

## 6. 当前结论与剩余阻塞

- RC1 的实现、真 UI、闸门、核包、runtime 和两套实机样本已完成；本记录完成后，发布关键 B 项具备 A 级证据。
- 插件仓库 `D:\GIT\git.chinosk6.cn\gkms-localify-dmm` 的提交仍未推送到可访问远端，原因是 HTTPS 认证失败。
- Gate A 下一动作是恢复插件仓库认证并推送现有提交；随后才能合并主仓库和对外分发 ZIP + DLL。
- 逐张表选表仍为非首发阻塞 B；装饰物理“手感完美”仍不是首发条件。
