# Gakumas Mod 插件当前状态

本文记录当前独立 Mod 插件仓库的真实状态。当前唯一运行时插件是 `src/GakumasModPlugin`，产物为 `xinput1_3.dll`。

## 1. 当前结论

- 插件可以独立加载并运行本地 Mod 资源替换逻辑。
- 当前验证重点是 `mdl_chr_hmsz-cstm-0051_body` 这类单 body renderer 服装替换。
- 自制 mesh 可以替换到原始 `SkinnedMeshRenderer.sharedMesh`，不要求顶点数和原版一致。
- 插件会按骨骼名把 mod mesh 的 skinning 数据重排到原始 renderer 的 bones 顺序。
- replacement 可选声明 `skeleton`/`skeletonAsset` TextAsset；声明后保留 mod 的原始 bone weights，按 sidecar
  的 parent/localTRS 创建缺失骨，并把混合 `bones[]` 写回原始 renderer。rui 示例为 90 根共享骨 + 11 根嫁接骨。
- 新增专属骨的**独立 ActorSwing 物理已跑通**(2026-07-17,runtime 路线)。前提是 sidecar 必须带
  每骨摆动参数和每条链的链尾 tip;缺任一样都不摆。详见 `../docs/physics-bones-findings.md`。
- 插件会先 clone mod mesh，再对 clone 后的 mesh 做顶点空间转换和 skinning patch，避免污染 AssetBundle 缓存。
- 如果 mesh patch 失败，插件会保留游戏原始 mesh，不再把坏 mesh 塞进 renderer。
- 贴图替换通过 `rendererName`、`materialSlot`、shader property 和 AssetBundle 内资源路径完成。
- 独立日志写入 `gakumas-local/mod-plugin.log`。
- 角色模型资源按 `face` / `hair` / `body` 三类部位理解和制作；一个 mod bundle 可以包含多个部位资源，但单个 FBX/prefab 应只对应其中一个部位。

## 2. Mod 包结构

当前插件扫描：

```text
gakumas-local/local-files/mods/<mod-id>/mod.json
```

最小目录示例：

```text
gakumas-local/local-files/mods/hmsz-0051-test/
  mod.json
  hmsz_0051_mod.bundle
```

`mod.json` 示例：

```json
{
  "schemaVersion": 2,
  "id": "hmsz-0051-test",
  "name": "hmsz-0051-test",
  "version": "0.1.0",
  "author": "your_name",
  "priority": 0,
  "enabled": true,
  "replacements": [
    {
      "source": "mdl_chr_hmsz-cstm-0051_body",
      "part": "body",
      "priority": 0,
      "bundle": "hmsz_0051_mod.bundle",
      "asset": "Assets/Mods/hmsz_0051/mdl_chr_hmsz-cstm-0051_body.prefab",
      "type": "GameObject",
      "renderers": [
        {
          "rendererId": "body",
          "targetRenderer": "Geo_Body",
          "modRenderer": "Geo_Body"
        }
      ],
      "replaceMaterials": false,
      "textures": [
        {
          "rendererName": "Geo_Body",
          "materialSlot": 0,
          "property": "_BaseMap",
          "asset": "Assets/Mods/hmsz_0051/t_chr_hmsz-cstm-0051_bdy_col.png",
          "type": "Texture2D"
        }
      ]
    }
  ]
}
```

关键字段：

- `enabled`: 是否启用该 mod。
- `priority`: mod 或单条 replacement 的优先级；同一原始资源被多个 mod 注册时，高优先级生效，同优先级后扫描到的规则覆盖前者并写冲突日志。
- `from` / `source` / `target`: 游戏原始资源名。v2 推荐使用 `source`。
- `part`: 资源部位，取值为 `face`、`hair` 或 `body`。
- `bundle` / `assetBundle`: 当前 mod 目录下的 AssetBundle 文件名。
- `asset` / `to` / `name`: AssetBundle 内资源路径。
- `skeleton` / `skeletonAsset`: 可选的 TextAsset 骨架 sidecar 路径；用于需要保留 IP 专属骨权重的 bundle。
- `type`: Unity 资源类型，目前主路径是 `GameObject`。
- `renderers`: v2 renderer 配对规则。`targetRenderer` 是游戏原始 renderer，`modRenderer` 是 mod prefab 内 renderer。
- `rendererName`: v1 单 renderer 简写，0051 body 可以用 `Geo_Body`；v2 推荐使用 `renderers`。
- `replaceMaterials`: 是否直接替换 `sharedMaterials`。当前建议保持 `false`，优先复用游戏原始材质，只替换贴图。
- `textures`: 材质贴图替换规则。

