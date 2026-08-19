"""Blender 侧的两个按钮：① 适配 ② 导出 mod。

作者只开 Blender。这里做三件 Blender 才做得了的事——摆 T-pose、看一眼模型合不合格、
把模型和作者的声明交出去——然后调用无头 Unity 完成学马那一侧的全部规矩（补必需节点、
材质语义、摇物、扭转驱动器、打包）。作者不需要打开 Unity，也不需要知道它存在。

分工的判据是「这一步改的是作者的东西还是学马的东西」：
改作者的（姿势、权重、贴图）留在 Blender，他看得见；改学马的留在 Unity，他不用管。
"""
import json
import subprocess
from pathlib import Path

import bpy
from bpy.props import StringProperty
from bpy.types import Operator
from mathutils import Vector

# 学马的静止姿势：530 套原版实测完全一致——双臂精确贴身体的左右轴，双腿贴向下，最大偏差 4.0°。
# 出包姿势的误差会 1:1 传到每一条动画上，所以这是硬要求，不是风格。
#
# 方向不写死成 (±1,0,0)：FBX 的上轴和左右手性各家不同（这副原神模型在 Blender 的骨架局部空间里
# 是 Y-up，而且左右与 Unity 相反，硬编码会读出 124.7° 的假偏差）。改成从骨架自己量出一组基，
# 任何导入约定都成立。
T_POSE_LIMBS = [
    ("LeftArm", "LeftForeArm", "left"),
    ("LeftForeArm", "LeftHand", "left"),
    ("RightArm", "RightForeArm", "right"),
    ("RightForeArm", "RightHand", "right"),
    ("LeftUpLeg", "LeftLeg", "down"),
    ("LeftLeg", "LeftFoot", "down"),
    ("RightUpLeg", "RightLeg", "down"),
    ("RightLeg", "RightFoot", "down"),
]


def body_basis(armature, source_of):
    """从骨架量出「上 / 角色自己的左 / 前」三个方向。"""
    bones = armature.data.bones

    def head(name):
        actual = source_of.get(name, name)
        return bones[actual].head_local if actual in bones else None

    hips, headb = head("Hips"), head("Head")
    left_leg, right_leg = head("LeftUpLeg"), head("RightUpLeg")
    if hips is None or headb is None or left_leg is None or right_leg is None:
        return None
    up = (headb - hips)
    left = (left_leg - right_leg)
    if up.length < 1e-6 or left.length < 1e-6:
        return None
    up = up.normalized()
    left = (left - up * left.dot(up)).normalized()
    return {"up": up, "left": left, "right": -left, "down": -up,
            "forward": up.cross(left).normalized()}

# Unity 侧要求的 52 根人形骨名（Humanoid 全集）。
HUMANOID = (
    ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head"]
    + [f"{s}{b}" for s in ("Left", "Right")
       for b in ("Shoulder", "Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot", "ToeBase")]
    + [f"{s}Hand{f}{j}" for s in ("Left", "Right")
       for f in ("Index", "Middle", "Ring", "Pinky", "Thumb") for j in (1, 2, 3)]
)
REQUIRED = ["Hips", "Spine", "Head", "LeftArm", "LeftForeArm", "LeftHand",
            "RightArm", "RightForeArm", "RightHand", "LeftUpLeg", "LeftLeg", "LeftFoot",
            "RightUpLeg", "RightLeg", "RightFoot"]


def bone_map(armature):
    """源骨名 → 学马骨名。用插件现有的 8 张预设表，名字对不上时返回原名。

    没有这一步，下面所有按学马骨名找骨的探针都会一根也匹配不上，然后安静地报 0.0°——
    冒烟测试第一次跑出来就是这个假绿灯。
    """
    from . import core, topology_map
    names = [b.name for b in armature.data.bones]
    try:
        result = core.build_bone_remap(names, HUMANOID)
        mapping = dict(result.get("bones") or {})
    except Exception:
        mapping = {}
    # 预设表没覆盖到必需骨（骨名不属于那八家）就退到结构识别——人体只有一种拓扑。
    if any(bone not in set(mapping.values()) for bone in REQUIRED):
        guessed = topology_map.build(armature)
        if guessed:
            for source, humanoid in guessed.items():
                mapping.setdefault(source, humanoid)
    return {name: mapping.get(name, name) for name in names}


def _armature(context):
    obj = context.object
    if obj and obj.type == "ARMATURE":
        return obj
    if obj and obj.type == "MESH" and obj.find_armature():
        return obj.find_armature()
    for candidate in context.scene.objects:
        if candidate.type == "ARMATURE":
            return candidate
    return None


