# GakumasMI

面向《学园偶像大师》DMM Windows 版的 AssetBundle 视觉 Mod 制作工具。

项目以 Blender 插件为核心，用于制作服装和发型 Mod。作者可以在 Blender 中完成目标导入、模型整理、材质与贴图准备、骨骼映射和最终导出，无需安装 Unity。

## 功能

- 制作服装与发型 AssetBundle Mod
- 导入游戏原版参考模型和骨架
- 映射作者模型与游戏骨骼
- 准备贴图、材质和描边数据
- 检查模型并导出完整 Mod 目录
- 提供用于识别目标资源的 3DMigoto 抓帧环境

## 下载与安装

从 [GitHub Releases](https://github.com/chihya72/gakumas-modding/releases) 下载：

```text
gakumas-mod-toolkit-<版本>.zip
```

发布包包含 Blender 插件、3DMigoto 抓帧环境和安装说明：

```text
blender-addon\
  gakumas_mi-<版本>.zip

3dmigoto_gkms\
安装说明.txt
```

在 Blender 中打开：

```text
编辑 → 偏好设置 → 插件 → 从磁盘安装
```

选择 `gakumas_mi-<版本>.zip` 并启用。插件面板位于：

```text
3D 视图 → 右侧边栏（N）→ GakumasMI
```

支持 Blender 4.2 LTS 和 4.5 LTS。完整的资源库、Python 依赖、抓帧环境和 Runtime 安装方法见 [安装与资源](docs/wiki/1-安装与资源.md)。

## 制作流程

插件按照五个阶段组织制作过程：

```text
1 目标与参照
2 作者模型
3 材质与贴图
4 骨架与物理
5 检查与导出
```

第一次使用建议从 [body Mod 快速上手](docs/wiki/3-快速上手-body.md) 开始。

## 成品安装

插件会导出包含 `mod.json` 和 AssetBundle 的完整 Mod 目录：

```text
<mod-id>\
├─ mod.json
└─ <mod-id>.bundle
```

将它放入：

```text
<游戏目录>\gakumas-mod\mods\<mod-id>\
```

成品由独立的 [Gakumas Mod Runtime](https://github.com/chihya72/gakumas-mod-runtime/releases) 加载和管理。

## 使用边界

本项目只制作模型、贴图、材质和显隐相关的视觉 Mod，不修改文本、数值、抽卡、货币、网络或服务端逻辑。

作者模型需要具备可用的骨架和权重。插件不会自动完成建模对齐、删头、UV 整理或坏权重修复。

3DMigoto 在本项目中只用于抓帧，不负责加载成品 Mod。

## 文档

- [作者手册](docs/wiki/Home.md)
- [安装与资源](docs/wiki/1-安装与资源.md)
- [body Mod 快速上手](docs/wiki/3-快速上手-body.md)
- [常见问题与排错](docs/wiki/11-常见问题与排错.md)
- [参与开发](CONTRIBUTING.md)

## 许可证

项目许可证见 [LICENSE](LICENSE)，第三方组件与来源见 [third-party-notices.md](third-party-notices.md)。

本项目是第三方视觉修改工具，仅供学习与个人使用，使用风险由使用者承担。
