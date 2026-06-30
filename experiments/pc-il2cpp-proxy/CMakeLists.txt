cmake_minimum_required(VERSION 3.15)
project(gkms_il2cpp_probe CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "Build x64: cmake -A x64 ...")
endif()

# --- MinHook (for the main-thread pump hook on Time.get_deltaTime) ---
# Clone it once into third_party/minhook:
#   git clone --depth 1 https://github.com/TsudaKageyu/minhook third_party/minhook
set(MINHOOK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/third_party/minhook" CACHE PATH "MinHook root")
if(EXISTS "${MINHOOK_DIR}/CMakeLists.txt")
    add_subdirectory("${MINHOOK_DIR}" minhook_build)
else()
    message(FATAL_ERROR "MinHook not found at ${MINHOOK_DIR} -- see comment above / README.md")
endif()

# Output MUST be named xinput1_3.dll so the game loads it.
add_library(xinput1_3 SHARED dllmain.cpp)
target_include_directories(xinput1_3 PRIVATE "${MINHOOK_DIR}/include")
target_link_libraries(xinput1_3 PRIVATE minhook)
set_target_properties(xinput1_3 PROPERTIES
    OUTPUT_NAME "xinput1_3"
    PREFIX ""
    SUFFIX ".dll")