def _meshes_of(armature):
    return [o for o in bpy.data.objects if o.type == "MESH" and o.find_armature() is armature]


def rest_pose_error(armature, mapping=None):
    """出包姿势离标准 T-pose 有多远，取最大的那一段。"""
    mapping = mapping or bone_map(armature)
    source_of = {gakumas: source for source, gakumas in mapping.items()}
    basis = body_basis(armature, source_of)
    if basis is None:
        return None, None
    bones = armature.data.bones
    worst, limb = 0.0, None
    matched = 0
    for parent, child, axis in T_POSE_LIMBS:
        label = parent
        parent, child = source_of.get(parent, parent), source_of.get(child, child)
        if parent not in bones or child not in bones:
            continue
        matched += 1
        direction = (bones[child].head_local - bones[parent].head_local)
        if direction.length < 1e-6:
            continue
        angle = direction.normalized().angle(basis[axis])
        degrees = angle * 57.2957795
        if degrees > worst:
            worst, limb = degrees, label
    # 一根探针都没命中 = 骨名映射没建起来，不能当成「姿势没问题」。
    return (worst, limb) if matched else (None, None)


class GMI_OT_pose_t_pose(Operator):
    """把骨架摆成学马的标准 T-pose 并应用为静止姿势"""

    bl_idname = "gmi.pose_t_pose"
    bl_label = "摆 T-pose"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        armature = _armature(context)
        if armature is None:
            self.report({"ERROR"}, "场景里没有骨架")
            return {"CANCELLED"}

        mapping = bone_map(armature)
        source_of = {gakumas: source for source, gakumas in mapping.items()}
        shaped = [m.name for m in _meshes_of(armature) if m.data.shape_keys]
        if shaped:
            self.report({"ERROR"},
                        f"这些网格有形态键，Blender 不允许在它们上面应用骨架修改器：{', '.join(shaped[:3])}。"
                        "学马的身体不用形态键（表情走骨），删掉后再点一次")
            return {"CANCELLED"}

        before, _ = rest_pose_error(armature, mapping)
        if before is None:
            self.report({"ERROR"}, "骨名对不上学马的人形骨，先在骨骼映射表里对好")
            return {"CANCELLED"}
        previous = context.view_layer.objects.active
        context.view_layer.objects.active = armature
        bpy.ops.object.mode_set(mode="POSE")
        try:
            moved = 0
            # `bone.head_local`（基是用它量的）和 `pose_bone.head` 都在骨架物体空间，不需要任何
            # 转换。先前乘了一次 matrix_world，那里面正好有 FBX 导入留下的 90°，腿被整整转歪 90°。
            basis = body_basis(armature, source_of)
            # 两轮：转父骨会带着子骨一起走，一轮下来子骨还差几度（实测 5.9°），第二轮收到 1° 内。
            for _ in range(2):
             for parent, child, axis in T_POSE_LIMBS:
                bone = armature.pose.bones.get(source_of.get(parent, parent))
                target = armature.pose.bones.get(source_of.get(child, child))
                if bone is None or target is None:
                    continue
                current = (target.head - bone.head)
                if current.length < 1e-6:
                    continue
                # 父骨先转、子骨后转（顺序在 T_POSE_LIMBS 里）。
                turn = current.normalized().rotation_difference(basis[axis])
                matrix = bone.matrix.copy()
                matrix.translation = Vector((0, 0, 0))
                rotated = turn.to_matrix().to_4x4() @ matrix
                rotated.translation = bone.matrix.translation
                bone.matrix = rotated
                context.view_layer.update()
                moved += 1
            bpy.ops.object.mode_set(mode="OBJECT")
            # 应用为静止姿势：Blender 自己会把蒙皮和 bindpose 一起搬过去，这一步交给 DCC
            # 比在导出侧重算网格安全得多。
            for mesh in _meshes_of(armature):
                for modifier in mesh.modifiers:
                    if modifier.type == "ARMATURE":
                        with context.temp_override(object=mesh):
                            bpy.ops.object.modifier_copy(modifier=modifier.name)
                            bpy.ops.object.modifier_apply(modifier=modifier.name)
            context.view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode="POSE")
            bpy.ops.pose.armature_apply(selected=False)
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")
            context.view_layer.objects.active = previous

        after, limb = rest_pose_error(armature, mapping)
        self.report({"INFO"}, f"摆正 {moved} 段：离标准 T-pose {before:.1f}° → {after:.1f}°")
        return {"FINISHED"}


