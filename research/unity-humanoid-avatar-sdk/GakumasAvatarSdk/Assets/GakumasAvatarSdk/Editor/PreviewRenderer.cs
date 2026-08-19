// 把出包的模型画出来给作者看。
//
// 这一整天的教训：闸门全绿而画面不对，是因为我一直在看数字。作者更是——度数、权重占比、
// 骨数对他没有意义，一张图有。所以构建结束后直接渲两张（正面、侧面）回传给面板。
//
// 用 Unity 自己的离屏渲染，不需要窗口，但**批处理不能带 `-nographics`**（那会连图形设备都不
// 创建）。调用方负责去掉那个 flag；这里拿不到设备就老实说渲不了，不假装。
using System.IO;
using UnityEngine;

namespace GakumasSdk
{
    public static class PreviewRenderer
    {
        private const int Size = 768;

        /// <summary>Renders the prefab from the front and the side. Returns the files written.</summary>
        public static string[] Render(GameObject prefab, string directory, string name)
        {
            if (SystemInfo.graphicsDeviceType == UnityEngine.Rendering.GraphicsDeviceType.Null)
            {
                Debug.LogWarning("[SDK] 预览图：批处理没有图形设备（带了 -nographics），跳过渲染");
                return new string[0];
            }
            Directory.CreateDirectory(directory);
            var instance = Object.Instantiate(prefab);
            var written = new System.Collections.Generic.List<string>();
            var camera = new GameObject("gmi-preview-camera").AddComponent<Camera>();
            var lightObject = new GameObject("gmi-preview-light");
            var light = lightObject.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1.1f;
            lightObject.transform.rotation = Quaternion.Euler(35f, 160f, 0f);
            var texture = new RenderTexture(Size, Size, 24, RenderTextureFormat.ARGB32);

            try
            {
                var bounds = Encapsulate(instance);
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0.98f, 0.98f, 0.98f, 1f);
                camera.orthographic = true;
                camera.orthographicSize = Mathf.Max(bounds.extents.y, bounds.extents.x) * 1.15f;
                camera.targetTexture = texture;

                foreach (var (label, direction) in new[]
                         {
                             ("front", new Vector3(0f, 0f, -1f)),
                             ("side", new Vector3(-1f, 0f, 0f)),
                         })
                {
                    camera.transform.position = bounds.center - direction * (bounds.size.magnitude + 2f);
                    camera.transform.rotation = Quaternion.LookRotation(direction, Vector3.up);
                    camera.Render();

                    var previous = RenderTexture.active;
                    RenderTexture.active = texture;
                    var image = new Texture2D(Size, Size, TextureFormat.RGB24, false);
                    image.ReadPixels(new Rect(0, 0, Size, Size), 0, 0);
                    image.Apply();
                    RenderTexture.active = previous;

                    var path = Path.Combine(directory, $"{name}.{label}.png");
                    File.WriteAllBytes(path, image.EncodeToPNG());
                    Object.DestroyImmediate(image);
                    written.Add(path.Replace('\\', '/'));
                }
                Debug.Log($"[SDK] 预览图 → {string.Join(", ", written)}");
            }
            finally
            {
                camera.targetTexture = null;
                Object.DestroyImmediate(texture);
                Object.DestroyImmediate(camera.gameObject);
                Object.DestroyImmediate(lightObject);
                Object.DestroyImmediate(instance);
            }
            return written.ToArray();
        }

        private static Bounds Encapsulate(GameObject instance)
        {
            var renderers = instance.GetComponentsInChildren<Renderer>(true);
            if (renderers.Length == 0)
                return new Bounds(instance.transform.position, Vector3.one);
            var bounds = renderers[0].bounds;
            foreach (var renderer in renderers)
                bounds.Encapsulate(renderer.bounds);
            return bounds;
        }
    }
}
