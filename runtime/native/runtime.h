#pragma once

#include <windows.h>
#include <string>

extern HMODULE g_runtime_module;

void RuntimeInitializeOnce();
void RuntimeLog(const std::string& message);
void RunIl2CppDiagnostics();
