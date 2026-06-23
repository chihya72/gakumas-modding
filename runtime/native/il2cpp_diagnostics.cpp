#include "runtime.h"

#include <chrono>
#include <cstdint>
#include <sstream>
#include <string_view>
#include <thread>
#include <unordered_set>

namespace {
template <typename T>
T Export(HMODULE module, const char* name) {
    return reinterpret_cast<T>(GetProcAddress(module, name));
}

std::string PointerText(const void* pointer) {
    std::ostringstream stream;
    stream << pointer;
    return stream.str();
}

using class_get_method_from_name_t = const void* (*)(void*, const char*, int);
using image_get_class_count_t = std::size_t (*)(const void*);
using image_get_class_t = void* (*)(const void*, std::size_t);
using class_get_methods_t = const void* (*)(void*, void**);
using class_get_name_t = const char* (*)(void*);
using class_get_namespace_t = const char* (*)(void*);
using method_get_name_t = const char* (*)(const void*);

void LogMethod(
    class_get_method_from_name_t class_get_method,
    void* klass,
    const char* class_name,
    const char* method_name,
    int argument_count) {
    const void* method = klass
        ? class_get_method(klass, method_name, argument_count)
        : nullptr;
    RuntimeLog(
        std::string("UnityEngine.") + class_name + "." + method_name +
        "(" + std::to_string(argument_count) + ")=" + PointerText(method));
}

void ScanGameMethodOwners(
    const void** assemblies,
    std::size_t assembly_count,
    const void* (*assembly_get_image)(const void*),
    const char* (*image_get_name)(const void*),
    image_get_class_count_t image_get_class_count,
    image_get_class_t image_get_class,
    class_get_methods_t class_get_methods,
    class_get_name_t class_get_name,
    class_get_namespace_t class_get_namespace,
    method_get_name_t method_get_name) {
    const std::unordered_set<std::string_view> target_methods = {
        "SetBodyCostume",
        "SetHeadCostume",
        "get_BodyAssetId",
        "get_CostumeAssetNames",
        "GetActorCostumes",
        "SetPreviewCostumes",
        "SetSelectedCostume",
    };

    std::size_t match_count = 0;
    for (std::size_t assembly_index = 0; assembly_index < assembly_count; ++assembly_index) {
        const void* image = assembly_get_image(assemblies[assembly_index]);
        if (!image) continue;
        const char* image_name = image_get_name(image);
        const std::size_t class_count = image_get_class_count(image);
        for (std::size_t class_index = 0; class_index < class_count; ++class_index) {
            void* klass = image_get_class(image, class_index);
            if (!klass) continue;
            void* iterator = nullptr;
            while (const void* method = class_get_methods(klass, &iterator)) {
                const char* method_name = method_get_name(method);
                if (!method_name || target_methods.find(method_name) == target_methods.end()) continue;
                const char* namespace_name = class_get_namespace(klass);
                const char* class_name = class_get_name(klass);
                RuntimeLog(
                    std::string("Game method owner: ") +
                    (image_name ? image_name : "<unknown image>") + " :: " +
                    (namespace_name ? namespace_name : "") + "." +
                    (class_name ? class_name : "<unknown class>") + "." + method_name);
                ++match_count;
            }
        }
    }
    RuntimeLog("Game method owner scan complete; matches=" + std::to_string(match_count));
}
}