def check(context):
    """出一份「作者能看懂、每条带下一步」的检查结果。"""
    findings = []
    armature = _armature(context)
    if armature is None:
        return [{"level": "fail", "message": "场景里没有骨架", "action": "先导入模型"}], None

    mapping = bone_map(armature)
    bones = set(mapping.values())
    missing_required = [b for b in REQUIRED if b not in bones]
    missing_optional = [b for b in HUMANOID if b not in bones and b not in REQUIRED]
    if missing_required:
        findings.append({
            "level": "fail",
            "message": f"缺 {len(missing_required)} 根必需人形骨：{', '.join(missing_required[:6])}",
            "action": "先在骨骼映射表里把它们对上，或者这副骨架做不了",
        })
    else:
        findings.append({"level": "ok", "message": f"人形骨齐全（可选骨缺 {len(missing_optional)} 根）"})

    worst, limb = rest_pose_error(armature, mapping)
    if worst is None:
        findings.append({"level": "fail", "message": "骨名对不上，姿势无法判断",
                         "action": "先在骨骼映射表里把人形骨对上"})
    elif worst > 20:
        findings.append({"level": "fail", "message": f"静止姿势离 T-pose 太远（{limb} 偏 {worst:.0f}°）",
                         "action": "点上面的「摆 T-pose」"})
    elif worst > 10:
        findings.append({"level": "warn", "message": f"静止姿势有点歪（{limb} 偏 {worst:.0f}°），动画会跟着偏",
                         "action": "建议点「摆 T-pose」"})
    else:
        findings.append({"level": "ok", "message": f"静止姿势是 T-pose（最大偏 {worst:.1f}°）"})

    meshes = _meshes_of(armature)
    if not meshes:
        findings.append({"level": "fail", "message": "骨架上没有蒙皮网格", "action": "检查网格的骨架修改器"})
    else:
        materials = [slot.material.name for mesh in meshes for slot in mesh.material_slots if slot.material]
        if not materials:
            findings.append({"level": "fail", "message": "网格没有材质", "action": "至少给每段几何一个材质"})
        else:
            findings.append({"level": "ok", "message": f"{len(meshes)} 个网格 / {len(materials)} 个材质"})

    # 孤立单骨的衣物骨：层 0 是锚定层，一根骨的飘带在游戏里不会动。
    lonely = []
    for bone in armature.data.bones:
        if mapping.get(bone.name) in HUMANOID or bone.children:
            continue
        if bone.parent and mapping.get(bone.parent.name) not in HUMANOID:
            lonely.append(bone.name)
    if lonely:
        findings.append({
            "level": "warn",
            "message": f"{len(lonely)} 根装饰骨是孤立单骨，游戏里不会动：{', '.join(lonely[:4])}",
            "action": "想让它动就各加一根尾骨（一条链至少两根）",
        })
    return findings, armature


class GMI_OT_check_adapt(Operator):
    """检查这副模型能不能做成学马 mod，问题都写成下一步"""

    bl_idname = "gmi.check_adapt"
    bl_label = "适配检查"

    def execute(self, context):
        findings, _ = check(context)
        context.scene.gmi_unity_report = json.dumps(findings, ensure_ascii=False)
        for item in findings:
            level = {"ok": "INFO", "warn": "WARNING", "fail": "ERROR"}[item["level"]]
            self.report({level}, item["message"])
        return {"FINISHED"}


def _find_unity():
    """按 Unity Hub 的默认布局找编辑器；作者只需要装一次，之后不再露面。"""
    roots = [Path(r"C:/Program Files/Unity/Hub/Editor"), Path(r"D:/Unity/Hub/Editor")]
    found = []
    for root in roots:
        if root.is_dir():
            found += [p for p in root.glob("*/Editor/Unity.exe")]
    # 6000.x 优先：SDK 工程是这个大版本建的
    found.sort(key=lambda p: (not p.parts[-3].startswith("6000"), p.parts[-3]), reverse=False)
    return str(found[0]) if found else ""


