# 插件运行时换网格机制(读 ModRuntime.cpp 源码结论)

chinosk6 `gkms-localify-dmm` 插件如何把 mod 网格塞进游戏。理解这个才能懂为什么 bindpose
要转置、为什么共享骨自动 retarget、为什么无损方案要扩这里。权威源码在
`gakumas-mod-runtime/src/runtime/ModRuntime.cpp`。

## 加载链

1. `version.dll`/`xinput1_3.dll` 代理注入 → IL2CPP runtime。
2. 扫 `gakumas-local/local-files/mods/<id>/mod.json`,注册替换规则(bundle 懒加载)。
3. Hook AssetBundle 加载,命中原始资源名(如 `mdl_chr_hmsz-cstm-0000_body`)→ 加载 mod prefab。
4. 配对 renderer(targetRenderer↔modRenderer,按名),对每对做换网格。

## 换网格核心(`PatchModMeshSkinningToOriginalOrder`,~L1142)

**关键:插件把补好的 mod 网格 `set_sharedMesh` 塞回原(学马活体)renderer**
(`SkinnedMeshRenderer_set_sharedMesh(pair.originalRenderer, clonedModMesh)`,~L1798)。
原 renderer 保留**学马活体 bones[]**(被学马动画驱动)。

流程:
1. `CloneUnityObject`:clone mod 网格(顶点/**colors32**/UV 全保留,不动)。
2. `TransformModMeshVerticesToOriginalRendererSpace`:把 mod 顶点变换到原 renderer 空间
   (处理 renderer transform 偏移)。
3. `PatchModMeshSkinningToOriginalOrder`:
   - `BuildBoneNameIndexMap(originalBones)`:学马活体骨 名→索引。
   - 遍历 mod bones,按名找学马骨:`modToOriginalBoneIndex[i] = 学马索引 或 -1`。
   - **没找到的 → fallback 到 Hips**(`fallbackBoneIndex`)。← **这就是有损的根源**。
   - 重排权重索引到学马骨序;归一化;`droppedInfluences`/`fallbackVertices` 统计。
   - **bindpose**:当 `originalRoot名==modRoot名`(都是 Hips)→ `useModBindposes`:
     `remappedBindposes[origIdx] = modBindpose[i] × bindposeSpaceAdjustment`。
     即**用 mod(IP)自己的 bindpose**,乘一个 renderer 空间校正矩阵。
   - `SetMeshBindposes` + `SetMeshBoneWeights`(不动顶点/颜色)。
4. `set_sharedMesh(原 renderer, 补好的网格)` + 贴图/材质覆盖。

## 三条由此推出的关键事实

### A. 为什么 bindpose 要转置、且必须正确
运行时 `useModBindposes` 直接用 mod 网格的 bindpose 参与蒙皮:
`skinnedV = Σ wᵢ · 学马活体骨ᵢ · IP_bindposeᵢ · v`。
IP_bindpose 若转置/非法 → 整个蒙皮爆炸(incident §3)。**bindpose 正确性由我方 bundle 保证**,
插件不修。

### B. 为什么共享骨自动 retarget 到学马体型
`学马活体骨ᵢ × IP_bindposeᵢ`:IP 顶点在 IP bind 空间,被学马活体骨驱动。因为 root 名相同
(Hips)走 useModBindposes,IP 与学马同 QualiArts 骨架,该乘积把 IP 网格自动重定向到学马比例。
**这就是为什么不需要 Blender 预烘对齐**。

### C. 为什么 reparent 有损、无损方案要扩这里
学马 renderer 的 `bones[]` 固定 146 根,**没有 IP 专属骨的槽位**。插件当前"没同名就 fallback
Hips"→ 专属骨信息丢失。无损方案(`lossless-full-skeleton-plan.md`)改这里:**没同名就
`il2cpp GameObject.new` 建 Transform、SetParent 到学马父骨、写 IP localTRS、塞进 bones[]**,
并保持 IP 原始 bindpose/权重不改。这是对本函数的增量分支,不是重写。

## 我方网格不碰的字段(所以要在 bundle 里就正确)

插件 clone 后**不动**:顶点、法线、切线、UV、**colors32(描边)**、submesh、材质槽结构。
→ 这些必须在 JSON→Mesh 导入器阶段就正确(COLOR 描边、bindpose 转置、UV)。
插件**会改**:bindpose(乘空间校正)、boneWeights(remap 骨序)、贴图(按 mod.json 覆盖)。

## 贴图覆盖

`ApplyMaterialTextureReplacements`:按 mod.json 的 rendererName+materialSlot+property 从 bundle
加载 Texture2D 覆盖。`replaceMaterials=false` 时复用学马原材质只换贴图(_BaseMap/_DefMap/_ShadeMap)。
材质槽数不足时(学马单材质 vs mod 双 submesh)slot1 覆盖可能不生效——native-co 小件的已知限制。

## 诊断日志(mod-plugin.log)

`[ModAsset] Patched mod mesh skinning ... matchedBones=90 droppedInfluences=0 fallbackVertices=0
bindposeMode=mod-remapped originalRoot="Hips" modRoot="Hips"` +
`Weighted bone diagnostics ... modTop=[...] originalTop=[...]`(两者一致=权重落对骨)。
几何炸但这些行正常 → bindpose/坐标问题,不是骨映射。
