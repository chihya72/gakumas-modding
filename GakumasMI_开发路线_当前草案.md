# GakumasMI 开发路线（当前草案）

> **2026-06-25 更新（v0.4.8）**：单 t0 身体的 Blender → 3DMigoto → 游戏（换模 + 动画 +
> 贴图 + 多 mod 共存）完整闭环已达成并发布；一键即可对任意 body 生成完整配置档。本文为
> 总体产品愿景，**最新执行状态、完成度与后续计划以**
> [`research/current-status-and-roadmap.md`](research/current-status-and-roadmap.md)**为准**
> （下方分阶段计划属早期草案，部分已完成/调整）。

> **项目定位**：为《学园偶像大师》建立一套以 **3DMigoto / DX11** 为核心的视觉 Mod 体系。  
> **目标用户**：玩家只需安装运行环境；Mod 作者主要使用 Blender，不要求安装完整 Unity、制作 AssetBundle 或手动研究 Shader Hash。  
> **本文范围**：模型、贴图、材质、Renderer 显隐、部分 Shader / 后处理等视觉 Mod。文本汉化、游戏逻辑和数值修改不纳入本路线。

---

## 1. 当前已验证状态

### 1.1 游戏可切换至 DX11

当前通过启动参数：

```text
-force-d3d11
```

已确认游戏实际使用 Direct3D 11。日志中存在：

```text
Forcing GfxDevice: Direct3D 11
Direct3D:
    Version: Direct3D 11.0 [level 11.1]
Graphics API: Direct3D11
```

这意味着游戏具备原版 3DMigoto 的基础运行条件。

### 1.2 原版 3DMigoto 已成功注入

游戏窗口中出现：

```text
VS: 0/0  PS: 0/0  CS: 0/0  skip
Stereo disabled
```

说明 3DMigoto 的 `d3d11.dll` 已接管 DX11 渲染链路，当前可进入 Hunting / Frame Analysis / 资源替换验证阶段。

### 1.3 当前技术观察

- 游戏引擎：Unity `6000.0.67f1`
- 渲染后端：URP + 自定义 `CampusRenderPipeline`
- 当前测试环境：`SRP Batcher: False`
- 显卡：RTX 4060 Laptop GPU
- 当前策略：使用 `-force-d3d11` 运行，避免默认 DX12 路径导致 3DMigoto 失效

> `SRP Batcher: False` 仅表示当前环境中批处理未启用；是否能稳定按角色/服装拆分 Drawcall，仍需通过 Frame Analysis 实测确认。

---

## 2. 总体目标与边界

## 2.1 总体目标

建立类似终末地、鸣潮等 Model Importer 生态的流程：

```text
玩家：
安装 GakumasMI Runtime
→ 放入 Mod
→ 正常启动游戏
→ 启用视觉 Mod

Mod 作者：
Blender
→ 导入目标服装/部件参考数据
→ 修改模型或贴图
→ 一键导出 GakumasMI Mod
→ 发布给玩家
```

作者不应被要求：

- 安装 Unity 6000；
- 手动构建 AssetBundle；
- 使用 AssetRipper 研究资源；
- 手动寻找 Vertex Shader / Pixel Shader Hash；
- 手动写 `.ini`、`.buf`、`.fmt`；
- 了解游戏启动参数或 DMM 登录参数。

## 2.2 不纳入首期范围

以下能力不作为早期目标：

- 游戏数值、抽卡、货币、关卡、网络逻辑修改；
- 文本汉化或 Localify 插件替代；
- Animator Controller 替换；
- 新增游戏逻辑组件；
- 新增复杂骨骼、物理链、布料模拟；
- 修改联网验证、反作弊或服务端通信；
- 将 DMM 临时登录 Token 保存、读取或上传。

## 2.3 技术边界

3DMigoto 的核心能力是对 GPU 渲染调用进行拦截和替换，因此首期重点是：

