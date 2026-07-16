#pragma once

#include <string>

namespace GakumasMod::Log {
    void Info(const char* msg);
    void InfoFmt(const char* fmt, ...);
    void Warn(const char* msg);
    void WarnFmt(const char* fmt, ...);
    void Error(const char* msg);
    void ErrorFmt(const char* fmt, ...);
    std::string Format(const char* fmt, ...);
}