### 2.1 角色资源部位规则

当前角色模型应先按三类部位拆分：

- `face`: 一个角色的一套面部资源，包含该面部状态需要的面部表现。若同一角色因为眼镜等差异有独立面部资源，应视为另一个 `face` replacement。
- `hair`: 一个发型或一个发饰资源。当前观察到的 renderer 只有两种合法结构：单 `Geo_Hair`，或 `Geo_Hair` + `Geo_HairProp`。其中 `Geo_HairProp` 用于发饰、蝴蝶结等同发型资源内的 prop。
- `body`: 从脖子以下到鞋子的身体和服装资源。当前观察到的 renderer 固定为单 `Geo_Body`。

当前 renderer 约定：

| part | renderer 结构 | 初版处理 |
| --- | --- | --- |
| `body` | 只能是 `Geo_Body` | 已作为主路径验证 |
| `hair` | `Geo_Hair` 或 `Geo_Hair` + `Geo_HairProp` | 插件已有 manifest v2 多 renderer 基础支持，需要补真实 hair 模板 |
| `face` | 特殊，暂不在本文固定 | 需要单独研究 profile、材质槽和 renderer 规则 |

制作和打包时建议遵守：

- 一个 AssetBundle 可以包含多个部位，例如同时包含一个 `face`、一个 `hair` 和一个 `body` replacement。
- 一个 FBX/prefab 应只对应一个部位，不应在同一个 FBX 里混放 `face`、`hair`、`body`。
- `mod.json` 里应为每个部位写独立 replacement，分别指向对应的游戏原始资源名和 bundle 内 asset path。
- 当前 0051 验证主要集中在 `body`；`hair` 规则已经收敛为 `Geo_Hair` 或 `Geo_Hair` + `Geo_HairProp`，后续需要补 hair 模板和 profile；`face` 的公开模板、profile 和材质规则还需要单独讨论。

## 3. 运行原理

1. 游戏加载目录中的 `xinput1_3.dll`。
2. 代理 DLL 转发系统 XInput 导出函数，同时启动 mod runtime。
3. runtime 设置工作目录，初始化 `gakumas-local/mod-plugin.log`。
4. 等待 `GameAssembly.dll` 和 IL2CPP 环境可用。
5. 初始化 UnityResolve 和 MinHook。
6. 扫描 `gakumas-local/local-files/mods` 下的 `mod.json`。
7. 注册资源替换规则，但 AssetBundle 在 replacement 命中时才懒加载。
8. Hook AssetBundle 加载结果，命中原始资源名后加载 mod prefab。
9. 在原始 GameObject 上进行 mesh/texture 替换，并返回原始对象引用。

当前版本的稳定性修复点：

- 不再在后台初始化线程中直接加载 mod AssetBundle。初始化阶段只扫描 manifest 和注册规则，真正的 AssetBundle 加载推迟到 replacement 命中时执行。
- 初始化线程会显式 attach 到 IL2CPP domain，避免后台线程直接调用 Unity/IL2CPP API 带来的崩溃风险。
- 已移除暂时没有实际替换用途的 `AssetBundleRequest.get_allAssets` hook，当前只保留同步/异步单资源替换所需 hook 点。
- 本地 bundle 加载改用 Unity 内部 `AssetBundle.LoadFromFile_Internal(System.String,System.UInt32,System.UInt64)`，调用参数为 `(path, 0, 0)`，避免 `AssetBundle.LoadFromFile` 在目标版本中解析不到方法。

主要 hook 点：

- `UnityEngine.AssetBundle::LoadAsset_Internal(System.String,System.Type)`
- `UnityEngine.AssetBundle::LoadAssetAsync_Internal(System.String,System.Type)`
- `UnityEngine.AssetBundleRequest::GetResult()`
- `UnityEngine.AssetBundleRequest::get_asset()`

当前不安装：

