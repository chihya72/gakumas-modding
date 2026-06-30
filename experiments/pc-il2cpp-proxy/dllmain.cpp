// GakumasMI PC IL2CPP probe — xinput1_3.dll proxy (polling, no third-party deps).
//
// Loads into the PC client by hijacking xinput1_3.dll, resolves IL2CPP straight
// from GameAssembly.dll's public exports, and every few seconds enumerates all
// SkinnedMeshRenderers via Resources.FindObjectsOfTypeAll — logging each skinned
// mesh and flagging the body parts that match the 065048 costume capture.
//
// No hooking → no MinHook → builds with just MSVC. This is the PC platform layer;
// the detection logic mirrors the Android HookMesh design (resolve by class/method
// name, read Mesh stats).
//
// Build: see CMakeLists.txt (x64). Drop the resulting xinput1_3.dll next to the game exe.

#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <initializer_list>
#include <string>
#include <fstream>
#include <unordered_set>
#include <unordered_map>
#include <vector>
#include "MinHook.h"

// ----- Forward the real xinput1_3 exports to the system DLL (64-bit System32) ---
// Absolute path avoids forwarding to ourselves (we are also named xinput1_3.dll).
#pragma comment(linker, "/export:XInputGetState=C:\\Windows\\System32\\xinput1_3.XInputGetState,@2")
#pragma comment(linker, "/export:XInputSetState=C:\\Windows\\System32\\xinput1_3.XInputSetState,@3")
#pragma comment(linker, "/export:XInputGetCapabilities=C:\\Windows\\System32\\xinput1_3.XInputGetCapabilities,@4")
#pragma comment(linker, "/export:XInputEnable=C:\\Windows\\System32\\xinput1_3.XInputEnable,@5")
#pragma comment(linker, "/export:XInputGetDSoundAudioDeviceGuids=C:\\Windows\\System32\\xinput1_3.XInputGetDSoundAudioDeviceGuids,@6")
#pragma comment(linker, "/export:XInputGetBatteryInformation=C:\\Windows\\System32\\xinput1_3.XInputGetBatteryInformation,@7")
#pragma comment(linker, "/export:XInputGetKeystroke=C:\\Windows\\System32\\xinput1_3.XInputGetKeystroke,@8")

// ----------------------------- logging --------------------------------------
static std::ofstream g_log;
static void LogLine(const std::string& s) {
    OutputDebugStringA((s + "\n").c_str());
    if (g_log.is_open()) { g_log << s << "\n"; g_log.flush(); }
    printf("%s\n", s.c_str());
}
static void Logf(const char* fmt, ...) {
    char buf[1024];
    va_list ap; va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    LogLine(buf);
}

// --------------------------- IL2CPP exports ---------------------------------
typedef void*       (*il2cpp_domain_get_t)();
typedef void*       (*il2cpp_thread_attach_t)(void* domain);
typedef void**      (*il2cpp_domain_get_assemblies_t)(void* domain, size_t* size);
typedef void*       (*il2cpp_assembly_get_image_t)(void* assembly);
typedef const char* (*il2cpp_image_get_name_t)(void* image);
typedef void*       (*il2cpp_class_from_name_t)(void* image, const char* ns, const char* name);
typedef void*       (*il2cpp_class_get_method_from_name_t)(void* klass, const char* name, int argc);
typedef void*       (*il2cpp_class_get_methods_t)(void* klass, void** iter);
typedef const char* (*il2cpp_method_get_name_t)(void* method);
typedef uint32_t    (*il2cpp_method_get_param_count_t)(void* method);
typedef void*       (*il2cpp_method_get_param_t)(void* method, uint32_t index);
typedef const char* (*il2cpp_type_get_name_t)(void* type);
typedef void*       (*il2cpp_class_get_type_t)(void* klass);
typedef void*       (*il2cpp_type_get_object_t)(void* type);
typedef void*       (*il2cpp_object_new_t)(void* klass);
typedef void*       (*il2cpp_array_new_t)(void* elemClass, size_t count);
typedef uint32_t    (*il2cpp_gchandle_new_t)(void* obj, int pinned);
typedef void*       (*il2cpp_string_new_t)(const char* str);

static il2cpp_domain_get_t                 il2cpp_domain_get = nullptr;
static il2cpp_thread_attach_t              il2cpp_thread_attach = nullptr;
static il2cpp_domain_get_assemblies_t      il2cpp_domain_get_assemblies = nullptr;
static il2cpp_assembly_get_image_t         il2cpp_assembly_get_image = nullptr;
static il2cpp_image_get_name_t             il2cpp_image_get_name = nullptr;
static il2cpp_class_from_name_t            il2cpp_class_from_name = nullptr;
static il2cpp_class_get_method_from_name_t il2cpp_class_get_method_from_name = nullptr;
static il2cpp_class_get_methods_t          il2cpp_class_get_methods = nullptr;
static il2cpp_method_get_name_t            il2cpp_method_get_name = nullptr;
static il2cpp_method_get_param_count_t     il2cpp_method_get_param_count = nullptr;
static il2cpp_method_get_param_t           il2cpp_method_get_param = nullptr;
static il2cpp_type_get_name_t              il2cpp_type_get_name = nullptr;
static il2cpp_class_get_type_t             il2cpp_class_get_type = nullptr;
static il2cpp_type_get_object_t            il2cpp_type_get_object = nullptr;
static il2cpp_object_new_t                 il2cpp_object_new = nullptr;
static il2cpp_array_new_t                  il2cpp_array_new = nullptr;
static il2cpp_gchandle_new_t               il2cpp_gchandle_new = nullptr;
static il2cpp_string_new_t                 il2cpp_string_new = nullptr;

template <typename T> static T Imp(HMODULE m, const char* n) { return reinterpret_cast<T>(GetProcAddress(m, n)); }

static bool ResolveIl2cppApi(HMODULE ga) {
    il2cpp_domain_get                 = Imp<il2cpp_domain_get_t>(ga, "il2cpp_domain_get");
    il2cpp_thread_attach              = Imp<il2cpp_thread_attach_t>(ga, "il2cpp_thread_attach");
    il2cpp_domain_get_assemblies      = Imp<il2cpp_domain_get_assemblies_t>(ga, "il2cpp_domain_get_assemblies");
    il2cpp_assembly_get_image         = Imp<il2cpp_assembly_get_image_t>(ga, "il2cpp_assembly_get_image");
    il2cpp_image_get_name             = Imp<il2cpp_image_get_name_t>(ga, "il2cpp_image_get_name");
    il2cpp_class_from_name            = Imp<il2cpp_class_from_name_t>(ga, "il2cpp_class_from_name");
    il2cpp_class_get_method_from_name = Imp<il2cpp_class_get_method_from_name_t>(ga, "il2cpp_class_get_method_from_name");
    il2cpp_class_get_methods          = Imp<il2cpp_class_get_methods_t>(ga, "il2cpp_class_get_methods");
    il2cpp_method_get_name            = Imp<il2cpp_method_get_name_t>(ga, "il2cpp_method_get_name");
    il2cpp_method_get_param_count     = Imp<il2cpp_method_get_param_count_t>(ga, "il2cpp_method_get_param_count");
    il2cpp_method_get_param           = Imp<il2cpp_method_get_param_t>(ga, "il2cpp_method_get_param");
    il2cpp_type_get_name              = Imp<il2cpp_type_get_name_t>(ga, "il2cpp_type_get_name");
    il2cpp_class_get_type             = Imp<il2cpp_class_get_type_t>(ga, "il2cpp_class_get_type");
    il2cpp_type_get_object            = Imp<il2cpp_type_get_object_t>(ga, "il2cpp_type_get_object");
    il2cpp_object_new                 = Imp<il2cpp_object_new_t>(ga, "il2cpp_object_new");
    il2cpp_array_new                  = Imp<il2cpp_array_new_t>(ga, "il2cpp_array_new");
    il2cpp_gchandle_new               = Imp<il2cpp_gchandle_new_t>(ga, "il2cpp_gchandle_new");
    il2cpp_string_new                 = Imp<il2cpp_string_new_t>(ga, "il2cpp_string_new");
    return il2cpp_domain_get && il2cpp_domain_get_assemblies && il2cpp_assembly_get_image &&
           il2cpp_image_get_name && il2cpp_class_from_name && il2cpp_class_get_method_from_name &&
           il2cpp_class_get_type && il2cpp_type_get_object &&
           il2cpp_object_new && il2cpp_array_new;
}

// IL2CPP MethodInfo: first field is the native method pointer.
static void* MethodPtr(void* methodInfo) { return methodInfo ? *reinterpret_cast<void**>(methodInfo) : nullptr; }

static void* FindMethodByParamName(void* klass, const char* name, uint32_t argc, const char* paramNamePart) {
    if (!klass || !il2cpp_class_get_methods || !il2cpp_method_get_name ||
        !il2cpp_method_get_param_count || !il2cpp_method_get_param || !il2cpp_type_get_name) {
        return nullptr;
    }
    void* iter = nullptr;
    while (void* method = il2cpp_class_get_methods(klass, &iter)) {
        const char* methodName = il2cpp_method_get_name(method);
        if (!methodName || strcmp(methodName, name) != 0) continue;
        if (il2cpp_method_get_param_count(method) != argc) continue;
        if (argc == 0) return method;
        void* paramType = il2cpp_method_get_param(method, 0);
        const char* typeName = paramType ? il2cpp_type_get_name(paramType) : nullptr;
        if (typeName && strstr(typeName, paramNamePart)) {
            Logf("[resolve] %s(%s) -> %p", name, typeName, method);
            return method;
        }
    }
    return nullptr;
}

// Match an overload by the type-name of a specific parameter index. Needed for
// ImageConversion.LoadImage: both overloads have param0=Texture2D, but param1 is
// "System.Byte[]" vs "Unity.Collections.NativeArray`1<System.Byte>". Picking the
// wrong one makes LoadImage silently fail on a byte[].
static void* FindMethodByParamAt(void* klass, const char* name, uint32_t argc,
                                 uint32_t paramIndex, const char* paramNamePart) {
    if (!klass || !il2cpp_class_get_methods || !il2cpp_method_get_name ||
        !il2cpp_method_get_param_count || !il2cpp_method_get_param || !il2cpp_type_get_name) return nullptr;
    void* iter = nullptr;
    while (void* method = il2cpp_class_get_methods(klass, &iter)) {
        const char* methodName = il2cpp_method_get_name(method);
        if (!methodName || strcmp(methodName, name) != 0) continue;
        if (il2cpp_method_get_param_count(method) != argc) continue;
        void* pt = il2cpp_method_get_param(method, paramIndex);
        const char* tn = pt ? il2cpp_type_get_name(pt) : nullptr;
        if (tn && strstr(tn, paramNamePart)) {
            Logf("[resolve] %s param%u=%s -> %p", name, paramIndex, tn, method);
            return method;
        }
    }
    return nullptr;
}