- Vertex Buffer / Index Buffer 替换；
- Texture 替换；
- 材质贴图槽替换；
- Shader Override / Shader Fix；
- Drawcall 跳过；
- Renderer 对应部分的显隐替代；
- 少量后处理和 UI 视觉替换。

它不是 Unity 运行时框架，不应承担文本、脚本逻辑或游戏数据修改职责。

---

## 3. 最终架构

```text
┌──────────────────────────────────────────────────────┐
│                   玩家侧：GakumasMI                   │
├──────────────────────────────────────────────────────┤
│ GakumasMI Runtime                                    │
│ ├─ 3DMigoto DX11 Runtime                             │
│ ├─ Gakumas 专用 d3dx.ini / ShaderFix                 │
│ ├─ Profile 驱动的 Hash / Drawcall 映射               │
│ ├─ Mod 扫描、启用顺序、日志与错误提示                │
│ └─ DX11 启动检查与兼容性检查                         │
│                                                      │
│ GakumasMI Profiles                                   │
│ ├─ 游戏版本指纹                                      │
│ ├─ 角色 / 服装 / 部件 Drawcall 映射                  │
│ ├─ VB / IB Layout 定义                               │
│ ├─ 贴图槽、材质、Shader 信息                         │
│ └─ 已验证场景与已知问题                              │
│                                                      │
│ Mods                                                 │
│ └─ 作者_角色_服装/                                   │
│    ├─ manifest.json                                  │
│    ├─ mod.ini                                        │
│    ├─ Buffers/                                       │
│    ├─ Textures/                                      │
│    └─ Preview.png                                    │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│                 作者侧：GakumasMI Tools               │
├──────────────────────────────────────────────────────┤
│ Blender 插件                                          │
│ ├─ 导入目标 Profile / 参考模型                        │
│ ├─ 保留顶点布局、UV、权重和骨骼组                    │
│ ├─ 导出 VB / IB / FMT / DDS                          │
│ ├─ 自动生成 mod.ini                                  │
│ ├─ 输出 manifest.json                                │
│ └─ Mod Validator                                     │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│          核心开发者侧：研究与 Profile 制作            │
├──────────────────────────────────────────────────────┤
│ 3DMigoto Hunting / Frame Analysis                     │
│ AssetRipper / AssetStudio                             │
│ Unity（仅内部资源核对，不进入普通作者流程）           │
│ Hash 数据库、Drawcall 映射、版本差异比对              │
└──────────────────────────────────────────────────────┘
```

---

## 4. 核心设计原则

## 4.1 视觉 Mod 完整迁移至 3DMigoto

公开作者流程不依赖 Unity AssetBundle。

Unity、AssetRipper、资源导出与 Prefab 分析只保留给核心维护者，用于：

- 识别角色和服装资源；
- 核对部件名称、骨骼和材质；
- 协助建立 Drawcall Profile；
- 处理版本更新后的资源差异；
- 排查 3DMigoto 替换失败的原因。

## 4.2 Profile 驱动，而不是作者手工写 Hash

所有关键 Hash、渲染槽位和资源结构应由官方维护的 Profile 提供。

作者在 Blender 内选择的是语义化目标：

```text
角色：花海佑芽
服装：目标服装 ID
部件：上衣 / 下装 / 鞋子 / 饰品
Profile：gakumas-<game-version>-<costume-id>
```

作者不应直接接触：

```ini
[TextureOverride_A1B2C3D4]
hash = a1b2c3d4
```

导出器根据 Profile 自动生成 3DMigoto 所需 `.ini`、`.buf`、`.fmt`、纹理路径和资源绑定关系。

## 4.3 Release Runtime 与开发 Hunting 环境分离

开发环境允许：

- HUD；
- Shader Hunting；
- Frame Analysis；
- Shader Dump；
- 调试日志；
- 手工测试热键。

发布给普通玩家的 Runtime 应默认：

- 关闭绿色 Hunting HUD；
- 关闭不必要的 Dump；
- 限制调试输出；
- 统一管理 Mod 加载顺序；
- 提供清晰的错误日志和安全模式。

