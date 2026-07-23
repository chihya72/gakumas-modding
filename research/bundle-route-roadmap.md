# bundle 路线图(3Dmigoto 流程 → chinosk6 bundle mod)

> **完整分步路线图(4 Phase,每步带 file:line + 完成判据)已随交接包入本仓**:
> [`../ab-route-handoff/docs/bundle-route-roadmap.md`](../ab-route-handoff/docs/bundle-route-roadmap.md)
> (IP 仓 `06-ab-route-handoff/docs/` 为同源上游)。
>
> 本文件是 gakumas-modding 侧的入口摘要——路线跨两个仓库(GakumasMI 在本仓,打包/插件/模板在 IP handoff 仓),在这里留个指针免得找不到。

## 进度（2026-07-15）
Phase 1、2A、2B 均已实现并验证通过。
- **P1**（`export_bundle_source` 算子）+ **2A**（headless Unity build）：Blender 4.2.7 跑通算子（`tests/blender_smoke.py`，须 `--factory-startup`）、Unity 6000.0.67f1 batchmode 产出合法 bundle。修复了 `core.py` `write_bundle_source` 的 `rootBone` 硬编码（改 `_bundle_root_bone` 按 `rootBonePathId` 权威推导），`tests/test_bundle_source_contract.py` 2 passed。
- **2B**（`tools/patch_unity_bundle.py` UnityPy 模板补丁）：解码 diff 证实与 2A 产物 Mesh（顶点/color32/权重/索引/submesh/bindpose）、6 张贴图、TextAsset **全等价**；`tests/test_unity_bundle_patch.py` 1 passed。

- **P3 完成 + 2B 覆盖面扩展**：908 模板建齐并全 R32，统一存放在 `GakumasModeBundle_0119_Build/AssetBundles/Windows`（build 脚本模板恒 UInt32；`dist/templates` 副本已废弃；`tools/upgrade_template_r32.py` 留作存量补救）。真实 mod（madoka 泳装 body，65796 顶点 / 原 9 材质）走通免 Unity 2B——补了 R32 模板（破 65535 上限）、P1 材质归并 `core.merge_material_groups`（9→1 submesh，按目标 bdy/bdyco 归并+校验）、2B `_tex_key` 属性名归一化。

- **✅ 游戏内验证通过**：madoka body（泳装 v9，65796 顶点/原 9 材质）经免 Unity 2B 链在游戏里渲染正确。修了骨序对齐 bug（[`tools/patch_unity_bundle.py`](../tools/patch_unity_bundle.py) `_reorder_smr_bones`：模板 prefab `m_Bones` 按 sidecar 拓扑序重排）。**免 Unity 2B 链（Blender→R32 模板→UnityPy→游戏）首次端到端贯通。**
- **✅ hair/hairprop 也已游戏内验证**：用 madoka `发型doing.blend` 替换 `mdl_chr_ttmr-hair-0002_hair`，`Geo_Hair`/`Geo_HairProp` 均成功加载，`meshApplied=2`、`textureApplied=2`、`skippedMeshes=0`。颜色问题确认为将 `Hair21_D.png` 同时作为 hair `t0/t1/t4`，已改为 `Hair21_D` / `Hair21_MSK` / `Hair21_SDW`；发饰保持不变。完整记录见 IP 仓 `docs/work-summary-2026-07-15.md` §8.4。

- **✅ 阶段收口（2026-07-24）**：P1 算子（`export_bundle_source` + `_bundle_*` + `merge_material_groups` + `_bundle_root_bone`）正式并入 GakumasMI 插件本体（`core.py`/`operators.py`/`ui.py` 加「导出 bundle 源」按钮，gated 于 `gmi_profile_weights`），连同 2B 工具（`patch_unity_bundle.py` / `build_phase3_templates.py` / `upgrade_template_r32.py`）与测试（契约 + 补丁，4 passed）一并入库。研究阶段到此收口，路线转维护。

**P4（物理骨）2026-07-16 翻案复活**：1 层墙根因经 iOS 无壳二进制逆向确定——`UpdateChainInfo` 沿 `transform.GetChild(0)` 逐级 `GetComponent<ActorSwingDynamicBone>` 建层，不是实例化时绑定。runtime 路线改三点（每骨 AddComponent 真挂组件 / rootBones 只放链根 / 链骨设第一子节点）即可重试，无需 option A。详见 IP 仓 physics-bones-findings.md §9。以下为翻案前记录：

