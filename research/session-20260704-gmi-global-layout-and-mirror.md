# 2026-07-04 GakumasMI Global Layout And Mirror Session

## Background

This session started from the goal of avoiding per-costume or per-character pixel shader / texture hashes for body texture layout adaptation.

The initial working idea was a global landmark texture:

- Texture hash: `0ff26bed`
- Resource type from FrameAnalysis: `Texture2D`, `64x64`, array `6`, format `R9G9B9E5_SHAREDEXP`, `texturecube`
- Observed layout rule:
  - A: base/mask at `ps-t0/ps-t1`, landmark at `ps-t2`
  - B: base/mask at `ps-t1/ps-t2`, landmark at `ps-t3`
  - C/mirror-like: base/mask at `ps-t0/ps-t1`, no landmark at `ps-t3`

Important conclusion: only B moves base/mask and causes the severe checkerboard-style corruption. A and C can share the same base/mask binding.

## What Went Wrong Mid-Session

Several temporary fixes were tried and then rejected:

- Per-costume shade probes were added for C detection:
  - `92920b63`
  - `bb5905b2`
  - `9bb4042f`
  - `c2e32f4f`
  - `792b424a`
  - `8321a82b`
  - `66573a90`
- This reintroduced exactly the problem the session was meant to avoid: recording one-off costume shade hashes.
- It also caused normal and mirror scenes to receive wrong custom shade bindings.
- Temporary Chisaki-specific skips were added:
  - `1a922dbd`
  - `55266f0f`
- Local asset analysis later proved those are not Chisaki body leftovers. They are game prop meshes from `mdl_prp_ssdrink-normal-00_ssdrink`:
  - `1a922dbd` matches `Geo_Water`, `indexCount = 2232`
  - `55266f0f` matches `Geo_Ssdrink`, `indexCount = 6288`, plus a later `first = 6288, count = 2280` draw
- Therefore skipping them was a bad direction: it removed a common game prop, not a body residual.

## Local Resource Analysis

Inputs used:

- FrameAnalysis folders:
  - `D:/Games/gakumas/FrameAnalysis-2026-07-04-035746`
  - `D:/Games/gakumas/FrameAnalysis-2026-07-04-040408`
  - `D:/Games/gakumas/FrameAnalysis-2026-07-04-041930`
  - `D:/Games/gakumas/FrameAnalysis-2026-07-04-042601`
  - `D:/Games/gakumas/FrameAnalysis-2026-07-04-043506`
- AssetRipper install:
  - `C:/Users/10725/Downloads/AssetRipper_win_x64`
- Local decrypted asset bundles:
  - `D:/GIT/Gakuen-idolmaster-ab-decrypt/output/asset_bundle`
- Scriptable analysis also used UnityPy and AssetStudio CLI because AssetRipper available here is the local web GUI form.

Analysis artifacts written under:

- `D:/GIT/gakumas-modding/build/layout-universal-analysis/`

Useful findings:

- All `mdl_chr_*-cstm-0140_body` body meshes have `Geo_Body` submeshes `76890 + 1071`; they do not match the `2232/6288/2280` residual draw counts.
- `5bb30edf` matches the standard `_CombinedFaceMesh` split pattern, not a body extra.
- `8423ce4e` is a large face/body-like draw in the surrounding character pass and should not be skipped blindly.
- The suspicious 512x512 atlas seen in mirror frames is a costume/face/prop material atlas, not a body shade map and not a stable body-layout landmark.
- The robust stable landmark remains `0ff26bed`, and only for B-layout detection at `ps-t3`.

## Final Runtime Strategy

The final strategy intentionally removes C/shade detection:

- `layout = 0`: default A/C
  - bind only:
    - `ps-t0 = Resource...Basecolor`
    - `ps-t1 = Resource...Packedmask`
  - do not bind custom shade in A/C.
- `layout = 1`: B, detected by `0ff26bed` at `ps-t3`
  - bind:
    - `ps-t1 = Resource...Basecolor`
    - `ps-t2 = Resource...Packedmask`
    - `ps-t5 = Resource...Shadecolor`

Tradeoff:

- A/C no longer use the mod's custom shade map, so shade color may differ slightly from the authored mod.
- In exchange, A/C and mirror scenes no longer get wrong shade-slot overwrites.
- No per-costume shade hash is required.

## Files Changed In Game Mods

All active mod INI files were backed up before the final edit:

- `D:/Games/gakumas/Mods/author.hski.my-mod/mod.ini.bak.20260704-051359`
- `D:/Games/gakumas/Mods/bangdream/mod.ini.bak.20260704-051359`
- `D:/Games/gakumas/Mods/chisaki/mod.ini.bak.20260704-051359`
- `D:/Games/gakumas/Mods/fuyuko/mod.ini.bak.20260704-051359`
- `D:/Games/gakumas/Mods/mltd2/mod.ini.bak.20260704-051359`
- `D:/Games/gakumas/Mods/saki/mod.ini.bak.20260704-051359`

