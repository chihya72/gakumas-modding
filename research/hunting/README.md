# Hunting / Frame Analysis 工作流

> 环境：`D:\Games\gakumas`  
> 基准目标：`research/baseline/target.json`

## 当前配置

游戏目录的 `d3dx.ini` 已启用：

```ini
[Include]
include_recursive = Mods

[Hunting]
hunting = 1
marking_mode = skip
verbose_overlay = 1
analyse_frame = no_modifiers VK_F8
analyse_options = desc mono share_dupes
```

首帧几何分析使用了 `dump_vb dump_ib buf txt desc mono share_dupes`。当前已切换至贴图研究模式：全局不重复导出 Buffer，仅由角色主 Shader 的开发 Override 定向执行：

```ini
analyse_options = dump_tex jps_dds desc mono share_dupes
```

仍不抓取 RenderTarget 或 Depth。贴图只在角色主材质 Shader 命中时导出。

## 热键

| 操作 | 热键 |
| --- | --- |
| 重载配置与 ShaderFix | `F10` |
| 抓取下一帧 | `F8` |
| 开关 Hunting HUD | 小键盘 `0` |
| 上一个 / 下一个 Pixel Shader | 小键盘 `1` / `2` |
| 标记 Pixel Shader | 小键盘 `3` |
| 上一个 / 下一个 Vertex Shader | 小键盘 `4` / `5` |
| 标记 Vertex Shader | 小键盘 `6` |
| 上一个 / 下一个 Index Buffer | 小键盘 `7` / `8` |
| 标记 Index Buffer | 小键盘 `9` |
| 上一个 / 下一个 Vertex Buffer | 小键盘 `/` / `*` |
| 标记 Vertex Buffer | 小键盘 `-` |
| 清除当前 Hunting 选择 | 小键盘 `+` |

只有游戏窗口位于前台时热键才生效。

## 首次抓帧步骤

1. 进入 `adv_dear_hski_009` 开场首句并暂停；
2. 确认背景为 `env_3d_adv_waitingroom-00-00-noon`；
3. 确认画面中仅有 `hski`；
4. 使用左下角界面隐藏功能，尽量移除对话框；
5. 按 `F10` 载入本配置；
6. 按一次 `F8`，不要长按；
7. 等待画面恢复响应及磁盘写入结束；
8. 在游戏目录确认生成新的 `FrameAnalysis-*` 文件夹；
9. 记录文件夹名称、大小、文件数与抓取时间；
10. 不立即进行第二次抓帧，先分析首帧结果。

## 输出与保护规则

- Frame Analysis 默认输出到游戏根目录的 `FrameAnalysis-*`；
- 共享去重资源由 `share_dupes` 管理；
- 不要手动删除共享去重目录中的单个文件；
- 一次只按一次 `F8`；
- 若抓帧后长时间无响应，先等待磁盘写入完成，不连续触发；
- 不把 DMM Token、进程命令行或账号信息写入研究记录；
- 分析完成前保留原始抓帧目录，不重命名其中资源文件。

## 首帧验收

- [x] 生成唯一的新 `FrameAnalysis-*` 目录；
- [x] 目录中存在 `log.txt` 或等价调用记录；
- [x] 存在 `*-vb*.buf` 与对应 `.txt` / `.dsc`；
- [x] 存在 `*-ib*.buf` 与对应 `.txt` / `.dsc`；
- [x] 抓帧期间游戏未崩溃；
- [x] 抓帧目录大小合理；
- [x] 能从调用记录定位咲季身体、脸与头发的候选 Drawcall。

首帧输出：`D:\Games\gakumas\FrameAnalysis-2026-06-21-105931`，分析结果见 `profiles/hski-cstm-0000/`。
