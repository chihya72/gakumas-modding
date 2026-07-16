#pragma once

#include "ModLog.hpp"
#include "../deps/UnityResolve/UnityResolve.hpp"

#include <string>
#include <vector>

namespace GakumasMod::Il2cppUtils {
    struct Il2CppClassHead {
        const void* image;
        void* gc_desc;
        const char* name;
        const char* namespaze;
    };

    struct Il2CppObject {
        union {
            void* klass;
            void* vtable;
        };
        void* monitor;
    };

    enum Il2CppTypeEnum {
        IL2CPP_TYPE_END = 0x00,
        IL2CPP_TYPE_VOID = 0x01,
        IL2CPP_TYPE_BOOLEAN = 0x02,
        IL2CPP_TYPE_CHAR = 0x03,
        IL2CPP_TYPE_I1 = 0x04,
        IL2CPP_TYPE_U1 = 0x05,
        IL2CPP_TYPE_I2 = 0x06,
        IL2CPP_TYPE_U2 = 0x07,
        IL2CPP_TYPE_I4 = 0x08,
        IL2CPP_TYPE_U4 = 0x09,
        IL2CPP_TYPE_I8 = 0x0a,
        IL2CPP_TYPE_U8 = 0x0b,
        IL2CPP_TYPE_R4 = 0x0c,
        IL2CPP_TYPE_R8 = 0x0d,
        IL2CPP_TYPE_STRING = 0x0e,
        IL2CPP_TYPE_PTR = 0x0f,
        IL2CPP_TYPE_BYREF = 0x10,
        IL2CPP_TYPE_VALUETYPE = 0x11,
        IL2CPP_TYPE_CLASS = 0x12,
        IL2CPP_TYPE_ARRAY = 0x14,
        IL2CPP_TYPE_GENERICINST = 0x15,
        IL2CPP_TYPE_OBJECT = 0x1c,
        IL2CPP_TYPE_SZARRAY = 0x1d,
    };

    struct Il2CppType {
        void* dummy;
        unsigned int attrs : 16;
        Il2CppTypeEnum type : 8;
        unsigned int num_mods : 6;
        unsigned int byref : 1;
        unsigned int pinned : 1;
    };

    struct Il2CppReflectionType {
        Il2CppObject object;
        const Il2CppType* type;
    };

    inline UnityResolve::Class* GetClass(const std::string& assemblyName,
        const std::string& nameSpaceName,
        const std::string& className) {
        const auto assembly = UnityResolve::Get(assemblyName);
        if (!assembly) {
            Log::ErrorFmt("[ModAsset] Assembly not found: %s", assemblyName.c_str());
            return nullptr;
        }

        const auto klass = assembly->Get(className, nameSpaceName);
        if (!klass) {
            Log::ErrorFmt("[ModAsset] Class not found: %s::%s (%s)",
                nameSpaceName.c_str(),
                className.c_str(),
                assemblyName.c_str());
            return nullptr;
        }
        return klass;
    }

    inline UnityResolve::Method* GetMethod(const std::string& assemblyName,
        const std::string& nameSpaceName,
        const std::string& className,
        const std::string& methodName,
        const std::vector<std::string>& args = {}) {
        const auto klass = GetClass(assemblyName, nameSpaceName, className);
        if (!klass) return nullptr;

        const auto method = klass->Get<UnityResolve::Method>(methodName, args);
        if (!method) {
            Log::ErrorFmt("[ModAsset] Method not found: %s::%s.%s",
                nameSpaceName.c_str(),
                className.c_str(),
                methodName.c_str());
            return nullptr;
        }
        return method;
    }

    inline void* GetMethodPointer(const std::string& assemblyName,
        const std::string& nameSpaceName,
        const std::string& className,
        const std::string& methodName,
        const std::vector<std::string>& args = {}) {
        const auto method = GetMethod(assemblyName, nameSpaceName, className, methodName, args);
        return method ? method->function : nullptr;
    }

    inline void* il2cpp_resolve_icall(const char* name) {
        return UnityResolve::Invoke<void*>("il2cpp_resolve_icall", name);
    }

    inline Il2CppClassHead* get_class_from_instance(const void* instance) {
        if (!instance) return nullptr;
        return static_cast<Il2CppClassHead*>(*static_cast<void* const*>(instance));
    }
}