~~runtime 建链只得 1 层。~~option A 探针已证明 bundle 原生
`ActorSwing*` 组件和字段可被 il2cpp 完整反序列化,但四种最小集成路径均未到达层数判定;
最终 live attach 精确命中 hmsz 并补入 `3 bones + 1 chain` 后,原生 `RegisterBones` 因
initializeData 并行表错位抛越界。继续必须前移到 initializeData 构建前/完整合法 prefab 原生
实例化,代价超过该 opt-in 功能收益。**换装主线不受影响;新骨独立物理暂不支持,优先复用 base
骨继承物理。** 完整证据见 IP 仓 [`docs/physics-bones-findings.md`](../../IP/06-ab-route-handoff/docs/physics-bones-findings.md)
§4,时间线见 work-summary §8.9–§8.10。

## 目标
让现有 3Dmigoto/GakumasMI 换装作者，以最小成本产出 `hmsz_0000_ruinurs.bundle` 那样的结果（原生蒙皮 / 正确描边透明 / 专属骨物理），**且开发者侧不装 Unity**。

## 核心架构判断
打包是唯一碰 Unity 的一步 → 压成「工具作者一次性 / 每 body 一次」产模板，开发者只跑 UnityPy 模板补丁。Unity 工程版本 **6000.0.67f1**（bundle 头写死，必须匹配游戏运行时）。

## 三个决定难度的关键事实（读 `ModRuntime.cpp` 得出）
1. 插件按 **骨名字符串** 认骨，不看 `m_BoneNameHashes` → prefab 骨 Transform 只需名字/顺序对，TRS 无所谓。
2. mesh 落到 **原 renderer**，`replaceMaterials:false` 保留原材质，贴图按 `property` 逐槽换 → bundle 材质是占位。
3. 顶点空间由插件自己修正 → 不用预对齐。

## 四 Phase 摘要
- **P1**（本仓）GakumasMI 加「导出 bundle 源」算子：fork 点 [`gakumas_mi/operators.py:1021`](../gakumas_mi/operators.py)（数据装配处，逆蒙皮之前），出 geojson + bones sidecar + PNG + mod.json。geojson 字段名须对齐 IP 仓 build 脚本的 `Geo` 类。复用 `_synthesize_export_native_colors`（operators.py:701）、`_synthesize_skeleton_from_mesh`（core.py:1254）；泛化 [`ai-model-workspace/rui-nurs-hmsz-0000/scripts/process_geo_body.py`](../ai-model-workspace/rui-nurs-hmsz-0000/scripts/process_geo_body.py) 后删硬编码。
- **P2** 打包：2A headless Unity build（参照系）→ 2B UnityPy 模板补丁（开发者终态，无 Unity）。
- **P3** 全套 template.bundle：每基础 body 一个，用 [`tools/export_all_body_json.py`](../tools/export_all_body_json.py) + 2A 产，打到 `dist/`。同骨架一个模板覆盖该 body 所有服装。
- **P4** 新增物理骨：**✅ 已翻案跑通**（2026-07-16）。1 层墙真因不是集成入口，而是导出侧两处数据缺口：链尾 tip 骨（走 `extraSwingBones` 段）+ 每骨摆动参数（从源 bundle typetree 读出）。补齐后 `UpdateChainInfo` 自己就建对层数，插件手搭 layer 的补丁反成重复已删。翅膀/裙摆/缎带/听诊器实机真摆。详见上文「进度」段与 [`../ab-route-handoff/docs/physics-bones-findings.md`](../ab-route-handoff/docs/physics-bones-findings.md) §9。

## 开发者成本（复述目标）
Blender 前期流程**不变** → 新按钮「导出 bundle 源」→ 跑 UnityPy 补丁脚本（**无 Unity**）→ 装 chinosk6 插件替代 3Dmigoto（一次性）。

## 相关
- **路线选型对比**：[3dmigoto-vs-ab-route.md](3dmigoto-vs-ab-route.md)——两条换装路线（3Dmigoto 逆蒙皮 vs AB bundle 原生）拦截点差异与各自代价。
- 本仓：[research/current-status-and-roadmap.md](current-status-and-roadmap.md)、[research/inverse-skin-matrix-recovery.md](inverse-skin-matrix-recovery.md)
- 弃用：il2cpp-proxy 探针（`experiments/pc-il2cpp-proxy`）已决定不产品化，只把「原生蒙皮 + 复用 bindpose + 带 COLOR」结论并入本路线。
