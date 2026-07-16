#include "ModLog.hpp"
#include "ModRuntime.hpp"

#include <Windows.h>

#include <filesystem>
#include <string>
#include <thread>

namespace {
    void SetGameWorkingDirectory() {
        std::string moduleName;
        moduleName.resize(MAX_PATH);
        moduleName.resize(GetModuleFileNameA(nullptr, moduleName.data(), MAX_PATH));

        const std::filesystem::path exePath(moduleName);
        if (exePath.filename() != "gakumas.exe") {
            GakumasMod::Log::WarnFmt("[ModAsset] Host process is not gakumas.exe: %s",
                exePath.filename().string().c_str());
            return;
        }

        std::error_code ec;
        std::filesystem::current_path(exePath.parent_path(), ec);
        if (ec) {
            GakumasMod::Log::ErrorFmt("[ModAsset] Failed to set working directory: %s",
                ec.message().c_str());
        }
    }
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(module);
        SetGameWorkingDirectory();
        std::thread([] {
            GakumasMod::Runtime::Initialize();
        }).detach();
    }
    else if (reason == DLL_PROCESS_DETACH) {
        GakumasMod::Runtime::Shutdown();
    }
    return TRUE;
}