- `UnityEngine.AssetBundleRequest::get_allAssets()`

## 4. 已实现能力

面向 mod 作者：

- 替换游戏内已有 body prefab 的 `SkinnedMeshRenderer.sharedMesh`。
- 支持 mod mesh 顶点数、拓扑、UV 与原版不同。
- 支持按骨骼名重排 bone index。
- 支持 renderer local space 顶点转换。
- 支持 `rendererName` 精确匹配 renderer。
- 支持 manifest v2 的 `renderers[].targetRenderer/modRenderer` 配对。
- 支持 `priority` 冲突处理和冲突日志。
- 支持 `part: face | hair | body` 字段。
- 支持按材质槽和 shader property 替换贴图。
- 支持 source profile dump，便于查看目标资源真实 renderer/bone/material 规格。
- 支持离线 Validator 初版，检查 manifest 和包结构。
- 支持作者诊断工具 `tools/gakumas_mod_doctor.py`，输出 `author_diagnostics.json/html` 和下一步修复建议。

面向 mod 用户：

- 错误 mesh patch 不会直接覆盖原始 mesh。
- 日志独立于旧插件，方便反馈给 mod 作者。
- 插件运行时只依赖自身 DLL、MinHook、UnityResolve 和本地 Mod 包。

## 5. 能力边界

这些问题本质上属于资源制作或后续工具链能力，当前插件不承诺自动解决：

- 自动修复错误蒙皮或判断权重是否自然。
- 让新增骨骼自动获得游戏原始 Animator 的独立动画曲线；新增专属骨默认由其父骨驱动，物理层
  另由 ActorSwing 接管。
- rui-nurs→hmsz-0000 的 lossless graft 会创建 11 根缺失专属骨并保留其权重/层级,另按
  `extraSwingBones` 补 14 根无权重链尾;带摆动参数的骨由 ActorSwing 正常驱动。
- 自动把 VRM/MMD 材质转换成目标游戏 shader 所需的完整贴图组。
- 自动重展 UV 或自动烘焙 `_DefMap`、`_ShadeMap`、`_RampAddMap`。
- 自动新增复杂 prefab 逻辑组件。
- 自动判断美术表现是否正确。

插件现在做的是稳定替换、失败保护、诊断输出和作者工具链基础。

## 6. 当前主要缺口

- manifest v2 基础字段已经开始支持，但还缺少版本约束、依赖关系和完整包格式迁移策略。
- `renderers` 基础结构已经支持多 renderer。它对 body 不是初版阻塞项，因为 body 固定单 `Geo_Body`；但它对 hair 是必要能力，因为 hair 存在 `Geo_Hair` + `Geo_HairProp` 结构。
- Validator / Doctor 还不能离线解析 AssetBundle 内部对象来确认真实 asset path。
- Unity Editor Builder 仍需要完善成一键打包工具。
- 贴图 property 映射表和材质检查器还不完整。
- 热重载尚未实现。
- `replaceMaterials=false` 时修改的是原始材质实例上的贴图，仍需继续确认共享材质影响范围。
- Source Profile Dump 目前主要跟随 replacement 命中触发，后续应增加主动 dump 热键或命令。
- 无损骨架嫁接已完成,新骨 ActorSwing 物理已跑通(runtime 路线,不需要 bundle 授权组件)。
  「只建 1 层」的旧结论是误诊:真因是 sidecar 缺链尾 tip,`UpdateChainInfo` 会排除每条链的
  最后一根。补齐 tip + 摆动参数后它自己就建对层数,插件不再干预 layers。
  详见 `../docs/physics-bones-findings.md`。

## 7. 初版发布判断

对于 0051 单 body renderer 服装替换，当前插件已经具备初版可用条件；hair 的单 `Geo_Hair` 和 `Geo_Hair` + `Geo_HairProp` 路线已有基础支持，但仍需真实 hair mod 验证：

- 能独立加载。
- 能替换 mesh 和贴图。
- 有失败保护。
- 有独立日志。
- 有基础 Validator、模板和示例目录。

但对公开发布，应明确标注为 alpha / 作者预览版，并把“资源必须按目标骨骼、renderer、材质槽和贴图 property 制作”写进作者文档。后续开发重点应放在作者工具、hair 双 renderer 模板、face 模板和热重载上。
