# Headless Blender exporter: yuika.blend -> .gmim binary for the PC IL2CPP probe.
#   blender -b yuika.blend --python export_gmim.py -- out.gmim
#   blender -b yuika.blend --python export_gmim.py -- out.gmim --alpha-texture atlas.png --alpha-cutoff 0.33
#   blender -b yuika.blend --python export_gmim.py -- out.gmim --cutout-materials 3,7 --alpha-cutoff 0.33
#
# Exports the largest mesh: vertices/normals/uv (Unity axes) + per-vertex top-4
# bone weights keyed by BONE NAME (= vertex group name after GakumasMI transfer),
# split on (vertex, normal, uv) seams. Bindposes are NOT exported — the DLL reuses
# the live original Geo_Body bindposes (already aligned to the live bones[] order).
#
# Per-submesh render mode (ver>=3): each submesh is opaque (uses the live m_bdy) or
# cutout/co (the DLL clones an m_bdyco-like material that discards A<cutoff). A submesh
# is cutout if its material's `gmi_alpha_mode` is NATIVE_CO/CO (same marking the main
# GakumasMI plugin uses), or its slot index is listed in --cutout-materials, or its
# material name contains "bdyco". This mirrors the real asset's m_bdy + m_bdyco split.
#
# .gmim format (little-endian):
#   "GMIM", u32 ver=3, u32 vertCount, u32 subMeshCount, u32 boneCount
#   boneCount x [u16 nameLen, utf8 name]
#   subMeshCount x [u8 mode(0=opaque,1=cutout/co), f32 cutoff]   <-- ver>=3
#   vertCount x 3f pos ; vertCount x 3f normal ; vertCount x 2f uv
#   vertCount x 4f color (RGBA)          <-- ver>=2
#   vertCount x 4x(i32 boneTableIdx(-1=unused), f32 weight)
#   subMeshCount x [u32 indexCount, indexCount x u32 index]
# Vertex COLOR matters: the Gakumas toon/body shader reads COLOR0; a mesh with no
# color channel samples (0,0,0,0) and the shader takes its "dark" branch -> black body.
import bpy, sys, struct, math

def to_unity(v):  # Blender Z-up/-Y-forward -> Unity Y-up/Z-forward
    return (float(v[0]), float(v[2]), float(-v[1]))

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out_path = argv[0] if argv else "out.gmim"

alpha_texture_path = None
alpha_cutoff = 0.0
cutout_slots = set()        # material slot indices forced to cutout via CLI
i = 1
while i < len(argv):
    if argv[i] == "--alpha-texture" and i + 1 < len(argv):
        alpha_texture_path = argv[i + 1]
        i += 2
    elif argv[i] == "--alpha-cutoff" and i + 1 < len(argv):
        alpha_cutoff = float(argv[i + 1])
        i += 2
    elif argv[i] == "--cutout-materials" and i + 1 < len(argv):
        cutout_slots = {int(x) for x in argv[i + 1].split(",") if x.strip() != ""}
        i += 2
    else:
        i += 1

# cutoff written into the .gmim for cutout submeshes (game-native m_bdyco uses ~0.33).
submesh_cutoff = alpha_cutoff if alpha_cutoff > 0 else 0.33

# pick the largest mesh object
obj = max((o for o in bpy.data.objects if o.type == "MESH"),
          key=lambda o: len(o.data.vertices), default=None)
if obj is None:
    raise SystemExit("no mesh object found")
print(f"[export] object='{obj.name}' verts={len(obj.data.vertices)} mats={len(obj.material_slots)}")

mesh = obj.data
uv_layer = mesh.uv_layers.active or (mesh.uv_layers[0] if mesh.uv_layers else None)
if uv_layer is None:
    raise SystemExit("mesh has no UV layer")
try:
    mesh.calc_tangents(uvmap=uv_layer.name)
except Exception as e:
    print("[export] calc_tangents failed, falling back to loop normals:", e)
    mesh.calc_normals_split()
mesh.calc_loop_triangles()

world = obj.matrix_world
nmat = world.to_3x3().inverted_safe().transposed()
vg_names = {i: g.name for i, g in enumerate(obj.vertex_groups)}

# vertex color attribute (GakumasMI writes the shader-facing attribute as
# "COLOR"; do not trust Blender's active color layer, which may be a preview or
# imported helper layer with values the Gakumas shader does not understand).
col_attr = getattr(mesh, "color_attributes", None)
col_attr = (col_attr.get("COLOR") or col_attr.active_color or (col_attr[0] if len(col_attr) else None)) if col_attr else None
col_corner = (col_attr.domain == "CORNER") if col_attr else False
print(f"[export] color attr: {col_attr.name if col_attr else None} domain={col_attr.domain if col_attr else '-'}")
def loop_color(li, vi):
    if col_attr is None:
        return (1.0, 1.0, 1.0, 1.0)
    c = col_attr.data[li if col_corner else vi].color
    return (float(c[0]), float(c[1]), float(c[2]), float(c[3]))

alpha_image = None
alpha_w = alpha_h = 0
alpha_pixels = None
if alpha_texture_path and alpha_cutoff > 0:
    alpha_image = bpy.data.images.load(alpha_texture_path, check_existing=True)
    alpha_w, alpha_h = alpha_image.size
    alpha_pixels = list(alpha_image.pixels[:])
    print(f"[export] alpha cull texture='{alpha_texture_path}' size={alpha_w}x{alpha_h} cutoff={alpha_cutoff}")