void RunIl2CppDiagnostics() {
    HMODULE game_assembly = nullptr;
    for (int attempt = 0; attempt < 600 && !game_assembly; ++attempt) {
        game_assembly = GetModuleHandleW(L"GameAssembly.dll");
        if (!game_assembly) std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    if (!game_assembly) {
        RuntimeLog("ERROR: GameAssembly.dll was not available after 60 seconds");
        return;
    }
    RuntimeLog("GameAssembly.dll located");

    using domain_get_t = void* (*)();
    using thread_attach_t = void* (*)(void*);
    using domain_get_assemblies_t = const void** (*)(void*, std::size_t*);
    using assembly_get_image_t = const void* (*)(const void*);
    using image_get_name_t = const char* (*)(const void*);
    using class_from_name_t = void* (*)(const void*, const char*, const char*);

    auto domain_get = Export<domain_get_t>(game_assembly, "il2cpp_domain_get");
    auto thread_attach = Export<thread_attach_t>(game_assembly, "il2cpp_thread_attach");
    auto domain_get_assemblies = Export<domain_get_assemblies_t>(game_assembly, "il2cpp_domain_get_assemblies");
    auto assembly_get_image = Export<assembly_get_image_t>(game_assembly, "il2cpp_assembly_get_image");
    auto image_get_name = Export<image_get_name_t>(game_assembly, "il2cpp_image_get_name");
    auto class_from_name = Export<class_from_name_t>(game_assembly, "il2cpp_class_from_name");
    auto class_get_method = Export<class_get_method_from_name_t>(game_assembly, "il2cpp_class_get_method_from_name");
    auto image_get_class_count = Export<image_get_class_count_t>(game_assembly, "il2cpp_image_get_class_count");
    auto image_get_class = Export<image_get_class_t>(game_assembly, "il2cpp_image_get_class");
    auto class_get_methods = Export<class_get_methods_t>(game_assembly, "il2cpp_class_get_methods");
    auto class_get_name = Export<class_get_name_t>(game_assembly, "il2cpp_class_get_name");
    auto class_get_namespace = Export<class_get_namespace_t>(game_assembly, "il2cpp_class_get_namespace");
    auto method_get_name = Export<method_get_name_t>(game_assembly, "il2cpp_method_get_name");
    if (!domain_get || !thread_attach || !domain_get_assemblies || !assembly_get_image ||
        !image_get_name || !class_from_name || !class_get_method || !image_get_class_count ||
        !image_get_class || !class_get_methods || !class_get_name || !class_get_namespace ||
        !method_get_name) {
        RuntimeLog("ERROR: one or more required IL2CPP exports are missing");
        return;
    }

    void* domain = domain_get();
    if (!domain) {
        RuntimeLog("ERROR: il2cpp_domain_get returned null");
        return;
    }
    thread_attach(domain);
    std::size_t assembly_count = 0;
    const void** assemblies = domain_get_assemblies(domain, &assembly_count);
    RuntimeLog("IL2CPP domain attached; assemblies=" + std::to_string(assembly_count));

    const void* core_image = nullptr;
    const void* asset_bundle_image = nullptr;
    const void* game_image = nullptr;
    for (std::size_t index = 0; index < assembly_count; ++index) {
        const void* image = assembly_get_image(assemblies[index]);
        const char* name = image ? image_get_name(image) : nullptr;
        if (!name) continue;
        std::string image_name(name);
        if (image_name == "UnityEngine.CoreModule.dll") core_image = image;
        if (image_name == "UnityEngine.AssetBundleModule.dll") asset_bundle_image = image;
        if (image_name == "Assembly-CSharp.dll") game_image = image;
    }
    if (!core_image || !asset_bundle_image) {
        RuntimeLog("ERROR: required UnityEngine images were not found");
        return;
    }

    void* mesh_class = class_from_name(core_image, "UnityEngine", "Mesh");
    void* object_class = class_from_name(core_image, "UnityEngine", "Object");
    void* component_class = class_from_name(core_image, "UnityEngine", "Component");
    void* transform_class = class_from_name(core_image, "UnityEngine", "Transform");
    void* renderer_class = class_from_name(core_image, "UnityEngine", "Renderer");
    void* skinned_mesh_renderer_class = class_from_name(
        core_image, "UnityEngine", "SkinnedMeshRenderer");
    void* asset_bundle_class = class_from_name(asset_bundle_image, "UnityEngine", "AssetBundle");
    const void* load_asset_internal = asset_bundle_class
        ? class_get_method(asset_bundle_class, "LoadAsset_Internal", 2) : nullptr;

    RuntimeLog("UnityEngine.Mesh class=" + PointerText(mesh_class));
    RuntimeLog("UnityEngine.SkinnedMeshRenderer class=" + PointerText(skinned_mesh_renderer_class));
    RuntimeLog("UnityEngine.Renderer class=" + PointerText(renderer_class));
    RuntimeLog("UnityEngine.Transform class=" + PointerText(transform_class));
    RuntimeLog("UnityEngine.Component class=" + PointerText(component_class));

    LogMethod(class_get_method, object_class, "Object", "get_name", 0);
    LogMethod(class_get_method, component_class, "Component", "get_transform", 0);
    LogMethod(class_get_method, transform_class, "Transform", "get_localToWorldMatrix", 0);
    LogMethod(class_get_method, transform_class, "Transform", "get_worldToLocalMatrix", 0);
    LogMethod(class_get_method, renderer_class, "Renderer", "get_enabled", 0);
    LogMethod(class_get_method, skinned_mesh_renderer_class, "SkinnedMeshRenderer", "get_sharedMesh", 0);
    LogMethod(class_get_method, skinned_mesh_renderer_class, "SkinnedMeshRenderer", "set_sharedMesh", 1);
    LogMethod(class_get_method, skinned_mesh_renderer_class, "SkinnedMeshRenderer", "get_bones", 0);
    LogMethod(class_get_method, skinned_mesh_renderer_class, "SkinnedMeshRenderer", "set_bones", 1);
    LogMethod(class_get_method, skinned_mesh_renderer_class, "SkinnedMeshRenderer", "get_rootBone", 0);
    LogMethod(class_get_method, mesh_class, "Mesh", "get_vertexCount", 0);
    LogMethod(class_get_method, mesh_class, "Mesh", "get_bindposes", 0);
    LogMethod(class_get_method, mesh_class, "Mesh", "get_boneWeights", 0);
    LogMethod(class_get_method, mesh_class, "Mesh", "GetBonesPerVertex", 0);
    LogMethod(class_get_method, mesh_class, "Mesh", "GetAllBoneWeights", 0);
    LogMethod(class_get_method, mesh_class, "Mesh", "SetVertices", 1);
    LogMethod(class_get_method, mesh_class, "Mesh", "SetBoneWeights", 2);
    RuntimeLog("UnityEngine.AssetBundle.LoadAsset_Internal(2)=" + PointerText(load_asset_internal));

    // Fixed lookups only. These owners were identified by the one successful
    // portion of the earlier scan; no global class/method enumeration occurs.
    if (game_image) {
        void* live_idol_data = class_from_name(
            game_image, "Campus.Live.Data", "LiveIdolData");
        void* photography_slot = class_from_name(
            game_image, "Campus.Photography", "PhotographyIdolSlotData");
        void* costume_select_model = class_from_name(
            game_image, "Campus.OutGame.Costume", "CostumeSelectScreenModel");
        RuntimeLog("Game.LiveIdolData=" + PointerText(live_idol_data));
        RuntimeLog("Game.LiveIdolData.get_CostumeAssetNames(0)=" + PointerText(
            live_idol_data ? class_get_method(live_idol_data, "get_CostumeAssetNames", 0) : nullptr));
        RuntimeLog("Game.PhotographyIdolSlotData=" + PointerText(photography_slot));
        RuntimeLog("Game.PhotographyIdolSlotData.SetBodyCostume(1)=" + PointerText(
            photography_slot ? class_get_method(photography_slot, "SetBodyCostume", 1) : nullptr));
        RuntimeLog("Game.CostumeSelectScreenModel=" + PointerText(costume_select_model));
        RuntimeLog("Game.CostumeSelectScreenModel.SetSelectedCostume(1)=" + PointerText(
            costume_select_model ? class_get_method(costume_select_model, "SetSelectedCostume", 1) : nullptr));
    } else {
        RuntimeLog("Game.Assembly-CSharp image not found");
    }
    if (mesh_class && skinned_mesh_renderer_class && transform_class) {
        RuntimeLog("IL2CPP diagnostics READY for read-only SkinnedMeshRenderer probe stage");
    } else {
        RuntimeLog("IL2CPP diagnostics incomplete; method enumeration required");
    }

    // Exhaustive Assembly-CSharp enumeration caused an access violation on
    // Unity 6000.0.67f1. Keep live discovery to fixed class/method lookups.
    RuntimeLog("Runtime probe complete; exhaustive game-method scan disabled");
}
