from pathlib import Path

import bpy


archive = Path(r"D:\GIT\gakumas-modding\dist\gakumas_mi-0.3.0.zip")
result = bpy.ops.preferences.addon_install(filepath=str(archive), overwrite=True)
assert result == {"FINISHED"}, result
result = bpy.ops.preferences.addon_enable(module="gakumas_mi")
assert result == {"FINISHED"}, result
assert hasattr(bpy.types.Scene, "gmi_profile_dir")
profile = Path(bpy.context.scene.gmi_profile_dir)
assert (profile / "profile.json").is_file()
assert (profile / "Reference" / "Geo_Body.json").is_file()
print("GMI_INSTALL_OK", archive.stat().st_size)
