#include "ModRuntime.hpp"

#include "ModIl2cppUtils.hpp"
#include "ModLog.hpp"

#include <Windows.h>
#include <MinHook.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <cstdint>
#include <functional>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace GakumasMod::Runtime {
    using Il2cppString = UnityResolve::UnityType::String;

    namespace {
        template <typename T>
        using UnityArray = UnityResolve::UnityType::Array<T>;
        using Il2CppGCHandle = void*;

        struct LocalModMaterialTextureReplacement {
            std::string rendererName;
            int materialSlot{ -1 };
            std::string propertyName;
            std::string assetName;
            std::string typeName{ "Texture2D" };
        };

        struct LocalModMaterialColorReplacement {
            std::string rendererName;
            int materialSlot{ -1 };
            std::string propertyName;
            float r{ 1.0f };
            float g{ 1.0f };
            float b{ 1.0f };
            float a{ 1.0f };
        };

        struct LocalModMaterialFloatReplacement {
            std::string rendererName;
            int materialSlot{ -1 };
            std::string propertyName;
            float value{};
        };

        struct LocalModUnityColor {
            float r{ 1.0f };
            float g{ 1.0f };
            float b{ 1.0f };
            float a{ 1.0f };
        };

        struct LocalModMaterialSlotCopy {
            std::string rendererName;
            int fromSlot{ -1 };
            int toSlot{ -1 };
        };

        struct LocalModRendererRule {
            std::string rendererId;
            std::string targetRenderer;
            std::string modRenderer;
        };

        struct LocalModAssetReplacement {
            std::string modName;
            std::string manifestPath;
            std::string sourceName;
            std::string part;
            std::string assetName;
            std::string skeletonAssetName;
            std::string bundlePath;
            std::string typeName;
            bool replaceWholeObject{};
            bool attachToOriginal{};
            std::string rendererName;
            int priority{};
            bool replaceMaterials{};
            Il2CppGCHandle bundleHandle{};
            std::vector<LocalModRendererRule> rendererRules{};
            std::vector<LocalModMaterialSlotCopy> materialCopies{};
            std::vector<LocalModMaterialTextureReplacement> materialTextures{};
            std::vector<LocalModMaterialColorReplacement> materialColors{};
            std::vector<LocalModMaterialFloatReplacement> materialFloats{};
            void* attachAsset{};
            std::vector<void*> attachSourceMeshes{};
        };

        struct LocalModRendererPair {
            void* originalRenderer{};
            void* modRenderer{};
            size_t originalIndex{};
            size_t modIndex{};
        };

        struct LocalModBoneWeight {
            float weight0{};
            float weight1{};
            float weight2{};
            float weight3{};
            int boneIndex0{};
            int boneIndex1{};
            int boneIndex2{};
            int boneIndex3{};
        };

        // The swing params the source bundle authors per bone. Everything else the
        // runtime bone exposes (rootWeight, pendulum, wind...) is computed rather than
        // authored — source m_Weight is 1.0 on every bone while live base bones read
        // rootWeight=0.3 — so we only carry these and leave the rest to the game.
        struct LocalIpBoneSwing {
            float damping{};
            float stiffness{};
            float spring{};
            float mass{};
            bool useWindGlobalForce{};
        };

        struct LocalIpBone {
            std::string name;
            int parentIndex{ -1 };
            UnityResolve::UnityType::Vector3 localPosition{};
            UnityResolve::UnityType::Quaternion localRotation{};
            UnityResolve::UnityType::Vector3 localScale{};
            std::optional<LocalIpBoneSwing> swing{};
        };

        // The unweighted tip of each swing chain. Skinning doesn't need them so they
        // never reach the mesh's bone array, but the sim does — a chain's last segment
        // is defined by its tip. They stay out of LocalIpBone because that list must
        // remain index-aligned with the mod mesh's bones, so they attach by parent name.
        struct LocalIpExtraBone {
            std::string name;
            std::string parentName;
            UnityResolve::UnityType::Vector3 localPosition{};
            UnityResolve::UnityType::Quaternion localRotation{};
            UnityResolve::UnityType::Vector3 localScale{};
            std::optional<LocalIpBoneSwing> swing{};
        };

        struct ActorSwingInitialTransform {
            UnityResolve::UnityType::Vector3 localPosition{};
            UnityResolve::UnityType::Quaternion localRotation{};
            UnityResolve::UnityType::Vector3 position{};
            UnityResolve::UnityType::Quaternion rotation{};
        };

        using AssetBundleLoadAssetFn = void* (*)(void*, Il2cppString*, void*);
        using AssetBundleLoadAssetAsyncFn = void* (*)(void*, Il2cppString*, void*);
        using AssetBundleRequestGetResultFn = void* (*)(void*);
        using AssetBundleRequestGetAssetFn = void* (*)(void*);
        using CampusActorAnimationRigRegisterBonesFn = void (*)(void*, void*);

        AssetBundleLoadAssetFn AssetBundle_LoadAsset_Orig{};
        AssetBundleLoadAssetAsyncFn AssetBundle_LoadAssetAsync_Orig{};
        AssetBundleRequestGetResultFn AssetBundleRequest_GetResult_Orig{};
        AssetBundleRequestGetAssetFn AssetBundleRequest_get_asset_Orig{};
        CampusActorAnimationRigRegisterBonesFn CampusActorAnimationRig_RegisterBones_Orig{};

        std::atomic_bool g_initialized{};
        std::vector<void*> g_hookTargets{};
        std::mutex g_historyMutex;
        std::mutex g_bundleMutex;
        std::unordered_map<void*, std::string> g_loadHistory{};

        std::unordered_map<std::string, Il2CppGCHandle> g_bundleHandleMap{};
        std::unordered_map<std::string, LocalModAssetReplacement> g_replacementMap{};
        std::unordered_map<std::string, Il2CppGCHandle> g_loadedAssetHandleMap{};
        std::unordered_set<void*> g_transformedMeshSet{};
        // Names (GameObject names) of mod-created ActorSwingDynamicBone. Matched by name
        // (not pointer) because the graft runs on the loaded prefab; the game then
        // Instantiates it, so the scene clone's bones are different pointers with the
        // same names. See AddActorSwingBonesToAnimationData.
        std::unordered_set<std::string> g_createdActorSwingBoneNames{};
        std::vector<Il2CppGCHandle> g_runtimeMeshHandles{};
        std::vector<Il2CppGCHandle> g_runtimeBoneHandles{};
        std::unordered_map<void*, std::vector<void*>> g_hybridBonesByRenderer{};
        std::unordered_set<std::string> g_dumpedProfiles{};
        std::atomic_bool g_rigRegisterObserved{};
        std::atomic_bool g_nativeChainValidation{};
        std::unordered_set<void*> g_nativeChainAttachedRoots{};

        bool AttachNativeChainToLiveRoot(UnityResolve::UnityType::Transform* rootTransform);

        std::string ToLowerAscii(std::string value) {
            std::transform(value.begin(), value.end(), value.begin(), [](const unsigned char c) {
                return static_cast<char>(std::tolower(c));
            });
            return value;
        }

        std::string NormalizeAssetName(std::string name) {
            std::replace(name.begin(), name.end(), '\\', '/');
            return ToLowerAscii(std::move(name));
        }

        std::string SanitizeFileName(std::string value) {
            for (auto& c : value) {
                if (c == '\\' || c == '/' || c == ':' || c == '*' || c == '?' || c == '"' || c == '<' || c == '>' || c == '|') {
                    c = '_';
                }
            }
            return value.empty() ? "unknown" : value;
        }

        const char* GetUnityObjectClassName(void* obj) {
            const auto klass = Il2cppUtils::get_class_from_instance(obj);
            return klass && klass->name ? klass->name : "null";
        }

        std::string GetUnityObjectNameString(void* obj) {
            if (!obj) return {};
            static auto Object_get_name = reinterpret_cast<Il2cppString * (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Object", "get_name"));
            if (Object_get_name) {
                if (const auto name = Object_get_name(obj)) {
                    if (const auto value = name->ToString(); !value.empty()) {
                        return value;
                    }
                }
            }

            static auto Object_GetName = reinterpret_cast<Il2cppString * (*)(void*)>(
                Il2cppUtils::il2cpp_resolve_icall("UnityEngine.Object::GetName(UnityEngine.Object)"));
            const auto name = Object_GetName ? Object_GetName(obj) : nullptr;
            return name ? name->ToString() : std::string{};
        }

        bool IsNativeObjectAlive(void* obj) {
            if (!obj) return false;
            static auto IsNativeObjectAliveFn = reinterpret_cast<bool (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Object", "IsNativeObjectAlive"));
            return IsNativeObjectAliveFn ? IsNativeObjectAliveFn(obj) : true;
        }

        void LogAssetTrace(const char* hookName, const std::string& name, void* result = nullptr, void* requestType = nullptr) {
            const auto lowered = ToLowerAscii(name);
            if (lowered.find("mdl_chr_") == std::string::npos
                && lowered.find("geo_body") == std::string::npos
                && lowered.find("t_chr_") == std::string::npos) {
                return;
            }

            Log::InfoFmt("[ModAssetTrace] %s name=\"%s\" requestType=%p result=%p resultType=%s",
                hookName,
                name.c_str(),
                requestType,
                result,
                GetUnityObjectClassName(result));
        }

        std::optional<std::string> GetJsonString(const nlohmann::json& data, const char* key) {
            if (!data.contains(key) || !data[key].is_string()) return std::nullopt;
            return data[key].get<std::string>();
        }

        std::optional<std::string> GetFirstJsonString(const nlohmann::json& data, std::initializer_list<const char*> keys) {
            for (const auto key : keys) {
                if (const auto value = GetJsonString(data, key)) {
                    return value;
                }
            }
            return std::nullopt;
        }

        int GetJsonInt(const nlohmann::json& data, const char* key, const int fallback) {
            return data.contains(key) && data[key].is_number_integer()
                ? data[key].get<int>()
                : fallback;
        }

        float GetJsonFloat(const nlohmann::json& data, const char* key, const float fallback) {
            return data.contains(key) && data[key].is_number()
                ? data[key].get<float>()
                : fallback;
        }

        std::string InferPartFromAssetName(const std::string& sourceName) {
            const auto normalized = NormalizeAssetName(sourceName);
            if (normalized.find("_face") != std::string::npos || normalized.ends_with("-face")) return "face";
            if (normalized.find("_hair") != std::string::npos || normalized.ends_with("-hair")) return "hair";
            if (normalized.find("_body") != std::string::npos || normalized.ends_with("-body")) return "body";
            return {};
        }

        bool IsValidPart(const std::string& part) {
            return part.empty() || part == "face" || part == "hair" || part == "body";
        }

        bool AttachIl2cppThread(const HMODULE gameAssembly) {
            using DomainGetFn = void* (*)();
            using ThreadAttachFn = void* (*)(void*);

            const auto domainGet = reinterpret_cast<DomainGetFn>(GetProcAddress(gameAssembly, "il2cpp_domain_get"));
            const auto threadAttach = reinterpret_cast<ThreadAttachFn>(GetProcAddress(gameAssembly, "il2cpp_thread_attach"));
            if (!domainGet || !threadAttach) {
                Log::Error("[ModAsset] Cannot resolve il2cpp thread attach exports.");
                return false;
            }

            const auto domain = domainGet();
            if (!domain) {
                Log::Error("[ModAsset] il2cpp_domain_get returned null.");
                return false;
            }

            const auto thread = threadAttach(domain);
            if (!thread) {
                Log::Error("[ModAsset] il2cpp_thread_attach returned null.");
                return false;
            }
            return true;
        }

        UnityResolve::Method* FindMethodByNameAndArgCount(UnityResolve::Class* klass,
            const std::string& methodName,
            const size_t argCount) {
            if (!klass) return nullptr;
            for (const auto method : klass->methods) {
                if (!method || method->name != methodName || method->args.size() != argCount) continue;
                return method;
            }
            return nullptr;
        }

        UnityResolve::Class* FindClassByName(const std::string& className) {
            for (const auto assembly : UnityResolve::assembly) {
                if (!assembly) continue;
                for (const auto klass : assembly->classes) {
                    if (klass && klass->name == className) return klass;
                }
            }
            return nullptr;
        }

        void* AddComponentByClass(UnityResolve::UnityType::GameObject* gameObject,
            UnityResolve::Class* componentClass) {
            if (!gameObject || !componentClass) return nullptr;
            static auto gameObjectClass = Il2cppUtils::GetClass(
                "UnityEngine.CoreModule.dll", "UnityEngine", "GameObject");
            static auto addComponent = FindMethodByNameAndArgCount(gameObjectClass, "AddComponent", 1);
            return addComponent
                ? addComponent->Invoke<void*>(gameObject, componentClass->GetType())
                : nullptr;
        }

        // Reliable managed List<T>.Add. UnityResolve's List::Add calls the un-inflated
        // generic List`1::Add and faults ("Add Invoke Error"); resolve the INFLATED Add
        // from the list's actual runtime class and go through il2cpp_runtime_invoke, which
        // sets up the generic RGCTX correctly. Returns false if the call raised.
        bool ListAddManaged(void* listObj, void* item) {
            if (!listObj) return false;
            const auto klass = Il2cppUtils::get_class_from_instance(listObj);
            if (!klass) return false;
            const auto method = UnityResolve::Invoke<void*>(
                "il2cpp_class_get_method_from_name", klass, "Add", 1);
            if (!method) return false;
            void* args[1] = { item };
            void* exc = nullptr;
            UnityResolve::Invoke<void*>("il2cpp_runtime_invoke", method, listObj, args, &exc);
            return exc == nullptr;
        }

        // Allocate a fresh managed object of the same class as templateObj (for a generic
        // List, the same instantiation — e.g. reuse an existing chain's rootBones as the
        // List<ActorSwingDynamicBone> type template; also used to clone a ChainLayerInfo).
        // il2cpp_object_new + parameterless ctor. Returns nullptr on failure.
        void* CreateObjectLike(void* templateObj) {
            if (!templateObj) return nullptr;
            const auto klass = Il2cppUtils::get_class_from_instance(templateObj);
            if (!klass) return nullptr;
            const auto obj = UnityResolve::Invoke<void*>("il2cpp_object_new", klass);
            if (!obj) return nullptr;
            const auto ctor = UnityResolve::Invoke<void*>(
                "il2cpp_class_get_method_from_name", klass, ".ctor", 0);
            if (ctor) {
                void* exc = nullptr;
                UnityResolve::Invoke<void*>("il2cpp_runtime_invoke", ctor, obj, nullptr, &exc);
                if (exc) return nullptr;
            }
            return obj;
        }

        bool InitializeActorSwingDynamicBone(void* component, UnityResolve::Class* componentClass,
            const std::optional<LocalIpBoneSwing>& swing) {
            if (!component || !componentClass) return false;
            auto transform = reinterpret_cast<UnityResolve::UnityType::Component*>(component)->GetTransform();
            if (!transform) return false;

            if (const auto setDefaults = componentClass->Get<UnityResolve::Method>("SetDefaultValues")) {
                setDefaults->Invoke<void>(component);
            }
            // SetDefaultValues leaves a bone inert (mass=0, spring=0), which is right only
            // for a chain's anchor — the source authors those very values on e.g. Wing1_S,
            // but Wing2_S wants mass=0.5/spring=0.3 and never swung while stuck on defaults.
            if (swing) {
                const auto setFloat = [&](const char* name, float value) {
                    if (const auto f = componentClass->Get<UnityResolve::Field>(name))
                        *reinterpret_cast<float*>(
                            reinterpret_cast<std::uintptr_t>(component) + f->offset) = value;
                };
                setFloat("damping", swing->damping);
                setFloat("stiffness", swing->stiffness);
                setFloat("spring", swing->spring);
                setFloat("mass", swing->mass);
                if (const auto f = componentClass->Get<UnityResolve::Field>("useWindGlobalForce"))
                    *reinterpret_cast<bool*>(
                        reinterpret_cast<std::uintptr_t>(component) + f->offset) = swing->useWindGlobalForce;
            }

            const ActorSwingInitialTransform initial{
                transform->GetLocalPosition(), transform->GetLocalRotation(),
                transform->GetPosition(), transform->GetRotation() };
            if (const auto modelingTransform = componentClass->Get<UnityResolve::Field>("modelingTransform")) {
                *reinterpret_cast<ActorSwingInitialTransform*>(
                    reinterpret_cast<std::uintptr_t>(component) + modelingTransform->offset) = initial;
            }
            if (const auto updateInitial = componentClass->Get<UnityResolve::Method>("UpdateInitialTransform")) {
                updateInitial->Invoke<void>(component, initial);
            }
            if (const auto updateDepth = componentClass->Get<UnityResolve::Method>("UpdateHierarchyDepth")) {
                updateDepth->Invoke<void>(component);
            }
            return true;
        }

        size_t AddActorSwingBonesToAnimationData(void* rootTransform, void* initializeData) {
            if (!rootTransform || !initializeData) {
                Log::Warn("[ModAsset] ActorSwing scan skipped: root or initializeData is null.");
                return 0;
            }
            const auto dynamicBoneClass = FindClassByName("ActorSwingDynamicBone");
            const auto initializeDataClass = FindClassByName("CampusActorAnimationInitializeData");
            if (!dynamicBoneClass || !initializeDataClass) {
                Log::WarnFmt("[ModAsset] ActorSwing scan skipped: dynamicBoneClass=%p initializeDataClass=%p",
                    dynamicBoneClass, initializeDataClass);
                return 0;
            }

            auto dynamicBones = initializeDataClass->GetValue<UnityResolve::UnityType::List<void*>*>(
                initializeData, "swingDynamicBones");
            if (!dynamicBones) {
                Log::Warn("[ModAsset] ActorSwing scan skipped: initializeData.swingDynamicBones is null.");
                return 0;
            }

            const auto rootGameObject = reinterpret_cast<UnityResolve::UnityType::Component*>(rootTransform)
                ->GetGameObject();
            const auto allBones = rootGameObject && IsNativeObjectAlive(rootGameObject)
                ? rootGameObject->GetComponentsInChildren<void*>(dynamicBoneClass, true)
                : std::vector<void*>{};
            Log::InfoFmt("[ModAsset] ActorSwing scan: root=%p rootGameObject=%p name=%s components=%zu dataList=%d",
                rootTransform, rootGameObject,
                rootGameObject ? GetUnityObjectNameString(rootGameObject).c_str() : "(null)",
                allBones.size(), dynamicBones->size);
            size_t added = 0;
            for (const auto bone : allBones) {
                if (!bone || !IsNativeObjectAlive(bone)) continue;
                bool exists = false;
                if (dynamicBones->pList) {
                    for (int i = 0; i < dynamicBones->size; ++i) {
                        if (dynamicBones->pList->At(static_cast<unsigned int>(i)) == bone) {
                            exists = true;
                            break;
                        }
                    }
                }
                if (!exists && ListAddManaged(dynamicBones, bone)) {
                    ++added;
                }
            }

            if (const auto chainClass = FindClassByName("ActorSwingChain")) {
                const auto chains = rootGameObject && IsNativeObjectAlive(rootGameObject)
                    ? rootGameObject->GetComponentsInChildren<void*>(chainClass, true)
                    : std::vector<void*>{};
                // Select the current character's mod-created bones by NAME on the live
                // instance. The graft ran on the loaded prefab, then the game Instantiated
                // it — so pointer-based tracking (the old g_createdActorSwingBones set, and
                // the manual Transform.GetParent walk that crashed at ModRuntime.cpp:419)
                // never matched the scene clone. allBones is this root's live dynamic-bone
                // snapshot; the clone preserves GameObject names, so name matching finds them.
                std::vector<void*> currentRootCreatedBones;
                for (const auto bone : allBones) {
                    if (!bone || !IsNativeObjectAlive(bone)) continue;
                    if (g_createdActorSwingBoneNames.count(GetUnityObjectNameString(bone))) {
                        currentRootCreatedBones.emplace_back(bone);
                    }
                }
                // ponytail: un-modded character has no mod-created bones here — don't touch
                // its swing chains (OnEnable/UpdateChainInfo) at all, restore vanilla behavior.
                if (currentRootCreatedBones.empty()) return added;
                // The mod's bones (nurse-dress ribbons/wings/stethoscope) belong to NO existing
                // chain (topology: their roots hang off LeftShoulder/RightShoulder/Spine2, not
                // under any base-costume swing chain). Source rui-nurs drives them with a single
                // ActorSwingChain on Pelvis whose rootBones lists each sub-chain top. Reproduce
                // that here: host one ActorSwingChain on Pelvis, add the mod's chain-root bones
                // (those whose parent is NOT a dynamic bone) to its rootBones, register it into
                // initializeData.swingChains, then UpdateChainInfo. Uses ListAddManaged because
                // UnityResolve's List::Add faults on the un-inflated generic method.
                std::vector<void*> chainRootBones;  // mod bones that top their own sub-chain
                for (const auto bone : currentRootCreatedBones) {
                    const auto transform = reinterpret_cast<UnityResolve::UnityType::Component*>(bone)->GetTransform();
                    const auto parent = transform ? transform->GetParent() : nullptr;
                    const auto parentGo = parent ? parent->GetGameObject() : nullptr;
                    const bool parentDynamic = parentGo && parentGo->GetComponent<void*>(dynamicBoneClass);
                    Log::InfoFmt("[ModAsset] ActorSwing created-bone topology: name=%s parent=%s parentDynamic=%d",
                        GetUnityObjectNameString(bone).c_str(),
                        parent ? GetUnityObjectNameString(parent).c_str() : "(null)", parentDynamic ? 1 : 0);
                    if (!parentDynamic) chainRootBones.emplace_back(bone);
                }

                // Host the chain on the skeleton root. Source (偶像荣耀) names it "Pelvis";
                // the mod grafts onto Gakumas' base skeleton whose root is "Hips" — so accept
                // either, and fall back to the RegisterBones root GameObject so we never no-op.
                UnityResolve::UnityType::GameObject* pelvisGo = nullptr;
                if (!chainRootBones.empty()) {
                    const auto t0 = reinterpret_cast<UnityResolve::UnityType::Component*>(chainRootBones.front())->GetTransform();
                    for (auto p = t0; p && IsNativeObjectAlive(p); p = p->GetParent()) {
                        const auto n = GetUnityObjectNameString(p);
                        if (n == "Pelvis" || n == "Hips") { pelvisGo = p->GetGameObject(); break; }
                    }
                }
                if (!pelvisGo) pelvisGo = rootGameObject;
                // Template List type from any existing chain's rootBones (List<ActorSwingDynamicBone>).
                void* templateRootList = nullptr;
                for (const auto chain : chains) {
                    if (const auto rb = chainClass->GetValue<void*>(chain, "rootBones")) { templateRootList = rb; break; }
                }

                size_t chainRootsAdded = 0, swingChainRegistered = 0;
                if (pelvisGo && templateRootList && !chainRootBones.empty()) {
                    // Reuse a mod chain we already put on Pelvis if RegisterBones re-fires; else create one.
                    void* hostChain = nullptr;
                    for (const auto chain : chains) {
                        const auto go = reinterpret_cast<UnityResolve::UnityType::Component*>(chain)->GetGameObject();
                        if (go == pelvisGo) { hostChain = chain; break; }
                    }
                    const bool createdChain = hostChain == nullptr;
                    if (!hostChain) hostChain = AddComponentByClass(pelvisGo, chainClass);
                    if (hostChain) {
                        auto rootBones = chainClass->GetValue<void*>(hostChain, "rootBones");
                        if (!rootBones) {
                            rootBones = CreateObjectLike(templateRootList);
                            if (rootBones) {
                                if (const auto f = chainClass->Get<UnityResolve::Field>("rootBones"))
                                    *reinterpret_cast<void**>(reinterpret_cast<std::uintptr_t>(hostChain) + f->offset) = rootBones;
                            }
                        }
                        if (rootBones) {
                            const auto rbList = reinterpret_cast<UnityResolve::UnityType::List<void*>*>(rootBones);
                            // UpdateChainInfo (RE'd from the unpacked iOS binary; findings §9)
                            // builds layers by walking transform.GetChild(0) from each ROOT and
                            // requiring an ActorSwingDynamicBone component on every step — so
                            // rootBones takes only the sub-chain tops; the rest of each chain is
                            // discovered by that walk. (The old all-bones fill made every bone a
                            // 1-layer chain root.)
                            for (const auto bone : chainRootBones) {
                                bool exists = false;
                                if (rbList->pList) {
                                    for (int i = 0; i < rbList->size; ++i)
                                        if (rbList->pList->At(static_cast<unsigned int>(i)) == bone) { exists = true; break; }
                                }
                                if (!exists && ListAddManaged(rootBones, bone)) ++chainRootsAdded;
                            }
                        }
                        // Register the chain so the rig actually drives it.
                        if (createdChain) {
                            if (const auto initDataClass = FindClassByName("CampusActorAnimationInitializeData")) {
                                if (const auto swingChains = initDataClass->GetValue<void*>(initializeData, "swingChains")) {
                                    if (ListAddManaged(swingChains, hostChain)) ++swingChainRegistered;
                                }
                            }
                        }
                        if (createdChain) {
                            if (const auto onEnable = chainClass->Get<UnityResolve::Method>("OnEnable"))
                                onEnable->Invoke<void>(hostChain);
                        }
                        // Resolve each chain's bones per depth: depthBones[d] holds every bone d
                        // levels below a root (d=0 → the roots themselves). UpdateChainInfo only
                        // ever builds layer[0] for a runtime chain, so we append the rest from this
                        // below. Follow any child carrying the component rather than strictly
                        // GetChild(0) — our bones are first children anyway (the sibling-reorder
                        // repair this replaces never once fired), and this is not the game's walk.
                        std::vector<std::vector<void*>> depthBones;
                        for (const auto rootBone : chainRootBones) {
                            void* bone = rootBone;
                            auto t = reinterpret_cast<UnityResolve::UnityType::Component*>(rootBone)->GetTransform();
                            for (size_t depth = 0; bone && t && IsNativeObjectAlive(t); ++depth) {
                                if (depthBones.size() <= depth) depthBones.emplace_back();
                                depthBones[depth].push_back(bone);
                                UnityResolve::UnityType::Transform* next = nullptr;
                                void* nextBone = nullptr;
                                const int childCount = t->GetChildCount();
                                for (int i = 0; i < childCount; ++i) {
                                    const auto child = t->GetChild(i);
                                    const auto childGo = child ? child->GetGameObject() : nullptr;
                                    if (const auto c = childGo ? childGo->GetComponent<void*>(dynamicBoneClass) : nullptr) {
                                        next = child;
                                        nextBone = c;
                                        break;
                                    }
                                }
                                if (!next) break;
                                t = next;
                                bone = nextBone;
                            }
                        }
                        std::string depthStat;
                        for (const auto& d : depthBones) depthStat += std::to_string(d.size()) + "/";
                        Log::InfoFmt("[ModAsset] ActorSwing chain walk: roots=%zu depths=%zu bonesPerDepth=%s",
                            chainRootBones.size(), depthBones.size(), depthStat.c_str());
                        // Diagnostic: which bones did UpdateChainInfo put in which layer, vs a base
                        // chain? It omits each chain's last bone (the tip only defines the final
                        // segment and must not be simulated), so a complete chain of depth N yields
                        // N-1 layers.
                        const auto layerStats = [&](void* ch) -> std::string {
                            const auto chainInfoClass = FindClassByName("ChainInfo");
                            const auto layerClass = FindClassByName("ChainLayerInfo");
                            if (!chainInfoClass || !layerClass) return "n/a";
                            const auto ci = chainClass->GetValue<void*>(ch, "chains");
                            if (!ci) return "noChains";
                            const auto ly = chainInfoClass->GetValue<UnityResolve::UnityType::List<void*>*>(ci, "layers");
                            if (!ly || !ly->pList) return "noLayers";
                            int total = 0;
                            for (int i = 0; i < ly->size; ++i) {
                                if (const auto layer = ly->pList->At(static_cast<unsigned int>(i)))
                                    if (const auto bl = layerClass->GetValue<UnityResolve::UnityType::List<void*>*>(layer, "bones"))
                                        total += bl->size;
                            }
                            return std::to_string(ly->size) + "layers/" + std::to_string(total) + "bones";
                        };
                        // Name every bone per layer: a bone appearing twice means it gets simulated
                        // twice and the chain explodes, which is exactly what hand-built layers did.
                        const auto layerNames = [&](void* ch) {
                            const auto chainInfoClass = FindClassByName("ChainInfo");
                            const auto layerClass = FindClassByName("ChainLayerInfo");
                            const auto ci = chainInfoClass && layerClass ? chainClass->GetValue<void*>(ch, "chains") : nullptr;
                            const auto ly = ci ? chainInfoClass->GetValue<UnityResolve::UnityType::List<void*>*>(ci, "layers") : nullptr;
                            if (!ly || !ly->pList) return;
                            for (int i = 0; i < ly->size; ++i) {
                                const auto layer = ly->pList->At(static_cast<unsigned int>(i));
                                const auto bl = layer ? layerClass->GetValue<UnityResolve::UnityType::List<void*>*>(layer, "bones") : nullptr;
                                std::string names;
                                if (bl && bl->pList)
                                    for (int b = 0; b < bl->size; ++b)
                                        names += GetUnityObjectNameString(bl->pList->At(static_cast<unsigned int>(b))) + " ";
                                Log::InfoFmt("[ModAsset] ActorSwing layer[%d] active=%d bones=%s", i,
                                    layer ? layerClass->GetValue<bool>(layer, "active") : 0, names.c_str());
                            }
                        };
                        // UpdateChainInfo builds the layers; nothing here should touch them. It looked
                        // broken while it produced a single layer for us, but the chains were simply
                        // missing their tips: it omits each chain's last bone, so the tipless
                        // Wing1->Wing2 lost Wing2 (the bone that should swing) and yielded 1 layer.
                        // With the tips supplied it yields the expected depth-1 layers on its own.
                        const std::string beforeStat = layerStats(hostChain);
                        if (const auto updateInfo = chainClass->Get<UnityResolve::Method>("UpdateChainInfo")) {
                            static bool loggedAddr = false;
                            if (!loggedAddr) {
                                loggedAddr = true;
                                const auto ga = reinterpret_cast<void*>(GetModuleHandleW(L"GameAssembly.dll"));
                                const auto ud = chainClass->Get<UnityResolve::Method>("UpdateHierarchyDepth");
                                Log::InfoFmt("[ModAsset] ActorSwing method addrs: gaBase=%p UpdateChainInfo=%p UpdateHierarchyDepth=%p",
                                    ga, updateInfo->function, ud ? ud->function : nullptr);
                            }
                            updateInfo->Invoke<void>(hostChain);
                        }
                        std::string baseStat = "none";
                        for (const auto ch : chains) { if (ch != hostChain) { baseStat = layerStats(ch); break; } }
                        Log::InfoFmt("[ModAsset] ActorSwing chain layers: before=%s our=%s base=%s",
                            beforeStat.c_str(), layerStats(hostChain).c_str(), baseStat.c_str());
                        layerNames(hostChain);
                    }
                }
                Log::InfoFmt("[ModAsset] ActorSwing new chain: pelvis=%p chainRoots=%zu added=%zu registered=%zu createdBones=%zu",
                    pelvisGo, chainRootBones.size(), chainRootsAdded, swingChainRegistered, currentRootCreatedBones.size());
            }
            return added;
        }

        void LogActorSwingChainStats(void* rootTransform, const char* label) {
            if (!rootTransform) return;
            const auto chainClass = FindClassByName("ActorSwingChain");
            const auto chainInfoClass = FindClassByName("ChainInfo");
            const auto layerClass = FindClassByName("ChainLayerInfo");
            if (!chainClass || !chainInfoClass || !layerClass) return;

            const auto rootGameObject = reinterpret_cast<UnityResolve::UnityType::Component*>(rootTransform)
                ->GetGameObject();
            if (!rootGameObject || !IsNativeObjectAlive(rootGameObject)) return;
            const auto chains = rootGameObject->GetComponentsInChildren<void*>(chainClass, true);
            for (const auto chain : chains) {
                if (!chain || !IsNativeObjectAlive(chain)) continue;
                const auto chainInfo = chainClass->GetValue<void*>(chain, "chains");
                const auto layers = chainInfo
                    ? chainInfoClass->GetValue<UnityResolve::UnityType::List<void*>*>(chainInfo, "layers")
                    : nullptr;
                int totalBones = 0;
                if (layers && layers->pList) {
                    for (int i = 0; i < layers->size; ++i) {
                        if (const auto layer = layers->pList->At(static_cast<unsigned int>(i))) {
                            if (const auto bones = layerClass->GetValue<UnityResolve::UnityType::List<void*>*>(layer, "bones"))
                                totalBones += bones->size;
                        }
                    }
                }
                const auto stat = layers && layers->pList
                    ? std::to_string(layers->size) + "layers/" + std::to_string(totalBones) + "bones"
                    : (chainInfo ? "noLayers" : "noChains");
                Log::InfoFmt("[ModAsset] %s ActorSwing chain layers: object=%s stats=%s",
                    label,
                    GetUnityObjectNameString(chain).c_str(),
                    stat.c_str());
            }
        }

        size_t AddActorSwingChainsToAnimationData(void* rootTransform, void* initializeData) {
            const auto chainClass = FindClassByName("ActorSwingChain");
            const auto initializeDataClass = FindClassByName("CampusActorAnimationInitializeData");
            if (!rootTransform || !initializeData || !chainClass || !initializeDataClass) return 0;
            const auto rootGameObject = reinterpret_cast<UnityResolve::UnityType::Component*>(rootTransform)->GetGameObject();
            const auto swingChains = initializeDataClass->GetValue<UnityResolve::UnityType::List<void*>*>(
                initializeData, "swingChains");
            if (!rootGameObject || !swingChains) return 0;

            size_t added = 0;
            for (const auto chain : rootGameObject->GetComponentsInChildren<void*>(chainClass, true)) {
                bool exists = false;
                if (swingChains->pList) {
                    for (int i = 0; i < swingChains->size; ++i) {
                        if (swingChains->pList->At(static_cast<unsigned int>(i)) == chain) {
                            exists = true;
                            break;
                        }
                    }
                }
                if (!exists && ListAddManaged(swingChains, chain)) ++added;
            }
            return added;
        }

        void CampusActorAnimationRig_RegisterBones_Hook(void* self, void* initializeData) {
            const auto initializeDataClass = FindClassByName("CampusActorAnimationInitializeData");
            auto rootTransform = initializeDataClass
                ? initializeDataClass->GetValue<UnityResolve::UnityType::Transform*>(initializeData, "root")
                : nullptr;
            if (!rootTransform && self) {
                rootTransform = reinterpret_cast<UnityResolve::UnityType::Component*>(self)->GetTransform();
            }
            if (!g_rigRegisterObserved.exchange(true)) {
                Log::InfoFmt("[ModAsset] CampusActorAnimationRig.RegisterBones observed: self=%p root=%p data=%p",
                    self, rootTransform, initializeData);
            }
            const auto nativeChainAttached = AttachNativeChainToLiveRoot(rootTransform);
            const auto added = AddActorSwingBonesToAnimationData(rootTransform, initializeData);
            if (added) {
                const auto dynamicBones = initializeDataClass
                    ? initializeDataClass->GetValue<UnityResolve::UnityType::List<void*>*>(
                        initializeData, "swingDynamicBones")
                    : nullptr;
                Log::InfoFmt("[ModAsset] ActorSwing data grafted before CampusActorAnimationRig.RegisterBones: added=%zu total=%d",
                    added, dynamicBones ? dynamicBones->size : 0);
            }
            if (nativeChainAttached) {
                const auto chainsAdded = AddActorSwingChainsToAnimationData(rootTransform, initializeData);
                Log::InfoFmt("[ModAsset] Native ActorSwing chain registered before CampusActorAnimationRig.RegisterBones: added=%zu",
                    chainsAdded);
            }
            CampusActorAnimationRig_RegisterBones_Orig(self, initializeData);
            if (g_nativeChainValidation) {
                LogActorSwingChainStats(rootTransform, "native");
            }
        }

        void LogAssetBundleLoadMethodsOnce() {
            static bool dumped = false;
            if (dumped) return;
            dumped = true;

            const auto assetBundleClass = Il2cppUtils::GetClass(
                "UnityEngine.AssetBundleModule.dll", "UnityEngine", "AssetBundle");
            if (!assetBundleClass) return;

            for (const auto method : assetBundleClass->methods) {
                if (!method) continue;
                const auto methodName = method->name;
                if (methodName.find("LoadFrom") == std::string::npos
                    && methodName.find("LoadAsset") == std::string::npos) {
                    continue;
                }

                std::string args;
                for (size_t i = 0; i < method->args.size(); ++i) {
                    if (i) args += ", ";
                    args += method->args[i] && method->args[i]->pType
                        ? method->args[i]->pType->name
                        : "<unknown>";
                }
                Log::InfoFmt("[ModAsset] AssetBundle method: %s(%s) return=%s fn=%p",
                    methodName.c_str(),
                    args.c_str(),
                    method->return_type ? method->return_type->name.c_str() : "<unknown>",
                    method->function);
            }
        }

        UnityResolve::Class* GetSystemByteClass() {
            static UnityResolve::Class* byteClass = nullptr;
            if (byteClass) return byteClass;

            const char* assemblies[] = {
                "mscorlib.dll",
                "System.Private.CoreLib.dll",
                "netstandard.dll",
            };
            for (const auto assemblyName : assemblies) {
                const auto assembly = UnityResolve::Get(assemblyName);
                if (!assembly) continue;
                byteClass = assembly->Get("Byte", "System");
                if (byteClass) return byteClass;
            }

            Log::Error("[ModAsset] Cannot resolve System.Byte class for AssetBundle.LoadFromMemory.");
            return nullptr;
        }

        UnityArray<std::uint8_t>* ReadFileToManagedByteArray(const std::filesystem::path& path) {
            std::ifstream stream(path, std::ios::binary | std::ios::ate);
            if (!stream.is_open()) {
                Log::ErrorFmt("[ModAsset] Cannot open mod asset bundle file: %s", path.string().c_str());
                return nullptr;
            }

            const auto size = stream.tellg();
            if (size <= 0) {
                Log::ErrorFmt("[ModAsset] Mod asset bundle file is empty: %s", path.string().c_str());
                return nullptr;
            }
            stream.seekg(0, std::ios::beg);

            std::vector<std::uint8_t> bytes(static_cast<size_t>(size));
            if (!stream.read(reinterpret_cast<char*>(bytes.data()), size)) {
                Log::ErrorFmt("[ModAsset] Cannot read mod asset bundle file: %s", path.string().c_str());
                return nullptr;
            }

            const auto byteClass = GetSystemByteClass();
            if (!byteClass) return nullptr;

            const auto array = UnityArray<std::uint8_t>::New(byteClass, bytes.size());
            if (!array) {
                Log::ErrorFmt("[ModAsset] Cannot allocate managed byte array for bundle: %s size=%zu",
                    path.string().c_str(),
                    bytes.size());
                return nullptr;
            }
            array->Insert(bytes.data(), bytes.size());
            return array;
        }

        void* LoadAssetBundleFromMemoryFile(const std::filesystem::path& absolutePath) {
            const auto bytes = ReadFileToManagedByteArray(absolutePath);
            if (!bytes) return nullptr;

            using LoadFromMemoryInternalFn = void* (*)(UnityArray<std::uint8_t>*, uint32_t);
            static auto LoadFromMemoryInternal = reinterpret_cast<LoadFromMemoryInternalFn>(
                Il2cppUtils::il2cpp_resolve_icall(
                    "UnityEngine.AssetBundle::LoadFromMemory_Internal(System.Byte[],System.UInt32)"));
            if (LoadFromMemoryInternal) {
                if (auto bundle = LoadFromMemoryInternal(bytes, 0)) {
                    Log::InfoFmt("[ModAsset] Loaded mod asset bundle via LoadFromMemory_Internal icall: %s",
                        absolutePath.string().c_str());
                    return bundle;
                }
            }

            const auto assetBundleClass = Il2cppUtils::GetClass(
                "UnityEngine.AssetBundleModule.dll", "UnityEngine", "AssetBundle");
            static auto LoadFromMemoryInternalMethod = FindMethodByNameAndArgCount(
                assetBundleClass, "LoadFromMemory_Internal", 2);
            if (LoadFromMemoryInternalMethod) {
                if (auto bundle = LoadFromMemoryInternalMethod->Invoke<void*>(
                    bytes,
                    static_cast<uint32_t>(0))) {
                    Log::InfoFmt("[ModAsset] Loaded mod asset bundle via managed LoadFromMemory_Internal: %s",
                        absolutePath.string().c_str());
                    return bundle;
                }
            }

            LogAssetBundleLoadMethodsOnce();
            Log::ErrorFmt("[ModAsset] Cannot load mod asset bundle via LoadFromMemory_Internal: %s",
                absolutePath.string().c_str());
            return nullptr;
        }

        void* LoadAssetBundleFromFile(const std::string& path) {
            const auto absolutePath = std::filesystem::absolute(path).lexically_normal();
            const auto normalizedPath = absolutePath.string();
            const auto bundlePath = Il2cppString::New(normalizedPath);
            if (!bundlePath) return nullptr;

            static auto LoadFromFileAsync = Il2cppUtils::GetMethod(
                "UnityEngine.AssetBundleModule.dll",
                "UnityEngine",
                "AssetBundle",
                "LoadFromFileAsync");
            static auto AssetBundleCreateRequest_get_assetBundle = Il2cppUtils::GetMethod(
                "UnityEngine.AssetBundleModule.dll",
                "UnityEngine",
                "AssetBundleCreateRequest",
                "get_assetBundle");
            if (!LoadFromFileAsync || !AssetBundleCreateRequest_get_assetBundle) {
                Log::ErrorFmt("[ModAsset] Cannot resolve font-style AssetBundle loader methods: %s",
                    normalizedPath.c_str());
                return nullptr;
            }

            const auto request = LoadFromFileAsync->Invoke<void*>(bundlePath);
            if (!request) {
                Log::ErrorFmt("[ModAsset] AssetBundle.LoadFromFileAsync returned null: %s",
                    normalizedPath.c_str());
                return nullptr;
            }

            const auto bundle = AssetBundleCreateRequest_get_assetBundle->Invoke<void*>(request);
            if (!bundle) {
                Log::ErrorFmt("[ModAsset] AssetBundleCreateRequest.get_assetBundle returned null: %s",
                    normalizedPath.c_str());
                return nullptr;
            }

            Log::InfoFmt("[ModAsset] Loaded mod asset bundle via font-style LoadFromFileAsync: %s",
                normalizedPath.c_str());
            return bundle;
        }

        Il2CppGCHandle LoadLocalModAssetBundle(const std::filesystem::path& bundlePath) {
            const auto normalizedPath = bundlePath.lexically_normal().string();
            if (const auto iter = g_bundleHandleMap.find(normalizedPath); iter != g_bundleHandleMap.end()) {
                return iter->second;
            }

            const auto assetBundle = LoadAssetBundleFromFile(normalizedPath);
            if (!assetBundle) {
                Log::ErrorFmt("[ModAsset] Failed to load mod asset bundle: %s", normalizedPath.c_str());
                return nullptr;
            }

            const auto bundleHandle = UnityResolve::Invoke<Il2CppGCHandle>("il2cpp_gchandle_new", assetBundle, false);
            if (!bundleHandle) {
                Log::ErrorFmt("[ModAsset] Failed to create mod asset bundle GCHandle: %s", normalizedPath.c_str());
                return nullptr;
            }

            g_bundleHandleMap.emplace(normalizedPath, bundleHandle);
            Log::InfoFmt("[ModAsset] Loaded mod asset bundle: %s", normalizedPath.c_str());
            return bundleHandle;
        }

        void LoadLocalModManifest(const std::filesystem::path& manifestPath) {
            std::ifstream stream(manifestPath);
            if (!stream.is_open()) {
                Log::ErrorFmt("[ModAsset] Cannot open mod manifest: %s", manifestPath.string().c_str());
                return;
            }

            nlohmann::json manifest;
            try {
                stream >> manifest;
            }
            catch (const std::exception& e) {
                Log::ErrorFmt("[ModAsset] Cannot parse mod manifest %s: %s",
                    manifestPath.string().c_str(),
                    e.what());
                return;
            }

            if (manifest.contains("enabled") && manifest["enabled"].is_boolean() && !manifest["enabled"].get<bool>()) {
                Log::InfoFmt("[ModAsset] Skipped disabled mod manifest: %s", manifestPath.string().c_str());
                return;
            }

            if (!manifest.contains("replacements") || !manifest["replacements"].is_array()) {
                Log::ErrorFmt("[ModAsset] Manifest has no replacements array: %s", manifestPath.string().c_str());
                return;
            }

            const auto manifestDir = manifestPath.parent_path();
            const auto modName = GetJsonString(manifest, "name")
                .or_else([&] { return GetJsonString(manifest, "id"); })
                .value_or(manifestPath.stem().string());
            const auto manifestPriority = GetJsonInt(manifest, "priority", 0);
            int loadedCount = 0;

            for (const auto& item : manifest["replacements"]) {
                if (!item.is_object()) continue;

                const auto sourceName = GetFirstJsonString(item, { "from", "source", "target" });
                const auto bundleName = GetFirstJsonString(item, { "bundle", "assetBundle", "assetbundle" });
                if (!sourceName || !bundleName) {
                    Log::ErrorFmt("[ModAsset] Invalid replacement in %s: from/source/target and bundle are required.",
                        manifestPath.string().c_str());
                    continue;
                }

                const auto assetName = GetFirstJsonString(item, { "asset", "to", "name" }).value_or(*sourceName);
                const auto skeletonAssetName = GetFirstJsonString(item, { "skeleton", "skeletonAsset" }).value_or("");
                const auto typeName = GetJsonString(item, "type").value_or("GameObject");
                const auto replaceWholeObject = item.contains("replaceWholeObject")
                    && item["replaceWholeObject"].is_boolean()
                    && item["replaceWholeObject"].get<bool>();
                const auto attachToOriginal = item.contains("attachToOriginal")
                    && item["attachToOriginal"].is_boolean()
                    && item["attachToOriginal"].get<bool>();
                const auto rendererName = GetJsonString(item, "rendererName").value_or("");
                auto part = GetJsonString(item, "part").value_or(InferPartFromAssetName(*sourceName));
                if (!IsValidPart(part)) {
                    Log::ErrorFmt("[ModAsset] Invalid replacement part in %s: source=%s part=%s expected=face/hair/body",
                        manifestPath.string().c_str(), sourceName->c_str(), part.c_str());
                    continue;
                }
                const auto priority = GetJsonInt(item, "priority", manifestPriority);
                const auto replaceMaterials = item.contains("replaceMaterials")
                    && item["replaceMaterials"].is_boolean()
                    && item["replaceMaterials"].get<bool>();

                std::vector<LocalModRendererRule> rendererRules{};
                if (item.contains("renderers") && item["renderers"].is_array()) {
                    for (const auto& rendererItem : item["renderers"]) {
                        if (!rendererItem.is_object()) continue;
                        const auto targetRenderer = GetJsonString(rendererItem, "targetRenderer");
                        const auto modRenderer = GetJsonString(rendererItem, "modRenderer");
                        if (!targetRenderer || !modRenderer) {
                            Log::ErrorFmt("[ModAsset] Invalid renderer rule in %s: targetRenderer and modRenderer are required.",
                                manifestPath.string().c_str());
                            continue;
                        }

                        rendererRules.emplace_back(LocalModRendererRule{
                            GetJsonString(rendererItem, "rendererId").value_or(""),
                            *targetRenderer,
                            *modRenderer,
                        });
                    }
                }

                std::vector<LocalModMaterialTextureReplacement> materialTextures{};
                std::vector<LocalModMaterialSlotCopy> materialCopies{};
                if (item.contains("materialCopies") && item["materialCopies"].is_array()) {
                    for (const auto& copyItem : item["materialCopies"]) {
                        if (!copyItem.is_object()) continue;

                        materialCopies.emplace_back(LocalModMaterialSlotCopy{
                            GetJsonString(copyItem, "rendererName").value_or(rendererName),
                            GetJsonInt(copyItem, "fromSlot", GetJsonInt(copyItem, "sourceSlot", -1)),
                            GetJsonInt(copyItem, "toSlot", GetJsonInt(copyItem, "targetSlot", -1)),
                        });
                    }
                }

                std::vector<LocalModMaterialColorReplacement> materialColors{};
                if (item.contains("materialColors") && item["materialColors"].is_array()) {
                    for (const auto& colorItem : item["materialColors"]) {
                        if (!colorItem.is_object()) continue;

                        const auto propertyName = GetFirstJsonString(colorItem, { "property", "shaderProperty", "name" });
                        if (!propertyName) {
                            Log::ErrorFmt("[ModAsset] Invalid material color replacement in %s: property is required.",
                                manifestPath.string().c_str());
                            continue;
                        }

                        float r = GetJsonFloat(colorItem, "r", 1.0f);
                        float g = GetJsonFloat(colorItem, "g", 1.0f);
                        float b = GetJsonFloat(colorItem, "b", 1.0f);
                        float a = GetJsonFloat(colorItem, "a", 1.0f);
                        if (colorItem.contains("value") && colorItem["value"].is_array()) {
                            const auto& value = colorItem["value"];
                            if (value.size() > 0 && value[0].is_number()) r = value[0].get<float>();
                            if (value.size() > 1 && value[1].is_number()) g = value[1].get<float>();
                            if (value.size() > 2 && value[2].is_number()) b = value[2].get<float>();
                            if (value.size() > 3 && value[3].is_number()) a = value[3].get<float>();
                        }

                        materialColors.emplace_back(LocalModMaterialColorReplacement{
                            GetJsonString(colorItem, "rendererName").value_or(rendererName),
                            GetJsonInt(colorItem, "materialSlot", -1),
                            *propertyName,
                            r,
                            g,
                            b,
                            a,
                        });
                    }
                }

                std::vector<LocalModMaterialFloatReplacement> materialFloats{};
                if (item.contains("materialFloats") && item["materialFloats"].is_array()) {
                    for (const auto& floatItem : item["materialFloats"]) {
                        if (!floatItem.is_object()) continue;

                        const auto propertyName = GetFirstJsonString(floatItem, { "property", "shaderProperty", "name" });
                        if (!propertyName) {
                            Log::ErrorFmt("[ModAsset] Invalid material float replacement in %s: property is required.",
                                manifestPath.string().c_str());
                            continue;
                        }

                        materialFloats.emplace_back(LocalModMaterialFloatReplacement{
                            GetJsonString(floatItem, "rendererName").value_or(rendererName),
                            GetJsonInt(floatItem, "materialSlot", -1),
                            *propertyName,
                            GetJsonFloat(floatItem, "value", 0.0f),
                        });
                    }
                }

                if (item.contains("textures") && item["textures"].is_array()) {
                    for (const auto& textureItem : item["textures"]) {
                        if (!textureItem.is_object()) continue;

                        const auto propertyName = GetFirstJsonString(textureItem, { "property", "shaderProperty", "name" });
                        const auto textureAssetName = GetFirstJsonString(textureItem, { "asset", "texture", "to" });
                        if (!propertyName || !textureAssetName) {
                            Log::ErrorFmt("[ModAsset] Invalid texture replacement in %s: property and asset are required.",
                                manifestPath.string().c_str());
                            continue;
                        }

                        materialTextures.emplace_back(LocalModMaterialTextureReplacement{
                            GetJsonString(textureItem, "rendererName").value_or(rendererName),
                            GetJsonInt(textureItem, "materialSlot", -1),
                            *propertyName,
                            *textureAssetName,
                            GetJsonString(textureItem, "type").value_or("Texture2D"),
                        });
                    }
                }

                const auto bundlePath = (manifestDir / *bundleName).lexically_normal();
                if (!std::filesystem::is_regular_file(bundlePath)) {
                    Log::ErrorFmt("[ModAsset] Mod bundle not found: %s", bundlePath.string().c_str());
                    continue;
                }

                const auto replacementKey = NormalizeAssetName(*sourceName);
                if (const auto existing = g_replacementMap.find(replacementKey); existing != g_replacementMap.end()) {
                    if (priority < existing->second.priority) {
                        Log::WarnFmt("[ModAsset] Replacement conflict skipped by priority: source=%s newMod=%s newPriority=%d existingMod=%s existingPriority=%d",
                            sourceName->c_str(),
                            modName.c_str(),
                            priority,
                            existing->second.modName.c_str(),
                            existing->second.priority);
                        continue;
                    }

                    Log::WarnFmt("[ModAsset] Replacement conflict overridden: source=%s newMod=%s newPriority=%d existingMod=%s existingPriority=%d",
                        sourceName->c_str(),
                        modName.c_str(),
                        priority,
                        existing->second.modName.c_str(),
                        existing->second.priority);
                }

                g_replacementMap[replacementKey] = LocalModAssetReplacement{
                    modName,
                    manifestPath.string(),
                    *sourceName,
                    part,
                    assetName,
                    skeletonAssetName,
                    bundlePath.string(),
                    typeName,
                    replaceWholeObject,
                    attachToOriginal,
                    rendererName,
                    priority,
                    replaceMaterials,
                    0,
                    std::move(rendererRules),
                    std::move(materialCopies),
                    std::move(materialTextures),
                    std::move(materialColors),
                    std::move(materialFloats),
                };
                ++loadedCount;
                const auto& registeredReplacement = g_replacementMap[replacementKey];
                Log::InfoFmt("[ModAsset] Registered replacement: %s -> %s (%s) mod=%s part=%s priority=%d wholeObject=%d skeleton=%s rendererRules=%zu materialCopies=%zu textures=%zu colors=%zu floats=%zu",
                    sourceName->c_str(),
                    assetName.c_str(),
                    bundlePath.string().c_str(),
                    modName.c_str(),
                    registeredReplacement.part.c_str(),
                    registeredReplacement.priority,
                    registeredReplacement.replaceWholeObject ? 1 : 0,
                    registeredReplacement.skeletonAssetName.c_str(),
                    registeredReplacement.rendererRules.size(),
                    registeredReplacement.materialCopies.size(),
                    registeredReplacement.materialTextures.size(),
                    registeredReplacement.materialColors.size(),
                    registeredReplacement.materialFloats.size());
            }

            Log::InfoFmt("[ModAsset] Manifest loaded: %s, replacements=%d", modName.c_str(), loadedCount);
        }

        void LoadLocalModManifests() {
            const auto modRoot = std::filesystem::path("./gakumas-local/local-files/mods");
            g_replacementMap.clear();

            if (!std::filesystem::exists(modRoot)) {
                Log::InfoFmt("[ModAsset] Mod directory not found, skipped: %s", modRoot.string().c_str());
                return;
            }

            std::vector<std::filesystem::path> manifestPaths{};
            for (const auto& entry : std::filesystem::directory_iterator(modRoot)) {
                if (entry.is_regular_file() && entry.path().extension() == ".json") {
                    manifestPaths.emplace_back(entry.path());
                    continue;
                }

                if (!entry.is_directory()) continue;
                const auto manifestPath = entry.path() / "mod.json";
                if (std::filesystem::is_regular_file(manifestPath)) {
                    manifestPaths.emplace_back(manifestPath);
                }
            }
            std::sort(manifestPaths.begin(), manifestPaths.end());

            for (const auto& manifestPath : manifestPaths) {
                LoadLocalModManifest(manifestPath);
            }

            Log::InfoFmt("[ModAsset] Registered mod asset replacements: %zu", g_replacementMap.size());
        }

        LocalModAssetReplacement* FindLocalModAssetReplacement(const std::string& sourceName) {
            const auto iter = g_replacementMap.find(NormalizeAssetName(sourceName));
            return iter == g_replacementMap.end() ? nullptr : &iter->second;
        }

        UnityResolve::Class* GetLocalModUnityClass(const std::string& typeName) {
            const auto typeKey = ToLowerAscii(typeName);
            if (typeKey == "gameobject" || typeKey == "unityengine.gameobject") {
                return Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "GameObject");
            }
            if (typeKey == "mesh" || typeKey == "unityengine.mesh") {
                return Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "Mesh");
            }
            if (typeKey == "material" || typeKey == "unityengine.material") {
                return Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "Material");
            }
            if (typeKey == "texture2d" || typeKey == "unityengine.texture2d") {
                return Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "Texture2D");
            }
            if (typeKey == "textasset" || typeKey == "unityengine.textasset") {
                return Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "TextAsset");
            }
            if (typeKey == "sprite" || typeKey == "unityengine.sprite") {
                return Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "Sprite");
            }

            Log::ErrorFmt("[ModAsset] Unsupported replacement type \"%s\", fallback to GameObject.", typeName.c_str());
            return Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "GameObject");
        }

        Il2cppUtils::Il2CppReflectionType* GetLocalModReflectionType(const std::string& typeName) {
            const auto klass = GetLocalModUnityClass(typeName);
            if (!klass) return nullptr;

            const auto il2cppType = UnityResolve::Invoke<void*>("il2cpp_class_get_type", klass->address);
            return il2cppType
                ? UnityResolve::Invoke<Il2cppUtils::Il2CppReflectionType*>("il2cpp_type_get_object", il2cppType)
                : nullptr;
        }

        void* LoadLocalModAssetFromBundle(const Il2CppGCHandle bundleHandle,
            const std::string& bundlePath,
            const std::string& assetName,
            const std::string& typeName) {
            const auto cacheKey = NormalizeAssetName(bundlePath + "|" + assetName + "|" + typeName);
            if (const auto iter = g_loadedAssetHandleMap.find(cacheKey); iter != g_loadedAssetHandleMap.end()) {
                auto cachedAsset = UnityResolve::Invoke<void*>("il2cpp_gchandle_get_target", iter->second);
                if (cachedAsset && IsNativeObjectAlive(cachedAsset)) {
                    return cachedAsset;
                }
                UnityResolve::Invoke<void>("il2cpp_gchandle_free", std::exchange(iter->second, nullptr));
                g_loadedAssetHandleMap.erase(iter);
            }

            const auto assetBundle = UnityResolve::Invoke<void*>("il2cpp_gchandle_get_target", bundleHandle);
            if (!assetBundle) {
                Log::ErrorFmt("[ModAsset] Mod bundle target is null: %s", bundlePath.c_str());
                return nullptr;
            }

            const auto reflectionType = GetLocalModReflectionType(typeName);
            if (!reflectionType) {
                Log::ErrorFmt("[ModAsset] Cannot resolve mod asset type: %s", typeName.c_str());
                return nullptr;
            }

            static auto AssetBundle_LoadAsset = Il2cppUtils::GetMethod(
                "UnityEngine.AssetBundleModule.dll",
                "UnityEngine",
                "AssetBundle",
                "LoadAsset_Internal",
                { "System.String", "System.Type" });
            if (!AssetBundle_LoadAsset) {
                Log::Error("[ModAsset] Cannot resolve AssetBundle.LoadAsset_Internal managed method for replacement.");
                return nullptr;
            }

            auto modAsset = AssetBundle_LoadAsset->Invoke<void*>(
                assetBundle,
                Il2cppString::New(assetName),
                reflectionType);
            if (!modAsset) {
                Log::ErrorFmt("[ModAsset] Failed to load mod asset: %s type=%s bundle=%s",
                    assetName.c_str(),
                    typeName.c_str(),
                    bundlePath.c_str());
                return nullptr;
            }

            g_loadedAssetHandleMap[cacheKey] = UnityResolve::Invoke<Il2CppGCHandle>("il2cpp_gchandle_new", modAsset, false);
            Log::InfoFmt("[ModAsset] Loaded mod asset: %s type=%s result=%p resultType=%s",
                assetName.c_str(),
                typeName.c_str(),
                modAsset,
                GetUnityObjectClassName(modAsset));
            return modAsset;
        }

        void* LoadLocalModReplacementAsset(LocalModAssetReplacement& replacement) {
            if (!replacement.bundleHandle) {
                replacement.bundleHandle = LoadLocalModAssetBundle(replacement.bundlePath);
            }
            if (!replacement.bundleHandle) {
                Log::ErrorFmt("[ModAsset] Replacement bundle unavailable, keeping original asset: %s bundle=%s",
                    replacement.sourceName.c_str(),
                    replacement.bundlePath.c_str());
                return nullptr;
            }

            return LoadLocalModAssetFromBundle(
                replacement.bundleHandle,
                replacement.bundlePath,
                replacement.assetName,
                replacement.typeName);
        }

        std::string GetTextAssetText(void* asset) {
            static auto TextAsset_get_text = reinterpret_cast<Il2cppString* (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "TextAsset", "get_text"));
            const auto text = asset && TextAsset_get_text ? TextAsset_get_text(asset) : nullptr;
            return text ? text->ToString() : std::string{};
        }

        void* CloneUnityObject(void* obj, const std::string& sourceName, const size_t rendererIndex) {
            if (!obj) return nullptr;

            using CloneFn = void* (*)(void*);
            static auto Object_InternalCloneSingle = reinterpret_cast<CloneFn>(
                Il2cppUtils::il2cpp_resolve_icall("UnityEngine.Object::Internal_CloneSingle(UnityEngine.Object)"));

            auto clone = Object_InternalCloneSingle ? Object_InternalCloneSingle(obj) : nullptr;
            if (!clone) {
                static auto Object_Instantiate = reinterpret_cast<CloneFn>(
                    Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Object",
                        "Instantiate", { "UnityEngine.Object" }));
                clone = Object_Instantiate ? Object_Instantiate(obj) : nullptr;
            }
            if (!clone) {
                Log::ErrorFmt("[ModAsset] Failed to clone mod mesh: %s renderer=%zu sourceMesh=%p",
                    sourceName.c_str(),
                    rendererIndex,
                    obj);
                return nullptr;
            }

            g_runtimeMeshHandles.emplace_back(UnityResolve::Invoke<Il2CppGCHandle>("il2cpp_gchandle_new", clone, false));
            Log::InfoFmt("[ModAsset] Cloned mod mesh before patch: %s renderer=%zu sourceMesh=%p clonedMesh=%p",
                sourceName.c_str(),
                rendererIndex,
                obj,
                clone);
            return clone;
        }

        UnityArray<void*>* GetSkinnedMeshRendererBones(void* renderer) {
            static auto SkinnedMeshRenderer_get_bones = reinterpret_cast<UnityArray<void*>* (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "SkinnedMeshRenderer", "get_bones"));
            return renderer && SkinnedMeshRenderer_get_bones ? SkinnedMeshRenderer_get_bones(renderer) : nullptr;
        }

        void* GetSkinnedMeshRendererSharedMesh(void* renderer) {
            static auto SkinnedMeshRenderer_get_sharedMesh = reinterpret_cast<void* (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "SkinnedMeshRenderer", "get_sharedMesh"));
            return renderer && SkinnedMeshRenderer_get_sharedMesh ? SkinnedMeshRenderer_get_sharedMesh(renderer) : nullptr;
        }

        void SetSkinnedMeshRendererBones(void* renderer, UnityArray<void*>* bones) {
            static auto SkinnedMeshRenderer_set_bones = reinterpret_cast<void (*)(void*, UnityArray<void*>*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "SkinnedMeshRenderer", "set_bones"));
            if (renderer && bones && SkinnedMeshRenderer_set_bones) SkinnedMeshRenderer_set_bones(renderer, bones);
        }

        void* GetSkinnedMeshRendererRootBone(void* renderer) {
            static auto SkinnedMeshRenderer_get_rootBone = reinterpret_cast<void* (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "SkinnedMeshRenderer", "get_rootBone"));
            return renderer && SkinnedMeshRenderer_get_rootBone ? SkinnedMeshRenderer_get_rootBone(renderer) : nullptr;
        }

        int GetMeshVertexCount(void* mesh) {
            static auto Mesh_get_vertexCount = reinterpret_cast<int (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Mesh", "get_vertexCount"));
            return mesh && Mesh_get_vertexCount ? Mesh_get_vertexCount(mesh) : -1;
        }

        int GetMeshIntProperty(void* mesh, const char* propertyName) {
            static std::unordered_map<std::string, int (*)(void*)> accessors;
            if (!mesh) return -1;
            auto& fn = accessors[propertyName];
            if (!fn) {
                fn = reinterpret_cast<int (*)(void*)>(
                    Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Mesh", propertyName));
            }
            return fn ? fn(mesh) : -1;
        }

        UnityArray<UnityResolve::UnityType::Vector3>* GetMeshVertices(void* mesh) {
            static auto Mesh_get_vertices = reinterpret_cast<UnityArray<UnityResolve::UnityType::Vector3>* (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Mesh", "get_vertices"));
            return mesh && Mesh_get_vertices ? Mesh_get_vertices(mesh) : nullptr;
        }

        void SetMeshVertices(void* mesh, UnityArray<UnityResolve::UnityType::Vector3>* vertices) {
            static auto Mesh_set_vertices = reinterpret_cast<void (*)(void*, UnityArray<UnityResolve::UnityType::Vector3>*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Mesh", "set_vertices"));
            if (mesh && vertices && Mesh_set_vertices) Mesh_set_vertices(mesh, vertices);
        }

        void RecalculateMeshBounds(void* mesh) {
            static auto Mesh_RecalculateBounds = reinterpret_cast<void (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Mesh", "RecalculateBounds"));
            if (mesh && Mesh_RecalculateBounds) Mesh_RecalculateBounds(mesh);
        }

        UnityResolve::UnityType::Transform* GetComponentTransform(void* component) {
            static auto Component_get_transform = reinterpret_cast<UnityResolve::UnityType::Transform * (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Component", "get_transform"));
            return component && Component_get_transform ? Component_get_transform(component) : nullptr;
        }

        UnityResolve::UnityType::Vector3 InverseTransformPoint(void* transform, const UnityResolve::UnityType::Vector3& position) {
            static auto method = UnityResolve::Get("UnityEngine.CoreModule.dll")
                ->Get("Transform")
                ->Get<UnityResolve::Method>("InverseTransformPoint");
            return transform && method ? method->Invoke<UnityResolve::UnityType::Vector3>(transform, position) : UnityResolve::UnityType::Vector3{};
        }

        UnityResolve::UnityType::Vector3 TransformPoint(void* transform, const UnityResolve::UnityType::Vector3& position) {
            static auto method = UnityResolve::Get("UnityEngine.CoreModule.dll")
                ->Get("Transform")
                ->Get<UnityResolve::Method>("TransformPoint");
            return transform && method ? method->Invoke<UnityResolve::UnityType::Vector3>(transform, position) : UnityResolve::UnityType::Vector3{};
        }

        UnityResolve::UnityType::Matrix4x4 GetTransformLocalToWorldMatrix(void* transform) {
            static auto Transform_get_localToWorldMatrix = reinterpret_cast<UnityResolve::UnityType::Matrix4x4(*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Transform", "get_localToWorldMatrix"));
            return transform && Transform_get_localToWorldMatrix ? Transform_get_localToWorldMatrix(transform) : UnityResolve::UnityType::Matrix4x4{};
        }

        UnityResolve::UnityType::Matrix4x4 GetTransformWorldToLocalMatrix(void* transform) {
            static auto Transform_get_worldToLocalMatrix = reinterpret_cast<UnityResolve::UnityType::Matrix4x4(*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Transform", "get_worldToLocalMatrix"));
            return transform && Transform_get_worldToLocalMatrix ? Transform_get_worldToLocalMatrix(transform) : UnityResolve::UnityType::Matrix4x4{};
        }

        UnityResolve::UnityType::Matrix4x4 MultiplyMatrix4x4(const UnityResolve::UnityType::Matrix4x4& left,
            const UnityResolve::UnityType::Matrix4x4& right) {
            static auto Matrix4x4_op_Multiply = reinterpret_cast<UnityResolve::UnityType::Matrix4x4(*)(UnityResolve::UnityType::Matrix4x4, UnityResolve::UnityType::Matrix4x4)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Matrix4x4", "op_Multiply",
                    { "UnityEngine.Matrix4x4", "UnityEngine.Matrix4x4" }));
            if (Matrix4x4_op_Multiply) return Matrix4x4_op_Multiply(left, right);

            UnityResolve::UnityType::Matrix4x4 result{};
            for (int row = 0; row < 4; ++row) {
                for (int col = 0; col < 4; ++col) {
                    float value = 0.0f;
                    for (int i = 0; i < 4; ++i) value += left.m[row][i] * right.m[i][col];
                    result.m[row][col] = value;
                }
            }
            return result;
        }

        UnityResolve::UnityType::Matrix4x4 GetBindposeRendererSpaceAdjustment(void* originalRenderer, void* modRenderer) {
            const auto originalTransform = GetComponentTransform(originalRenderer);
            const auto modTransform = GetComponentTransform(modRenderer);
            if (!originalTransform || !modTransform) return {};

            return MultiplyMatrix4x4(
                GetTransformWorldToLocalMatrix(modTransform),
                GetTransformLocalToWorldMatrix(originalTransform));
        }

        UnityArray<UnityResolve::UnityType::Matrix4x4>* GetMeshBindposes(void* mesh) {
            static auto Mesh_get_bindposes = reinterpret_cast<UnityArray<UnityResolve::UnityType::Matrix4x4>* (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Mesh", "get_bindposes"));
            return mesh && Mesh_get_bindposes ? Mesh_get_bindposes(mesh) : nullptr;
        }

        void SetMeshBindposes(void* mesh, UnityArray<UnityResolve::UnityType::Matrix4x4>* bindposes) {
            static auto Mesh_set_bindposes = reinterpret_cast<void (*)(void*, UnityArray<UnityResolve::UnityType::Matrix4x4>*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Mesh", "set_bindposes"));
            if (mesh && bindposes && Mesh_set_bindposes) Mesh_set_bindposes(mesh, bindposes);
        }

        UnityArray<LocalModBoneWeight>* GetMeshBoneWeights(void* mesh) {
            static auto Mesh_get_boneWeights = reinterpret_cast<UnityArray<LocalModBoneWeight>* (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Mesh", "get_boneWeights"));
            return mesh && Mesh_get_boneWeights ? Mesh_get_boneWeights(mesh) : nullptr;
        }

        void SetMeshBoneWeights(void* mesh, UnityArray<LocalModBoneWeight>* boneWeights) {
            static auto Mesh_set_boneWeights = reinterpret_cast<void (*)(void*, UnityArray<LocalModBoneWeight>*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Mesh", "set_boneWeights"));
            if (mesh && boneWeights && Mesh_set_boneWeights) Mesh_set_boneWeights(mesh, boneWeights);
        }

        std::unordered_map<std::string, size_t> BuildBoneNameIndexMap(UnityArray<void*>* bones) {
            std::unordered_map<std::string, size_t> result;
            if (!bones) return result;

            for (std::uintptr_t i = 0; i < bones->max_length; ++i) {
                const auto name = GetUnityObjectNameString(bones->At(static_cast<unsigned int>(i)));
                if (!name.empty() && !result.contains(name)) {
                    result.emplace(name, static_cast<size_t>(i));
                }
            }
            return result;
        }

        bool LoadIpBoneSidecar(const LocalModAssetReplacement& replacement, std::vector<LocalIpBone>& bones,
            std::vector<LocalIpExtraBone>& extraBones) {
            if (replacement.skeletonAssetName.empty()) return false;

            const auto asset = LoadLocalModAssetFromBundle(
                replacement.bundleHandle,
                replacement.bundlePath,
                replacement.skeletonAssetName,
                "TextAsset");
            const auto text = GetTextAssetText(asset);
            if (text.empty()) {
                Log::ErrorFmt("[ModAsset] IP skeleton sidecar is empty or unavailable: %s asset=%s",
                    replacement.sourceName.c_str(), replacement.skeletonAssetName.c_str());
                return false;
            }

            try {
                const auto document = nlohmann::json::parse(text);
                if (!document.contains("bones") || !document["bones"].is_array()) {
                    throw std::runtime_error("bones array is required");
                }

                const auto parseVector3 = [](const nlohmann::json& value) {
                    if (!value.is_array() || value.size() < 3) throw std::runtime_error("Vector3 array is invalid");
                    return UnityResolve::UnityType::Vector3(
                        value[0].get<float>(), value[1].get<float>(), value[2].get<float>());
                };
                const auto parseQuaternion = [](const nlohmann::json& value) {
                    if (!value.is_array() || value.size() < 4) throw std::runtime_error("Quaternion array is invalid");
                    return UnityResolve::UnityType::Quaternion(
                        value[0].get<float>(), value[1].get<float>(), value[2].get<float>(), value[3].get<float>());
                };

                const auto parseSwing = [](const nlohmann::json& item) -> std::optional<LocalIpBoneSwing> {
                    if (!item.contains("swing") || !item["swing"].is_object()) return std::nullopt;
                    const auto& s = item["swing"];
                    return LocalIpBoneSwing{
                        s.value("damping", 0.0f), s.value("stiffness", 0.0f),
                        s.value("spring", 0.0f), s.value("mass", 0.0f),
                        s.value("useWindGlobalForce", false) };
                };

                bones.clear();
                bones.reserve(document["bones"].size());
                for (const auto& item : document["bones"]) {
                    if (!item.is_object() || !item.contains("name") || !item["name"].is_string()) {
                        throw std::runtime_error("bone name is required");
                    }
                    LocalIpBone bone{};
                    bone.name = item["name"].get<std::string>();
                    bone.parentIndex = item.value("parentIndex", -1);
                    bone.localPosition = parseVector3(item.at("localPosition"));
                    bone.localRotation = parseQuaternion(item.at("localRotation"));
                    bone.localScale = parseVector3(item.at("localScale"));
                    bone.swing = parseSwing(item);
                    bones.emplace_back(std::move(bone));
                }

                extraBones.clear();
                if (document.contains("extraSwingBones") && document["extraSwingBones"].is_array()) {
                    for (const auto& item : document["extraSwingBones"]) {
                        if (!item.is_object() || !item.contains("name") || !item.contains("parentName")) {
                            throw std::runtime_error("extra swing bone needs name and parentName");
                        }
                        LocalIpExtraBone bone{};
                        bone.name = item["name"].get<std::string>();
                        bone.parentName = item["parentName"].get<std::string>();
                        bone.localPosition = parseVector3(item.at("localPosition"));
                        bone.localRotation = parseQuaternion(item.at("localRotation"));
                        bone.localScale = parseVector3(item.at("localScale"));
                        bone.swing = parseSwing(item);
                        extraBones.emplace_back(std::move(bone));
                    }
                }
                return !bones.empty();
            }
            catch (const std::exception& e) {
                Log::ErrorFmt("[ModAsset] Cannot parse IP skeleton sidecar: %s asset=%s error=%s",
                    replacement.sourceName.c_str(), replacement.skeletonAssetName.c_str(), e.what());
                bones.clear();
                return false;
            }
        }

        bool SetTransformParent(UnityResolve::UnityType::Transform* child,
            UnityResolve::UnityType::Transform* parent) {
            static auto Transform_SetParent = FindMethodByNameAndArgCount(
                Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "Transform"),
                "SetParent", 2);
            if (!child || !parent || !Transform_SetParent) return false;
            Transform_SetParent->Invoke<void>(child, parent, false);
            return true;
        }

        bool AttachNativeChainToLiveRoot(UnityResolve::UnityType::Transform* rootTransform) {
            if (!rootTransform) return false;
            const auto rootGameObject = rootTransform->GetGameObject();
            if (!rootGameObject) return false;
            if (g_nativeChainAttachedRoots.contains(rootGameObject)) return true;

            const auto rendererClass = Il2cppUtils::GetClass(
                "UnityEngine.CoreModule.dll", "UnityEngine", "SkinnedMeshRenderer");
            if (!rendererClass) return false;
            const auto renderers = rootGameObject->GetComponentsInChildren<void*>(rendererClass, true);

            for (auto& [key, replacement] : g_replacementMap) {
                if (!replacement.attachToOriginal || !replacement.attachAsset) continue;
                bool matched = false;
                void* matchedMesh = nullptr;
                for (const auto renderer : renderers) {
                    const auto mesh = GetSkinnedMeshRendererSharedMesh(renderer);
                    if (mesh && std::find(replacement.attachSourceMeshes.begin(), replacement.attachSourceMeshes.end(), mesh)
                        != replacement.attachSourceMeshes.end()) {
                        matched = true;
                        matchedMesh = mesh;
                        break;
                    }
                }
                if (!matched) {
                    Log::InfoFmt("[ModAsset] Native chain live-root mismatch: root=%s target=%s renderers=%zu sourceMeshes=%zu",
                        GetUnityObjectNameString(rootGameObject).c_str(), replacement.sourceName.c_str(),
                        renderers.size(), replacement.attachSourceMeshes.size());
                    continue;
                }

                const auto subtreeClone = CloneUnityObject(replacement.attachAsset, replacement.sourceName, 0);
                const auto cloneGameObject = reinterpret_cast<UnityResolve::UnityType::GameObject*>(subtreeClone);
                const auto attached = cloneGameObject
                    && SetTransformParent(cloneGameObject->GetTransform(), rootTransform);
                if (!attached) return false;
                // ponytail: the §4 probe has one attach subtree per actor; key by
                // (root, replacement) when manifests need multiple native subtrees.
                g_nativeChainAttachedRoots.emplace(rootGameObject);
                Log::InfoFmt("[ModAsset] Attached native chain subtree to live actor: root=%s source=%s matchedMesh=%s clone=%p",
                    GetUnityObjectNameString(rootGameObject).c_str(), replacement.sourceName.c_str(),
                    GetUnityObjectNameString(matchedMesh).c_str(), subtreeClone);
                return true;
            }
            return false;
        }

        UnityArray<void*>* BuildHybridBoneArray(void* originalRenderer,
            UnityArray<void*>* originalBones,
            UnityArray<void*>* modBones,
            const std::vector<LocalIpBone>& sidecarBones,
            const std::vector<LocalIpExtraBone>& extraBones,
            const std::string& sourceName,
            const size_t rendererIndex,
            size_t& matchedBones,
            size_t& createdBones,
            std::vector<void*>& createdDynamicBones) {
            if (!originalRenderer || !originalBones || !modBones || sidecarBones.size() != modBones->max_length) return nullptr;
            if (const auto cached = g_hybridBonesByRenderer.find(originalRenderer); cached != g_hybridBonesByRenderer.end()
                && cached->second.size() == sidecarBones.size()
                && std::all_of(cached->second.begin(), cached->second.end(), [](const void* bone) { return bone && IsNativeObjectAlive(const_cast<void*>(bone)); })) {
                const auto transformClass = Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "Transform");
                if (!transformClass) return nullptr;
                auto result = UnityArray<void*>::New(transformClass, cached->second.size());
                for (size_t i = 0; i < cached->second.size(); ++i) result->At(static_cast<unsigned int>(i)) = cached->second[i];
                matchedBones = 0;
                for (const auto& bone : sidecarBones) if (BuildBoneNameIndexMap(originalBones).contains(bone.name)) ++matchedBones;
                createdBones = sidecarBones.size() - matchedBones;
                return result;
            }

            const auto transformClass = Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "Transform");
            const auto gameObjectClass = Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "GameObject");
            if (!transformClass || !gameObjectClass) return nullptr;

            const auto originalBoneIndexMap = BuildBoneNameIndexMap(originalBones);
            const auto hips = originalBoneIndexMap.find("Hips");
            size_t fallbackParentIndex = 0;
            if (hips != originalBoneIndexMap.end()) {
                fallbackParentIndex = hips->second;
            }
            else {
                const auto root = std::find_if(sidecarBones.begin(), sidecarBones.end(),
                    [&](const LocalIpBone& bone) {
                        return bone.parentIndex < 0 && originalBoneIndexMap.contains(bone.name);
                    });
                if (root != sidecarBones.end()) {
                    fallbackParentIndex = originalBoneIndexMap.at(root->name);
                }
                else if (originalBones->max_length == 0) {
                    Log::ErrorFmt("[ModAsset] Cannot build IP skeleton: original renderer has no root bone: %s renderer=%zu",
                        sourceName.c_str(), rendererIndex);
                    return nullptr;
                }
            }

            const auto createBone = [&](const std::string& name, UnityResolve::UnityType::Transform* parent,
                const UnityResolve::UnityType::Vector3& localPosition,
                const UnityResolve::UnityType::Quaternion& localRotation,
                const UnityResolve::UnityType::Vector3& localScale,
                const std::optional<LocalIpBoneSwing>& swing) -> UnityResolve::UnityType::Transform* {
                auto gameObject = gameObjectClass->New<UnityResolve::UnityType::GameObject>();
                if (!gameObject) return nullptr;
                UnityResolve::UnityType::GameObject::Create(gameObject, name);
                auto transform = gameObject->GetTransform();
                if (!transform || !SetTransformParent(transform, parent)) return nullptr;
                transform->SetLocalPosition(localPosition);
                transform->SetLocalRotation(localRotation);
                transform->SetLocalScale(localScale);
                if (const auto dynamicBoneClass = FindClassByName("ActorSwingDynamicBone")) {
                    const auto dynamicBone = AddComponentByClass(gameObject, dynamicBoneClass);
                    if (dynamicBone && InitializeActorSwingDynamicBone(dynamicBone, dynamicBoneClass, swing)) {
                        g_createdActorSwingBoneNames.emplace(name);
                        createdDynamicBones.emplace_back(dynamicBone);
                    }
                }
                g_runtimeBoneHandles.emplace_back(UnityResolve::Invoke<Il2CppGCHandle>("il2cpp_gchandle_new", gameObject, false));
                return transform;
            };

            std::vector<void*> hybridBones(sidecarBones.size());
            std::vector<unsigned char> states(sidecarBones.size());
            std::function<bool(size_t)> buildBone;
            buildBone = [&](const size_t index) {
                if (index >= sidecarBones.size()) return false;
                if (states[index] == 2) return true;
                if (states[index] == 1) return false;
                states[index] = 1;

                const auto& sidecarBone = sidecarBones[index];
                if (const auto original = originalBoneIndexMap.find(sidecarBone.name); original != originalBoneIndexMap.end()) {
                    hybridBones[index] = originalBones->At(static_cast<unsigned int>(original->second));
                    ++matchedBones;
                }
                else {
                    auto parent = reinterpret_cast<UnityResolve::UnityType::Transform*>(
                        originalBones->At(static_cast<unsigned int>(fallbackParentIndex)));
                    if (sidecarBone.parentIndex >= 0) {
                        if (static_cast<size_t>(sidecarBone.parentIndex) >= sidecarBones.size()
                            || !buildBone(static_cast<size_t>(sidecarBone.parentIndex))) return false;
                        parent = reinterpret_cast<UnityResolve::UnityType::Transform*>(hybridBones[static_cast<size_t>(sidecarBone.parentIndex)]);
                    }

                    const auto transform = createBone(sidecarBone.name, parent, sidecarBone.localPosition,
                        sidecarBone.localRotation, sidecarBone.localScale, sidecarBone.swing);
                    if (!transform) return false;
                    hybridBones[index] = transform;
                    ++createdBones;
                }

                states[index] = 2;
                return hybridBones[index] != nullptr;
            };

            for (size_t i = 0; i < sidecarBones.size(); ++i) {
                if (!buildBone(i)) {
                    Log::ErrorFmt("[ModAsset] Cannot build IP skeleton hierarchy: %s renderer=%zu bone=%s index=%zu",
                        sourceName.c_str(), rendererIndex, sidecarBones[i].name.c_str(), i);
                    return nullptr;
                }
            }

            // Attach each chain's tip. These carry no skin weights so they stay out of
            // hybridBones, but the sim needs them: without a tip the last segment is
            // undefined and the chain diverges instead of swinging.
            size_t extraCreated = 0;
            for (const auto& extra : extraBones) {
                const auto parent = std::find_if(sidecarBones.begin(), sidecarBones.end(),
                    [&](const LocalIpBone& bone) { return bone.name == extra.parentName; });
                if (parent == sidecarBones.end()) {
                    Log::WarnFmt("[ModAsset] Chain tip has no parent in the mesh skeleton, skipped: %s parent=%s",
                        extra.name.c_str(), extra.parentName.c_str());
                    continue;
                }
                const auto parentTransform = reinterpret_cast<UnityResolve::UnityType::Transform*>(
                    hybridBones[static_cast<size_t>(std::distance(sidecarBones.begin(), parent))]);
                if (parentTransform && createBone(extra.name, parentTransform, extra.localPosition,
                    extra.localRotation, extra.localScale, extra.swing)) {
                    ++extraCreated;
                }
            }
            if (!extraBones.empty()) {
                Log::InfoFmt("[ModAsset] Chain tips attached: %zu/%zu renderer=%zu",
                    extraCreated, extraBones.size(), rendererIndex);
            }

            g_hybridBonesByRenderer[originalRenderer] = hybridBones;
            auto result = UnityArray<void*>::New(transformClass, hybridBones.size());
            for (size_t i = 0; i < hybridBones.size(); ++i) result->At(static_cast<unsigned int>(i)) = hybridBones[i];
            return result;
        }

        void UpdateMaxBoneIndex(int& currentMax, const int boneIndex) {
            if (boneIndex > currentMax) currentMax = boneIndex;
        }

        void AddBoneWeightStat(std::vector<double>& totals, const int boneIndex, const float weight) {
            if (weight <= 0.0f || boneIndex < 0 || static_cast<size_t>(boneIndex) >= totals.size()) return;
            totals[static_cast<size_t>(boneIndex)] += static_cast<double>(weight);
        }

        std::string FormatTopBoneWeightStats(const std::vector<double>& totals, UnityArray<void*>* bones, const size_t limit) {
            std::vector<size_t> indices;
            indices.reserve(totals.size());
            for (size_t i = 0; i < totals.size(); ++i) {
                if (totals[i] > 0.000001) indices.push_back(i);
            }

            std::sort(indices.begin(), indices.end(), [&](const size_t left, const size_t right) {
                return totals[left] > totals[right];
            });

            std::string result;
            const auto count = indices.size() < limit ? indices.size() : limit;
            for (size_t i = 0; i < count; ++i) {
                const auto boneIndex = indices[i];
                if (!result.empty()) result += ", ";
                const auto boneName = bones && boneIndex < bones->max_length
                    ? GetUnityObjectNameString(bones->At(static_cast<unsigned int>(boneIndex)))
                    : std::string{};
                result += boneName.empty() ? "#" + std::to_string(boneIndex) : boneName;
                result += ":";
                result += std::to_string(totals[boneIndex]);
            }
            return result;
        }

        void RemapBoneInfluence(int& boneIndex, float& weight, const int fallbackBoneIndex,
            const std::vector<int>& modToOriginalBoneIndex, size_t& remappedCount, size_t& droppedInfluences) {
            if (weight <= 0.0f) {
                boneIndex = fallbackBoneIndex;
                return;
            }

            if (boneIndex < 0 || static_cast<size_t>(boneIndex) >= modToOriginalBoneIndex.size()) {
                boneIndex = fallbackBoneIndex;
                weight = 0.0f;
                ++droppedInfluences;
                return;
            }

            const auto originalBoneIndex = modToOriginalBoneIndex[static_cast<size_t>(boneIndex)];
            if (originalBoneIndex < 0) {
                boneIndex = fallbackBoneIndex;
                weight = 0.0f;
                ++droppedInfluences;
                return;
            }

            if (originalBoneIndex != boneIndex) ++remappedCount;
            boneIndex = originalBoneIndex;
        }

        bool NormalizeBoneWeight(LocalModBoneWeight& weight, const int fallbackBoneIndex, size_t& fallbackVertices) {
            const auto total = weight.weight0 + weight.weight1 + weight.weight2 + weight.weight3;
            if (total > 0.000001f) {
                const auto invTotal = 1.0f / total;
                weight.weight0 *= invTotal;
                weight.weight1 *= invTotal;
                weight.weight2 *= invTotal;
                weight.weight3 *= invTotal;
                return true;
            }

            weight.weight0 = 1.0f;
            weight.weight1 = 0.0f;
            weight.weight2 = 0.0f;
            weight.weight3 = 0.0f;
            weight.boneIndex0 = fallbackBoneIndex;
            weight.boneIndex1 = fallbackBoneIndex;
            weight.boneIndex2 = fallbackBoneIndex;
            weight.boneIndex3 = fallbackBoneIndex;
            ++fallbackVertices;
            return false;
        }

        bool TransformModMeshVerticesToOriginalRendererSpace(void* originalRenderer, void* modRenderer, void* modMesh,
            const std::string& sourceName, const size_t rendererIndex) {
            if (!originalRenderer || !modRenderer || !modMesh) return false;
            if (g_transformedMeshSet.contains(modMesh)) return true;

            const auto originalTransform = GetComponentTransform(originalRenderer);
            const auto modTransform = GetComponentTransform(modRenderer);
            const auto vertices = GetMeshVertices(modMesh);
            if (!originalTransform || !modTransform || !vertices) {
                Log::ErrorFmt("[ModAsset] Cannot transform mod mesh vertices: %s renderer=%zu originalTransform=%p modTransform=%p vertices=%zu",
                    sourceName.c_str(),
                    rendererIndex,
                    originalTransform,
                    modTransform,
                    vertices ? static_cast<size_t>(vertices->max_length) : 0);
                return false;
            }

            for (std::uintptr_t i = 0; i < vertices->max_length; ++i) {
                const auto modLocal = vertices->At(static_cast<unsigned int>(i));
                const auto world = TransformPoint(modTransform, modLocal);
                vertices->At(static_cast<unsigned int>(i)) = InverseTransformPoint(originalTransform, world);
            }

            SetMeshVertices(modMesh, vertices);
            RecalculateMeshBounds(modMesh);
            g_transformedMeshSet.emplace(modMesh);
            Log::InfoFmt("[ModAsset] Transformed mod mesh vertices to original renderer space: %s renderer=%zu vertices=%zu originalRenderer=\"%s\" modRenderer=\"%s\"",
                sourceName.c_str(),
                rendererIndex,
                static_cast<size_t>(vertices->max_length),
                GetUnityObjectNameString(originalRenderer).c_str(),
                GetUnityObjectNameString(modRenderer).c_str());
            return true;
        }

        bool PatchModMeshSkinningLosslessly(void* originalRenderer, void* modRenderer, void* originalMesh, void* modMesh,
            const LocalModAssetReplacement& replacement, const std::string& sourceName, const size_t rendererIndex) {
            const auto matrixClass = Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "Matrix4x4");
            const auto originalBones = GetSkinnedMeshRendererBones(originalRenderer);
            const auto modBones = GetSkinnedMeshRendererBones(modRenderer);
            const auto modBindposes = GetMeshBindposes(modMesh);
            const auto modBoneWeights = GetMeshBoneWeights(modMesh);
            if (!matrixClass || !originalBones || !modBones || !modBindposes || !modBoneWeights) return false;

            const auto originalRootName = GetUnityObjectNameString(GetSkinnedMeshRendererRootBone(originalRenderer));
            const auto modRootName = GetUnityObjectNameString(GetSkinnedMeshRendererRootBone(modRenderer));
            if (originalRootName.empty() || originalRootName != modRootName
                || modBindposes->max_length != modBones->max_length) {
                Log::ErrorFmt("[ModAsset] Lossless IP skeleton requires matching roots and bone/bindpose counts: %s renderer=%zu originalRoot=\"%s\" modRoot=\"%s\" modBones=%zu modBindposes=%zu",
                    sourceName.c_str(), rendererIndex, originalRootName.c_str(), modRootName.c_str(),
                    static_cast<size_t>(modBones->max_length), static_cast<size_t>(modBindposes->max_length));
                return false;
            }

            std::vector<LocalIpBone> sidecarBones;
            std::vector<LocalIpExtraBone> extraSwingBones;
            if (!LoadIpBoneSidecar(replacement, sidecarBones, extraSwingBones) || sidecarBones.size() != modBones->max_length) {
                Log::ErrorFmt("[ModAsset] Lossless IP skeleton sidecar count mismatch: %s renderer=%zu sidecar=%zu modBones=%zu",
                    sourceName.c_str(), rendererIndex, sidecarBones.size(), static_cast<size_t>(modBones->max_length));
                return false;
            }

            for (size_t i = 0; i < sidecarBones.size(); ++i) {
                const auto modBoneName = GetUnityObjectNameString(modBones->At(static_cast<unsigned int>(i)));
                if (sidecarBones[i].name != modBoneName
                    || sidecarBones[i].parentIndex < -1
                    || sidecarBones[i].parentIndex >= static_cast<int>(i)) {
                    Log::ErrorFmt("[ModAsset] Lossless IP skeleton sidecar order/hierarchy mismatch: %s renderer=%zu index=%zu sidecar=\"%s\" mod=\"%s\" parent=%d",
                        sourceName.c_str(), rendererIndex, i, sidecarBones[i].name.c_str(), modBoneName.c_str(), sidecarBones[i].parentIndex);
                    return false;
                }
            }

            for (std::uintptr_t i = 0; i < modBoneWeights->max_length; ++i) {
                const auto& weight = modBoneWeights->At(static_cast<unsigned int>(i));
                const auto validBoneIndex = [&](const int boneIndex) {
                    return boneIndex >= 0 && static_cast<std::uintptr_t>(boneIndex) < modBones->max_length;
                };
                if (!validBoneIndex(weight.boneIndex0) || !validBoneIndex(weight.boneIndex1)
                    || !validBoneIndex(weight.boneIndex2) || !validBoneIndex(weight.boneIndex3)) {
                    Log::ErrorFmt("[ModAsset] Lossless IP skeleton found an invalid source weight index: %s renderer=%zu vertex=%zu",
                        sourceName.c_str(), rendererIndex, static_cast<size_t>(i));
                    return false;
                }
            }

            size_t matchedBones = 0;
            size_t createdBones = 0;
            std::vector<void*> createdDynamicBones;
            const auto hybridBones = BuildHybridBoneArray(
                originalRenderer, originalBones, modBones, sidecarBones, extraSwingBones, sourceName, rendererIndex,
                matchedBones, createdBones, createdDynamicBones);
            if (!hybridBones) return false;

            auto adjustedBindposes = UnityArray<UnityResolve::UnityType::Matrix4x4>::New(matrixClass, modBindposes->max_length);
            const auto bindposeSpaceAdjustment = GetBindposeRendererSpaceAdjustment(originalRenderer, modRenderer);
            for (std::uintptr_t i = 0; i < modBindposes->max_length; ++i) {
                adjustedBindposes->At(static_cast<unsigned int>(i)) = MultiplyMatrix4x4(
                    modBindposes->At(static_cast<unsigned int>(i)), bindposeSpaceAdjustment);
            }

            SetMeshBindposes(modMesh, adjustedBindposes);
            SetSkinnedMeshRendererBones(originalRenderer, hybridBones);
            RecalculateMeshBounds(modMesh);
            Log::InfoFmt("[ModAsset] Applied lossless IP skeleton graft: %s renderer=%zu matchedBones=%zu createdBones=%zu bones=%zu boneWeights=%zu swingPrepared=%zu droppedInfluences=0 fallbackVertices=0",
                sourceName.c_str(), rendererIndex, matchedBones, createdBones,
                static_cast<size_t>(hybridBones->max_length), static_cast<size_t>(modBoneWeights->max_length),
                createdDynamicBones.size());
            return true;
        }

        bool PatchModMeshSkinningToOriginalOrder(void* originalRenderer, void* modRenderer, void* originalMesh, void* modMesh,
            const LocalModAssetReplacement& replacement, const std::string& sourceName, const size_t rendererIndex) {
            if (!replacement.skeletonAssetName.empty()) {
                return PatchModMeshSkinningLosslessly(
                    originalRenderer, modRenderer, originalMesh, modMesh, replacement, sourceName, rendererIndex);
            }
            const auto boneWeightClass = Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "BoneWeight");
            const auto matrixClass = Il2cppUtils::GetClass("UnityEngine.CoreModule.dll", "UnityEngine", "Matrix4x4");
            if (!boneWeightClass || !matrixClass) return false;

            const auto originalBones = GetSkinnedMeshRendererBones(originalRenderer);
            const auto modBones = GetSkinnedMeshRendererBones(modRenderer);
            const auto originalBindposes = GetMeshBindposes(originalMesh);
            const auto modBindposes = GetMeshBindposes(modMesh);
            const auto modBoneWeights = GetMeshBoneWeights(modMesh);
            if (!originalBones || !modBones || !originalBindposes || !modBindposes || !modBoneWeights) {
                Log::ErrorFmt("[ModAsset] Cannot patch skinning to original order: %s renderer=%zu originalBones=%zu modBones=%zu originalBindposes=%zu modBindposes=%zu modBoneWeights=%zu",
                    sourceName.c_str(),
                    rendererIndex,
                    originalBones ? static_cast<size_t>(originalBones->max_length) : 0,
                    modBones ? static_cast<size_t>(modBones->max_length) : 0,
                    originalBindposes ? static_cast<size_t>(originalBindposes->max_length) : 0,
                    modBindposes ? static_cast<size_t>(modBindposes->max_length) : 0,
                    modBoneWeights ? static_cast<size_t>(modBoneWeights->max_length) : 0);
                return false;
            }

            const auto originalBoneIndexMap = BuildBoneNameIndexMap(originalBones);
            std::vector<int> modToOriginalBoneIndex(modBones->max_length, -1);
            size_t matchedBones = 0;
            for (std::uintptr_t i = 0; i < modBones->max_length; ++i) {
                const auto modBoneName = GetUnityObjectNameString(modBones->At(static_cast<unsigned int>(i)));
                if (const auto iter = originalBoneIndexMap.find(modBoneName); iter != originalBoneIndexMap.end()) {
                    modToOriginalBoneIndex[static_cast<size_t>(i)] = static_cast<int>(iter->second);
                    ++matchedBones;
                }
            }

            int fallbackBoneIndex = 0;
            if (const auto iter = originalBoneIndexMap.find("Hips"); iter != originalBoneIndexMap.end()) {
                fallbackBoneIndex = static_cast<int>(iter->second);
            }

            auto remappedBoneWeights = UnityArray<LocalModBoneWeight>::New(boneWeightClass, modBoneWeights->max_length);
            auto remappedBindposes = UnityArray<UnityResolve::UnityType::Matrix4x4>::New(matrixClass, originalBones->max_length);
            size_t remappedIndices = 0;
            size_t remappedBindposeCount = 0;
            size_t droppedInfluences = 0;
            size_t fallbackVertices = 0;
            int maxOriginalBoneIndex = -1;
            int maxModBoneIndex = -1;
            std::vector<double> modBoneWeightTotals(modBones->max_length, 0.0);
            std::vector<double> originalBoneWeightTotals(originalBones->max_length, 0.0);
            const auto originalRootName = GetUnityObjectNameString(GetSkinnedMeshRendererRootBone(originalRenderer));
            const auto modRootName = GetUnityObjectNameString(GetSkinnedMeshRendererRootBone(modRenderer));
            const auto useModBindposes = !originalRootName.empty() && originalRootName == modRootName && modBindposes->max_length > 0;
            const auto bindposeMode = useModBindposes ? "mod-remapped" : "original";
            const auto bindposeSpaceAdjustment = GetBindposeRendererSpaceAdjustment(originalRenderer, modRenderer);

            for (std::uintptr_t i = 0; i < originalBones->max_length; ++i) {
                remappedBindposes->At(static_cast<unsigned int>(i)) =
                    i < originalBindposes->max_length
                        ? originalBindposes->At(static_cast<unsigned int>(i))
                        : UnityResolve::UnityType::Matrix4x4{};
                if (i < originalBindposes->max_length) ++remappedBindposeCount;
            }

            if (useModBindposes) {
                remappedBindposeCount = 0;
                for (std::uintptr_t i = 0; i < modBones->max_length && i < modBindposes->max_length; ++i) {
                    const auto originalBoneIndex = modToOriginalBoneIndex[static_cast<size_t>(i)];
                    if (originalBoneIndex >= 0 && static_cast<std::uintptr_t>(originalBoneIndex) < remappedBindposes->max_length) {
                        remappedBindposes->At(static_cast<unsigned int>(originalBoneIndex)) =
                            MultiplyMatrix4x4(modBindposes->At(static_cast<unsigned int>(i)), bindposeSpaceAdjustment);
                        ++remappedBindposeCount;
                    }
                }
            }

            for (std::uintptr_t i = 0; i < modBoneWeights->max_length; ++i) {
                auto weight = modBoneWeights->At(static_cast<unsigned int>(i));
                UpdateMaxBoneIndex(maxModBoneIndex, weight.boneIndex0);
                UpdateMaxBoneIndex(maxModBoneIndex, weight.boneIndex1);
                UpdateMaxBoneIndex(maxModBoneIndex, weight.boneIndex2);
                UpdateMaxBoneIndex(maxModBoneIndex, weight.boneIndex3);
                AddBoneWeightStat(modBoneWeightTotals, weight.boneIndex0, weight.weight0);
                AddBoneWeightStat(modBoneWeightTotals, weight.boneIndex1, weight.weight1);
                AddBoneWeightStat(modBoneWeightTotals, weight.boneIndex2, weight.weight2);
                AddBoneWeightStat(modBoneWeightTotals, weight.boneIndex3, weight.weight3);

                RemapBoneInfluence(weight.boneIndex0, weight.weight0, fallbackBoneIndex, modToOriginalBoneIndex, remappedIndices, droppedInfluences);
                RemapBoneInfluence(weight.boneIndex1, weight.weight1, fallbackBoneIndex, modToOriginalBoneIndex, remappedIndices, droppedInfluences);
                RemapBoneInfluence(weight.boneIndex2, weight.weight2, fallbackBoneIndex, modToOriginalBoneIndex, remappedIndices, droppedInfluences);
                RemapBoneInfluence(weight.boneIndex3, weight.weight3, fallbackBoneIndex, modToOriginalBoneIndex, remappedIndices, droppedInfluences);
                NormalizeBoneWeight(weight, fallbackBoneIndex, fallbackVertices);

                UpdateMaxBoneIndex(maxOriginalBoneIndex, weight.boneIndex0);
                UpdateMaxBoneIndex(maxOriginalBoneIndex, weight.boneIndex1);
                UpdateMaxBoneIndex(maxOriginalBoneIndex, weight.boneIndex2);
                UpdateMaxBoneIndex(maxOriginalBoneIndex, weight.boneIndex3);
                AddBoneWeightStat(originalBoneWeightTotals, weight.boneIndex0, weight.weight0);
                AddBoneWeightStat(originalBoneWeightTotals, weight.boneIndex1, weight.weight1);
                AddBoneWeightStat(originalBoneWeightTotals, weight.boneIndex2, weight.weight2);
                AddBoneWeightStat(originalBoneWeightTotals, weight.boneIndex3, weight.weight3);
                remappedBoneWeights->At(static_cast<unsigned int>(i)) = weight;
            }

            SetMeshBindposes(modMesh, remappedBindposes);
            SetMeshBoneWeights(modMesh, remappedBoneWeights);
            RecalculateMeshBounds(modMesh);
            Log::InfoFmt("[ModAsset] Patched mod mesh skinning to original order: %s renderer=%zu matchedBones=%zu originalBones=%zu modBones=%zu boneWeights=%zu remappedIndices=%zu remappedBindposes=%zu bindposeMode=%s originalRoot=\"%s\" modRoot=\"%s\" droppedInfluences=%zu fallbackVertices=%zu fallbackBoneIndex=%d maxModBoneIndex=%d maxOriginalBoneIndex=%d bindposes=%zu",
                sourceName.c_str(),
                rendererIndex,
                matchedBones,
                static_cast<size_t>(originalBones->max_length),
                static_cast<size_t>(modBones->max_length),
                static_cast<size_t>(modBoneWeights->max_length),
                remappedIndices,
                remappedBindposeCount,
                bindposeMode,
                originalRootName.c_str(),
                modRootName.c_str(),
                droppedInfluences,
                fallbackVertices,
                fallbackBoneIndex,
                maxModBoneIndex,
                maxOriginalBoneIndex,
                static_cast<size_t>(remappedBindposes->max_length));
            Log::InfoFmt("[ModAsset] Weighted bone diagnostics: %s renderer=%zu modTop=[%s] originalTop=[%s]",
                sourceName.c_str(),
                rendererIndex,
                FormatTopBoneWeightStats(modBoneWeightTotals, modBones, 16).c_str(),
                FormatTopBoneWeightStats(originalBoneWeightTotals, originalBones, 16).c_str());
            return matchedBones > 0;
        }

        void LogSkinnedMeshRendererDiagnostics(const std::string& sourceName, const size_t rendererIndex,
            void* originalRenderer, void* modRenderer, void* originalMesh, void* modMesh, const char* stage) {
            const auto originalBones = GetSkinnedMeshRendererBones(originalRenderer);
            const auto modBones = GetSkinnedMeshRendererBones(modRenderer);
            const auto originalBindposes = GetMeshBindposes(originalMesh);
            const auto modBindposes = GetMeshBindposes(modMesh);
            const auto originalRootBone = GetSkinnedMeshRendererRootBone(originalRenderer);
            const auto modRootBone = GetSkinnedMeshRendererRootBone(modRenderer);
            Log::InfoFmt("[ModAsset] Mesh diagnostics %s: %s renderer=%zu originalRenderer=\"%s\" modRenderer=\"%s\" originalMesh=\"%s\" modMesh=\"%s\" originalVertices=%d modVertices=%d originalBones=%zu modBones=%zu originalBindposes=%zu modBindposes=%zu originalRoot=\"%s\" modRoot=\"%s\"",
                stage,
                sourceName.c_str(),
                rendererIndex,
                GetUnityObjectNameString(originalRenderer).c_str(),
                GetUnityObjectNameString(modRenderer).c_str(),
                GetUnityObjectNameString(originalMesh).c_str(),
                GetUnityObjectNameString(modMesh).c_str(),
                GetMeshVertexCount(originalMesh),
                GetMeshVertexCount(modMesh),
                originalBones ? static_cast<size_t>(originalBones->max_length) : 0,
                modBones ? static_cast<size_t>(modBones->max_length) : 0,
                originalBindposes ? static_cast<size_t>(originalBindposes->max_length) : 0,
                modBindposes ? static_cast<size_t>(modBindposes->max_length) : 0,
                GetUnityObjectNameString(originalRootBone).c_str(),
                GetUnityObjectNameString(modRootBone).c_str());
        }

        std::optional<size_t> FindRendererIndexByName(const std::vector<void*>& renderers,
            const std::string& rendererName,
            const std::unordered_set<size_t>* usedIndices = nullptr) {
            if (rendererName.empty()) return std::nullopt;

            for (size_t i = 0; i < renderers.size(); ++i) {
                if (usedIndices && usedIndices->contains(i)) continue;
                if (GetUnityObjectNameString(renderers[i]) == rendererName) return i;
            }
            return std::nullopt;
        }

        std::vector<LocalModRendererPair> BuildRendererPairs(const std::vector<void*>& originalRenderers,
            const std::vector<void*>& modRenderers,
            const LocalModAssetReplacement& replacement) {
            std::vector<LocalModRendererPair> pairs;
            std::unordered_set<size_t> usedOriginalIndices;
            std::unordered_set<size_t> usedModIndices;

            const auto addPair = [&](const size_t originalIndex, const size_t modIndex) {
                if (originalIndex >= originalRenderers.size() || modIndex >= modRenderers.size()) return;
                if (usedOriginalIndices.contains(originalIndex) || usedModIndices.contains(modIndex)) return;
                pairs.emplace_back(LocalModRendererPair{ originalRenderers[originalIndex], modRenderers[modIndex], originalIndex, modIndex });
                usedOriginalIndices.emplace(originalIndex);
                usedModIndices.emplace(modIndex);
            };

            if (!replacement.rendererRules.empty()) {
                for (const auto& rule : replacement.rendererRules) {
                    auto originalIndex = FindRendererIndexByName(originalRenderers, rule.targetRenderer, &usedOriginalIndices);
                    auto modIndex = FindRendererIndexByName(modRenderers, rule.modRenderer, &usedModIndices);
                    if (!originalIndex && originalRenderers.size() == 1 && !usedOriginalIndices.contains(0)) {
                        originalIndex = 0;
                        Log::WarnFmt("[ModAsset] Renderer rule target not found, fallback to only original renderer: %s rendererId=\"%s\" targetRenderer=\"%s\" actual=\"%s\"",
                            replacement.sourceName.c_str(),
                            rule.rendererId.c_str(),
                            rule.targetRenderer.c_str(),
                            GetUnityObjectNameString(originalRenderers[0]).c_str());
                    }
                    if (!modIndex && modRenderers.size() == 1 && !usedModIndices.contains(0)) {
                        modIndex = 0;
                        Log::WarnFmt("[ModAsset] Renderer rule mod not found, fallback to only mod renderer: %s rendererId=\"%s\" modRenderer=\"%s\" actual=\"%s\"",
                            replacement.sourceName.c_str(),
                            rule.rendererId.c_str(),
                            rule.modRenderer.c_str(),
                            GetUnityObjectNameString(modRenderers[0]).c_str());
                    }
                    if (originalIndex && modIndex) {
                        addPair(*originalIndex, *modIndex);
                        continue;
                    }

                    Log::ErrorFmt("[ModAsset] Renderer rule pair not found: %s rendererId=\"%s\" targetRenderer=\"%s\" modRenderer=\"%s\" originalRenderers=%zu modRenderers=%zu",
                        replacement.sourceName.c_str(),
                        rule.rendererId.c_str(),
                        rule.targetRenderer.c_str(),
                        rule.modRenderer.c_str(),
                        originalRenderers.size(),
                        modRenderers.size());
                }
                return pairs;
            }

            if (!replacement.rendererName.empty()) {
                auto originalIndex = FindRendererIndexByName(originalRenderers, replacement.rendererName);
                auto modIndex = FindRendererIndexByName(modRenderers, replacement.rendererName);

                if (!originalIndex && originalRenderers.size() == 1) {
                    originalIndex = 0;
                    Log::WarnFmt("[ModAsset] Original rendererName not found, fallback to only original renderer: %s rendererName=\"%s\" actual=\"%s\"",
                        replacement.sourceName.c_str(), replacement.rendererName.c_str(), GetUnityObjectNameString(originalRenderers[0]).c_str());
                }
                if (!modIndex && modRenderers.size() == 1) {
                    modIndex = 0;
                    Log::WarnFmt("[ModAsset] Mod rendererName not found, fallback to only mod renderer: %s rendererName=\"%s\" actual=\"%s\"",
                        replacement.sourceName.c_str(), replacement.rendererName.c_str(), GetUnityObjectNameString(modRenderers[0]).c_str());
                }
                if (originalIndex && modIndex) addPair(*originalIndex, *modIndex);
                else {
                    Log::ErrorFmt("[ModAsset] RendererName pair not found: %s rendererName=\"%s\" originalRenderers=%zu modRenderers=%zu",
                        replacement.sourceName.c_str(), replacement.rendererName.c_str(), originalRenderers.size(), modRenderers.size());
                }
                return pairs;
            }

            for (size_t originalIndex = 0; originalIndex < originalRenderers.size(); ++originalIndex) {
                const auto originalName = GetUnityObjectNameString(originalRenderers[originalIndex]);
                if (originalName.empty()) continue;
                if (const auto modIndex = FindRendererIndexByName(modRenderers, originalName, &usedModIndices)) {
                    addPair(originalIndex, *modIndex);
                }
            }

            size_t originalIndex = 0;
            size_t modIndex = 0;
            while (originalIndex < originalRenderers.size() && modIndex < modRenderers.size()) {
                while (originalIndex < originalRenderers.size() && usedOriginalIndices.contains(originalIndex)) ++originalIndex;
                while (modIndex < modRenderers.size() && usedModIndices.contains(modIndex)) ++modIndex;
                if (originalIndex < originalRenderers.size() && modIndex < modRenderers.size()) {
                    addPair(originalIndex, modIndex);
                    ++originalIndex;
                    ++modIndex;
                }
            }
            return pairs;
        }

        bool ApplyMaterialTextureReplacements(void* renderer, void* materialsObject,
            const LocalModAssetReplacement& replacement, const size_t rendererIndex) {
            const auto materials = reinterpret_cast<UnityArray<void*>*>(materialsObject);
            if (!materials) return false;

            static auto Material_SetTexture = reinterpret_cast<void (*)(void*, Il2cppString*, void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Material",
                    "SetTexture", { "System.String", "UnityEngine.Texture" }));
            if (!Material_SetTexture) {
                Log::Error("[ModAsset] Cannot resolve Material.SetTexture.");
                return false;
            }

            const auto activeRendererName = GetUnityObjectNameString(renderer);
            size_t applied = 0;
            for (const auto& textureReplacement : replacement.materialTextures) {
                if (!textureReplacement.rendererName.empty()
                    && !activeRendererName.empty()
                    && textureReplacement.rendererName != activeRendererName) {
                    continue;
                }
                if (textureReplacement.materialSlot < 0
                    || static_cast<std::uintptr_t>(textureReplacement.materialSlot) >= materials->max_length) {
                    continue;
                }

                const auto textureAsset = LoadLocalModAssetFromBundle(
                    replacement.bundleHandle,
                    replacement.bundlePath,
                    textureReplacement.assetName,
                    textureReplacement.typeName);
                if (!textureAsset) {
                    Log::ErrorFmt("[ModAsset] Material texture load failed: %s property=%s",
                        textureReplacement.assetName.c_str(),
                        textureReplacement.propertyName.c_str());
                    continue;
                }

                const auto material = materials->At(static_cast<unsigned int>(textureReplacement.materialSlot));
                if (!material) continue;
                Material_SetTexture(material, Il2cppString::New(textureReplacement.propertyName), textureAsset);
                ++applied;
                Log::InfoFmt("[ModAsset] Applied material texture: %s renderer=%zu rendererName=\"%s\" slot=%d property=%s texture=%s result=%p",
                    replacement.sourceName.c_str(),
                    rendererIndex,
                    activeRendererName.c_str(),
                    textureReplacement.materialSlot,
                    textureReplacement.propertyName.c_str(),
                    textureReplacement.assetName.c_str(),
                    textureAsset);
            }

            if (applied > 0) {
                Log::InfoFmt("[ModAsset] Material texture replacement finished: %s renderer=%zu applied=%zu",
                    replacement.sourceName.c_str(), rendererIndex, applied);
            }
            return applied > 0;
        }

        bool ApplyMaterialSlotCopies(void* renderer, void* materialsObject, void (*setSharedMaterials)(void*, void*),
            const LocalModAssetReplacement& replacement, const size_t rendererIndex) {
            const auto materials = reinterpret_cast<UnityArray<void*>*>(materialsObject);
            if (!renderer || !materials || !setSharedMaterials || replacement.materialCopies.empty()) {
                return false;
            }

            const auto activeRendererName = GetUnityObjectNameString(renderer);
            size_t applied = 0;
            for (const auto& materialCopy : replacement.materialCopies) {
                if (!materialCopy.rendererName.empty()
                    && !activeRendererName.empty()
                    && materialCopy.rendererName != activeRendererName) {
                    continue;
                }
                if (materialCopy.fromSlot < 0 || materialCopy.toSlot < 0
                    || static_cast<std::uintptr_t>(materialCopy.fromSlot) >= materials->max_length
                    || static_cast<std::uintptr_t>(materialCopy.toSlot) >= materials->max_length) {
                    Log::WarnFmt("[ModAsset] Material slot copy skipped out of range: %s renderer=%zu rendererName=\"%s\" from=%d to=%d materialCount=%zu",
                        replacement.sourceName.c_str(),
                        rendererIndex,
                        activeRendererName.c_str(),
                        materialCopy.fromSlot,
                        materialCopy.toSlot,
                        static_cast<size_t>(materials->max_length));
                    continue;
                }

                const auto sourceMaterial = materials->At(static_cast<unsigned int>(materialCopy.fromSlot));
                if (!sourceMaterial) {
                    Log::WarnFmt("[ModAsset] Material slot copy skipped null source: %s renderer=%zu rendererName=\"%s\" from=%d to=%d",
                        replacement.sourceName.c_str(),
                        rendererIndex,
                        activeRendererName.c_str(),
                        materialCopy.fromSlot,
                        materialCopy.toSlot);
                    continue;
                }

                materials->At(static_cast<unsigned int>(materialCopy.toSlot)) = sourceMaterial;
                ++applied;
                Log::InfoFmt("[ModAsset] Copied material slot: %s renderer=%zu rendererName=\"%s\" from=%d to=%d material=\"%s\"",
                    replacement.sourceName.c_str(),
                    rendererIndex,
                    activeRendererName.c_str(),
                    materialCopy.fromSlot,
                    materialCopy.toSlot,
                    GetUnityObjectNameString(sourceMaterial).c_str());
            }

            if (applied > 0) {
                setSharedMaterials(renderer, materialsObject);
                Log::InfoFmt("[ModAsset] Material slot copy finished: %s renderer=%zu applied=%zu",
                    replacement.sourceName.c_str(), rendererIndex, applied);
                return true;
            }
            return false;
        }

        bool MaterialHasProperty(void* material, const std::string& propertyName) {
            static auto Material_HasProperty = reinterpret_cast<bool (*)(void*, Il2cppString*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Material",
                    "HasProperty", { "System.String" }));
            return !Material_HasProperty || Material_HasProperty(material, Il2cppString::New(propertyName));
        }

        bool ApplyMaterialColorReplacements(void* renderer, void* materialsObject,
            const LocalModAssetReplacement& replacement, const size_t rendererIndex) {
            const auto materials = reinterpret_cast<UnityArray<void*>*>(materialsObject);
            if (!materials || replacement.materialColors.empty()) return false;

            static auto Material_SetColor = reinterpret_cast<void (*)(void*, Il2cppString*, LocalModUnityColor)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Material",
                    "SetColor", { "System.String", "UnityEngine.Color" }));
            if (!Material_SetColor) {
                Log::Error("[ModAsset] Cannot resolve Material.SetColor.");
                return false;
            }

            const auto activeRendererName = GetUnityObjectNameString(renderer);
            size_t applied = 0;
            for (const auto& colorReplacement : replacement.materialColors) {
                if (!colorReplacement.rendererName.empty()
                    && !activeRendererName.empty()
                    && colorReplacement.rendererName != activeRendererName) {
                    continue;
                }
                if (colorReplacement.materialSlot < 0
                    || static_cast<std::uintptr_t>(colorReplacement.materialSlot) >= materials->max_length) {
                    continue;
                }

                const auto material = materials->At(static_cast<unsigned int>(colorReplacement.materialSlot));
                if (!material || !MaterialHasProperty(material, colorReplacement.propertyName)) continue;
                Material_SetColor(material, Il2cppString::New(colorReplacement.propertyName), LocalModUnityColor{
                    colorReplacement.r,
                    colorReplacement.g,
                    colorReplacement.b,
                    colorReplacement.a,
                });
                ++applied;
                Log::InfoFmt("[ModAsset] Applied material color: %s renderer=%zu rendererName=\"%s\" slot=%d property=%s value=(%.3f,%.3f,%.3f,%.3f)",
                    replacement.sourceName.c_str(),
                    rendererIndex,
                    activeRendererName.c_str(),
                    colorReplacement.materialSlot,
                    colorReplacement.propertyName.c_str(),
                    colorReplacement.r,
                    colorReplacement.g,
                    colorReplacement.b,
                    colorReplacement.a);
            }

            if (applied > 0) {
                Log::InfoFmt("[ModAsset] Material color replacement finished: %s renderer=%zu applied=%zu",
                    replacement.sourceName.c_str(), rendererIndex, applied);
            }
            return applied > 0;
        }

        bool ApplyMaterialFloatReplacements(void* renderer, void* materialsObject,
            const LocalModAssetReplacement& replacement, const size_t rendererIndex) {
            const auto materials = reinterpret_cast<UnityArray<void*>*>(materialsObject);
            if (!materials || replacement.materialFloats.empty()) return false;

            static auto Material_SetFloat = reinterpret_cast<void (*)(void*, Il2cppString*, float)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Material",
                    "SetFloat", { "System.String", "System.Single" }));
            if (!Material_SetFloat) {
                Log::Error("[ModAsset] Cannot resolve Material.SetFloat.");
                return false;
            }

            const auto activeRendererName = GetUnityObjectNameString(renderer);
            size_t applied = 0;
            for (const auto& floatReplacement : replacement.materialFloats) {
                if (!floatReplacement.rendererName.empty()
                    && !activeRendererName.empty()
                    && floatReplacement.rendererName != activeRendererName) {
                    continue;
                }
                if (floatReplacement.materialSlot < 0
                    || static_cast<std::uintptr_t>(floatReplacement.materialSlot) >= materials->max_length) {
                    continue;
                }

                const auto material = materials->At(static_cast<unsigned int>(floatReplacement.materialSlot));
                if (!material || !MaterialHasProperty(material, floatReplacement.propertyName)) continue;
                Material_SetFloat(material, Il2cppString::New(floatReplacement.propertyName), floatReplacement.value);
                ++applied;
                Log::InfoFmt("[ModAsset] Applied material float: %s renderer=%zu rendererName=\"%s\" slot=%d property=%s value=%.3f",
                    replacement.sourceName.c_str(),
                    rendererIndex,
                    activeRendererName.c_str(),
                    floatReplacement.materialSlot,
                    floatReplacement.propertyName.c_str(),
                    floatReplacement.value);
            }

            if (applied > 0) {
                Log::InfoFmt("[ModAsset] Material float replacement finished: %s renderer=%zu applied=%zu",
                    replacement.sourceName.c_str(), rendererIndex, applied);
            }
            return applied > 0;
        }

        nlohmann::json DumpMaterial(void* material) {
            nlohmann::json result;
            result["name"] = GetUnityObjectNameString(material);

            static auto Material_get_shader = reinterpret_cast<void* (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Material", "get_shader"));
            const auto shader = material && Material_get_shader ? Material_get_shader(material) : nullptr;
            result["shader"] = GetUnityObjectNameString(shader);
            result["properties"] = nlohmann::json::array();

            static auto Shader_GetPropertyCount = reinterpret_cast<int (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Shader", "GetPropertyCount"));
            static auto Shader_GetPropertyName = reinterpret_cast<Il2cppString * (*)(void*, int)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Shader", "GetPropertyName", { "System.Int32" }));
            if (shader && Shader_GetPropertyCount && Shader_GetPropertyName) {
                const auto count = Shader_GetPropertyCount(shader);
                for (int i = 0; i < count; ++i) {
                    if (const auto propertyName = Shader_GetPropertyName(shader, i)) {
                        result["properties"].push_back(propertyName->ToString());
                    }
                }
            }
            return result;
        }

        void DumpSourceProfileIfNeeded(const std::string& sourceName, void* originalGameObject) {
            const auto profileKey = NormalizeAssetName(sourceName);
            if (g_dumpedProfiles.contains(profileKey)) return;
            g_dumpedProfiles.emplace(profileKey);

            const auto skinnedMeshRendererClass = Il2cppUtils::GetClass(
                "UnityEngine.CoreModule.dll", "UnityEngine", "SkinnedMeshRenderer");
            if (!skinnedMeshRendererClass || !originalGameObject) return;

            auto renderers = reinterpret_cast<UnityResolve::UnityType::GameObject*>(originalGameObject)
                ->GetComponentsInChildren<void*>(skinnedMeshRendererClass, true);
            static auto SkinnedMeshRenderer_get_sharedMesh = reinterpret_cast<void* (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "SkinnedMeshRenderer", "get_sharedMesh"));
            static auto Renderer_get_sharedMaterials = reinterpret_cast<void* (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Renderer", "get_sharedMaterials"));

            nlohmann::json profile;
            profile["schemaVersion"] = 1;
            profile["source"] = sourceName;
            profile["part"] = InferPartFromAssetName(sourceName);
            profile["renderers"] = nlohmann::json::array();

            for (size_t rendererIndex = 0; rendererIndex < renderers.size(); ++rendererIndex) {
                const auto renderer = renderers[rendererIndex];
                const auto mesh = SkinnedMeshRenderer_get_sharedMesh ? SkinnedMeshRenderer_get_sharedMesh(renderer) : nullptr;
                const auto bones = GetSkinnedMeshRendererBones(renderer);
                const auto rootBone = GetSkinnedMeshRendererRootBone(renderer);

                nlohmann::json rendererJson;
                rendererJson["index"] = rendererIndex;
                rendererJson["name"] = GetUnityObjectNameString(renderer);
                rendererJson["type"] = "SkinnedMeshRenderer";
                rendererJson["rootBone"] = GetUnityObjectNameString(rootBone);
                rendererJson["mesh"] = {
                    {"name", GetUnityObjectNameString(mesh)},
                    {"vertexCount", GetMeshVertexCount(mesh)},
                    {"subMeshCount", GetMeshIntProperty(mesh, "get_subMeshCount")},
                    {"blendShapeCount", GetMeshIntProperty(mesh, "get_blendShapeCount")}
                };
                rendererJson["bones"] = nlohmann::json::array();
                if (bones) {
                    for (std::uintptr_t i = 0; i < bones->max_length; ++i) {
                        rendererJson["bones"].push_back(GetUnityObjectNameString(bones->At(static_cast<unsigned int>(i))));
                    }
                }

                rendererJson["materials"] = nlohmann::json::array();
                const auto materials = Renderer_get_sharedMaterials
                    ? reinterpret_cast<UnityArray<void*>*>(Renderer_get_sharedMaterials(renderer))
                    : nullptr;
                if (materials) {
                    for (std::uintptr_t i = 0; i < materials->max_length; ++i) {
                        auto materialJson = DumpMaterial(materials->At(static_cast<unsigned int>(i)));
                        materialJson["slot"] = i;
                        rendererJson["materials"].push_back(materialJson);
                    }
                }

                profile["renderers"].push_back(rendererJson);
            }

            std::error_code ec;
            const auto profileDir = std::filesystem::path("./gakumas-local/profiles");
            std::filesystem::create_directories(profileDir, ec);
            const auto outputPath = profileDir / (SanitizeFileName(sourceName) + ".profile.json");
            std::ofstream output(outputPath);
            if (!output.is_open()) {
                Log::ErrorFmt("[ModAsset] Cannot write source profile: %s", outputPath.string().c_str());
                return;
            }
            output << profile.dump(2);
            Log::InfoFmt("[ModAsset] Source profile dumped: %s renderers=%zu",
                outputPath.string().c_str(),
                renderers.size());
        }

        bool ApplySkinnedMeshReplacement(void* originalGameObject, void* modGameObject,
            const LocalModAssetReplacement& replacement) {
            if (!originalGameObject || !modGameObject) return false;
            const auto& sourceName = replacement.sourceName;

            DumpSourceProfileIfNeeded(sourceName, originalGameObject);

            const auto skinnedMeshRendererClass = Il2cppUtils::GetClass(
                "UnityEngine.CoreModule.dll", "UnityEngine", "SkinnedMeshRenderer");
            if (!skinnedMeshRendererClass) return false;

            auto originalRenderers = reinterpret_cast<UnityResolve::UnityType::GameObject*>(originalGameObject)
                ->GetComponentsInChildren<void*>(skinnedMeshRendererClass, true);
            auto modRenderers = reinterpret_cast<UnityResolve::UnityType::GameObject*>(modGameObject)
                ->GetComponentsInChildren<void*>(skinnedMeshRendererClass, true);

            if (originalRenderers.empty() || modRenderers.empty()) {
                Log::ErrorFmt("[ModAsset] SkinnedMeshRenderer not found: %s original=%zu replacement=%zu",
                    sourceName.c_str(), originalRenderers.size(), modRenderers.size());
                return false;
            }

            static auto SkinnedMeshRenderer_get_sharedMesh = reinterpret_cast<void* (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "SkinnedMeshRenderer", "get_sharedMesh"));
            static auto SkinnedMeshRenderer_set_sharedMesh = reinterpret_cast<void (*)(void*, void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "SkinnedMeshRenderer", "set_sharedMesh"));
            static auto Renderer_get_sharedMaterials = reinterpret_cast<void* (*)(void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Renderer", "get_sharedMaterials"));
            static auto Renderer_set_sharedMaterials = reinterpret_cast<void (*)(void*, void*)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "Renderer", "set_sharedMaterials"));
            static auto SkinnedMeshRenderer_set_updateWhenOffscreen = reinterpret_cast<void (*)(void*, bool)>(
                Il2cppUtils::GetMethodPointer("UnityEngine.CoreModule.dll", "UnityEngine", "SkinnedMeshRenderer", "set_updateWhenOffscreen"));

            if (!SkinnedMeshRenderer_get_sharedMesh || !SkinnedMeshRenderer_set_sharedMesh) {
                Log::Error("[ModAsset] Cannot resolve SkinnedMeshRenderer mesh accessors.");
                return false;
            }

            const auto rendererPairs = BuildRendererPairs(originalRenderers, modRenderers, replacement);
            size_t meshApplied = 0;
            size_t textureApplied = 0;
            size_t skippedMeshes = 0;

            for (size_t pairIndex = 0; pairIndex < rendererPairs.size(); ++pairIndex) {
                const auto& pair = rendererPairs[pairIndex];
                const auto originalMesh = SkinnedMeshRenderer_get_sharedMesh(pair.originalRenderer);
                const auto sourceModMesh = SkinnedMeshRenderer_get_sharedMesh(pair.modRenderer);
                const auto originalMaterials = Renderer_get_sharedMaterials ? Renderer_get_sharedMaterials(pair.originalRenderer) : nullptr;
                const auto modMaterials = Renderer_get_sharedMaterials ? Renderer_get_sharedMaterials(pair.modRenderer) : nullptr;
                void* appliedMesh = nullptr;

                LogSkinnedMeshRendererDiagnostics(sourceName, pair.originalIndex, pair.originalRenderer, pair.modRenderer,
                    originalMesh, sourceModMesh, "before");

                if (sourceModMesh) {
                    const auto clonedModMesh = CloneUnityObject(sourceModMesh, sourceName, pair.originalIndex);
                    const auto transformOk = clonedModMesh
                        && TransformModMeshVerticesToOriginalRendererSpace(pair.originalRenderer, pair.modRenderer,
                            clonedModMesh, sourceName, pair.originalIndex);
                    const auto skinningOk = transformOk
                        && PatchModMeshSkinningToOriginalOrder(pair.originalRenderer, pair.modRenderer, originalMesh,
                            clonedModMesh, replacement, sourceName, pair.originalIndex);

                    if (transformOk && skinningOk) {
                        SkinnedMeshRenderer_set_sharedMesh(pair.originalRenderer, clonedModMesh);
                        appliedMesh = clonedModMesh;
                        ++meshApplied;
                    }
                    else {
                        ++skippedMeshes;
                        Log::ErrorFmt("[ModAsset] Skipped mesh replacement because patch failed: %s renderer=%zu originalRenderer=\"%s\" modRenderer=\"%s\" sourceMesh=%p clonedMesh=%p transformOk=%d skinningOk=%d",
                            sourceName.c_str(),
                            pair.originalIndex,
                            GetUnityObjectNameString(pair.originalRenderer).c_str(),
                            GetUnityObjectNameString(pair.modRenderer).c_str(),
                            sourceModMesh,
                            clonedModMesh,
                            transformOk ? 1 : 0,
                            skinningOk ? 1 : 0);
                    }
                }
                else {
                    ++skippedMeshes;
                    Log::ErrorFmt("[ModAsset] Replacement renderer has no mesh: %s renderer=%zu modRenderer=\"%s\"",
                        sourceName.c_str(),
                        pair.originalIndex,
                        GetUnityObjectNameString(pair.modRenderer).c_str());
                }

                if (replacement.replaceMaterials && modMaterials && Renderer_set_sharedMaterials) {
                    Renderer_set_sharedMaterials(pair.originalRenderer, modMaterials);
                }
                const auto activeMaterials = replacement.replaceMaterials && modMaterials ? modMaterials : originalMaterials;
                ApplyMaterialSlotCopies(pair.originalRenderer, activeMaterials, Renderer_set_sharedMaterials,
                    replacement, pair.originalIndex);
                ApplyMaterialColorReplacements(pair.originalRenderer, activeMaterials, replacement, pair.originalIndex);
                ApplyMaterialFloatReplacements(pair.originalRenderer, activeMaterials, replacement, pair.originalIndex);
                if (ApplyMaterialTextureReplacements(pair.originalRenderer, activeMaterials, replacement, pair.originalIndex)) {
                    ++textureApplied;
                }
                if (SkinnedMeshRenderer_set_updateWhenOffscreen) {
                    SkinnedMeshRenderer_set_updateWhenOffscreen(pair.originalRenderer, true);
                }

                const auto currentOriginalMesh = SkinnedMeshRenderer_get_sharedMesh(pair.originalRenderer);
                LogSkinnedMeshRendererDiagnostics(sourceName, pair.originalIndex, pair.originalRenderer, pair.modRenderer,
                    currentOriginalMesh, appliedMesh ? appliedMesh : sourceModMesh, "after");

                Log::InfoFmt("[ModAsset] SkinnedMeshRenderer pair processed: %s pair=%zu originalRenderer=%zu modRenderer=%zu originalName=\"%s\" modName=\"%s\" meshApplied=%d materials=%p replaceMaterials=%d",
                    sourceName.c_str(),
                    pairIndex,
                    pair.originalIndex,
                    pair.modIndex,
                    GetUnityObjectNameString(pair.originalRenderer).c_str(),
                    GetUnityObjectNameString(pair.modRenderer).c_str(),
                    appliedMesh ? 1 : 0,
                    modMaterials,
                    replacement.replaceMaterials ? 1 : 0);
            }

            Log::InfoFmt("[ModAsset] SkinnedMeshRenderer replacement finished: %s originalRenderers=%zu replacementRenderers=%zu pairs=%zu meshApplied=%zu textureApplied=%zu skippedMeshes=%zu",
                sourceName.c_str(),
                originalRenderers.size(),
                modRenderers.size(),
                rendererPairs.size(),
                meshApplied,
                textureApplied,
                skippedMeshes);
            return meshApplied > 0 || textureApplied > 0;
        }

        void* ReplaceLocalModAssetIfNeeded(void* originalResult, const std::string& sourceName) {
            const auto replacement = FindLocalModAssetReplacement(sourceName);
            if (!replacement) return originalResult;

            Log::InfoFmt("[ModAsset] Replacement hit: %s -> %s mod=%s part=%s priority=%d",
                sourceName.c_str(),
                replacement->assetName.c_str(),
                replacement->modName.c_str(),
                replacement->part.c_str(),
                replacement->priority);
            const auto modAsset = LoadLocalModReplacementAsset(*replacement);
            if (!modAsset) {
                Log::ErrorFmt("[ModAsset] Replacement failed, keeping original asset: %s", sourceName.c_str());
                return originalResult;
            }

            if (replacement->attachToOriginal) {
                g_nativeChainValidation = true;
                replacement->attachAsset = modAsset;
                replacement->attachSourceMeshes.clear();
                const auto originalGo = reinterpret_cast<UnityResolve::UnityType::GameObject*>(originalResult);
                const auto rendererClass = Il2cppUtils::GetClass(
                    "UnityEngine.CoreModule.dll", "UnityEngine", "SkinnedMeshRenderer");
                if (originalGo && rendererClass) {
                    for (const auto renderer : originalGo->GetComponentsInChildren<void*>(rendererClass, true)) {
                        if (const auto mesh = GetSkinnedMeshRendererSharedMesh(renderer))
                            replacement->attachSourceMeshes.emplace_back(mesh);
                    }
                }
                Log::InfoFmt("[ModAsset] Armed native chain subtree for live actor attach: %s original=%p originalName=%s subtree=%p sourceMeshes=%zu",
                    sourceName.c_str(), originalResult, GetUnityObjectNameString(originalResult).c_str(), modAsset,
                    replacement->attachSourceMeshes.size());
                return originalResult;
            }

            if (replacement->replaceWholeObject) {
                g_nativeChainValidation = true;
                Log::InfoFmt("[ModAsset] Replaced asset by whole-object validation path: %s original=%p replacement=%p",
                    sourceName.c_str(), originalResult, modAsset);
                // Prefab-side deserialization check: did il2cpp deserialize our chain +
                // dynamic bones WITH fields (rootBones populated, damping non-zero)?
                // Answers "component identity + field data OK" without waiting for
                // scene instantiation.
                if (const auto go = reinterpret_cast<UnityResolve::UnityType::GameObject*>(modAsset)) {
                    const auto chainClass = FindClassByName("ActorSwingChain");
                    const auto boneClass = FindClassByName("ActorSwingDynamicBone");
                    if (chainClass && boneClass) {
                        const auto chains = go->GetComponentsInChildren<void*>(chainClass, true);
                        const auto bones = go->GetComponentsInChildren<void*>(boneClass, true);
                        int rootBonesSize = -1;
                        if (!chains.empty()) {
                            if (const auto rb = chainClass->GetValue<UnityResolve::UnityType::List<void*>*>(chains.front(), "rootBones"))
                                rootBonesSize = rb->size;
                        }
                        float damping = -1.f;
                        if (!bones.empty()) {
                            if (const auto f = boneClass->Get<UnityResolve::Field>("damping"))
                                damping = *reinterpret_cast<float*>(reinterpret_cast<std::uintptr_t>(bones.front()) + f->offset);
                        }
                        Log::InfoFmt("[ModAsset] whole-object prefab check: chains=%zu dynamicBones=%zu rootBones=%d damping=%.3f",
                            chains.size(), bones.size(), rootBonesSize, damping);
                    }
                }
                return modAsset;
            }

            if (ToLowerAscii(replacement->typeName) == "gameobject") {
                if (ApplySkinnedMeshReplacement(originalResult, modAsset, *replacement)) {
                    Log::InfoFmt("[ModAsset] Replaced asset in-place: %s original=%p replacementSource=%p",
                        sourceName.c_str(), originalResult, modAsset);
                    return originalResult;
                }

                Log::ErrorFmt("[ModAsset] In-place replacement failed, keeping original asset: %s", sourceName.c_str());
                return originalResult;
            }

            Log::InfoFmt("[ModAsset] Replaced asset by return value: %s original=%p replacement=%p replacementType=%s",
                sourceName.c_str(), originalResult, modAsset, GetUnityObjectClassName(modAsset));
            return modAsset;
        }

        void* AssetBundle_LoadAsset_Hook(void* self, Il2cppString* name, void* type) {
            auto result = AssetBundle_LoadAsset_Orig(self, name, type);
            if (name) {
                const auto assetName = name->ToString();
                LogAssetTrace("AssetBundle.LoadAsset_Internal", assetName, result, type);
                result = ReplaceLocalModAssetIfNeeded(result, assetName);
            }
            return result;
        }

        void* AssetBundle_LoadAssetAsync_Hook(void* self, Il2cppString* name, void* type) {
            auto result = AssetBundle_LoadAssetAsync_Orig(self, name, type);
            if (result && name) {
                const auto assetName = name->ToString();
                LogAssetTrace("AssetBundle.LoadAssetAsync_Internal", assetName, result, type);
                std::lock_guard lock(g_historyMutex);
                g_loadHistory.emplace(result, assetName);
            }
            return result;
        }

        std::string TakeRequestName(void* request) {
            std::lock_guard lock(g_historyMutex);
            if (const auto iter = g_loadHistory.find(request); iter != g_loadHistory.end()) {
                auto name = iter->second;
                g_loadHistory.erase(iter);
                return name;
            }
            return {};
        }

        void* AssetBundleRequest_GetResult_Hook(void* self) {
            auto result = AssetBundleRequest_GetResult_Orig(self);
            const auto name = TakeRequestName(self);
            if (!name.empty()) {
                LogAssetTrace("AssetBundleRequest.GetResult", name, result);
                result = ReplaceLocalModAssetIfNeeded(result, name);
            }
            return result;
        }

        void* AssetBundleRequest_get_asset_Hook(void* self) {
            const auto name = TakeRequestName(self);
            auto result = AssetBundleRequest_get_asset_Orig(self);
            if (!name.empty()) {
                LogAssetTrace("AssetBundleRequest.get_asset", name, result);
                result = ReplaceLocalModAssetIfNeeded(result, name);
            }
            return result;
        }

        void* ResolveAssetBundleLoadAssetHookAddress() {
            if (const auto addr = Il2cppUtils::il2cpp_resolve_icall(
                "UnityEngine.AssetBundle::LoadAsset_Internal(System.String,System.Type)")) {
                return addr;
            }
            return Il2cppUtils::GetMethodPointer("UnityEngine.AssetBundleModule.dll", "UnityEngine", "AssetBundle",
                "LoadAsset_Internal", { "System.String", "System.Type" });
        }

        void* ResolveAssetBundleLoadAssetAsyncHookAddress() {
            if (const auto addr = Il2cppUtils::il2cpp_resolve_icall(
                "UnityEngine.AssetBundle::LoadAssetAsync_Internal(System.String,System.Type)")) {
                return addr;
            }
            return Il2cppUtils::GetMethodPointer("UnityEngine.AssetBundleModule.dll", "UnityEngine", "AssetBundle",
                "LoadAssetAsync_Internal", { "System.String", "System.Type" });
        }

        void* ResolveAssetBundleRequestResultHookAddress() {
            if (const auto addr = Il2cppUtils::il2cpp_resolve_icall("UnityEngine.AssetBundleRequest::GetResult()")) {
                return addr;
            }
            return Il2cppUtils::GetMethodPointer("UnityEngine.AssetBundleModule.dll", "UnityEngine", "AssetBundleRequest", "GetResult");
        }

        void* ResolveAssetBundleRequestAssetHookAddress() {
            if (const auto addr = Il2cppUtils::il2cpp_resolve_icall("UnityEngine.AssetBundleRequest::get_asset()")) {
                return addr;
            }
            return Il2cppUtils::GetMethodPointer("UnityEngine.AssetBundleModule.dll", "UnityEngine", "AssetBundleRequest", "get_asset");
        }

        void* ResolveCampusActorAnimationRigRegisterBonesHookAddress() {
            const auto rigClass = FindClassByName("CampusActorAnimationRig");
            const auto method = rigClass
                ? FindMethodByNameAndArgCount(rigClass, "RegisterBones", 1)
                : nullptr;
            return method ? method->function : nullptr;
        }

        template <typename Fn>
        bool InstallHook(const char* name, void* target, void* hook, Fn* original) {
            if (!target) {
                Log::ErrorFmt("[ModAsset] Hook target is null: %s", name);
                return false;
            }
            if (const auto status = MH_CreateHook(target, hook, reinterpret_cast<void**>(original)); status != MH_OK) {
                Log::ErrorFmt("[ModAsset] MH_CreateHook failed: %s status=%s", name, MH_StatusToString(status));
                return false;
            }
            if (const auto status = MH_EnableHook(target); status != MH_OK) {
                Log::ErrorFmt("[ModAsset] MH_EnableHook failed: %s status=%s", name, MH_StatusToString(status));
                return false;
            }
            g_hookTargets.push_back(target);
            Log::InfoFmt("[ModAsset] Hook installed: %s target=%p", name, target);
            return true;
        }

        bool InstallHooks() {
            bool ok = true;
            ok &= InstallHook("AssetBundle.LoadAsset_Internal",
                ResolveAssetBundleLoadAssetHookAddress(),
                reinterpret_cast<void*>(AssetBundle_LoadAsset_Hook),
                &AssetBundle_LoadAsset_Orig);
            ok &= InstallHook("AssetBundle.LoadAssetAsync_Internal",
                ResolveAssetBundleLoadAssetAsyncHookAddress(),
                reinterpret_cast<void*>(AssetBundle_LoadAssetAsync_Hook),
                &AssetBundle_LoadAssetAsync_Orig);
            ok &= InstallHook("AssetBundleRequest.GetResult",
                ResolveAssetBundleRequestResultHookAddress(),
                reinterpret_cast<void*>(AssetBundleRequest_GetResult_Hook),
                &AssetBundleRequest_GetResult_Orig);
            ok &= InstallHook("AssetBundleRequest.get_asset",
                ResolveAssetBundleRequestAssetHookAddress(),
                reinterpret_cast<void*>(AssetBundleRequest_get_asset_Hook),
                &AssetBundleRequest_get_asset_Orig);
            if (const auto target = ResolveCampusActorAnimationRigRegisterBonesHookAddress()) {
                ok &= InstallHook("CampusActorAnimationRig.RegisterBones",
                    target,
                    reinterpret_cast<void*>(CampusActorAnimationRig_RegisterBones_Hook),
                    &CampusActorAnimationRig_RegisterBones_Orig);
            }
            else {
                Log::Warn("[ModAsset] CampusActorAnimationRig.RegisterBones unavailable; ActorSwing data graft disabled.");
            }
            return ok;
        }
    }

    bool Initialize() {
        if (g_initialized.exchange(true)) return true;

        Log::Info("[ModAsset] Standalone mod plugin initializing.");
        HMODULE gameAssembly{};
        for (int i = 0; i < 600 && !gameAssembly; ++i) {
            gameAssembly = GetModuleHandleA("GameAssembly.dll");
            if (!gameAssembly) std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        if (!gameAssembly) {
            Log::Error("[ModAsset] GameAssembly.dll not loaded; mod plugin disabled.");
            return false;
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(1000));
        UnityResolve::Init(gameAssembly, UnityResolve::Mode::Il2Cpp, false);
        if (!AttachIl2cppThread(gameAssembly)) {
            g_initialized = false;
            return false;
        }

        if (const auto status = MH_Initialize(); status != MH_OK && status != MH_ERROR_ALREADY_INITIALIZED) {
            Log::ErrorFmt("[ModAsset] MH_Initialize failed: %s", MH_StatusToString(status));
            g_initialized = false;
            return false;
        }

        const auto hooksOk = InstallHooks();
        LoadLocalModManifests();
        Log::InfoFmt("[ModAsset] Standalone mod plugin initialized. hooksOk=%d replacements=%zu",
            hooksOk ? 1 : 0,
            g_replacementMap.size());
        return hooksOk;
    }

    void Shutdown() {
        if (!g_initialized.exchange(false)) return;
        for (const auto target : g_hookTargets) {
            MH_DisableHook(target);
        }
        g_hookTargets.clear();
        Log::Info("[ModAsset] Standalone mod plugin shutdown.");
    }
}
