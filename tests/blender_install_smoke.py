import sys
from pathlib import Path

import bpy


args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
assert len(args) == 1, "usage: blender ... --python blender_install_smoke.py -- <addon.zip>"
archive = Path(args[0]).resolve()
assert archive.is_file(), archive
result = bpy.ops.preferences.addon_install(filepath=str(archive), overwrite=True)
assert result == {"FINISHED"}, result
result = bpy.ops.preferences.addon_enable(module="gakumas_mi")
assert result == {"FINISHED"}, result
assert hasattr(bpy.types.Scene, "gmi_profile_dir")
profile = Path(bpy.context.scene.gmi_profile_dir)
assert (profile / "profile.json").is_file()
print("GMI_INSTALL_OK", bpy.app.version_string, archive.stat().st_size)