static void* FindImage(const char* wantName) {
    size_t count = 0;
    void** asms = il2cpp_domain_get_assemblies(il2cpp_domain_get(), &count);
    for (size_t i = 0; i < count; ++i) {
        void* img = il2cpp_assembly_get_image(asms[i]);
        const char* n = img ? il2cpp_image_get_name(img) : nullptr;
        if (n && strcmp(n, wantName) == 0) return img;
    }
    return nullptr;
}

// Il2CppString x64: [klass(8)][monitor(8)][length(4)][utf16 chars...]
static std::string ReadStr(void* str) {
    if (!str) return "(null)";
    int32_t len = *reinterpret_cast<int32_t*>(reinterpret_cast<uint8_t*>(str) + 0x10);
    if (len <= 0 || len > 4096) return "(?)";
    const char16_t* c = reinterpret_cast<const char16_t*>(reinterpret_cast<uint8_t*>(str) + 0x14);
    std::string out; out.reserve(len);
    for (int i = 0; i < len; ++i) out.push_back(c[i] < 0x80 ? static_cast<char>(c[i]) : '?');
    return out;
}

// Il2CppArray x64: [klass(8)][monitor(8)][bounds(8)][max_length(8)][vector...]
static uintptr_t ArrayCount(void* arr)   { return arr ? *reinterpret_cast<uintptr_t*>(reinterpret_cast<uint8_t*>(arr) + 0x18) : 0; }
static void**    ArrayItems(void* arr)   { return arr ? reinterpret_cast<void**>(reinterpret_cast<uint8_t*>(arr) + 0x20) : nullptr; }

// Call ABI: instance method (this, MethodInfo*) ; static method (arg, MethodInfo*)
typedef int   (*get_int_t)(void* a, void* mi);
typedef void* (*get_obj_t)(void* a, void* mi);
typedef void  (*set_obj_t)(void* self, void* value, void* mi);
typedef void  (*set_int_t)(void* self, int value, void* mi);
typedef void  (*call_void_t)(void* self, void* mi);
typedef void  (*set_tris_t)(void* self, void* arr, int submesh, void* mi);
typedef void  (*ctor_ii_t)(void* self, int width, int height, void* mi);
typedef void  (*ctor_iiib_t)(void* self, int width, int height, int format, bool mip, void* mi);
typedef void  (*load_raw_t)(void* self, void* arr, void* mi);
typedef void  (*apply_t)(void* self, void* mi);
typedef void  (*ctor_obj_t)(void* self, void* other, void* mi);
typedef bool  (*load_image_t)(void* texture, void* data, bool markNonReadable, void* mi);
typedef bool  (*has_property_t)(void* self, void* name, void* mi);
typedef void* (*get_texture_t)(void* self, void* name, void* mi);
typedef void  (*set_texture_t)(void* self, void* name, void* texture, void* mi);
typedef int   (*property_to_id_t)(void* name, void* mi);
typedef bool  (*has_property_id_t)(void* self, int nameID, void* mi);
typedef void* (*get_texture_id_t)(void* self, int nameID, void* mi);
typedef void  (*set_texture_id_t)(void* self, int nameID, void* texture, void* mi);
typedef void  (*set_float_str_t)(void* self, void* name, float value, void* mi);
typedef float (*get_float_str_t)(void* self, void* name, void* mi);

static void* g_mi_findAll = nullptr;       // Resources.FindObjectsOfTypeAll(Type)
static void* g_mi_getSharedMesh = nullptr; // SkinnedMeshRenderer.get_sharedMesh
static void* g_mi_setSharedMesh = nullptr; // SkinnedMeshRenderer.set_sharedMesh
static void* g_mi_setUpdateOff = nullptr;  // SkinnedMeshRenderer.set_updateWhenOffscreen
static void* g_mi_getBones = nullptr;      // SkinnedMeshRenderer.get_bones -> Transform[]
static void* g_mi_vertexCount = nullptr;   // Mesh.get_vertexCount
static void* g_mi_subMeshCount = nullptr;  // Mesh.get_subMeshCount
static void* g_mi_getBindposes = nullptr;  // Mesh.get_bindposes -> Matrix4x4[]
static void* g_mi_getTriangles = nullptr;  // Mesh.get_triangles -> int[]
static void* g_mi_getName = nullptr;       // Object.get_name
static void* g_mi_setHideFlags = nullptr;  // Object.set_hideFlags
static void* g_mi_getSharedMaterials = nullptr; // Renderer.get_sharedMaterials
static void* g_mi_setSharedMaterials = nullptr; // Renderer.set_sharedMaterials
static void* g_mi_materialCtorCopy = nullptr;   // Material .ctor(Material)
static void* g_mi_getMainTexture = nullptr;     // Material.get_mainTexture()
static void* g_mi_setMainTexture = nullptr;     // Material.set_mainTexture(Texture)
static void* g_mi_hasPropertyString = nullptr;  // Material.HasProperty(string)
static void* g_mi_getTextureString = nullptr;   // Material.GetTexture(string)
static void* g_mi_setTextureString = nullptr;   // Material.SetTexture(string, Texture)
static void* g_mi_hasPropertyId = nullptr;      // Material.HasProperty(int)
static void* g_mi_getTextureId = nullptr;       // Material.GetTexture(int)
static void* g_mi_setTextureId = nullptr;       // Material.SetTexture(int, Texture)
static void* g_mi_propertyToID = nullptr;       // Shader.PropertyToID(string)
static void* g_mi_setFloatStr = nullptr;        // Material.SetFloat(string, float)
static void* g_mi_getFloatStr = nullptr;        // Material.GetFloat(string)
static void* g_mi_enableKeyword = nullptr;      // Material.EnableKeyword(string)
static void* g_mi_disableKeyword = nullptr;     // Material.DisableKeyword(string)
static void* g_mi_setRenderQueue = nullptr;     // Material.set_renderQueue(int)
static void* g_mi_getShader = nullptr;          // Material.get_shader -> Shader
static void* g_mi_getShaderKeywords = nullptr;  // Material.get_shaderKeywords -> string[]
static void* g_mi_tex2dCtorII = nullptr;        // Texture2D .ctor(int,int)
static void* g_mi_tex2dCtor4 = nullptr;         // Texture2D .ctor(int,int,TextureFormat,bool)
static void* g_mi_loadRaw = nullptr;            // Texture2D.LoadRawTextureData(byte[])
static void* g_mi_apply = nullptr;              // Texture2D.Apply()
static void* g_mi_loadImage = nullptr;          // ImageConversion.LoadImage(Texture2D, byte[], bool)
static void* g_mi_fileReadAllBytes = nullptr;   // System.IO.File.ReadAllBytes(string) -> byte[]
static void* g_mi_texWidth = nullptr;           // Texture.get_width
static void* g_mi_texHeight = nullptr;          // Texture.get_height
static void* g_smrTypeObject = nullptr;    // System.Type of SkinnedMeshRenderer

// for building a Mesh
static void* g_meshClass = nullptr;
static void* g_mi_meshCtor = nullptr;      // Mesh .ctor
static void* g_mi_setVertices = nullptr;   // Mesh.set_vertices(Vector3[])
static void* g_mi_setNormals = nullptr;    // Mesh.set_normals(Vector3[])
static void* g_mi_setUV = nullptr;         // Mesh.set_uv(Vector2[])
static void* g_mi_setColors = nullptr;     // Mesh.set_colors(Color[])
static void* g_mi_setBoneWeights = nullptr;// Mesh.set_boneWeights(BoneWeight[])
static void* g_mi_setBindposes = nullptr;  // Mesh.set_bindposes(Matrix4x4[])
static void* g_mi_setTriangles = nullptr;  // Mesh.set_triangles(int[])
static void* g_mi_setSubMeshCount = nullptr;// Mesh.set_subMeshCount(int)
static void* g_mi_SetTrianglesN = nullptr; // Mesh.SetTriangles(int[], int submesh)
static void* g_mi_recalcBounds = nullptr;  // Mesh.RecalculateBounds
static void* g_clsV3 = nullptr;            // element classes for il2cpp_array_new
static void* g_clsV2 = nullptr;
static void* g_clsColor = nullptr;         // UnityEngine.Color (4 floats = 16 bytes)
static void* g_clsM4 = nullptr;
static void* g_clsBW = nullptr;
static void* g_clsInt = nullptr;
static void* g_clsByte = nullptr;
static void* g_clsMaterial = nullptr;
static void* g_clsTexture2D = nullptr;
static std::string g_gmimPath;
static std::string g_atlasPath;
static void* g_yuikaAtlasTexture = nullptr;

static int CallInt(void* mi, void* self) {
    void* p = MethodPtr(mi); return p ? reinterpret_cast<get_int_t>(p)(self, mi) : -1;
}
static void* CallObj(void* mi, void* a) {
    void* p = MethodPtr(mi); return p ? reinterpret_cast<get_obj_t>(p)(a, mi) : nullptr;
}
static std::string Name(void* o) { return g_mi_getName && o ? ReadStr(CallObj(g_mi_getName, o)) : "?"; }

static void CallArr(void* mi, void* self, void* arr) {                 // setter(self, array)
    void* p = MethodPtr(mi); if (p) reinterpret_cast<set_obj_t>(p)(self, arr, mi);
}
static void CallVoid(void* mi, void* self) {                           // method(self) -> void
    void* p = MethodPtr(mi); if (p) reinterpret_cast<call_void_t>(p)(self, mi);
}
// New il2cpp value-type array filled from raw bytes.
static void* NewArr(void* elemClass, size_t count, const void* src, size_t elemSize) {
    void* arr = il2cpp_array_new(elemClass, count);
    if (arr && src) memcpy(reinterpret_cast<uint8_t*>(arr) + 0x20, src, count * elemSize);
    return arr;
}

static bool LoadAtlasBytesIntoTexture(void* texture) {
    if (!texture || !g_mi_loadImage || !g_clsByte) return false;
    std::ifstream f(g_atlasPath, std::ios::binary | std::ios::ate);
    if (!f) {
        Logf("[tex] atlas not found: %s", g_atlasPath.c_str());
        return false;
    }
    std::streamsize size = f.tellg();
    if (size <= 0) {
        Logf("[tex] atlas is empty: %s", g_atlasPath.c_str());
        return false;
    }
    f.seekg(0, std::ios::beg);
    std::vector<uint8_t> bytes((size_t)size);
    if (!f.read(reinterpret_cast<char*>(bytes.data()), size)) {
        Logf("[tex] cannot read atlas: %s", g_atlasPath.c_str());
        return false;
    }
    void* data = NewArr(g_clsByte, bytes.size(), bytes.data(), 1);
    void* load = MethodPtr(g_mi_loadImage);
    if (!data || !load) return false;
    Logf("[tex] LoadImage texture=%p bytes=%llu", texture, (unsigned long long)bytes.size());
    bool ok = reinterpret_cast<load_image_t>(load)(texture, data, false, g_mi_loadImage);
    Logf("[tex] LoadImage %s texture=%p", ok ? "OK" : "FAILED", texture);
    return ok;
}