## 4.4 Mod 包表达“语义目标”，而不是只表达 Hash

每个 Mod 至少声明：

- 作者、名称、版本；
- 目标角色；
- 目标服装；
- 目标部件；
- 适用 Profile；
- 是否替换 Mesh / Texture / Shader；
- 冲突信息；
- 预览图；
- 最低 Runtime 版本。

Hash 与具体 Drawcall 绑定信息放在生成的 `mod.ini` 与 Profile 侧，而不是让作者手工维护。

---

## 5. 推荐 Mod 包格式

```text
Mods/
└─ ExampleAuthor_Mizuki_Dress/
   ├─ manifest.json
   ├─ mod.ini
   ├─ Preview.png
   ├─ Buffers/
   │  ├─ BodyPosition.buf
   │  ├─ BodyBlend.buf
   │  ├─ BodyTexcoord.buf
   │  ├─ BodyColor.buf
   │  └─ Body.ib
   ├─ Textures/
   │  ├─ BodyDiffuse.dds
   │  ├─ BodyNormal.dds
   │  └─ BodyMask.dds
   └─ ShaderFixes/
      └─ optional_fix.ini
```

建议的 `manifest.json`：

```json
{
  "schemaVersion": 1,
  "id": "exampleauthor.mizuki.dress",
  "name": "Mizuki Dress",
  "version": "1.0.0",
  "author": "ExampleAuthor",
  "type": "model",
  "profile": "gakumas-3.x.x-mizuki-costume-001",
  "targets": ["body", "cloth", "shoes"],
  "dependencies": [],
  "conflicts": [],
  "runtime": ">=0.1.0"
}
```

---

## 6. 研发阶段与交付物

## Phase 0：稳定 DX11 启动与基础运行环境

### 目标

让核心开发环境能够稳定、重复地启动游戏并加载 3DMigoto。

### 当前已完成

- [x] 验证 `-force-d3d11` 生效；
- [x] 验证游戏实际运行于 Direct3D 11；
- [x] 验证原版 3DMigoto 成功注入；
- [x] 验证可见 3DMigoto Hunting HUD。

### 后续任务

- [ ] 确认从 DMM 正常启动链路中添加 DX11 参数的稳定方式；
- [ ] 不保存、不展示、不上传 `/pf_access_token` 等临时登录参数；
- [ ] 确认游戏更新后 EXE、启动参数或渲染 API 是否变化；
- [ ] 制作最小开发配置：Hunting、Frame Analysis、Log 分离；
- [ ] 制作最小发布配置：关闭 HUD、关闭无关 Dump。

### 完成标准

每次启动均可确认：

```text
Forcing GfxDevice: Direct3D 11
Graphics API: Direct3D11
```

且 3DMigoto 的日志可正常生成。

---

## Phase 1：建立首个 Drawcall Profile

### 目标

选择**一位偶像、一套固定服装、一个固定 3D 场景**，完整建立首个可用 Profile。

### 建议优先对象

优先选：

- 常驻、容易进入的 3D 场景；
- 角色模型稳定、镜头可控的场景；
- 服装部件相对清晰的一套衣装；
- 尽量避开复杂 Live 特效、过场特写和频繁切 LOD 的场景。

### 每个部件需要记录的信息

```text
Profile ID
角色 ID
服装 ID
部件名称
场景名称
Vertex Shader Hash
Pixel Shader Hash
Compute Shader Hash（如存在）
Index Buffer Hash
Vertex Buffer Layout
顶点数 / 索引数
VB Slot / Stride
骨骼索引、权重格式
材质与贴图槽位
Draw 顺序
是否可 skip
是否包含 BlendShape
是否存在 LOD
备注与已知问题
```

### 首期目标部件

- 脸部；
- 头发；
- 身体；
- 上衣；
- 下装；
- 鞋子；
- 饰品；
- 描边 / 阴影 / 特效相关 Drawcall。

### 完成标准

输出：

