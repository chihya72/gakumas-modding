// The whole SDK behind one command line, so the author never opens Unity.
//
//   Unity.exe -batchmode -quit -nographics -projectPath <sdk> \
//       -executeMethod GakumasSdk.ModBuilder.Build \
//       -gmiJob <job.json>
//
// The job file is written by the Blender addon and answers only what the SDK cannot work out for
// itself: which file, which character it replaces, which meshes are the body, and what the author
// knows about their own materials. Everything else — bone names, rest pose check, required nodes,
// physics, textures, packing — is this game's rules, and rules do not belong in the author's head.
//
// It writes `report.json` next to the bundle: a pass/fail list in plain sentences, each failure with
// the next action. Numbers stay in the log. The addon shows the sentences.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace GakumasSdk
{
    public static class ModBuilder
    {
        [Serializable]
        public class MaterialLabel
        {
            public string name;
            public string role = "cloth";   // cloth / skin / leather / shoe / metal
            public bool bareSkin;
        }

        [Serializable]
        public class ChainLabel
        {
            public string root;
            public string category;         // skirt / sleeve / ribbon / cloth / skin
        }

        [Serializable]
        public class TwistLabel
        {
            public string bone;
            public string role;             // LeftArm_Roll_H 等，见 TwistAdopter.Roles
        }

        [Serializable]
        public class Job
        {
            public string kind = "body";
            public string target;
            public string fbx;
            public string outputDirectory;
            public string[] keepMeshes;
            public string[] dropMaterials;
            public MaterialLabel[] materials;
            public ChainLabel[] chains;
            public TwistLabel[] twist;
            public bool stockJointRig;
        }

        [Serializable]
        private class Finding
        {
            public string level;            // ok / warn / fail
            public string message;
            public string action;
        }

        [Serializable]
        private class Report
        {
            public bool ok;
            public string bundle;
            public string modelName;
            public int bones;
            public int vertices;
            public int submeshes;
            public string[] previews = new string[0];
            public List<Finding> findings = new List<Finding>();
        }

        public static void Build()
        {
            var report = new Report();
            string outputDirectory = null;
            try
            {
                var job = ReadJob();
                outputDirectory = job.outputDirectory;
                Run(job, report);
            }
            catch (Exception error)
            {
                report.ok = false;
                report.findings.Add(new Finding
                {
                    level = "fail",
                    message = $"构建中断：{error.Message}",
                    action = "把这条和日志一起发给开发者",
                });
                Debug.LogError($"[SDK] {error}");
            }
            Write(report, outputDirectory);
            // Batchmode exit code, so the addon can tell failure from a crash without parsing text.
            if (!report.ok)
                EditorApplication.Exit(1);
        }

        private static Job ReadJob()
        {
            var args = Environment.GetCommandLineArgs();
            var index = Array.IndexOf(args, "-gmiJob");
            if (index < 0 || index + 1 >= args.Length)
                throw new Exception("命令行缺 -gmiJob <job.json>");
            var path = args[index + 1];
            if (!File.Exists(path))
                throw new Exception($"找不到任务文件 {path}");
            var job = JsonUtility.FromJson<Job>(File.ReadAllText(path));
            if (job == null || string.IsNullOrEmpty(job.fbx))
                throw new Exception($"任务文件读不出 fbx 字段：{path}");
            if (!File.Exists(job.fbx))
                throw new Exception($"找不到模型文件 {job.fbx}");
            if (string.IsNullOrEmpty(job.outputDirectory))
                job.outputDirectory = Path.GetDirectoryName(path);
            return job;
        }

        private static void Run(Job job, Report report)
        {
            var name = string.IsNullOrEmpty(job.target)
                ? Path.GetFileNameWithoutExtension(job.fbx)
                : job.target;
            ExternalModelImporter.SourceFbx = job.fbx.Replace('\\', '/');
            ExternalModelImporter.ModelName = name;
            if (job.keepMeshes != null && job.keepMeshes.Length > 0)
                ExternalModelImporter.KeepMeshes = job.keepMeshes;
            // The author listing their body meshes *is* the declaration of what to keep. Guessing on
            // top of it by material name is the trap this project keeps relearning — a rip's "Hair"
            // atlas routinely carries the legs — and here it silently dropped every submesh.
            ExternalModelImporter.DropMaterials = job.dropMaterials
                                                  ?? (job.keepMeshes != null && job.keepMeshes.Length > 0
                                                      ? new string[0]
                                                      : new[] { "Hair", "Face", "Eye", "Brow", "Pupil", "Default" });
            ChainClassifier.Overrides = (job.chains ?? new ChainLabel[0])
                .Where(c => !string.IsNullOrEmpty(c.root) && !string.IsNullOrEmpty(c.category))
                .ToDictionary(c => c.root, c => c.category);
            TwistAdopter.Overrides = (job.twist ?? new TwistLabel[0])
                .Where(t => !string.IsNullOrEmpty(t.bone) && !string.IsNullOrEmpty(t.role))
                .ToDictionary(t => t.bone, t => t.role);
            // Statics live as long as the editor does, and the menu path runs many builds per session.
            TwistAdopter.Vacant = new List<string>();
            BreastRigger.Status = null;

            WriteLabels(name, job.materials);

            if ((job.kind ?? "body").ToLowerInvariant() == "hair")
            {
                RunHair(job, name, report);
                return;
            }

            var root = ExternalModelImporter.Import();
            if (root == null)
            {
                report.findings.Add(new Finding
                {
                    level = "fail",
                    message = "模型导入失败",
                    action = "看看模型里是不是没有指定名字的网格，或者骨架不是 Humanoid",
                });
                return;
            }

            var renderer = root.GetComponentInChildren<SkinnedMeshRenderer>(true);
            report.modelName = name;
            report.bones = root.GetComponentsInChildren<Transform>(true).Length;
            report.vertices = renderer != null && renderer.sharedMesh != null ? renderer.sharedMesh.vertexCount : 0;
            report.submeshes = renderer != null && renderer.sharedMesh != null ? renderer.sharedMesh.subMeshCount : 0;

            Inspect(root, report);

            var prefab = SdkPipeline.Shape(root, name, true, null, job.stockJointRig);
            if (prefab == null)
            {
                report.findings.Add(new Finding
                {
                    level = "fail",
                    message = "装配失败",
                    action = "看报告里前面的失败项",
                });
                return;
            }
            ReportRig(report);
            SdkPipeline.BuildBundle();

            var built = $"Build/AssetBundles/{name}.bundle";
            if (!File.Exists(built))
            {
                report.findings.Add(new Finding { level = "fail", message = "没生成 bundle", action = "看日志" });
                return;
            }
            Directory.CreateDirectory(job.outputDirectory);
            var destination = Path.Combine(job.outputDirectory, $"{name}.bundle");
            File.Copy(built, destination, true);
            report.bundle = destination.Replace('\\', '/');
            report.previews = PreviewRenderer.Render(prefab, job.outputDirectory, name);
            report.ok = !report.findings.Any(f => f.level == "fail");
            Debug.Log($"[SDK] 构建完成 → {destination}");
        }

        /// <summary>Hair is a different part with different rules — see HairBuilder.</summary>
        private static void RunHair(Job job, string name, Report report)
        {
            var root = HairBuilder.Import(job.fbx.Replace('\\', '/'), name, job.keepMeshes);
            if (root == null)
            {
                report.findings.Add(new Finding
                {
                    level = "fail",
                    message = "发型导入失败",
                    action = "检查模型里有没有蒙皮的头发网格",
                });
                return;
            }
            var renderer = root.GetComponentInChildren<SkinnedMeshRenderer>(true);
            report.modelName = name;
            report.bones = root.GetComponentsInChildren<Transform>(true).Length;
            report.vertices = renderer != null && renderer.sharedMesh != null ? renderer.sharedMesh.vertexCount : 0;
            report.submeshes = renderer != null && renderer.sharedMesh != null ? renderer.sharedMesh.subMeshCount : 0;

            var strands = HairBuilder.Rig(root);
            report.findings.Add(strands > 0
                ? new Finding { level = "ok", message = $"发丝摇物装配 {strands} 条" }
                : new Finding
                {
                    level = "warn",
                    message = "一条发丝都没装上摇物",
                    action = "发丝至少要两根骨成链，单根骨在游戏里不会动",
                });
            report.findings.Add(new Finding
            {
                level = "ok",
                message = "顶点 COLOR 按发型自己的语义写入（379 套实测：LUT 行 0、rim 9、黑描边）",
            });
            report.findings.Add(new Finding
            {
                level = "warn",
                message = "发型的贴图语义（t1/t4）还没验过 —— 离线的发型库只有网格没有贴图，量不出来；"
                          + "身体那套是量过 530 套 body 包的，搬不过来",
                action = "颜色不对先怀疑这里，别先怀疑骨架；描边宽度 stock 是逐顶点画的，这里给的是常量档",
            });

            Validator.Check(root);
            var prefab = SdkPipeline.SavePrefab(root, name);
            if (prefab == null)
            {
                report.findings.Add(new Finding { level = "fail", message = "发型 prefab 保存失败", action = "看日志" });
                return;
            }
            SdkPipeline.BuildBundle();
            var built = $"Build/AssetBundles/{name}.bundle";
            if (!File.Exists(built))
            {
                report.findings.Add(new Finding { level = "fail", message = "没生成 bundle", action = "看日志" });
                return;
            }
            Directory.CreateDirectory(job.outputDirectory);
            var destination = Path.Combine(job.outputDirectory, $"{name}.bundle");
            File.Copy(built, destination, true);
            report.bundle = destination.Replace('\\', '/');
            report.previews = PreviewRenderer.Render(prefab, job.outputDirectory, name);
            report.ok = !report.findings.Any(f => f.level == "fail");
            Debug.Log($"[SDK] 发型构建完成 → {destination}");
        }

        /// <summary>
        /// What the additive steps could not find a bone for. These are warnings on purpose: the
        /// bundle is fine and loads, one joint just deforms worse than a stock one, and the fix is a
        /// bone in the author's DCC. Only saying it in the Unity log means the author never sees it.
        /// </summary>
        private static void ReportRig(Report report)
        {
            if (TwistAdopter.Vacant.Count > 0)
                report.findings.Add(new Finding
                {
                    level = "warn",
                    message = $"源模型没有 {string.Join("、", TwistAdopter.Vacant)} 这几根扭转骨，"
                              + "对应部位大角度扭转时会剪切",
                    action = "要修就在 Blender 里给那节肢体加一根扭转骨（位置见文档），再导一次；不修也能出包",
                });
            else
                report.findings.Add(new Finding { level = "ok", message = "扭转骨齐全" });

            if (!string.IsNullOrEmpty(BreastRigger.Status))
                report.findings.Add(BreastRigger.Status.StartsWith("没装")
                    ? new Finding
                    {
                        level = "warn",
                        message = BreastRigger.Status,
                        action = "模型没有胸部骨就没法装；有但没认出来，在 Blender 里把它挂到 Spine2 下面",
                    }
                    : new Finding { level = "ok", message = BreastRigger.Status });
        }

        /// <summary>The checks the author is allowed to fail on, phrased as what to do next.</summary>
        private static void Inspect(GameObject root, Report report)
        {
            var bones = new HashSet<string>();
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                bones.Add(transform.name);

            var missing = HumanoidBridge.Map.Select(entry => entry.Name).Where(n => !bones.Contains(n)).ToList();
            if (missing.Count > 0)
                report.findings.Add(new Finding
                {
                    level = "fail",
                    message = $"缺 {missing.Count} 根人形骨：{string.Join(", ", missing.Take(6))}",
                    action = "在 Blender 里把这些骨补上，或在 Unity 的 Humanoid 映射里指认它们",
                });
            else
                report.findings.Add(new Finding { level = "ok", message = "人形骨齐全" });

            var worst = 0f;
            string worstLimb = null;
            foreach (var (parent, child, expect, label) in RestProbes)
            {
                var a = root.GetComponentsInChildren<Transform>(true).FirstOrDefault(t => t.name == parent);
                var b = root.GetComponentsInChildren<Transform>(true).FirstOrDefault(t => t.name == child);
                if (a == null || b == null)
                    continue;
                var angle = Vector3.Angle(b.position - a.position, expect);
                if (angle > worst)
                {
                    worst = angle;
                    worstLimb = label;
                }
            }
            if (worst > 20f)
                report.findings.Add(new Finding
                {
                    level = "fail",
                    message = $"静止姿势离标准 T-pose 太远（{worstLimb} 偏 {worst:F0}°）",
                    action = "在 Blender 里点「摆 T-pose」再导出",
                });
            else if (worst > 10f)
                report.findings.Add(new Finding
                {
                    level = "warn",
                    message = $"静止姿势有点歪（{worstLimb} 偏 {worst:F0}°），动画会跟着偏这么多",
                    action = "建议在 Blender 里点「摆 T-pose」",
                });
            else
                report.findings.Add(new Finding { level = "ok", message = $"静止姿势是 T-pose（最大偏 {worst:F1}°）" });
        }

        private static readonly (string Parent, string Child, Vector3 Expect, string Label)[] RestProbes =
        {
            ("LeftArm", "LeftForeArm", Vector3.left, "左大臂"),
            ("RightArm", "RightForeArm", Vector3.right, "右大臂"),
            ("LeftUpLeg", "LeftLeg", Vector3.down, "左大腿"),
            ("RightUpLeg", "RightLeg", Vector3.down, "右大腿"),
        };

        /// <summary>Turns the job's material roles into the labels asset the surface step reads.</summary>
        private static void WriteLabels(string name, MaterialLabel[] materials)
        {
            if (materials == null || materials.Length == 0)
                return;
            const string directory = "Assets/Mods/External-Out";
            Directory.CreateDirectory(directory);
            var path = $"{directory}/{name}.labels.asset";
            var labels = AssetDatabase.LoadAssetAtPath<GakumasBodyLabels>(path);
            if (labels == null)
            {
                labels = ScriptableObject.CreateInstance<GakumasBodyLabels>();
                AssetDatabase.CreateAsset(labels, path);
            }
            labels.submeshes = materials.Select(m => new SubmeshLabel
            {
                material = m.name,
                surface = Surface(m.role),
                hasBareSkin = m.bareSkin,
            }).ToList();
            EditorUtility.SetDirty(labels);
            AssetDatabase.SaveAssets();
            Debug.Log($"[SDK] 材质标注按任务文件写入 {path}：{labels.submeshes.Count} 段");
        }

        private static SurfaceClass Surface(string role) => (role ?? "").ToLowerInvariant() switch
        {
            "skin" => SurfaceClass.Skin,
            "leather" => SurfaceClass.LeatherPlastic,
            "shoe" => SurfaceClass.LeatherShoe,
            "metal" => SurfaceClass.Metal,
            _ => SurfaceClass.Cloth,
        };

        private static void Write(Report report, string directory)
        {
            directory = string.IsNullOrEmpty(directory) ? "." : directory;
            Directory.CreateDirectory(directory);
            var path = Path.Combine(directory, "report.json");
            File.WriteAllText(path, JsonUtility.ToJson(report, true));
            Debug.Log($"[SDK] 报告 → {path}");
        }
    }
}