// Load yuika_atlas.png into a fresh Texture2D using the recipe proven in the
// GakumasLocalify hanhua: let .NET read the file (System.IO.File.ReadAllBytes ->
// a real managed byte[]) and decode via ImageConversion.LoadImage. Hand-built
// il2cpp byte[] + LoadRawTextureData proved unreliable here (black body).
static void* LoadPngTextureOnce() {
    if (g_yuikaAtlasTexture) return g_yuikaAtlasTexture;
    if (!g_clsTexture2D || !g_mi_tex2dCtorII || !g_mi_loadImage || !g_mi_fileReadAllBytes || !il2cpp_string_new) {
        Logf("[tex] missing Texture2D ctor/LoadImage/File.ReadAllBytes; skip atlas");
        return nullptr;
    }
    void* pathStr = il2cpp_string_new(g_atlasPath.c_str());
    void* bytes = reinterpret_cast<get_obj_t>(MethodPtr(g_mi_fileReadAllBytes))(pathStr, g_mi_fileReadAllBytes);
    if (!bytes) { Logf("[tex] File.ReadAllBytes returned null for %s", g_atlasPath.c_str()); return nullptr; }
    Logf("[tex] File.ReadAllBytes ok, byte[] len=%llu", (unsigned long long)ArrayCount(bytes));

    void* texture = il2cpp_object_new(g_clsTexture2D);
    reinterpret_cast<ctor_ii_t>(MethodPtr(g_mi_tex2dCtorII))(texture, 2, 2, g_mi_tex2dCtorII);
    bool ok = reinterpret_cast<load_image_t>(MethodPtr(g_mi_loadImage))(texture, bytes, false, g_mi_loadImage);
    int tw = g_mi_texWidth ? CallInt(g_mi_texWidth, texture) : -1;
    int th = g_mi_texHeight ? CallInt(g_mi_texHeight, texture) : -1;
    Logf("[tex] LoadImage %s texture=%p size=%dx%d", ok ? "OK" : "FAILED", texture, tw, th);
    if (!ok) return nullptr;
    if (il2cpp_gchandle_new) il2cpp_gchandle_new(texture, 1);
    g_yuikaAtlasTexture = texture;
    Logf("[tex] loaded atlas %s -> Texture2D=%p", g_atlasPath.c_str(), texture);
    return texture;
}

// Tiny solid RGBA32 texture (for neutral toon aux maps). yuika has only a base
// atlas; leaving ttmr's _DefMap (metallic/smoothness) makes the body black/glossy.
static void* CreateSolidTex(uint8_t r, uint8_t g, uint8_t b, uint8_t a) {
    if (!g_clsTexture2D || !g_clsByte || !g_mi_tex2dCtor4 || !g_mi_loadRaw) return nullptr;
    const int N = 4;
    std::vector<uint8_t> px(N * N * 4);
    for (int i = 0; i < N * N; ++i) { px[i*4]=r; px[i*4+1]=g; px[i*4+2]=b; px[i*4+3]=a; }
    void* t = il2cpp_object_new(g_clsTexture2D);
    reinterpret_cast<ctor_iiib_t>(MethodPtr(g_mi_tex2dCtor4))(t, N, N, 4, false, g_mi_tex2dCtor4);
    void* arr = NewArr(g_clsByte, px.size(), px.data(), 1);
    reinterpret_cast<load_raw_t>(MethodPtr(g_mi_loadRaw))(t, arr, g_mi_loadRaw);
    if (g_mi_apply) reinterpret_cast<apply_t>(MethodPtr(g_mi_apply))(t, g_mi_apply);
    if (il2cpp_gchandle_new) il2cpp_gchandle_new(t, 1);
    return t;
}
static void* g_neutralPacked = nullptr;   // _DefMap : (255,0,0,255) zero metallic/smoothness
static void* g_neutralShade  = nullptr;   // _ShadeMap: (128,128,128,0) no shade overlay
static void SetMatTexByName(void* material, const char* prop, void* tex) {
    if (!material || !tex || !g_mi_propertyToID || !g_mi_setTextureId || !il2cpp_string_new) return;
    void* name = il2cpp_string_new(prop); if (!name) return;
    int id = reinterpret_cast<property_to_id_t>(MethodPtr(g_mi_propertyToID))(name, g_mi_propertyToID);
    if (id == 0) return;
    reinterpret_cast<set_texture_id_t>(MethodPtr(g_mi_setTextureId))(material, id, tex, g_mi_setTextureId);
    Logf("[tex] set %s -> neutral tex=%p", prop, tex);
}
static void NeutralizeAuxMaps(void* material) {
    if (!g_neutralPacked) g_neutralPacked = CreateSolidTex(255, 0, 0, 255);
    if (!g_neutralShade)  g_neutralShade  = CreateSolidTex(128, 128, 128, 0);
    if (g_neutralPacked) SetMatTexByName(material, "_DefMap", g_neutralPacked);
    if (g_neutralShade)  SetMatTexByName(material, "_ShadeMap", g_neutralShade);
}

static void SetMatFloat(void* material, const char* prop, float value) {
    if (!material || !g_mi_setFloatStr || !il2cpp_string_new) return;
    void* name = il2cpp_string_new(prop);
    if (!name) return;
    reinterpret_cast<set_float_str_t>(MethodPtr(g_mi_setFloatStr))(material, name, value, g_mi_setFloatStr);
    Logf("[tex] SetFloat %s=%.3f", prop, value);
}

static void SetMatKeyword(void* material, const char* keyword, bool enabled) {
    if (!material || !il2cpp_string_new) return;
    void* mi = enabled ? g_mi_enableKeyword : g_mi_disableKeyword;
    if (!mi) return;
    void* name = il2cpp_string_new(keyword);
    if (!name) return;
    reinterpret_cast<set_obj_t>(MethodPtr(mi))(material, name, mi);
    Logf("[tex] %s keyword %s", enabled ? "enabled" : "disabled", keyword);
}

// Experimental: make the live Geo_Body material resemble the game's real
// cutout body-co material. fktn-cstm-0001 shows m_bdyco uses _ShaderType=1 and
// _Cull=0 while _AlphaClip stays 0, so the Campus shader's own mode switch seems
// more important than Unity's usual alpha-test keywords.
static void EnableCutout(void* material, float cutoff = 0.5f) {
    if (!material) return;
    SetMatFloat(material, "_ShaderType", 1.0f);
    SetMatFloat(material, "_Cull", 0.0f);
    SetMatFloat(material, "_AlphaClip", 0.0f);
    SetMatFloat(material, "_Cutoff", cutoff);
    SetMatFloat(material, "_Surface", 0.0f);
    SetMatFloat(material, "_Blend", 0.0f);
    SetMatFloat(material, "_Mode", 0.0f);
    SetMatFloat(material, "_RenderMode", 0.0f);
    SetMatFloat(material, "_ZWrite", 1.0f);
    SetMatFloat(material, "_SrcBlend", 1.0f);
    SetMatFloat(material, "_DstBlend", 0.0f);
    SetMatFloat(material, "_SrcAlphaBlend", 1.0f);
    SetMatFloat(material, "_DstAlphaBlend", 0.0f);
    SetMatKeyword(material, "_SURFACE_TYPE_TRANSPARENT", false);
    if (g_mi_setRenderQueue) {
        reinterpret_cast<set_int_t>(MethodPtr(g_mi_setRenderQueue))(material, -1, g_mi_setRenderQueue);
        Logf("[tex] set renderQueue=-1 on material=%p", material);
    }
    Logf("[tex] enabled Campus bdyco-like state on material=%p", material);
}

// Dump a material's shader + keywords + render-state floats. Used to read the
// game's live cutout material (Geo_Dresscurtain) and find the transparency switch
// by diffing against the opaque body material (m_bdy).
static void DumpMaterial(const char* tag, void* mat) {
    if (!mat) { Logf("[matdump] %s: null", tag); return; }
    void* sh = g_mi_getShader ? CallObj(g_mi_getShader, mat) : nullptr;
    Logf("[matdump] %s material=%p shader='%s'", tag, mat, sh ? Name(sh).c_str() : "?");
    if (g_mi_getShaderKeywords) {
        void* kw = CallObj(g_mi_getShaderKeywords, mat);
        uintptr_t n = ArrayCount(kw); void** it = ArrayItems(kw);
        if (n == 0) Logf("[matdump]   keywords: (none)");
        for (uintptr_t i = 0; i < n; ++i) Logf("[matdump]   keyword: %s", ReadStr(it[i]).c_str());
    }
    if (g_mi_getFloatStr && il2cpp_string_new) {
        auto gf = reinterpret_cast<get_float_str_t>(MethodPtr(g_mi_getFloatStr));
        const char* props[] = {"_Surface","_Blend","_Mode","_RenderMode","_ShaderType","_AlphaClip",
                               "_Cutoff","_SrcBlend","_DstBlend","_SrcAlphaBlend","_DstAlphaBlend",
                               "_ZWrite","_Cull","_QueueOffset"};
        std::string line = "[matdump]  ";
        char buf[64];
        for (auto p : props) { snprintf(buf, sizeof(buf), " %s=%.1f", p, gf(mat, il2cpp_string_new(p), g_mi_getFloatStr)); line += buf; }
        Logf("%s", line.c_str());
    }
}

static bool ApplyAtlasToMaterial(void* material, void* atlas) {
    if (!material || !atlas || !g_mi_setMainTexture) return false;
    Logf("[tex] set mainTexture material=%p atlas=%p", material, atlas);
    CallArr(g_mi_setMainTexture, material, atlas);
    Logf("[tex] set mainTexture OK material=%p", material);
    return true;
}

