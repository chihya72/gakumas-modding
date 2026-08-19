// What the author tells the SDK about their own materials.
//
// This game does not carry "surface kind" anywhere the SDK could read it: the toon threshold,
// smoothness, AO, outline colour and rim term are baked per material into t1 and the vertex COLOR,
// and stock costumes pick them by what the surface *is*. A model from anywhere else has none of that,
// so the author says it once, here, and the SDK reads it back on every later build.
//
// Deliberately two fields, because one is not enough:
//
//   surface       what this whole material section is — drives the t1 constants and the COLOR preset
//   hasBareSkin   whether this same section *also* covers bare skin
//
// The second exists because the skin/cloth split is not per material in this game. Stock `m_bdy`
// covers a dress and bare legs at once (hmsz-cstm-0059's first submesh holds 141 distinct COLOR
// values), and the split lives per texel in `t4.A` — a binary skin mask — and per vertex in COLOR.
// So a per-submesh dropdown alone cannot express it: tick hasBareSkin and the SDK resolves the split
// per texel, preferring a painted `*_<group>_skin.png` next to the textures and falling back to a
// colour heuristic (measured against stock: precision 0.94 / recall 0.95).
//
// An asset, not a component on the prefab: a MonoBehaviour of ours would be serialised into the
// bundle as a script the game cannot resolve, and would have to be stripped on the way out. This way
// there is nothing to strip and nothing to ship — and the author has a stable file to edit between
// builds instead of a component that gets rebuilt from scratch each import.
using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace GakumasSdk
{
    /// <summary>Surface kinds stock costumes distinguish. Names match gakumas_mi/material_presets.json.</summary>
    public enum SurfaceClass
    {
        Cloth = 0,
        Skin,
        LeatherPlastic,
        LeatherShoe,
        Metal,
    }

    [Serializable]
    public class SubmeshLabel
    {
        [Tooltip("只作对照，改它不影响构建")]
        public string material;

        public SurfaceClass surface = SurfaceClass.Cloth;

        [Tooltip("这块材质里同时有裸露皮肤（例如连衣裙和大腿共用一张图）")]
        public bool hasBareSkin;
    }

    public class GakumasBodyLabels : ScriptableObject
    {
        [Tooltip("按 submesh 顺序，一项一个材质段")]
        public List<SubmeshLabel> submeshes = new List<SubmeshLabel>();

        public SubmeshLabel For(int submesh) =>
            submesh >= 0 && submesh < submeshes.Count ? submeshes[submesh] : null;

        /// <summary>
        /// Loads the author's labels, creating them with a stock-shaped guess for any submesh not yet
        /// described. Existing entries are never overwritten — the author's edits are the input.
        /// </summary>
        public static GakumasBodyLabels LoadOrCreate(string assetPath, int submeshes, Func<int, string> groupFor)
        {
            var labels = AssetDatabase.LoadAssetAtPath<GakumasBodyLabels>(assetPath);
            var created = labels == null;
            if (created)
            {
                labels = CreateInstance<GakumasBodyLabels>();
                AssetDatabase.CreateAsset(labels, assetPath);
            }

            var added = 0;
            while (labels.submeshes.Count < submeshes)
            {
                var slot = labels.submeshes.Count;
                // Stock layout: the main sheet is a costume that also covers bare skin, the accessory
                // sheets are cloth only.
                labels.submeshes.Add(new SubmeshLabel
                {
                    material = $"m_{groupFor(slot)}",
                    surface = SurfaceClass.Cloth,
                    hasBareSkin = groupFor(slot) == "bdy",
                });
                added++;
            }
            if (added > 0)
                EditorUtility.SetDirty(labels);

            var summary = string.Join(", ", labels.submeshes.ConvertAll(item =>
                $"{item.material}={item.surface}{(item.hasBareSkin ? "+皮肤" : "")}"));
            Debug.Log($"[SDK] 材质标注 {(created ? "已新建" : "读自")} {assetPath}：{summary}" +
                      (added > 0 ? $"（{added} 项按原版布局猜的，作者可改后重新构建）" : ""));
            return labels;
        }
    }
}
