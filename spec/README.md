# GakumasMI Profile 与 Mod 包规范 v1

## Profile

每个 Profile 目录必须包含：

```text
profile.json
drawcall_map.json
material_map.json
texture_map.json
notes.md
```

`profile.json` 只保存目标、版本、Buffer 布局和部件身份；Drawcall、材质及贴图映射分别放入对应 map，避免单文件无限膨胀。游戏更新后新增 Hash 时，以构建 ID 建立变体，不覆盖仍受支持的旧 Hash。

## Mod 包

```text
<mod>/
├─ manifest.json
├─ mod.ini
├─ README.md
├─ Buffers/       # 可选
└─ Textures/      # 可选
```

资源文件使用 `<Component>.<Semantic>.<Format>.<ext>`：例如 `Body.IB.R16_UINT.buf`、`Body.BaseColor.dds`。INI Section 名必须带 Mod/目标前缀，避免跨包重名。

## 冲突键

冲突键格式为 `<actor>.<costume>.<component>.<replacement>`。同键表示默认不可并存：

- `hski.cstm-0000.body.mesh`
- `hski.cstm-0000.body.baseColor`
- `hski.cstm-0000.hair-accessory.renderer`

同一 Shader Hash 可以被多个 Mod 检查，但发布包必须避免与调试包同时加载；确需并存时应显式设计优先级，不以忽略警告作为发布方案。

## mod.ini 生成规则

1. 为相关 ShaderOverride 写入 `checktextureoverride`。
2. TextureOverride 仅匹配 Profile 中记录的 Hash。
3. Buffer 资源必须声明 `type` 和 `format`；贴图沿用文件内格式。
4. 所有 PoC 必须有可关闭路径；发布版可由 Manager 负责启停。
5. 阴影、主材质和描边 pass 必须分别验证。

运行 `pwsh -File tools/validate-packages.ps1` 校验 Profile、Manifest 和 INI 资源引用。