static bool ApplyAtlasInPlaceToMaterial(void* material) {
    if (!material || !g_mi_getMainTexture || !g_mi_loadImage || !g_clsByte) return false;
    void* texture = CallObj(g_mi_getMainTexture, material);
    if (texture) {
        Logf("[tex] material mainTexture=%p", texture);
        if (LoadAtlasBytesIntoTexture(texture)) return true;
    }

    Logf("[tex] material has no usable mainTexture: %p; probing shader texture properties", material);
    const char* candidates[] = {
        "_BaseMap", "_DefMap", "_RampAddMap", "_ShadeMap", "_RampMap",
        "_MainTex", "_BaseColorMap", "_BaseColorTex", "_AlbedoMap",
        "_DiffuseMap", "_Tex", "_Texture", "Texture2D_0"
    };
    void* propertyToIdPtr = MethodPtr(g_mi_propertyToID);
    void* hasIdPtr = MethodPtr(g_mi_hasPropertyId);
    void* getIdPtr = MethodPtr(g_mi_getTextureId);
    void* setIdPtr = MethodPtr(g_mi_setTextureId);
    void* hasStringPtr = MethodPtr(g_mi_hasPropertyString);
    void* getStringPtr = MethodPtr(g_mi_getTextureString);
    void* setStringPtr = MethodPtr(g_mi_setTextureString);
    for (const char* property : candidates) {
        void* name = il2cpp_string_new ? il2cpp_string_new(property) : nullptr;
        if (!name) continue;
        int propertyId = 0;
        if (propertyToIdPtr) {
            propertyId = reinterpret_cast<property_to_id_t>(propertyToIdPtr)(name, g_mi_propertyToID);
            Logf("[tex] PropertyToID(%s)=%d", property, propertyId);
        }

        if (propertyId != 0 && (hasIdPtr || getIdPtr || setIdPtr)) {
            if (hasIdPtr) {
                bool hasProperty = reinterpret_cast<has_property_id_t>(hasIdPtr)(material, propertyId, g_mi_hasPropertyId);
                Logf("[tex] HasPropertyID(%s/%d)=%d", property, propertyId, hasProperty ? 1 : 0);
                if (!hasProperty) continue;
            }
            if (getIdPtr) {
                void* propTexture = reinterpret_cast<get_texture_id_t>(getIdPtr)(material, propertyId, g_mi_getTextureId);
                Logf("[tex] GetTextureID(%s/%d) -> %p", property, propertyId, propTexture);
                // DO NOT LoadImage in-place on the live texture: a failed decode (DDS /
                // unsupported) replaces the game's real toon map with a placeholder -> black body.
                // Only the SetTexture-with-a-freshly-loaded-PNG path below is safe.
            }
            if (setIdPtr) {
                void* atlas = LoadPngTextureOnce();
                if (atlas) {
                    Logf("[tex] SetTextureID(%s/%d, atlas=%p)", property, propertyId, atlas);
                    reinterpret_cast<set_texture_id_t>(setIdPtr)(material, propertyId, atlas, g_mi_setTextureId);
                    Logf("[tex] SetTextureID OK via %s id=%d", property, propertyId);
                    // Keep game _DefMap/_ShadeMap (neutralizing them caused black).
                    // NOTE: cutout state is NOT applied here anymore. The atlas is shared by the
                    // opaque base (m_bdy) and the cloned cutout material (m_bdyco); only the clone
                    // gets EnableCutout, so opaque submeshes stay opaque. See EnsureSharedMaterials.
                    return true;
                }
            }
        }

        if (hasStringPtr) {
            bool hasProperty = reinterpret_cast<has_property_t>(hasStringPtr)(material, name, g_mi_hasPropertyString);
            Logf("[tex] HasPropertyString(%s)=%d", property, hasProperty ? 1 : 0);
            if (!hasProperty) continue;
        }
        if (getStringPtr) {
            void* propTexture = reinterpret_cast<get_texture_t>(getStringPtr)(material, name, g_mi_getTextureString);
            Logf("[tex] GetTextureString(%s) -> %p", property, propTexture);
            // (in-place LoadImage on live texture removed — destructive on failure, see above)
        }
        if (setStringPtr) {
            void* atlas = LoadPngTextureOnce();
            if (atlas) {
                Logf("[tex] SetTextureString(%s, atlas=%p)", property, atlas);
                reinterpret_cast<set_texture_t>(setStringPtr)(material, name, atlas, g_mi_setTextureString);
                Logf("[tex] SetTextureString OK via %s", property);
                return true;
            }
        }
    }
    return false;
}

static void* CloneMaterialWithAtlas(void* source, void* atlas) {
    if (!source || !g_clsMaterial || !g_mi_materialCtorCopy) return source;
    void* material = il2cpp_object_new(g_clsMaterial);
    void* ctor = MethodPtr(g_mi_materialCtorCopy);
    if (!material || !ctor) return source;
    Logf("[tex] clone material source=%p new=%p", source, material);
    reinterpret_cast<ctor_obj_t>(ctor)(material, source, g_mi_materialCtorCopy);
    Logf("[tex] clone material OK new=%p", material);
    if (atlas && g_mi_setMainTexture) {
        ApplyAtlasToMaterial(material, atlas);
    }
    if (il2cpp_gchandle_new) il2cpp_gchandle_new(material, 1);
    return material;
}

// Diagnostic only. Geo_Dresscurtain can exist in the scene, but it is a separate
// renderer/material and must not be used as the body answer for ttmr-cstm-0003.
static void* FindCutoutMaterial() {
    if (!g_mi_findAll || !g_smrTypeObject) return nullptr;
    void* arr = reinterpret_cast<get_obj_t>(MethodPtr(g_mi_findAll))(g_smrTypeObject, g_mi_findAll);
    uintptr_t n = ArrayCount(arr); void** items = ArrayItems(arr);
    for (uintptr_t i = 0; i < n; ++i) {
        void* r = items[i]; if (!r) continue;
        void* m = CallObj(g_mi_getSharedMesh, r); if (!m) continue;
        if (Name(m) == "Geo_Dresscurtain") {
            void* mats = CallObj(g_mi_getSharedMaterials, r);
            if (ArrayCount(mats) > 0) {
                void* mat = ArrayItems(mats)[0];
                Logf("[mesh] cutout source = Geo_Dresscurtain material=%p", mat);
                return mat;
            }
        }
    }
    return nullptr;
}

// External-model container parsed from a .gmim file (see export_gmim.py for the format).
struct Gmim {
    uint32_t vcount = 0, subcount = 0, bonecount = 0;
    std::vector<std::string> bones;
    std::vector<float> pos, nrm, uv, col;  // vcount*3, *3, *2, *4(RGBA, ver>=2)
    std::vector<int>   wbone;              // vcount*4 (table idx, -1=unused)
    std::vector<float> wweight;            // vcount*4
    std::vector<std::vector<int>> subs;    // subcount index lists
    std::vector<uint8_t> submode;          // subcount: 0=opaque(m_bdy), 1=cutout/co(m_bdyco) -- ver>=3
    std::vector<float>   subcutoff;        // subcount: alpha cutoff for cutout submeshes -- ver>=3
};

// Clone the opaque body material and switch the COPY into m_bdyco-like cutout state,
// so opaque submeshes keep the untouched m_bdy while cutout/co submeshes discard A=0.
// The clone inherits base's textures (atlas already applied in-place to base).
static void* CloneCutoutMaterial(void* base, float cutoff) {
    if (!base) return nullptr;
    if (!g_clsMaterial || !g_mi_materialCtorCopy) {
        // No copy ctor available: degrade to mutating base (whole body becomes cutout).
        Logf("[mesh] cutout clone unavailable; mutating base material in place");
        EnableCutout(base, cutoff);
        return base;
    }
    void* m = il2cpp_object_new(g_clsMaterial);
    void* ctor = MethodPtr(g_mi_materialCtorCopy);
    if (!m || !ctor) { EnableCutout(base, cutoff); return base; }
    reinterpret_cast<ctor_obj_t>(ctor)(m, base, g_mi_materialCtorCopy);
    EnableCutout(m, cutoff);
    if (il2cpp_gchandle_new) il2cpp_gchandle_new(m, 1);
    Logf("[mesh] cloned cutout material base=%p clone=%p cutoff=%.3f", base, m, cutoff);
    return m;
}

// Build a per-submesh sharedMaterials array: opaque submeshes -> base m_bdy (untouched),
// cutout/co submeshes (g.submode[s]==1) -> a single cloned cutout material. Driven by the
// .gmim per-submesh mode so the route matches the real m_bdy + m_bdyco split.
static bool EnsureSharedMaterials(void* renderer, const Gmim& g) {
    uint32_t submeshCount = g.subcount;
    if (!g_mi_getSharedMaterials || !g_mi_setSharedMaterials || !g_clsMaterial || submeshCount == 0) {
        return false;
    }
    void* oldArr = CallObj(g_mi_getSharedMaterials, renderer);
    uintptr_t oldCount = ArrayCount(oldArr);
    void** oldItems = ArrayItems(oldArr);
    void* base = (oldCount > 0 && oldItems) ? oldItems[0] : nullptr;
    if (!base) {
        Logf("[mesh] cannot build sharedMaterials: renderer has no source material");
        return false;
    }

    uint32_t cutoutSubs = 0;
    float cutoutCutoff = 0.5f;
    for (uint32_t s = 0; s < submeshCount; ++s) {
        if (s < g.submode.size() && g.submode[s]) {
            ++cutoutSubs;
            if (s < g.subcutoff.size()) cutoutCutoff = g.subcutoff[s];
        }
    }

    // Nothing to change: target already has enough material slots and no submesh needs cutout.
    if (oldCount >= submeshCount && cutoutSubs == 0) {
        Logf("[mesh] materials already cover submeshes: materials=%llu submeshes=%u (no cutout)",
             (unsigned long long)oldCount, submeshCount);
        return true;
    }

    Logf("[mesh] using Geo_Body material base=%p (Geo_Dresscurtain ignored)", base);
    bool atlasApplied = ApplyAtlasInPlaceToMaterial(base);

    void* cutoutMat = (cutoutSubs > 0) ? CloneCutoutMaterial(base, cutoutCutoff) : nullptr;

    std::vector<void*> materials(submeshCount, base);
    for (uint32_t s = 0; s < submeshCount; ++s) {
        bool isCutout = (s < g.submode.size() && g.submode[s]);
        materials[s] = (isCutout && cutoutMat) ? cutoutMat : base;
    }
    void* newArr = NewArr(g_clsMaterial, materials.size(), materials.data(), sizeof(void*));
    if (!newArr) {
        Logf("[mesh] cannot allocate sharedMaterials[%u]", submeshCount);
        return false;
    }
    Logf("[mesh] build sharedMaterials: %llu -> %u (opaque=base cutout=%p cutoutSubs=%u atlasInPlace=%d)",
         (unsigned long long)oldCount, submeshCount, cutoutMat, cutoutSubs, atlasApplied ? 1 : 0);
    CallArr(g_mi_setSharedMaterials, renderer, newArr);
    return true;
}

