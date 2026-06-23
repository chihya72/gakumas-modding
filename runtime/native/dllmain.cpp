#include "runtime.h"

HMODULE g_runtime_module = nullptr;

namespace {
DWORD WINAPI RuntimeBootstrap(LPVOID) {
    RuntimeInitializeOnce();
    return 0;
}
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_runtime_module = module;
        DisableThreadLibraryCalls(module);
        // Run outside the loader lock. This also makes the DLL usable through
        // post-launch LoadLibrary injection, without touching the D3D11 chain.
        HANDLE thread = CreateThread(nullptr, 0, RuntimeBootstrap, nullptr, 0, nullptr);
        if (thread) CloseHandle(thread);
    }
    return TRUE;
}
