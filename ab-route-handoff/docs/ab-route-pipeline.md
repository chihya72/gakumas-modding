# AB 路线完整流程(可重跑)

从 IP 服装名到进游戏成品。以 `rui-nurs-00 → hmsz-cstm-0000` 为例;新 mod 改常量即可。

## 0. 前置环境

- Python 3.12,含 `numpy` `Pillow` `UnityPy`。
- AssetStudio CLI:`D:\GIT\AssetStudio-net10.0-win\AssetStudio.CLI.exe`。
- Unity 6000.0.67f1(chinosk6 工程版本),**先在 Unity Hub 登录激活 license**。
- chinosk6 工程:`D:\GIT\git.chinosk6.cn\GakumasModeBundle_0119_Build`。
- chinosk6 插件 dll:`gkms-localify-dmm/build/bin/x64/Release/xinput1_3.dll`。

## 1. 解包 IP 源(下载去混淆 + AssetStudio 导出)

见 memory `ip-bundle-unpack-pipeline`。要点:

- Manifest:`D:\GIT\IP\01-unpacking\metadata\OctoDiff.json`,urlFormat
  `https://d2ilil7yh5oi1v.cloudfront.net/solis-{v}-{type}/{o}?generation={g}&alt=media`
  ({v}=uploadVersionId {type}=assetbundle {o}=objectName {g}=generation)。body 清单
  `metadata/body_bundles.csv`。旧 6.0.2 key 至今有效。
- 下载后去混淆:`crypt_by_string(obj, bundleName, 0,0,256)`(仅当 obj[:5]!=b"Unity")。
- **依赖**:body 常依赖 actor-shader(导网格不需要)+ 另一角色同服装 body
  (rui-nurs 依赖 yu-nurs;**各有独立 Geo_Body,分开单包导**)。
- 导网格:`AssetStudio.CLI <bundle> <out> --game Normal --unity_version 2022.3.57f1
  --types Mesh --names "^Geo_Body$" --export_type JSON --group_assets None` → `Geo_Body.json`。
- 导贴图:同上 `--types Texture2D --export_type Convert --image_format Png`。
  rui-nurs 出 6 张:bdy_col/def/sdw + bdyco_col_alp/def/sdw。

产物已在 `source/mdl_chr_rui-nurs-00_body/`。

## 2. 目标 game_ref

学马 body JSON 库:`D:\GIT\gakumas-modding\.local\assetstudio-body-json\`。
取目标 `mdl_chr_hmsz-cstm-0000_body/` 的 `Geo_Body.json` + `Geo_Body.skeleton.json`
(146 骨、含 localTRS、rootBone=Hips)。已在 `target/`。

目标身份靠抓帧对号:抓一帧目标服装,body IB 的索引数 / VB0 顶点数比对 body JSON 库
(`FrameAnalysis-2026-07-15-032013` = 74418idx/16832v = hmsz 默认服家族)。

## 3. 骨骼 sidecar

运行 `../scripts/export_rui_bones.py`，用 UnityPy 从 IP bundle 生成 `build/rui_bones.json`
(schemaVersion 4):每骨 index/name/是否匹配 hmsz/parentIndex/parentChain/localPosition/
localRotation/localScale。(Transform→GameObject→名字;m_Bones 指向 Transform,要经 GameObject
解析名字。)

物理骨还要两样东西，缺任何一样摆动都不对(详见 `physics-bones-findings.md`):

- **`swing`**(每骨可选):源 bundle 里 `ActorSwingDynamicBone` 授权的 `damping/stiffness/
  spring/mass/useWindGlobalForce`。typetree 内嵌在 bundle 里，UnityPy 直接读得动 MonoBehaviour；
  m_Script 指向缺失 CAB，所以按 typetree key 签名认 swing 骨。**`m_Weight` 不是 `rootWeight`**
  (源里全 1.0，base 运行时 0.3 → 运行时算的，别导)。不灌这些，插件只会跑 `SetDefaultValues`，
  拿到 mass=0/spring=0 的惰性默认值 → 骨不摆。
- **`extraSwingBones`**(顶层独立段，14 根):每条链的**链尾 tip**。它们没蒙皮权重 → 不在
  `m_Bones` → 不能进 `bones`(那里必须与 mod mesh 骨数组同长同序，插件有硬校验)，所以单列一段、
  按 `parentName` 挂。**按 `_End` 后缀筛会漏掉 `RightFrontStethoscope3_S`——要按"在不在 m_Bones
  里"判。** `UpdateChainInfo` 会排除每条链的最后一根(tip 只定义末节朝向、不参与模拟)，缺 tip 时
  真正该摆的那根会被当成 tip 排除掉——这就是长期误诊为"1 层墙"的真因。
生成脚本逻辑见 workspace 会话记录;核心:
```python
UnityPy.config.FALLBACK_UNITY_VERSION="2022.3.57f1"
# go_name[GameObjectPathID]=name; tf_go[TransformPathID]=GameObjectPathID
# bone_names[i] = go_name[tf_go[smr.m_Bones[i].path_id]]
# matched = name in hmsz skeleton node names
```
这就是无损方案所需的完整 localTRS sidecar；Unity Builder 将其作为 TextAsset 打进 bundle。

## 4. Geo_Body 处理器(纯 Python)

`../scripts/process_geo_body.py` → `build/rui_Geo_Body.processed.json`:
1. **权重保持原样**:顶点/骨索引/权重不改，运行时由插件按 sidecar 嫁接 11 根 IP 专属骨；无 sidecar 的普通 mod 仍走旧的按名 remap 分支。
2. **COLOR 描边**:逐顶点按源 _def(t1)+ _col 分类(skin/metal/glossy/matte/cloth)→ 学马描边类,
   只改 R.hi/R.lo/G.hi + 宽度 B.lo=15,保留源 ramp/rim(G.lo/B.hi/A)。方法
   `TEMPLATE_OUTLINE_RGB_WIDTH15_PRESERVE_GLOW_BHIGH_A`。COLOR 是每顶点 RGBA(无需展开)。
   顶点/法线/切线/UV 不动。
   分类判据与 process_textures 共用,保证 COLOR 与贴图不打架。
   预设来源 `gakumas_mi/material_presets.json`。

## 5. 贴图处理器(纯 Python)

`../scripts/process_textures.py` → `build/textures/rui_{bdy,bdyco}_{t0,t1,t4}.png`:
- t0 = 源 col(bdyco 保留 cutout alpha)。
- t1 = 逐像素分类写 presets 的 (toon,smooth,metal,ao)。**t1.A 是数据遮罩不是透明度**。
- t4 = 源 sdw,A 改为皮肤二值 mask。
- **肤色校准当前跳过**(需 hmsz-0000 皮肤采样)。

## 6. Unity JSON→Mesh 导入器(不走 FBX)

`GakumasModeBundle_0119_Build/Assets/Editor/BuildGakumasModBundleRuiNurs0000.cs`：类 `BuildGakumasModBundle`，菜单 `Gakumas Mod/Build Bundle From Mod Root`。
- 读 processed geojson(.txt)建 Mesh:vertices/normals/tangents/uv/**colors32 精确**/
  boneWeights/**bindposes(转置修正)**/2 submesh。
- 建 101 命名骨 Transform(导入器只负责提供顺序和名字，运行时 sidecar 会替换 renderer 的混合 bones[];root 名=Hips)。
- 建 prefab + `ConfigureTextures()`(t1 线性、t0/t4 sRGB,非压缩)+ 打 bundle。

stage 输入:把 `build/rui_Geo_Body.processed.json`、`build/rui_bones.json`、6 张贴图、mod.json
拷进工程 `Assets/Mods/hmsz_0000/`(JSON 用 .txt 扩展名)。

无头构建:
```bash
"C:/Program Files/Unity/Hub/Editor/6000.0.67f1/Editor/Unity.exe" -batchmode -quit \
  -projectPath "D:/GIT/IP/06-ab-route-handoff/GakumasModeBundle_0119_Build" \
  -executeMethod BuildGakumasModBundle.BuildFromArg -modRoot Assets/Mods/hmsz_0000 -logFile build.log
