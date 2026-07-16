#include "ModLog.hpp"

#include <Windows.h>

#include <cstdarg>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <mutex>

namespace GakumasMod::Log {
    namespace {
        constexpr const char* kLogPath = "./gakumas-local/mod-plugin.log";

        std::string VFormat(const char* fmt, va_list args) {
            if (!fmt) return {};

            va_list argsCopy;
            va_copy(argsCopy, args);
            const auto size = std::vsnprintf(nullptr, 0, fmt, argsCopy);
            va_end(argsCopy);
            if (size <= 0) return {};

            std::string result(static_cast<size_t>(size) + 1, '\0');
            std::vsnprintf(result.data(), result.size(), fmt, args);
            result.resize(static_cast<size_t>(size));
            return result;
        }

        std::ofstream& Stream() {
            static std::ofstream stream;
            static bool initialized = false;
            if (!initialized) {
                initialized = true;
                std::error_code ec;
                std::filesystem::create_directories("./gakumas-local", ec);
                stream.open(kLogPath, std::ios::app);
            }
            return stream;
        }

        void Write(const char* level, const char* msg) {
            static std::mutex mutex;
            std::lock_guard lock(mutex);

            auto& stream = Stream();
            if (stream.is_open()) {
                stream << "[" << level << "] GakumasMod: " << (msg ? msg : "") << '\n';
                stream.flush();
            }

            char debugLine[4096]{};
            std::snprintf(debugLine, sizeof(debugLine), "[%s] GakumasMod: %s\n", level, msg ? msg : "");
            OutputDebugStringA(debugLine);
        }
    }

    std::string Format(const char* fmt, ...) {
        va_list args;
        va_start(args, fmt);
        auto result = VFormat(fmt, args);
        va_end(args);
        return result;
    }

    void Info(const char* msg) {
        Write("INFO", msg);
    }

    void InfoFmt(const char* fmt, ...) {
        va_list args;
        va_start(args, fmt);
        const auto result = VFormat(fmt, args);
        va_end(args);
        Info(result.c_str());
    }

    void Warn(const char* msg) {
        Write("WARN", msg);
    }

    void WarnFmt(const char* fmt, ...) {
        va_list args;
        va_start(args, fmt);
        const auto result = VFormat(fmt, args);
        va_end(args);
        Warn(result.c_str());
    }

    void Error(const char* msg) {
        Write("ERROR", msg);
    }

    void ErrorFmt(const char* fmt, ...) {
        va_list args;
        va_start(args, fmt);
        const auto result = VFormat(fmt, args);
        va_end(args);
        Error(result.c_str());
    }
}
