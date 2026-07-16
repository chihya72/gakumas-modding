# AB 路线交接包(IP 服装 → 学马,含新骨物理)

把偶像荣耀(或任意来源)的服装 mesh + 贴图 + **完整骨架 + 摆动物理**无损嫁接到学马角色上,
走 chinosk6 `gkms-localify-dmm` 插件的 AB(AssetBundle)路线。

参考实现:`mdl_chr_rui-nurs-00_body`(护士服)→ `mdl_chr_hmsz-cstm-0000_body`。
2026-07-17 实机:换装、蒙皮、描边、翅膀/裙摆/缎带/听诊器摆动全部正常。

> **本包只含代码和文档。** 提取或派生的游戏资产(源 bundle、`rui_bones.json`、
> `rui_Geo_Body.processed.json`、贴图、成品 bundle)按仓库规矩不入公开库 —— 见根 `.gitignore`
> 「Extracted or derived game assets must not be pushed to the public repository」。
> 这些产物由 `scripts/` 在本地重新生成。

## 从哪读起

| 文档 | 权威范围 |
|---|---|
| [`docs/ab-route-pipeline.md`](docs/ab-route-pipeline.md) | **主线**:解包 → 处理 → sidecar → Unity 打包 → 部署的完整管线 |
| [`docs/physics-bones-findings.md`](docs/physics-bones-findings.md) | **新骨物理**:结论、规范、坑。做物理骨先读这份 |
| [`docs/lossless-full-skeleton-plan.md`](docs/lossless-full-skeleton-plan.md) | 为什么 reparent 有损、无损全骨架嫁接的设计依据 |
| [`docs/runtime-mechanism.md`](docs/runtime-mechanism.md) | 插件运行时如何换网格(bindpose 转置、共享骨 retarget 的由来) |
| [`docs/bundle-route-roadmap.md`](docs/bundle-route-roadmap.md) | 让换装作者免 Unity 产出成品的 4-Phase 落地图 |

## 目录

- `scripts/` — 数据侧(UnityPy)。`export_rui_bones.py` 出骨架 sidecar(含摆动参数 +
  链尾 tip),`process_geo_body.py` 出 mesh,`process_textures.py` 出贴图。
- `plugin/` — 运行时插件源码(`gkms-localify-dmm` 的 `src/GakumasModPlugin` 快照)。
  权威副本在该仓库;这里是交接快照,`plugin/mod_plugin_current_status.md` 记录能力边界。
- `unity/` — mod bundle 的 Unity 构建脚本 + `mod.json` 样例。

## 两条铁律

新骨物理**只有两个**必须由数据侧保证的前提,缺任一样都不摆(踩了很久才明白,细节见 findings):

1. **每条链必须带链尾 tip 骨。** 它没有蒙皮权重、不在 `m_Bones` 里,得单列 `extraSwingBones`。
   `UpdateChainInfo` 会排除每条链的最后一根 —— 没有 tip,真正该摆的那根就被当 tip 排除了。
2. **每骨必须灌源摆动参数**(`damping/stiffness/spring/mass/useWindGlobalForce`)。只调
   `SetDefaultValues` 拿到的是 `mass=0/spring=0` 的惰性默认值。

满足这两条后,**layers 交给游戏自己建,插件不要碰**。