// Build a simple quad mesh skinned 100% to "Hips" and assign it to the renderer.
// Proves the full create-Mesh -> set data -> skin -> render chain. Returns the new mesh.
static void* BuildQuadAndReplace(void* renderer) {
    if (!g_mi_meshCtor || !g_mi_setVertices || !g_mi_setBoneWeights || !g_mi_setBindposes ||
        !g_mi_setTriangles || !g_clsV3 || !g_clsBW || !g_clsM4 || !g_clsInt) {
        Logf("[build] missing a method/class, aborting"); return nullptr;
    }
    // locate "Hips" in the live bones[] + its length N
    void* bonesArr = CallObj(g_mi_getBones, renderer);
    int N = (int)ArrayCount(bonesArr);
    void** bptr = ArrayItems(bonesArr);
    int hips = -1;
    for (int i = 0; i < N; ++i) if (Name(bptr[i]) == "Hips") { hips = i; break; }
    if (hips < 0) { Logf("[build] Hips not found among %d bones", N); return nullptr; }
    Logf("[build] N=%d hips=%d", N, hips);

    // a ~0.6m quad, in front of/around the hips (local space; bindpose=identity)
    float verts[4][3] = { {-0.3f,-0.3f,0}, {0.3f,-0.3f,0}, {0.3f,0.3f,0}, {-0.3f,0.3f,0} };
    float norms[4][3] = { {0,0,1},{0,0,1},{0,0,1},{0,0,1} };
    float uvs[4][2]   = { {0,0},{1,0},{1,1},{0,1} };
    int   tris[6]     = { 0,1,2, 0,2,3 };
    // BoneWeight x64 layout: float w0..w3 (16) then int b0..b3 (16) = 32 bytes
    struct BW { float w0,w1,w2,w3; int b0,b1,b2,b3; } bw[4];
    for (int i = 0; i < 4; ++i) { bw[i] = {1.f,0,0,0, hips,0,0,0}; }
    // bindposes: N identity matrices (length must match bones[])
    std::vector<float> binds(N * 16, 0.f);
    for (int i = 0; i < N; ++i) { binds[i*16+0]=1; binds[i*16+5]=1; binds[i*16+10]=1; binds[i*16+15]=1; }

    // granular logging: each line is flushed, so on a crash the LAST line = the failing step
    Logf("[build] step: object_new(Mesh)");                 void* mesh = il2cpp_object_new(g_meshClass);
    Logf("[build] step: .ctor mesh=%p", mesh);              CallVoid(g_mi_meshCtor, mesh);
    Logf("[build] step: array Vector3 verts");              void* aV = NewArr(g_clsV3, 4, verts, 12);
    Logf("[build] step: set_vertices");                     CallArr(g_mi_setVertices, mesh, aV);
    if (g_mi_setNormals) { Logf("[build] step: set_normals"); CallArr(g_mi_setNormals, mesh, NewArr(g_clsV3, 4, norms, 12)); }
    if (g_mi_setUV && g_clsV2) { Logf("[build] step: set_uv"); CallArr(g_mi_setUV, mesh, NewArr(g_clsV2, 4, uvs, 8)); }
    Logf("[build] step: array BoneWeight");                 void* aBW = NewArr(g_clsBW, 4, bw, 32);
    Logf("[build] step: set_boneWeights");                  CallArr(g_mi_setBoneWeights, mesh, aBW);
    Logf("[build] step: array Matrix4x4 x%d", N);           void* aBP = NewArr(g_clsM4, N, binds.data(), 64);
    Logf("[build] step: set_bindposes");                    CallArr(g_mi_setBindposes, mesh, aBP);
    Logf("[build] step: array int triangles");             void* aT = NewArr(g_clsInt, 6, tris, 4);
    Logf("[build] step: set_triangles");                    CallArr(g_mi_setTriangles, mesh, aT);
    if (g_mi_recalcBounds) { Logf("[build] step: RecalculateBounds"); CallVoid(g_mi_recalcBounds, mesh); }
    if (g_mi_setHideFlags) { Logf("[build] step: set_hideFlags"); reinterpret_cast<set_int_t>(MethodPtr(g_mi_setHideFlags))(mesh, 32, g_mi_setHideFlags); }
    if (il2cpp_gchandle_new) { Logf("[build] step: gchandle_new"); il2cpp_gchandle_new(mesh, 1); }
    if (g_mi_setUpdateOff) { Logf("[build] step: set_updateWhenOffscreen"); reinterpret_cast<set_int_t>(MethodPtr(g_mi_setUpdateOff))(renderer, 1, g_mi_setUpdateOff); }
    Logf("[build] step: set_sharedMesh");                   reinterpret_cast<set_obj_t>(MethodPtr(g_mi_setSharedMesh))(renderer, mesh, g_mi_setSharedMesh);
    Logf("[build] DONE assigned quad mesh=%p to renderer=%p", mesh, renderer);
    return mesh;
}

// ============================ real mesh from .gmim ==========================
static bool LoadGmim(const std::string& path, Gmim& g) {
    std::ifstream f(path, std::ios::binary);
    if (!f) { Logf("[mesh] cannot open %s", path.c_str()); return false; }
    char magic[4]; f.read(magic, 4);
    if (memcmp(magic, "GMIM", 4) != 0) { Logf("[mesh] bad magic"); return false; }
    uint32_t ver;
    f.read((char*)&ver, 4); f.read((char*)&g.vcount, 4); f.read((char*)&g.subcount, 4); f.read((char*)&g.bonecount, 4);
    for (uint32_t i = 0; i < g.bonecount; ++i) {
        uint16_t len; f.read((char*)&len, 2);
        std::string s(len, 0); f.read(&s[0], len); g.bones.push_back(s);
    }
    // ver>=3: per-submesh render mode (0=opaque m_bdy, 1=cutout/co m_bdyco) + cutoff.
    g.submode.assign(g.subcount, 0);
    g.subcutoff.assign(g.subcount, 0.5f);
    if (ver >= 3) {
        for (uint32_t s = 0; s < g.subcount; ++s) {
            uint8_t mode = 0; float cutoff = 0.5f;
            f.read((char*)&mode, 1); f.read((char*)&cutoff, 4);
            g.submode[s] = mode; g.subcutoff[s] = cutoff;
        }
    }
    g.pos.resize(g.vcount * 3); f.read((char*)g.pos.data(), g.vcount * 3 * 4);
    g.nrm.resize(g.vcount * 3); f.read((char*)g.nrm.data(), g.vcount * 3 * 4);
    g.uv.resize(g.vcount * 2);  f.read((char*)g.uv.data(),  g.vcount * 2 * 4);
    if (ver >= 2) { g.col.resize(g.vcount * 4); f.read((char*)g.col.data(), g.vcount * 4 * 4); }
    g.wbone.resize(g.vcount * 4); g.wweight.resize(g.vcount * 4);
    for (uint32_t i = 0; i < g.vcount * 4; ++i) { f.read((char*)&g.wbone[i], 4); f.read((char*)&g.wweight[i], 4); }
    for (uint32_t s = 0; s < g.subcount; ++s) {
        uint32_t n; f.read((char*)&n, 4);
        std::vector<int> idx(n); f.read((char*)idx.data(), n * 4); g.subs.push_back(std::move(idx));
    }
    uint32_t cutoutSubs = 0;
    for (uint32_t s = 0; s < g.subcount; ++s) if (g.submode[s]) ++cutoutSubs;
    Logf("[mesh] loaded %s: verts=%u submeshes=%u bones=%u cutoutSubmeshes=%u (ver=%u)",
         path.c_str(), g.vcount, g.subcount, g.bonecount, cutoutSubs, ver);
    return f.good() || f.eof();
}

static bool Contains(const std::string& s, const char* needle) {
    return s.find(needle) != std::string::npos;
}

static bool StartsWith(const std::string& s, const char* prefix) {
    size_t n = strlen(prefix);
    return s.size() >= n && memcmp(s.data(), prefix, n) == 0;
}

static int FindLiveBone(const std::unordered_map<std::string, int>& live, const std::string& name) {
    auto it = live.find(name);
    return it != live.end() ? it->second : -1;
}

static int GuessFallbackBone(const std::unordered_map<std::string, int>& live, const std::string& name, int hips) {
    auto firstLive = [&](std::initializer_list<const char*> names) -> int {
        for (auto n : names) {
            int index = FindLiveBone(live, n);
            if (index >= 0) return index;
        }
        return -1;
    };

    if (StartsWith(name, "LeftHand")) {
        int v = firstLive({"LeftHand", "LeftForeArm", "LeftArm"});
        if (v >= 0) return v;
    }
    if (StartsWith(name, "RightHand")) {
        int v = firstLive({"RightHand", "RightForeArm", "RightArm"});
        if (v >= 0) return v;
    }
    if (StartsWith(name, "LeftForeArm") || StartsWith(name, "LeftArm")) {
        int v = firstLive({"LeftForeArm", "LeftArm", "LeftShoulder"});
        if (v >= 0) return v;
    }
    if (StartsWith(name, "RightForeArm") || StartsWith(name, "RightArm")) {
        int v = firstLive({"RightForeArm", "RightArm", "RightShoulder"});
        if (v >= 0) return v;
    }
    if (StartsWith(name, "LeftToe")) {
        int v = firstLive({"LeftToeBase", "LeftFoot", "LeftLeg"});
        if (v >= 0) return v;
    }
    if (StartsWith(name, "RightToe")) {
        int v = firstLive({"RightToeBase", "RightFoot", "RightLeg"});
        if (v >= 0) return v;
    }
    if (StartsWith(name, "LeftUpLeg") || StartsWith(name, "LeftLeg") || Contains(name, "Left") && Contains(name, "Skirt")) {
        int v = firstLive({"LeftUpLeg", "LeftLeg", "Hips"});
        if (v >= 0) return v;
    }
    if (StartsWith(name, "RightUpLeg") || StartsWith(name, "RightLeg") || Contains(name, "Right") && Contains(name, "Skirt")) {
        int v = firstLive({"RightUpLeg", "RightLeg", "Hips"});
        if (v >= 0) return v;
    }
    if (Contains(name, "Bust") || Contains(name, "Skirt") || Contains(name, "Dress")) {
        int v = firstLive({"Spine2", "Spine1", "Spine", "Hips"});
        if (v >= 0) return v;
    }
    if (Contains(name, "_Roll_H") || Contains(name, "_H")) {
        std::string stripped = name;
        size_t pos = stripped.find("_Roll_H");
        if (pos != std::string::npos) stripped.erase(pos);
        pos = stripped.find("_H");
        if (pos != std::string::npos) stripped.erase(pos);
        int v = FindLiveBone(live, stripped);
        if (v >= 0) return v;
    }
    return hips;
}