```
产物 `AssetBundles/Windows/hmsz_0000_ruinurs.bundle`。

## 7. mod.json + 部署

`unity/mod.json`(= final-mod/mod.json):schemaVersion 2,source=`mdl_chr_hmsz-cstm-0000_body`,
part=body,renderers Geo_Body↔Geo_Body,replaceMaterials=false,textures 绑
`_BaseMap`(t0)`_DefMap`(t1)`_ShadeMap`(t4) slot0(bdy)/slot1(bdyco)。

部署:
- `mod.json` + `hmsz_0000_ruinurs.bundle` → `D:\Games\gakumas\gakumas-local\local-files\mods\hmsz-0000-ruinurs\`
- `xinput1_3.dll` → 游戏根目录 `D:\Games\gakumas\`

## 8. 验收 + 诊断

进游戏选目标服装场景。插件日志 `D:\Games\gakumas\gakumas-local\mod-plugin.log`:
- `[ModAsset] Applied lossless IP skeleton graft ... matchedBones=90 createdBones=11
  droppedInfluences=0 fallbackVertices=0` → sidecar/混合 bones[] 已接管。
- `Weighted bone diagnostics ... modTop=[...] originalTop=[...]` 两者一致 → 权重落对骨。
- `Applied material texture ... _BaseMap/_DefMap/_ShadeMap` → 贴图命中。

**几何爆炸但日志干净 → 先查 bindpose 转置/坐标空间**(见 incident §3)。
**整体发暗 → 查 t1 色彩空间**(incident §4)。
**专属件错位/不动 → 查 sidecar 顺序、SetParent/localTRS 与 bindpose/坐标空间**(incident §5 / lossless plan)。

## 新 mod 最短路线

1. 解包新 IP body(§1)。
2. 抓帧定目标学马服装、取 game_ref(§2)。
3. 改脚本源/目标常量(路径、目标资源名、强制刚性骨名规则),跑 §3-5。
4. 改 Unity 导入器与 mod.json 的资源名,§6-7 构建部署。
5. §8 验收。别把当前案例的骨匹配数/reparent 表当常量,按新服装重算。


claude-opus-4-8 is temporarily unavailable, so auto mode cannot determine the safety of Write right now. Wait briefly and then try this action again. If it keeps failing, continue with other tasks that don't require this action and come back to it later. Note: reading files, searching code, and other read-only operations do not require the classifier and can still be used.
