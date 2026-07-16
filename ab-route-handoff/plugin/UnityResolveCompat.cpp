#include "ModLog.hpp"

#include <Windows.h>

#include <cstdarg>
#include <cstdio>
#include <string>
#include <string_view>

namespace GakumasMod::UnityResolveCompat {
    void ErrorFmt(const char* fmt, ...) {
        va_list args;
        va_start(args, fmt);
        const auto size = std::vsnprintf(nullptr, 0, fmt, args);
        va_end(args);
        if (size <= 0) {
            GakumasMod::Log::Error(fmt ? fmt : "");
            return;
        }

        std::string result(static_cast<size_t>(size) + 1, '\0');
        va_start(args, fmt);
        std::vsnprintf(result.data(), result.size(), fmt, args);
        va_end(args);
        result.resize(static_cast<size_t>(size));
        GakumasMod::Log::Error(result.c_str());
    }

    std::string ToUTF8(const std::wstring_view& wstr) {
        if (wstr.empty()) return {};
        const auto size = WideCharToMultiByte(
            CP_UTF8,
            0,
            wstr.data(),
            static_cast<int>(wstr.size()),
            nullptr,
            0,
            nullptr,
            nullptr);
        if (size <= 0) return {};

        std::string result(static_cast<size_t>(size), '\0');
        WideCharToMultiByte(
            CP_UTF8,
            0,
            wstr.data(),
            static_cast<int>(wstr.size()),
            result.data(),
            size,
            nullptr,
            nullptr);
        return result;
    }
}