// Build a real Unity Mesh from the .gmim file, remap weights to the live bones[]
// by name, reuse the original mesh bindposes, and assign it. Main thread only.
static void* BuildFromFileAndReplace(void* renderer) {
    Gmim g;
    if (!LoadGmim(g_gmimPath, g)) return nullptr;
    if (!g_mi_meshCtor || !g_clsV3 || !g_clsBW || !g_clsInt) { Logf("[mesh] missing class/method"); return nullptr; }

    void* orig = CallObj(g_mi_getSharedMesh, renderer);
    void* bonesArr = CallObj(g_mi_getBones, renderer);
    int N = (int)ArrayCount(bonesArr); void** bptr = ArrayItems(bonesArr);
    std::unordered_map<std::string, int> live;
    for (int i = 0; i < N; ++i) live[Name(bptr[i])] = i;
    int hips = live.count("Hips") ? live["Hips"] : 0;

    // gmim bone-table index -> live index. If this costume lacks an exact bone,
    // use a nearby stable body bone so missing skirt/sleeve helpers do not
    // collapse everything to Hips.
    std::vector<int> tableToLive(g.bonecount, -1);
    int missing = 0, guessed = 0;
    std::vector<std::pair<uint32_t, std::string>> missingNames;
    for (uint32_t i = 0; i < g.bonecount; ++i) {
        auto it = live.find(g.bones[i]);
        if (it != live.end()) {
            tableToLive[i] = it->second;
        } else {
            missing++;
            tableToLive[i] = GuessFallbackBone(live, g.bones[i], hips);
            if (tableToLive[i] != hips) guessed++;
            if (missingNames.size() < 32) missingNames.push_back({i, g.bones[i]});
        }
    }
    if (missing) {
        Logf("[mesh] %d/%u gmim bones not in this costume; guessed=%d, remaining fallback=Hips", missing, g.bonecount, guessed);
        for (size_t i = 0; i < missingNames.size(); ++i) {
            uint32_t tableIndex = missingNames[i].first;
            Logf("[mesh] missing bone[%02llu]=%s -> live[%d]=%s",
                 (unsigned long long)tableIndex, missingNames[i].second.c_str(), tableToLive[tableIndex],
                 (tableToLive[tableIndex] >= 0 && tableToLive[tableIndex] < N) ? Name(bptr[tableToLive[tableIndex]]).c_str() : "?");
        }
    }

    // BoneWeight[] (x64: float w0..3 then int b0..3)
    struct BW { float w0,w1,w2,w3; int b0,b1,b2,b3; };
    std::vector<BW> bw(g.vcount);
    int fullFallbackVertices = 0, partialFallbackVertices = 0;
    double fallbackWeight = 0.0;
    for (uint32_t v = 0; v < g.vcount; ++v) {
        int   bi[4] = {0,0,0,0}; float ww[4] = {0,0,0,0}; int k = 0;
        bool usedFallback = false;
        for (int s = 0; s < 4; ++s) {
            int tb = g.wbone[v*4+s]; float w = g.wweight[v*4+s];
            if (tb < 0 || w <= 0.f) continue;
            int lv = tableToLive[tb];
            if (lv < 0) continue;
            if (g.bones[tb] != Name(bptr[lv])) { usedFallback = true; fallbackWeight += w; }
            bi[k] = lv; ww[k] = w; k++;
        }
        float sum = ww[0]+ww[1]+ww[2]+ww[3];
        if (sum <= 0.f) { bi[0] = hips; ww[0] = 1.f; sum = 1.f; fullFallbackVertices++; }
        else if (usedFallback) { partialFallbackVertices++; }
        bw[v] = { ww[0]/sum, ww[1]/sum, ww[2]/sum, ww[3]/sum, bi[0],bi[1],bi[2],bi[3] };
    }
    Logf("[mesh] fallback vertices: full=%d partial=%d fallbackWeight=%.1f",
         fullFallbackVertices, partialFallbackVertices, fallbackWeight);

    Logf("[mesh] step: object_new + ctor");
    void* mesh = il2cpp_object_new(g_meshClass); CallVoid(g_mi_meshCtor, mesh);
    Logf("[mesh] step: set_vertices/normals/uv");
    CallArr(g_mi_setVertices, mesh, NewArr(g_clsV3, g.vcount, g.pos.data(), 12));
    if (g_mi_setNormals) CallArr(g_mi_setNormals, mesh, NewArr(g_clsV3, g.vcount, g.nrm.data(), 12));
    if (g_mi_setUV && g_clsV2) CallArr(g_mi_setUV, mesh, NewArr(g_clsV2, g.vcount, g.uv.data(), 8));
    // vertex COLOR: Gakumas toon shader reads COLOR0; without it the body renders black.
    if (g_mi_setColors && g_clsColor && g.col.size() == (size_t)g.vcount * 4) {
        Logf("[mesh] step: set_colors");
        CallArr(g_mi_setColors, mesh, NewArr(g_clsColor, g.vcount, g.col.data(), 16));
    } else {
        Logf("[mesh] no vertex colors in gmim (ver<2?) -- body may render black");
    }
    Logf("[mesh] step: set_boneWeights");
    CallArr(g_mi_setBoneWeights, mesh, NewArr(g_clsBW, g.vcount, bw.data(), 32));
    Logf("[mesh] step: bindposes (reuse original)");
    void* bp = CallObj(g_mi_getBindposes, orig);
    if (bp) CallArr(g_mi_setBindposes, mesh, bp);
    int originalSubmeshes = CallInt(g_mi_subMeshCount, orig);
    bool materialsReady = EnsureSharedMaterials(renderer, g);
    if (!materialsReady && originalSubmeshes <= 1 && g.subcount > 1) {
        std::vector<int> merged;
        size_t total = 0;
        for (const auto& sub : g.subs) total += sub.size();
        merged.reserve(total);
        for (const auto& sub : g.subs) merged.insert(merged.end(), sub.begin(), sub.end());
        Logf("[mesh] step: sharedMaterials unavailable; target has %d submesh/material; merge gmim %u submeshes -> 1 (%llu indices)",
             originalSubmeshes, g.subcount, (unsigned long long)merged.size());
        if (g_mi_setSubMeshCount) reinterpret_cast<set_int_t>(MethodPtr(g_mi_setSubMeshCount))(mesh, 1, g_mi_setSubMeshCount);
        void* aT = NewArr(g_clsInt, merged.size(), merged.data(), 4);
        if (g_mi_SetTrianglesN) reinterpret_cast<set_tris_t>(MethodPtr(g_mi_SetTrianglesN))(mesh, aT, 0, g_mi_SetTrianglesN);
        else CallArr(g_mi_setTriangles, mesh, aT);
    } else {
        Logf("[mesh] step: subMeshCount=%u + SetTriangles (target original submeshes=%d, materialsReady=%d)",
             g.subcount, originalSubmeshes, materialsReady ? 1 : 0);
        if (g_mi_setSubMeshCount) reinterpret_cast<set_int_t>(MethodPtr(g_mi_setSubMeshCount))(mesh, (int)g.subcount, g_mi_setSubMeshCount);
        for (uint32_t s = 0; s < g.subcount; ++s) {
            void* aT = NewArr(g_clsInt, g.subs[s].size(), g.subs[s].data(), 4);
            if (g_mi_SetTrianglesN) reinterpret_cast<set_tris_t>(MethodPtr(g_mi_SetTrianglesN))(mesh, aT, (int)s, g_mi_SetTrianglesN);
            else CallArr(g_mi_setTriangles, mesh, aT);   // single-submesh fallback
        }
    }
    if (g_mi_recalcBounds) CallVoid(g_mi_recalcBounds, mesh);
    if (g_mi_setHideFlags) reinterpret_cast<set_int_t>(MethodPtr(g_mi_setHideFlags))(mesh, 32, g_mi_setHideFlags);
    if (il2cpp_gchandle_new) il2cpp_gchandle_new(mesh, 1);
    if (g_mi_setUpdateOff) reinterpret_cast<set_int_t>(MethodPtr(g_mi_setUpdateOff))(renderer, 1, g_mi_setUpdateOff);
    reinterpret_cast<set_obj_t>(MethodPtr(g_mi_setSharedMesh))(renderer, mesh, g_mi_setSharedMesh);
    Logf("[mesh] DONE assigned real mesh=%p to renderer=%p", mesh, renderer);
    return mesh;
}

// ---- main-thread pump: hook Time.get_deltaTime (called every frame on the main
// thread). F8 sets g_doBuild; the build then runs HERE, on the main thread, where
// creating a Mesh is legal. ----
static volatile bool g_doBuild = false;      // F6: quad diagnostic
static volatile bool g_doMeshFile = false;   // F8: real mesh from .gmim
static void* g_buildTarget = nullptr;
typedef float (*getDelta_t)(void* mi);
static getDelta_t g_origGetDelta = nullptr;
static void* g_mi_getDelta = nullptr;

static float Hook_getDeltaTime(void* mi) {
    float r = g_origGetDelta ? g_origGetDelta(mi) : 0.0f;
    if (g_doBuild) {
        g_doBuild = false;
        Logf("[main] quad build on main thread (tid=%lu)", GetCurrentThreadId());
        BuildQuadAndReplace(g_buildTarget);
    }
    if (g_doMeshFile) {
        g_doMeshFile = false;
        Logf("[main] real-mesh build on main thread (tid=%lu)", GetCurrentThreadId());
        BuildFromFileAndReplace(g_buildTarget);
    }
    return r;
}