```text
profiles/
└─ <idol>-<costume>/
   ├─ profile.json
   ├─ drawcall_map.json
   ├─ material_map.json
   ├─ texture_map.json
   └─ notes.md
```

---

## Phase 2：完成三类最小可行 Mod（PoC）

不要直接从完整服装替换开始。先依次验证三类能力。

### 2.1 部件隐藏 Mod

验证内容：

- `handling = skip`；
- 指定 Hash 是否稳定命中；
- 隐藏后是否出现残影、阴影残留或描边残留；
- 不同镜头、不同场景、不同 LOD 下是否一致。

建议从帽子、耳饰、外套等独立部件开始。

### 2.2 贴图替换 Mod

验证内容：

- Albedo / Diffuse；
- Normal；
- Mask / Lightmap；
- Alpha、透明材质；
- 不同分辨率、压缩格式与色彩空间；
- 多材质槽的贴图绑定。

建议先从衣服纹理替换开始，不直接动脸部、眼睛或复杂透明材质。

### 2.3 同骨骼 Mesh 替换 Mod

验证内容：

- Vertex Buffer / Index Buffer 替换；
- UV、Normal、Tangent、Vertex Color；
- Bone Index / Bone Weight；
- Bind Pose；
- BlendShape；
- 材质槽数量；
- 动画、镜头、Live 动作下是否正确变形。

首期限制：

```text
允许：修改现有模型外形、UV、权重、贴图
允许：增加或减少顶点
允许：复用目标部件既有骨骼
暂不允许：新增骨骼
暂不允许：新增物理链
暂不允许：修改 Animator
暂不允许：修改 Unity Prefab
```

### Phase 2 完成标准

至少实现：

- 一个隐藏部件 Mod；
- 一个服装贴图 Mod；
- 一个同骨骼 Mesh Mod；

且三者能在目标场景稳定加载、关闭和恢复。

---

## Phase 3：Profile 规范与 Runtime 规范化

### 目标

将一次性的 Hunting 成果转成可复用、可维护的数据规范。

### 需要形成的规范

- Profile 文件格式；
- Mod `manifest.json` 格式；
- `mod.ini` 自动生成规则；
- Buffer 命名规则；
- Texture 命名规则；
- Hash 多版本映射规则；
- LOD / 多 Drawcall / 描边与阴影处理规则；
- 冲突判定规则；
- 日志与错误码规则。

### Mod 冲突的基础分类

```text
同一角色 + 同一服装 + 同一部件 + 同一替换类型
```

例如：

- 两个 Mod 都替换同一衣服 Mesh：高冲突；
- 一个替换衣服 Mesh、另一个替换鞋子贴图：通常可并存；
- 一个 Mod Skip 原饰品、另一个 Mod 替换该饰品 Mesh：逻辑冲突；
- 多个 Mod 修改同一 Shader Fix：需要明确优先级。

---

## Phase 4：GakumasMI Blender 插件

### 目标

让作者从 Blender 完成导入、修改、验证与导出。

### 首版功能

```text
Import Gakumas Reference
Export Gakumas Mesh Mod
Export Gakumas Texture Mod
Validate Mod
```

### 导入侧要求

插件需要能够导入或读取：

- 对应角色/服装的参考模型；
- 目标骨骼；
- 顶点组与权重；
- UV；
- 必要的材质槽信息；
- Profile 元数据；
- 顶点布局要求。

### 导出侧要求

插件自动生成：

```text
Buffers/
Textures/
mod.ini
manifest.json
Preview.png（可选）
```

### Validator 必检项

```text
Position 是否存在
Normal 是否存在
Tangent 是否存在
UV 是否符合目标要求
Vertex Color 是否存在
顶点属性顺序与格式是否匹配
Bone Index / Bone Weight 是否匹配
材质槽数量是否匹配
BlendShape 是否缺失
贴图尺寸与格式是否合规
目标 Profile 是否匹配当前导出目标
```

### 完成标准

普通作者无需安装 Unity，即可从 Blender 导出可被 Runtime 加载的 Mod。

---