Edited:

- `D:/Games/gakumas/Mods/author.hski.my-mod/mod.ini`
- `D:/Games/gakumas/Mods/bangdream/mod.ini`
- `D:/Games/gakumas/Mods/chisaki/mod.ini`
- `D:/Games/gakumas/Mods/fuyuko/mod.ini`
- `D:/Games/gakumas/Mods/mltd2/mod.ini`
- `D:/Games/gakumas/Mods/saki/mod.ini`

Added:

- `D:/Games/gakumas/Mods/gmi_common/mod.ini`

Final shared probe lives in `gmi_common`:

```ini
[TextureOverrideGmiBodyLayoutLandmark]
hash = 0ff26bed
match_priority = 0
$\Mods\author.hski.my-mod\mod.ini\gmi_AuthorHskiMyMod_probe = 1
$\Mods\bangdream\mod.ini\gmi_Bangdream_probe = 1
$\Mods\chisaki\mod.ini\gmi_Chisaki_probe = 1
$\Mods\fuyuko\mod.ini\gmi_Fuyuko_probe = 1
$\Mods\mltd2\mod.ini\gmi_Mltd2_probe = 1
$\Mods\saki\mod.ini\gmi_Saki_probe = 1
```

Removed from active INIs:

- all `_cprobe` constants
- all `layout == 2` branches
- all `checktextureoverride = ps-t2` shade checks
- all costume shade probe `TextureOverride`s
- Chisaki-only `TextureOverrideChisakiBodyExtra0/1`

## Validation

Static checks after the final edit:

- Active mod INIs contain only one `0ff26bed` override, in `gmi_common`.
- No active `_cprobe` remains.
- No active `layout == 2` remains.
- No active `1a922dbd` / `55266f0f` skip remains.
- No active A/C `ps-t4 = Resource...Shadecolor` binding remains.
- B still binds shade at `ps-t5`.

FrameAnalysis replay checks:

- Existing mirror/normal FA logs replay to A/C for the relevant body draws, so the new logic only writes `ps-t0/ps-t1` there.
- B will still be detected only when `0ff26bed` is currently bound at `ps-t3`.

Runtime status:

- At the time of recording, `gakumas.exe` was not running.
- `D:/Games/gakumas/d3d11_log.txt` last write time was still `2026-07-04 04:35:58`, so no fresh F10 reload log existed after the final edit.
- Next manual verification should launch the game or press F10 after starting it, then check for:
  - no duplicate `0ff26bed` warnings
  - no `Unrecognised entry: $gmi_*_probe = 1` warnings
  - no mirror shade corruption
  - no missing `ssdrink` prop / unintended object deletion

## Rule For Future Work

Do not add per-costume PS or shade texture hashes to solve this layout problem.

If another scene breaks:

1. First classify it as base/mask layout, shade-only, or unrelated renderer.
2. Use FrameAnalysis state replay, not a screenshot guess.
3. If a suspicious IB appears, reverse-map it to local Unity assets before skipping it.
4. Treat `0ff26bed` at `ps-t2` (A) / `ps-t3` (B) as the current global layout signals.

## Update (same day, superseding "Final Runtime Strategy" above)

The "Final Runtime Strategy" section above is now partially superseded. Two changes landed after it:

1. **A-detection restored (custom shade back in normal scenes).** `0ff26bed` sits at
   `ps-t2` in layout A, so a second probe `checktextureoverride = ps-t2` recovers layout A
   and re-binds the mod's custom `shade` at `ps-t4`. This is still costume-independent (the
   landmark is global), so it does NOT reintroduce per-costume shade hashes. Final layout map:
   - `ps-t2` landmark → A → `t0/t1/t4`
   - `ps-t3` landmark → B → `t1/t2/t5`
   - neither → C/unknown → `t0/t1` only (no custom shade, safe)
2. **Self-contained per-mod, `gmi_common` dropped.** Each mod inlines its own
   `[TextureOverride<Mod>BodyLayoutLandmark] hash=0ff26bed` (with a distinct `match_priority`,
   NOT `allow_duplicate_hash` — that entry is only valid on ShaderOverride and warns on
   TextureOverride) setting its own local `$gmi_<Mod>_probe`. This removes the unverified
   cross-INI `$\Mods\...` variable syntax and lets each mod be copied/distributed alone.
   `gmi_common` was renamed to `DISABLED.gmi_common.bak` (excluded by `exclude_recursive`).
3. **Verified:** clean game restart, 3DMigoto log shows zero `Unrecognised entry` and zero
   `Duplicate TextureOverride hash=0ff26bed` warnings; six distinct `match_priority` values
   registered.
4. **Baked into the Blender add-on (gakumas-mi 0.7.2).** `gakumas_mi/core.py` now generates
   this structure automatically (`_landmark_layout_sections` / `_landmark_binding_block`); the
   old per-PS `slotVariant` code path was deleted. Authors never touch PS hashes again.
