#include "runtime.h"

#include <d3d11.h>
#include <mutex>

namespace {
HMODULE real_d3d11 = nullptr;
std::once_flag load_once;

void LoadRealD3D11() {
    real_d3d11 = LoadLibraryExW(L"d3d11.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    RuntimeInitializeOnce();
    RuntimeLog(real_d3d11 ? "System d3d11.dll loaded" : "ERROR: unable to load system d3d11.dll");
}

template <typename T>
T Resolve(const char* name) {
    std::call_once(load_once, LoadRealD3D11);
    return real_d3d11 ? reinterpret_cast<T>(GetProcAddress(real_d3d11, name)) : nullptr;
}
}

extern "C" HRESULT WINAPI D3D11CreateDevice(
    IDXGIAdapter* adapter,
    D3D_DRIVER_TYPE driver_type,
    HMODULE software,
    UINT flags,
    const D3D_FEATURE_LEVEL* feature_levels,
    UINT feature_level_count,
    UINT sdk_version,
    ID3D11Device** device,
    D3D_FEATURE_LEVEL* selected_feature_level,
    ID3D11DeviceContext** immediate_context) {
    using Function = decltype(&D3D11CreateDevice);
    auto function = Resolve<Function>("D3D11CreateDevice");
    if (!function) return E_FAIL;
    return function(adapter, driver_type, software, flags, feature_levels,
                    feature_level_count, sdk_version, device,
                    selected_feature_level, immediate_context);
}

extern "C" HRESULT WINAPI D3D11CreateDeviceAndSwapChain(
    IDXGIAdapter* adapter,
    D3D_DRIVER_TYPE driver_type,
    HMODULE software,
    UINT flags,
    const D3D_FEATURE_LEVEL* feature_levels,
    UINT feature_level_count,
    UINT sdk_version,
    const DXGI_SWAP_CHAIN_DESC* swap_chain_desc,
    IDXGISwapChain** swap_chain,
    ID3D11Device** device,
    D3D_FEATURE_LEVEL* selected_feature_level,
    ID3D11DeviceContext** immediate_context) {
    using Function = decltype(&D3D11CreateDeviceAndSwapChain);
    auto function = Resolve<Function>("D3D11CreateDeviceAndSwapChain");
    if (!function) return E_FAIL;
    return function(adapter, driver_type, software, flags, feature_levels,
                    feature_level_count, sdk_version, swap_chain_desc,
                    swap_chain, device, selected_feature_level,
                    immediate_context);
}