## Phase 5：GakumasMI Runtime / Mod Manager

### 定位

管理体验参考 XXMI 的“安装、启用、更新、诊断”思路，但不复制终末地的具体实现。

### 初版功能

- 检测 `gakumas.exe` 路径；
- 检测是否成功使用 DX11；
- 检测 3DMigoto Runtime 是否完整；
- 扫描、安装、启用、禁用 Mod；
- 管理 Mod 优先级；
- 显示依赖与冲突；
- 显示 Profile 匹配状态；
- 一键打开 Mods、Logs、Profiles；
- 游戏更新后默认进入安全模式；
- 导出诊断日志包。

### 明确限制

- 不读取、不保存 DMM 账号密码；
- 不保存、不上传临时登录 Token；
- 不替代官方 DMM 登录；
- 不修改联网、支付、账号或游戏数据逻辑。

### 建议的安全模式

当检测到以下任一项变化时：

```text
游戏版本变化
data.unity3d 指纹变化
目标资源指纹变化
Profile 版本不匹配
Shader / Hash 映射未验证
```

默认行为：

```text
标记 Mod 为“未验证”
默认不加载
允许开发者手动强制启用
```

---

## Phase 6：游戏更新维护体系

### 维护对象

```text
Unity Player 版本
gakumas.exe 指纹
data.unity3d 指纹
目标 AssetBundle 指纹
Shader Hash
VB / IB Hash
Drawcall 顺序
贴图槽绑定
角色服装结构
Profile 版本
```

### 更新流程

```text
游戏更新
→ 核心维护者在基准场景重新抓帧
→ 对比旧版与新版 Drawcall
→ 更新 Profile
→ 验证基准 Mod
→ 发布 Profile Patch
→ Runtime 标记旧 Mod 的兼容状态
→ 作者按需要重新导出或修复 Mod
```

### 重要原则

Profile 更新可以修复：

- Hash 变化；
- Drawcall 重定位；
- 配置映射变化；
- Shader Fix 变化。

但 Profile 更新**不保证**自动修复所有 Mesh Mod。若顶点布局、骨骼结构、材质槽或 BlendShape 发生实质变化，Mod 仍可能需要作者重新导出或手工修复。

---

## 7. 当前优先级

当前不应立即开发完整 Manager，也不应立即尝试全身服装替换。

当前执行状态：

- [x] 固定首个测试角色、服装和场景（花海咲季 / `cstm-0000` / 候机室白天，见 `research/baseline/target.json`）
- [x] 配置 3DMigoto Hunting / Frame Analysis 工作流并完成首帧抓取
- [ ] 建立首个完整 Drawcall Profile（Body / Face / Hair / Hair Accessory 映射已实机验证；二次贴图抓帧完成，Body `t0/t1/t4` 已映射，等待其余材质语义确认）
- [x] 成功隐藏一个独立部件（花海咲季 `cstm-0000` 发饰 PoC）
- [x] 成功替换一张服装贴图（Body Base Color `950989c5` 换色 PoC 已实机验证）
- [x] 成功替换一个同骨骼 Mesh（Body `4d5dfe7b` 索引级动画 Mesh PoC 已实机验证，骨骼动画正常）
- [x] 建立 Profile / Manifest v1 规范、资源命名规则与自动校验脚本（`spec/`、`tools/validate-packages.ps1`）
- [x] 完成 Blender 插件 `0.1.0`（Blender 4.2 LTS：参考 Mesh 导入、索引 Mesh 验证/导出、DDS 贴图包导出）
- [x] 定位上游 Bone Index / Bone Weight / Bind Pose（`Geo_Body`：152 根加权骨骼，Blender 插件 0.2 已支持加权参考导入）
- [x] 对照 EFMI / GIMI / WWMI / SRMI 的真实蒙皮切入点（见 `research/reference-framework-comparison.md`；EFMI 官方同样不支持 CPU-posed 组件 VB 换模）
- [x] 判定 Body Draw 前是否存在 GPU 可见的骨骼矩阵或 Compute Skinning 输入：**不存在**
- [x] 既然不存在 GPU 骨骼矩阵，放弃 GPU skinning bridge 与进程内 Runtime override，
  改用「逆解每帧矩阵 + 重蒙皮」（路线 C）。已实机验证，并于 2026-06-24 删除
  `runtime/native` 与表面驱动相关代码（可从 git 历史恢复）。