class GMI_OT_export_unity_mod(Operator):
    """导出 FBX + 任务文件，调用无头 Unity 打出 bundle"""

    bl_idname = "gmi.export_unity_mod"
    bl_label = "导出 mod"

    target: StringProperty(name="替换目标", default="mdl_chr_hmsz-cstm-0059_body")

    def execute(self, context):
        scene = context.scene
        findings, armature = check(context)
        if any(f["level"] == "fail" for f in findings):
            scene.gmi_unity_report = json.dumps(findings, ensure_ascii=False)
            self.report({"ERROR"}, "适配检查没过，先解决红色的项")
            return {"CANCELLED"}

        sdk = scene.gmi_unity_sdk_dir
        if not sdk or not (Path(sdk) / "Assets").is_dir():
            self.report({"ERROR"}, "先在面板里指定 Unity SDK 工程目录")
            return {"CANCELLED"}
        unity = scene.gmi_unity_editor or _find_unity()
        if not unity or not Path(unity).exists():
            self.report({"ERROR"}, "找不到 Unity 编辑器，请在面板里指定 Unity.exe")
            return {"CANCELLED"}

        out = Path(bpy.path.abspath(scene.gmi_output_dir or "//")) / "gmi-unity"
        out.mkdir(parents=True, exist_ok=True)
        fbx = out / "source.fbx"
        meshes = _meshes_of(armature)
        bpy.ops.object.select_all(action="DESELECT")
        for obj in meshes + [armature]:
            obj.select_set(True)
        context.view_layer.objects.active = armature
        # apply_scale_options 必须是 FBX_SCALE_UNITS：默认那档把「米→厘米」的换算写成节点上的
        # ×100 缩放，导出来的骨架每根骨都带 scale 100、网格只有 1.6cm 高，bindpose 随即对不上
        # （实测 240/257 根偏，最大 868mm）。骨上带缩放是这条管线的硬地板之一。
        bpy.ops.export_scene.fbx(
            filepath=str(fbx), use_selection=True, add_leaf_bones=False,
            bake_anim=False, mesh_smooth_type="FACE", path_mode="COPY", embed_textures=False,
            global_scale=1.0, apply_scale_options="FBX_SCALE_UNITS", apply_unit_scale=True)

        job = {
            "kind": scene.gmi_unity_kind,
            "target": self.target or scene.gmi_unity_target,
            "fbx": str(fbx).replace("\\", "/"),
            "outputDirectory": str(out / "out").replace("\\", "/"),
            "keepMeshes": [m.name for m in meshes],
            "materials": [
                {"name": slot.material.name, "role": "cloth", "bareSkin": False}
                for mesh in meshes for slot in mesh.material_slots if slot.material
            ],
        }
        job_path = out / "job.json"
        job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

        log = out / "unity.log"
        # 不带 -nographics：那个 flag 连图形设备都不创建，预览图就渲不出来。批处理照样无窗口。
        result = subprocess.run(
            [unity, "-batchmode", "-quit", "-projectPath", sdk,
             "-executeMethod", "GakumasSdk.ModBuilder.Build",
             "-gmiJob", str(job_path), "-logFile", str(log)],
            capture_output=True, text=True)

        report_path = Path(job["outputDirectory"]) / "report.json"
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            findings += report.get("findings", [])
            scene.gmi_unity_report = json.dumps(findings, ensure_ascii=False)
            load_previews(report.get("previews") or [])
            if report.get("ok"):
                self.report({"INFO"}, f"完成 → {report.get('bundle')}")
                return {"FINISHED"}
            self.report({"ERROR"}, "Unity 侧构建未通过，见面板里的报告")
            return {"CANCELLED"}

        scene.gmi_unity_report = json.dumps(
            findings + [{"level": "fail", "message": "Unity 没有产出报告",
                         "action": f"看日志 {log}"}], ensure_ascii=False)
        self.report({"ERROR"}, f"Unity 构建失败（退出码 {result.returncode}），日志 {log}")
        return {"CANCELLED"}


# 预览图：Unity 渲好回传路径，这里加载进 Blender 的预览集合，面板直接画出来。
# 作者看图不看数——这一整天的教训就是闸门全绿而画面不对，数字对作者更没有意义。
_previews = None
PREVIEW_KEYS = []


def load_previews(paths):
    global _previews
    import bpy.utils.previews
    if _previews is None:
        _previews = bpy.utils.previews.new()
    PREVIEW_KEYS.clear()
    for index, path in enumerate(paths):
        if not Path(path).exists():
            continue
        key = f"gmi_preview_{index}"
        if key in _previews:
            del _previews[key]
        _previews.load(key, str(path), "IMAGE")
        PREVIEW_KEYS.append(key)


def preview_icon(key):
    return _previews[key].icon_id if _previews and key in _previews else 0


def unregister_previews():
    global _previews
    if _previews is not None:
        import bpy.utils.previews
        bpy.utils.previews.remove(_previews)
        _previews = None


CLASSES = (GMI_OT_pose_t_pose, GMI_OT_check_adapt, GMI_OT_export_unity_mod)
