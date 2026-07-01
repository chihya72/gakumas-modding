"""分材质 t1/t4 烘焙的纯 core 冒烟测试（不依赖 bpy）。

直接按文件加载 core.py，绕过会 import bpy 的包 __init__。
"""
import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "gmi_core", ROOT / "gakumas_mi" / "core.py"
)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

presets = core.load_material_presets()
assert {"skin", "cloth", "metal", "neutral"} <= set(presets), presets.keys()

# 64x64：左半红→slot0，右半蓝→slot1
size = 64
base = np.zeros((size, size, 4), np.uint8)
base[..., 3] = 255
base[:, :32, 0] = 200
base[:, 32:, 2] = 200
tris = np.array([
    [[0, 0], [0.5, 0], [0.5, 1]], [[0, 0], [0.5, 1], [0, 1]],
    [[0.5, 0], [1, 0], [1, 1]], [[0.5, 0], [1, 1], [0.5, 1]],
], np.float32)
mat_ids = np.array([0, 0, 1, 1])

id_map = core.rasterize_material_ids(tris, mat_ids, size, dilate=2)
assert set(np.unique(id_map).tolist()) == {0, 1}, "栅格化应只剩两材质且全覆盖"
assert id_map[10, 5] == 0 and id_map[10, 60] == 1

t1, t4 = core.bake_material_maps(id_map, base, {0: "skin", 1: "metal"}, presets)

# t1 纯色：金属区金属度高、皮肤区金属度 0
assert t1[10, 60, 2] > 180 and t1[10, 5, 2] == 0, t1[10, 60].tolist()
# 金属区光滑度高于皮肤区
assert t1[10, 60, 1] > t1[10, 5, 1]
# t4.RGB 从基础色派生为原图暗色版
assert 0 < int(t4[10, 5, 0]) < int(base[10, 5, 0]), (t4[10, 5].tolist(), base[10, 5].tolist())
assert t4[10, 5, 1] == 0 and t4[10, 5, 2] == 0, t4[10, 5].tolist()
# 金属区 t4 从底色派生应比基础色暗（蓝通道线性亮度更低）
assert int(t4[10, 60, 2]) < int(base[10, 60, 2]), (t4[10, 60].tolist(), base[10, 60].tolist())
# 原生 sdw.A 更接近二值材质遮罩：皮肤 255，非皮肤 0。
assert t4[10, 5, 3] == 255, t4[10, 5, 3]
assert t4[10, 60, 3] == 0, t4[10, 60, 3]

# 部分通道覆盖：左侧材质是空白黑区，应保留预设；右侧有内容，覆盖 R。
partial = t1.copy()
r_override = np.zeros((size, size), np.uint8)
r_override[:, 32:] = 96
summary = core.apply_packed_mask_channel_overrides(partial, id_map, {0: r_override})
assert summary["mode"] == "partial-material", summary
assert summary["applied"]["R"] == [1], summary
assert partial[10, 5, 0] == t1[10, 5, 0], (partial[10, 5].tolist(), t1[10, 5].tolist())
assert partial[10, 60, 0] == 96, partial[10, 60].tolist()
assert partial[10, 60, 1] == t1[10, 60, 1], "只覆盖 R 时 G 不能被污染"

# 四通道齐全：视为作者提供的完整 t1，整图合成。
complete = t1.copy()
maps = {
    0: np.full((size, size), 10, np.uint8),
    1: np.full((size, size), 20, np.uint8),
    2: np.full((size, size), 30, np.uint8),
    3: np.full((size, size), 40, np.uint8),
}
summary = core.apply_packed_mask_channel_overrides(complete, id_map, maps)
assert summary["mode"] == "complete", summary
assert complete[10, 5].tolist() == [10, 20, 30, 40], complete[10, 5].tolist()
assert complete[10, 60].tolist() == [10, 20, 30, 40], complete[10, 60].tolist()

# 单通道极值 t4 派生应稳定（纯黑基础不报错）
black = np.zeros((4, 4, 3), np.uint8)
shade = core.shade_color_from_base(black, 0.5, -6, 1.1)
assert shade.shape == (4, 4, 3)

print("material_bake_smoke OK")