建议按以下顺序推进：

1. 固定一个测试角色、测试服装和测试场景；
2. 配置 3DMigoto Hunting / Frame Analysis 工作流；
3. 建立首个完整 Drawcall Profile；
4. 成功隐藏一个独立部件；
5. 成功替换一张服装贴图；
6. 成功替换一个同骨骼 Mesh；
7. 参考成熟 Model Importer，定位上游蒙皮资源并选定 GPU bridge 或 Runtime bridge；
8. 整理 Profile 与 Mod 包格式；
9. 再开发 Blender 导出插件；
10. 最后开发 Runtime Manager / 图形化管理器。

---

## 8. 当前项目拆分建议

```text
gakumas-3dmigoto-lab
├─ 研究环境
├─ Hunting 配置
├─ Frame Analysis
├─ Shader / Texture Hash 数据
├─ 基准场景测试
└─ PoC Mod

gakumasmi-profiles
├─ 游戏版本 Profile
├─ 角色 / 服装映射
├─ Drawcall / Material / Texture 数据
├─ 版本差异记录
└─ 已知问题

gakumasmi-tools
├─ Blender 插件
├─ 导入器
├─ 导出器
├─ Validator
└─ 打包器

gakumasmi-runtime
├─ 3DMigoto Release 配置
├─ Profile Loader
├─ Mod 扫描与排序
├─ 日志与诊断
└─ 安全模式

gakumasmi-mods
├─ 示例 Mod
├─ 模板 Mod
├─ 作者文档
└─ 发布规范
```

---

## 9. 风险与发布原则

### 9.1 在线游戏风险

该项目涉及第三方视觉修改工具。即使 Mod 不修改数值或网络数据，也仍可能违反游戏运营方的规则并带来账号处罚风险。

发布时应明确：

- 仅限用户自行承担风险；
- 不承诺不会触发封禁；
- 不提供绕过检测、规避反作弊或规避服务器校验功能；
- 不修改支付、账号、网络、数值与服务端逻辑；
- 不要求用户提交账号、密码或临时 Token。

### 9.2 版权与资源分发

应尽量避免在 Mod 包中直接重新分发完整官方模型、贴图、音频或 AssetBundle。

优先发布：

- 差异化 Buffer；
- 作者原创贴图；
- 生成的配置文件；
- 必要的 Mod 元数据；
- 不含官方原始资源的补丁式文件。

### 9.3 兼容性风险

Gakumas 持续更新后，以下内容可能失效：

- DX11 强制启动参数；
- Shader Hash；
- Drawcall 映射；
- 顶点布局；
- 骨骼和材质结构；
- 3DMigoto 注入兼容性。

因此 Runtime 必须始终提供：

- 日志；
- 禁用全部 Mod 的安全模式；
- Profile 版本检查；
- 单 Mod 快速禁用；
- 清晰的故障定位信息。

---

## 10. 最终定位

```text
视觉 Mod：
GakumasMI / 3DMigoto 负责

Mod 作者：
Blender + GakumasMI Tools 负责

Profile 与兼容性维护：
核心开发者负责

Unity、AssetRipper、Frame Analysis：
仅作为内部研究工具

文本汉化与功能插件：
继续使用独立的 Localify / version.dll 等路线
```

最终应形成的不是“一个能放入 `d3d11.dll` 的 Mod Loader”，而是一套具备以下能力的生态：

```text
DX11 Runtime
+ Profile 驱动的 Hash 映射
+ Blender 作者工具
+ 标准化 Mod 包
+ 版本兼容与安全模式
+ 可诊断、可维护的 Mod 管理体验
```