def sample_alpha(uv):
    if not alpha_pixels or alpha_w <= 0 or alpha_h <= 0:
        return 1.0
    u = float(uv[0]) % 1.0
    v = float(uv[1]) % 1.0
    x = min(alpha_w - 1, max(0, int(math.floor(u * alpha_w))))
    y = min(alpha_h - 1, max(0, int(math.floor(v * alpha_h))))
    return float(alpha_pixels[(y * alpha_w + x) * 4 + 3])

# per-vertex top-4 bone weights (by name)
vert_w = {}
for v in mesh.vertices:
    gw = sorted(
        (
            (vg_names[g.group], g.weight)
            for g in v.groups
            if g.weight > 0.0 and not vg_names[g.group].startswith("GMI_")
        ),
        key=lambda x: -x[1],
    )[:4]
    s = sum(w for _, w in gw) or 1.0
    vert_w[v.index] = [(n, w / s) for n, w in gw]

bone_table = {}            # name -> table index
def bone_idx(name):
    if name not in bone_table:
        bone_table[name] = len(bone_table)
    return bone_table[name]

# split on (vertex, normal, uv, color)
positions, normals, uvs, colors, weights = [], [], [], [], []
vmap = {}
submesh = {}               # material_index -> [indices]
culled_triangles = 0
def vkey(li):
    loop = mesh.loops[li]
    vi = loop.vertex_index
    n = to_unity((nmat @ loop.normal).normalized())
    uv = uv_layer.data[li].uv
    col = loop_color(li, vi)
    key = (vi, round(n[0], 4), round(n[1], 4), round(n[2], 4),
           round(uv[0], 5), round(uv[1], 5),
           round(col[0], 3), round(col[1], 3), round(col[2], 3), round(col[3], 3))
    return key, vi, n, (uv[0], uv[1]), col

for lt in mesh.loop_triangles:
    if alpha_pixels:
        tri_uvs = [uv_layer.data[li].uv for li in lt.loops]
        center = (
            (tri_uvs[0][0] + tri_uvs[1][0] + tri_uvs[2][0]) / 3.0,
            (tri_uvs[0][1] + tri_uvs[1][1] + tri_uvs[2][1]) / 3.0,
        )
        alphas = [sample_alpha(uv) for uv in tri_uvs] + [sample_alpha(center)]
        if max(alphas) < alpha_cutoff:
            culled_triangles += 1
            continue
    tri = []
    for li in lt.loops:
        key, vi, n, uv, col = vkey(li)
        idx = vmap.get(key)
        if idx is None:
            idx = len(positions)
            vmap[key] = idx
            positions.append(to_unity(world @ mesh.vertices[vi].co))
            normals.append(n)
            uvs.append(uv)
            colors.append(col)
            w = vert_w.get(vi, [])
            slots = []
            for nm, ww in w:
                slots.append((bone_idx(nm), float(ww)))
            while len(slots) < 4:
                slots.append((-1, 0.0))
            weights.append(slots)
        tri.append(idx)
    submesh.setdefault(lt.material_index, []).extend(tri)

bones = sorted(bone_table, key=lambda k: bone_table[k])
sub_keys = sorted(submesh)

# per-submesh render mode: cutout if material marked NATIVE_CO (same as the main plugin),
# or slot listed in --cutout-materials, or material name contains "bdyco".
def slot_is_cutout(mat_index):
    if mat_index in cutout_slots:
        return True
    mat = obj.material_slots[mat_index].material if mat_index < len(obj.material_slots) else None
    if mat is None:
        return False
    mode = getattr(mat, "gmi_alpha_mode", None)
    if mode in ("NATIVE_CO", "CO", "NATIVE_SECTION"):
        return True
    return "bdyco" in mat.name.lower()

sub_modes = [(1 if slot_is_cutout(k) else 0) for k in sub_keys]
print(f"[export] out verts={len(positions)} submeshes={len(sub_keys)} bones={len(bones)} "
      f"tris={sum(len(submesh[k]) for k in sub_keys)//3} cutoutSubmeshes={sum(sub_modes)}")
for k, m in zip(sub_keys, sub_modes):
    nm = obj.material_slots[k].material.name if k < len(obj.material_slots) and obj.material_slots[k].material else "?"
    print(f"[export]   submesh slot={k} material='{nm}' mode={'cutout' if m else 'opaque'}")
if alpha_pixels:
    print(f"[export] alpha culled triangles={culled_triangles}")

with open(out_path, "wb") as f:
    f.write(b"GMIM")
    f.write(struct.pack("<IIII", 3, len(positions), len(sub_keys), len(bones)))
    for nm in bones:
        b = nm.encode("utf-8")
        f.write(struct.pack("<H", len(b))); f.write(b)
    for m in sub_modes:
        f.write(struct.pack("<Bf", m, submesh_cutoff))   # ver>=3: per-submesh mode + cutoff
    for p in positions: f.write(struct.pack("<3f", *p))
    for n in normals:   f.write(struct.pack("<3f", *n))
    for u in uvs:       f.write(struct.pack("<2f", *u))
    for c in colors:    f.write(struct.pack("<4f", *c))
    for slots in weights:
        for bi, ww in slots: f.write(struct.pack("<if", bi, ww))
    for k in sub_keys:
        idxs = submesh[k]
        f.write(struct.pack("<I", len(idxs)))
        f.write(struct.pack("<%dI" % len(idxs), *idxs))
print(f"[export] wrote {out_path}")
