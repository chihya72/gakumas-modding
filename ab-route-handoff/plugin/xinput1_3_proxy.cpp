#include <Windows.h>
#include <Xinput.h>

#include <string>

namespace {
    HMODULE GetOriginalXInput() {
        static HMODULE module = [] {
            char systemDir[MAX_PATH]{};
            GetSystemDirectoryA(systemDir, MAX_PATH);
            std::string path = std::string(systemDir) + "\\xinput1_3.dll";
            return LoadLibraryA(path.c_str());
        }();
        return module;
    }

    FARPROC ResolveOriginal(const char* name) {
        const auto module = GetOriginalXInput();
        return module ? GetProcAddress(module, name) : nullptr;
    }

    FARPROC ResolveOriginalOrdinal(const WORD ordinal) {
        const auto module = GetOriginalXInput();
        return module ? GetProcAddress(module, MAKEINTRESOURCEA(ordinal)) : nullptr;
    }
}

extern "C" DWORD WINAPI XInputGetState(DWORD dwUserIndex, XINPUT_STATE* pState) noexcept {
    using Fn = DWORD(WINAPI*)(DWORD, XINPUT_STATE*);
    static auto fn = reinterpret_cast<Fn>(ResolveOriginal("XInputGetState"));
    return fn ? fn(dwUserIndex, pState) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" DWORD WINAPI XInputSetState(DWORD dwUserIndex, XINPUT_VIBRATION* pVibration) noexcept {
    using Fn = DWORD(WINAPI*)(DWORD, XINPUT_VIBRATION*);
    static auto fn = reinterpret_cast<Fn>(ResolveOriginal("XInputSetState"));
    return fn ? fn(dwUserIndex, pVibration) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" DWORD WINAPI XInputGetCapabilities(DWORD dwUserIndex, DWORD dwFlags, XINPUT_CAPABILITIES* pCapabilities) noexcept {
    using Fn = DWORD(WINAPI*)(DWORD, DWORD, XINPUT_CAPABILITIES*);
    static auto fn = reinterpret_cast<Fn>(ResolveOriginal("XInputGetCapabilities"));
    return fn ? fn(dwUserIndex, dwFlags, pCapabilities) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" void WINAPI XInputEnable(BOOL enable) noexcept {
    using Fn = void(WINAPI*)(BOOL);
    static auto fn = reinterpret_cast<Fn>(ResolveOriginal("XInputEnable"));
    if (fn) fn(enable);
}

extern "C" DWORD WINAPI XInputGetDSoundAudioDeviceGuids(DWORD dwUserIndex, GUID* pDSoundRenderGuid, GUID* pDSoundCaptureGuid) noexcept {
    using Fn = DWORD(WINAPI*)(DWORD, GUID*, GUID*);
    static auto fn = reinterpret_cast<Fn>(ResolveOriginal("XInputGetDSoundAudioDeviceGuids"));
    return fn ? fn(dwUserIndex, pDSoundRenderGuid, pDSoundCaptureGuid) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" DWORD WINAPI XInputGetBatteryInformation(DWORD dwUserIndex, BYTE devType, XINPUT_BATTERY_INFORMATION* pBatteryInformation) noexcept {
    using Fn = DWORD(WINAPI*)(DWORD, BYTE, XINPUT_BATTERY_INFORMATION*);
    static auto fn = reinterpret_cast<Fn>(ResolveOriginal("XInputGetBatteryInformation"));
    return fn ? fn(dwUserIndex, devType, pBatteryInformation) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" DWORD WINAPI XInputGetKeystroke(DWORD dwUserIndex, DWORD dwReserved, PXINPUT_KEYSTROKE pKeystroke) noexcept {
    using Fn = DWORD(WINAPI*)(DWORD, DWORD, PXINPUT_KEYSTROKE);
    static auto fn = reinterpret_cast<Fn>(ResolveOriginal("XInputGetKeystroke"));
    return fn ? fn(dwUserIndex, dwReserved, pKeystroke) : ERROR_EMPTY;
}

extern "C" DWORD WINAPI XInputGetStateEx(DWORD dwUserIndex, XINPUT_STATE* pState) noexcept {
    using Fn = DWORD(WINAPI*)(DWORD, XINPUT_STATE*);
    static auto fn = reinterpret_cast<Fn>(ResolveOriginalOrdinal(100));
    return fn ? fn(dwUserIndex, pState) : XInputGetState(dwUserIndex, pState);
}