// ------------------------------ init / poll ---------------------------------
static DWORD WINAPI InitThread(LPVOID) {
    AllocConsole();
    FILE* f; freopen_s(&f, "CONOUT$", "w", stdout);
    SetConsoleTitleA("GakumasMI IL2CPP probe");

    char exe[MAX_PATH]; GetModuleFileNameA(nullptr, exe, MAX_PATH);
    std::string dir(exe); dir = dir.substr(0, dir.find_last_of("\\/") + 1);
    std::string logPath = dir + "gkms_meshprobe.log";
    g_gmimPath = dir + "yuika.gmim";
    g_atlasPath = dir + "yuika_atlas.png";
    g_log.open(logPath, std::ios::out | std::ios::trunc);
    Logf("[probe] log: %s", logPath.c_str());
    Logf("[probe] gmim: %s", g_gmimPath.c_str());
    Logf("[probe] atlas: %s", g_atlasPath.c_str());

    HMODULE ga = nullptr;
    for (int i = 0; i < 600; ++i) {
        ga = GetModuleHandleA("GameAssembly.dll");
        if (ga && ResolveIl2cppApi(ga) && il2cpp_domain_get()) break;
        ga = nullptr; Sleep(100);
    }
    if (!ga) { Logf("[probe] GameAssembly.dll / il2cpp not found"); return 0; }
    if (il2cpp_thread_attach) il2cpp_thread_attach(il2cpp_domain_get());
    Logf("[probe] il2cpp ready");

    void* core = nullptr;
    for (int i = 0; i < 300; ++i) { core = FindImage("UnityEngine.CoreModule.dll"); if (core) break; Sleep(100); }
    if (!core) { Logf("[probe] UnityEngine.CoreModule.dll not found"); return 0; }

    void* smr  = il2cpp_class_from_name(core, "UnityEngine", "SkinnedMeshRenderer");
    void* rendererClass = il2cpp_class_from_name(core, "UnityEngine", "Renderer");
    void* materialClass = il2cpp_class_from_name(core, "UnityEngine", "Material");
    void* shaderClass = il2cpp_class_from_name(core, "UnityEngine", "Shader");
    void* texture2DClass = il2cpp_class_from_name(core, "UnityEngine", "Texture2D");
    void* mesh = il2cpp_class_from_name(core, "UnityEngine", "Mesh");
    void* obj  = il2cpp_class_from_name(core, "UnityEngine", "Object");
    void* res  = il2cpp_class_from_name(core, "UnityEngine", "Resources");
    if (!smr || !mesh || !obj || !res) { Logf("[probe] class resolve failed"); return 0; }

    g_mi_findAll       = il2cpp_class_get_method_from_name(res, "FindObjectsOfTypeAll", 1);
    g_mi_getSharedMesh = il2cpp_class_get_method_from_name(smr, "get_sharedMesh", 0);
    g_mi_setSharedMesh = il2cpp_class_get_method_from_name(smr, "set_sharedMesh", 1);
    g_mi_getBones      = il2cpp_class_get_method_from_name(smr, "get_bones", 0);
    g_mi_vertexCount   = il2cpp_class_get_method_from_name(mesh, "get_vertexCount", 0);
    g_mi_subMeshCount  = il2cpp_class_get_method_from_name(mesh, "get_subMeshCount", 0);
    g_mi_getBindposes  = il2cpp_class_get_method_from_name(mesh, "get_bindposes", 0);
    g_mi_getTriangles  = il2cpp_class_get_method_from_name(mesh, "get_triangles", 0);
    g_mi_getName       = il2cpp_class_get_method_from_name(obj, "get_name", 0);
    g_mi_setHideFlags  = il2cpp_class_get_method_from_name(obj, "set_hideFlags", 1);
    g_mi_setUpdateOff  = il2cpp_class_get_method_from_name(smr, "set_updateWhenOffscreen", 1);
    g_mi_getSharedMaterials = rendererClass ? il2cpp_class_get_method_from_name(rendererClass, "get_sharedMaterials", 0) : nullptr;
    g_mi_setSharedMaterials = rendererClass ? il2cpp_class_get_method_from_name(rendererClass, "set_sharedMaterials", 1) : nullptr;
    g_mi_materialCtorCopy = materialClass ? il2cpp_class_get_method_from_name(materialClass, ".ctor", 1) : nullptr;
    g_mi_getMainTexture = materialClass ? il2cpp_class_get_method_from_name(materialClass, "get_mainTexture", 0) : nullptr;
    g_mi_setMainTexture = materialClass ? il2cpp_class_get_method_from_name(materialClass, "set_mainTexture", 1) : nullptr;
    g_mi_hasPropertyString = FindMethodByParamName(materialClass, "HasProperty", 1, "String");
    g_mi_getTextureString = FindMethodByParamName(materialClass, "GetTexture", 1, "String");
    g_mi_setTextureString = FindMethodByParamName(materialClass, "SetTexture", 2, "String");
    g_mi_hasPropertyId = FindMethodByParamName(materialClass, "HasProperty", 1, "Int32");
    g_mi_getTextureId = FindMethodByParamName(materialClass, "GetTexture", 1, "Int32");
    g_mi_setTextureId = FindMethodByParamName(materialClass, "SetTexture", 2, "Int32");
    g_mi_propertyToID = FindMethodByParamName(shaderClass, "PropertyToID", 1, "String");
    g_mi_setFloatStr = FindMethodByParamName(materialClass, "SetFloat", 2, "String");
    g_mi_getFloatStr = FindMethodByParamName(materialClass, "GetFloat", 1, "String");
    g_mi_enableKeyword = FindMethodByParamName(materialClass, "EnableKeyword", 1, "String");
    g_mi_disableKeyword = FindMethodByParamName(materialClass, "DisableKeyword", 1, "String");
    g_mi_setRenderQueue = materialClass ? il2cpp_class_get_method_from_name(materialClass, "set_renderQueue", 1) : nullptr;
    g_mi_getShader = materialClass ? il2cpp_class_get_method_from_name(materialClass, "get_shader", 0) : nullptr;
    g_mi_getShaderKeywords = materialClass ? il2cpp_class_get_method_from_name(materialClass, "get_shaderKeywords", 0) : nullptr;
    Logf("[tex] SetFloat=%p EnableKeyword=%p set_renderQueue=%p", g_mi_setFloatStr, g_mi_enableKeyword, g_mi_setRenderQueue);
    if (!g_mi_hasPropertyString) g_mi_hasPropertyString = materialClass ? il2cpp_class_get_method_from_name(materialClass, "HasProperty", 1) : nullptr;
    if (!g_mi_getTextureString) g_mi_getTextureString = materialClass ? il2cpp_class_get_method_from_name(materialClass, "GetTexture", 1) : nullptr;
    if (!g_mi_setTextureString) g_mi_setTextureString = materialClass ? il2cpp_class_get_method_from_name(materialClass, "SetTexture", 2) : nullptr;
    if (!g_mi_propertyToID) g_mi_propertyToID = shaderClass ? il2cpp_class_get_method_from_name(shaderClass, "PropertyToID", 1) : nullptr;
    g_smrTypeObject    = il2cpp_type_get_object(il2cpp_class_get_type(smr));

    // --- build-a-Mesh resolutions ---
    g_meshClass        = mesh;
    g_mi_meshCtor      = il2cpp_class_get_method_from_name(mesh, ".ctor", 0);
    g_mi_setVertices   = il2cpp_class_get_method_from_name(mesh, "set_vertices", 1);
    g_mi_setNormals    = il2cpp_class_get_method_from_name(mesh, "set_normals", 1);
    g_mi_setUV         = il2cpp_class_get_method_from_name(mesh, "set_uv", 1);
    g_mi_setColors     = il2cpp_class_get_method_from_name(mesh, "set_colors", 1);
    g_mi_setBoneWeights= il2cpp_class_get_method_from_name(mesh, "set_boneWeights", 1);
    g_mi_setBindposes  = il2cpp_class_get_method_from_name(mesh, "set_bindposes", 1);
    g_mi_setTriangles  = il2cpp_class_get_method_from_name(mesh, "set_triangles", 1);
    g_mi_setSubMeshCount = il2cpp_class_get_method_from_name(mesh, "set_subMeshCount", 1);
    g_mi_SetTrianglesN = il2cpp_class_get_method_from_name(mesh, "SetTriangles", 2);
    g_mi_recalcBounds  = il2cpp_class_get_method_from_name(mesh, "RecalculateBounds", 0);
    g_clsV3 = il2cpp_class_from_name(core, "UnityEngine", "Vector3");
    g_clsV2 = il2cpp_class_from_name(core, "UnityEngine", "Vector2");
    g_clsColor = il2cpp_class_from_name(core, "UnityEngine", "Color");
    g_clsM4 = il2cpp_class_from_name(core, "UnityEngine", "Matrix4x4");
    g_clsBW = il2cpp_class_from_name(core, "UnityEngine", "BoneWeight");
    g_clsMaterial = materialClass;
    g_clsTexture2D = texture2DClass;
    void* corlib = FindImage("mscorlib.dll");
    g_clsInt = corlib ? il2cpp_class_from_name(corlib, "System", "Int32") : nullptr;
    g_clsByte = corlib ? il2cpp_class_from_name(corlib, "System", "Byte") : nullptr;
    void* imageConversionImage = FindImage("UnityEngine.ImageConversionModule.dll");
    void* imageConversionClass = imageConversionImage ? il2cpp_class_from_name(imageConversionImage, "UnityEngine", "ImageConversion") : nullptr;
    g_mi_tex2dCtorII = texture2DClass ? il2cpp_class_get_method_from_name(texture2DClass, ".ctor", 2) : nullptr;
    g_mi_tex2dCtor4  = texture2DClass ? il2cpp_class_get_method_from_name(texture2DClass, ".ctor", 4) : nullptr;
    // LoadRawTextureData(byte[]) vs LoadRawTextureData<T>(NativeArray<T>) -- both argc 1.
    // Resolve the byte[] overload by signature, else neutral maps become garbage -> black.
    g_mi_loadRaw     = texture2DClass ? FindMethodByParamAt(texture2DClass, "LoadRawTextureData", 1, 0, "Byte[]") : nullptr;
    if (!g_mi_loadRaw && texture2DClass)
        g_mi_loadRaw = il2cpp_class_get_method_from_name(texture2DClass, "LoadRawTextureData", 1);
    g_mi_apply       = texture2DClass ? il2cpp_class_get_method_from_name(texture2DClass, "Apply", 0) : nullptr;
    // Resolve the byte[] overload specifically (param1 = System.Byte[]), not NativeArray.
    g_mi_loadImage = imageConversionClass ? FindMethodByParamAt(imageConversionClass, "LoadImage", 3, 1, "Byte[]") : nullptr;
    if (!g_mi_loadImage && imageConversionClass)
        g_mi_loadImage = il2cpp_class_get_method_from_name(imageConversionClass, "LoadImage", 3);
    void* fileClass = corlib ? il2cpp_class_from_name(corlib, "System.IO", "File") : nullptr;
    g_mi_fileReadAllBytes = fileClass ? il2cpp_class_get_method_from_name(fileClass, "ReadAllBytes", 1) : nullptr;
    void* textureBase = il2cpp_class_from_name(core, "UnityEngine", "Texture");
    g_mi_texWidth  = textureBase ? il2cpp_class_get_method_from_name(textureBase, "get_width", 0) : nullptr;
    g_mi_texHeight = textureBase ? il2cpp_class_get_method_from_name(textureBase, "get_height", 0) : nullptr;
    Logf("[tex] ctor2=%p loadImage=%p File.ReadAllBytes=%p", g_mi_tex2dCtorII, g_mi_loadImage, g_mi_fileReadAllBytes);

    // main-thread pump hook on Time.get_deltaTime
    void* timeClass = il2cpp_class_from_name(core, "UnityEngine", "Time");
    g_mi_getDelta = timeClass ? il2cpp_class_get_method_from_name(timeClass, "get_deltaTime", 0) : nullptr;
    void* deltaTarget = MethodPtr(g_mi_getDelta);
    if (deltaTarget && MH_Initialize() == MH_OK &&
        MH_CreateHook(deltaTarget, reinterpret_cast<void*>(&Hook_getDeltaTime),
                      reinterpret_cast<void**>(&g_origGetDelta)) == MH_OK &&
        MH_EnableHook(deltaTarget) == MH_OK) {
        Logf("[main] hooked Time.get_deltaTime @ %p (main-thread pump ready)", deltaTarget);
    } else {
        Logf("[main] FAILED to hook Time.get_deltaTime @ %p -- F8 build will not work", deltaTarget);
    }

    Logf("[probe] methods findAll=%p sharedMesh=%p vc=%p name=%p type=%p", g_mi_findAll, g_mi_getSharedMesh, g_mi_vertexCount, g_mi_getName, g_smrTypeObject);
    Logf("[build] ctor=%p setV=%p setN=%p setUV=%p setBW=%p setBP=%p setTri=%p V3=%p BW=%p Int=%p",
         g_mi_meshCtor, g_mi_setVertices, g_mi_setNormals, g_mi_setUV, g_mi_setBoneWeights,
         g_mi_setBindposes, g_mi_setTriangles, g_clsV3, g_clsBW, g_clsInt);
    Logf("[build] materials get=%p set=%p Material=%p", g_mi_getSharedMaterials, g_mi_setSharedMaterials, g_clsMaterial);
    Logf("[tex] Texture2D=%p ctor=%p ImageConversion.LoadImage=%p Byte=%p setMainTexture=%p matCopy=%p",
         g_clsTexture2D, g_mi_tex2dCtorII, g_mi_loadImage, g_clsByte, g_mi_setMainTexture, g_mi_materialCtorCopy);
    Logf("[tex] getMainTexture=%p", g_mi_getMainTexture);
    Logf("[tex] PropertyToID=%p string_new=%p", g_mi_propertyToID, il2cpp_string_new);
    Logf("[tex] String Has/Get/Set=%p/%p/%p  ID Has/Get/Set=%p/%p/%p",
         g_mi_hasPropertyString, g_mi_getTextureString, g_mi_setTextureString,
         g_mi_hasPropertyId, g_mi_getTextureId, g_mi_setTextureId);
    if (!g_mi_findAll || !g_mi_getSharedMesh || !g_smrTypeObject) { Logf("[probe] missing essentials"); return 0; }

    Logf("[probe] ready. Hotkeys: F6 = quad, F7 = blank, F8 = real mesh (yuika.gmim), F9 = restore.");
    std::unordered_set<void*> seenMesh;
    bool dumpedBones = false;
    void* savedRenderer = nullptr;   // for the F8/F9 write test
    void* savedMesh = nullptr;
    void* findFn = MethodPtr(g_mi_findAll);
    set_obj_t setMeshFn = reinterpret_cast<set_obj_t>(MethodPtr(g_mi_setSharedMesh));

    auto gmimBoneNames = [&]() -> std::vector<std::string> {
        Gmim g;
        if (!LoadGmim(g_gmimPath, g)) return {};
        return g.bones;
    };

    auto bodyBoneCoverage = [&](void* renderer, const std::vector<std::string>& names) -> int {
        if (!renderer || names.empty()) return 0;
        void* bonesArr = CallObj(g_mi_getBones, renderer);
        int N = (int)ArrayCount(bonesArr);
        void** bptr = ArrayItems(bonesArr);
        std::unordered_set<std::string> live;
        for (int i = 0; i < N; ++i) live.insert(Name(bptr[i]));
        int matched = 0;
        for (const auto& name : names) {
            if (live.count(name)) matched++;
        }
        return matched;
    };

    auto findBestBody = [&]() -> void* {
        std::vector<std::string> names = gmimBoneNames();
        void* arr = reinterpret_cast<get_obj_t>(findFn)(g_smrTypeObject, g_mi_findAll);
        uintptr_t n = ArrayCount(arr); void** items = ArrayItems(arr);
        void* best = nullptr;
        int bestMatched = -1, bestBones = 0, bestVerts = 0, bestSubmeshes = 0;
        for (uintptr_t i = 0; i < n; ++i) {
            void* r = items[i];
            if (!r) continue;
            void* m = CallObj(g_mi_getSharedMesh, r);
            if (!m || Name(m) != "Geo_Body") continue;
            int matched = bodyBoneCoverage(r, names);
            int bones = (int)ArrayCount(CallObj(g_mi_getBones, r));
            int vc = CallInt(g_mi_vertexCount, m);
            int sm = CallInt(g_mi_subMeshCount, m);
            Logf("[pick] Geo_Body candidate renderer=%p verts=%d submeshes=%d bones=%d match=%d/%llu",
                 r, vc, sm, bones, matched, (unsigned long long)names.size());
            if (matched > bestMatched || (matched == bestMatched && bones > bestBones)) {
                best = r;
                bestMatched = matched;
                bestBones = bones;
                bestVerts = vc;
                bestSubmeshes = sm;
            }
        }
        if (!best) return nullptr;
        if (!names.empty() && bestMatched < (int)(names.size() * 95 / 100)) {
            Logf("[pick] best Geo_Body renderer=%p verts=%d submeshes=%d bones=%d match=%d/%llu -- not compatible enough; wait for the correct costume body",
                 best, bestVerts, bestSubmeshes, bestBones, bestMatched, (unsigned long long)names.size());
            return nullptr;
        }
        Logf("[pick] selected Geo_Body renderer=%p verts=%d submeshes=%d bones=%d match=%d/%llu",
             best, bestVerts, bestSubmeshes, bestBones, bestMatched, (unsigned long long)names.size());
        return best;
    };

    int tick = 0;
    while (true) {
        // ---- hotkeys (~10 Hz) ----
        if (GetAsyncKeyState(VK_F5) & 1) {                  // dump live materials by mesh name
            void* arr = reinterpret_cast<get_obj_t>(findFn)(g_smrTypeObject, g_mi_findAll);
            uintptr_t n = ArrayCount(arr); void** items = ArrayItems(arr);
            bool dumpedCurtain = false, dumpedBody = false;
            for (uintptr_t i = 0; i < n; ++i) {
                void* r = items[i]; if (!r) continue;
                void* m = CallObj(g_mi_getSharedMesh, r); if (!m) continue;
                std::string mn = Name(m);
                void* mats = CallObj(g_mi_getSharedMaterials, r);
                void* mat0 = (ArrayCount(mats) > 0) ? ArrayItems(mats)[0] : nullptr;
                if (mn == "Geo_Dresscurtain" && !dumpedCurtain) { dumpedCurtain = true; DumpMaterial("CUTOUT Geo_Dresscurtain", mat0); }
                if (mn == "Geo_Body" && !dumpedBody) { dumpedBody = true; DumpMaterial("OPAQUE Geo_Body", mat0); }
            }
            if (!dumpedCurtain) Logf("[matdump] no Geo_Dresscurtain in scene");
        }
        if (GetAsyncKeyState(VK_F7) & 1) {                  // blank (diagnostic)
            void* r = findBestBody();
            if (r && setMeshFn) {
                savedRenderer = r; savedMesh = CallObj(g_mi_getSharedMesh, r);
                setMeshFn(r, nullptr, g_mi_setSharedMesh);
                Logf("[write] F7: blanked Geo_Body renderer=%p (saved mesh=%p)", r, savedMesh);
            } else Logf("[write] F7: no Geo_Body found");
        }
        if (GetAsyncKeyState(VK_F6) & 1) {                  // quad diagnostic
            void* r = findBestBody();
            if (r) { savedRenderer = r; savedMesh = CallObj(g_mi_getSharedMesh, r); g_buildTarget = r; g_doBuild = true;
                     Logf("[build] F6: queued quad for renderer=%p (saved mesh=%p)", r, savedMesh); }
            else Logf("[build] F6: no Geo_Body found");
        }
        if (GetAsyncKeyState(VK_F8) & 1) {                  // real mesh from yuika.gmim
            void* r = findBestBody();
            if (r) { savedRenderer = r; savedMesh = CallObj(g_mi_getSharedMesh, r); g_buildTarget = r; g_doMeshFile = true;
                     Logf("[mesh] F8: queued real mesh for renderer=%p (saved mesh=%p)", r, savedMesh); }
            else Logf("[mesh] F8: no Geo_Body found");
        }
        if (GetAsyncKeyState(VK_F9) & 1) {
            if (savedRenderer && savedMesh && setMeshFn) {
                setMeshFn(savedRenderer, savedMesh, g_mi_setSharedMesh);  // restore
                Logf("[write] F9: restored mesh=%p to renderer=%p. Body should reappear.",
                     savedMesh, savedRenderer);
            } else {
                Logf("[write] F9: nothing saved to restore");
            }
        }

        // ---- enumerate ~every 3s ----
        if (tick % 30 == 0) {
            void* arr = reinterpret_cast<get_obj_t>(findFn)(g_smrTypeObject, g_mi_findAll);
            uintptr_t n = ArrayCount(arr);
            void** items = ArrayItems(arr);
            for (uintptr_t i = 0; i < n; ++i) {
                void* renderer = items[i];
                if (!renderer) continue;
                void* m = CallObj(g_mi_getSharedMesh, renderer);
                if (!m || seenMesh.count(m)) continue;
                seenMesh.insert(m);
                int vc    = CallInt(g_mi_vertexCount, m);
                int sm    = CallInt(g_mi_subMeshCount, m);
                int bones = (int)ArrayCount(CallObj(g_mi_getBones, renderer));
                int binds = (int)ArrayCount(CallObj(g_mi_getBindposes, m));
                int tris  = (int)(ArrayCount(CallObj(g_mi_getTriangles, m)) / 3);
                std::string mname = Name(m);
                bool isBody = (mname == "Geo_Body");
                Logf("[probe] renderer='%s' mesh='%s' verts=%d submeshes=%d tris=%d bones=%d bindposes=%d%s",
                     Name(renderer).c_str(), mname.c_str(), vc, sm, tris, bones, binds,
                     isBody ? "  <== BODY (replace target)" : "");
                if (isBody && !dumpedBones) {
                    dumpedBones = true;
                    void* bonesArr = CallObj(g_mi_getBones, renderer);
                    uintptr_t bn = ArrayCount(bonesArr);
                    void** bptr = ArrayItems(bonesArr);
                    Logf("[bones] Geo_Body bone list (%llu):", (unsigned long long)bn);
                    for (uintptr_t b = 0; b < bn; ++b)
                        Logf("[bones] %3llu  %s", (unsigned long long)b, Name(bptr[b]).c_str());
                }
            }
        }
        tick++;
        Sleep(100);
    }
}

BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        CreateThread(nullptr, 0, InitThread, nullptr, 0, nullptr);
    }
    return TRUE;
}
