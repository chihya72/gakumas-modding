#include "runtime.h"

#include <atomic>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <thread>

namespace {
std::once_flag init_once;
std::mutex log_mutex;

std::filesystem::path LogPath() {
    wchar_t module_path[MAX_PATH]{};
    GetModuleFileNameW(g_runtime_module, module_path, MAX_PATH);
    return std::filesystem::path(module_path).parent_path() / L"gakumasmi-runtime.log";
}
}

void RuntimeLog(const std::string& message) {
    std::lock_guard lock(log_mutex);
    std::ofstream stream(LogPath(), std::ios::app);
    SYSTEMTIME time{};
    GetLocalTime(&time);
    stream << '[' << time.wHour << ':' << time.wMinute << ':' << time.wSecond << "] "
           << message << '\n';
}

void RuntimeInitializeOnce() {
    std::call_once(init_once, [] {
        RuntimeLog("GakumasMI Runtime 0.1.1 initialized");
        wchar_t disabled[8]{};
        if (GetEnvironmentVariableW(L"GAKUMASMI_DIAGNOSTICS", disabled, 8) && disabled[0] == L'0') {
            RuntimeLog("IL2CPP diagnostics disabled by environment");
            return;
        }
        std::thread(RunIl2CppDiagnostics).detach();
    });
}
