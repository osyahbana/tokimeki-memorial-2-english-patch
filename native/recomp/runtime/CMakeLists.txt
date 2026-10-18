cmake_minimum_required(VERSION 3.20)
project(TM2Recompiled LANGUAGES C CXX)

set(PSXRECOMP_ROOT "" CACHE PATH "Pinned PSXRecomp checkout")
set(TM2_GENERATED_DIR "" CACHE PATH "Private generated Disc 1 C directory")
set(TM2_GAME_CONFIG "" CACHE FILEPATH "Private game.toml with local disc paths")
set(TM2_STATIC_OVERLAYS "" CACHE FILEPATH "Private generated overlays_static.c")
if(NOT EXISTS "${PSXRECOMP_ROOT}/runtime/runtime.cmake" OR
   NOT EXISTS "${TM2_GENERATED_DIR}/boot-loaded.exe_dispatch.c" OR
   NOT EXISTS "${TM2_GAME_CONFIG}")
    message(FATAL_ERROR "Set PSXRECOMP_ROOT, TM2_GENERATED_DIR and TM2_GAME_CONFIG to prepared local inputs")
endif()
if(TM2_STATIC_OVERLAYS AND NOT EXISTS "${TM2_STATIC_OVERLAYS}")
    message(FATAL_ERROR "TM2_STATIC_OVERLAYS was specified but does not exist")
endif()

add_executable(tm2-cdrom-regression test_cdrom_seek.c)
target_include_directories(tm2-cdrom-regression PRIVATE
    "${PSXRECOMP_ROOT}/runtime/tests" "${PSXRECOMP_ROOT}/runtime/include"
    "${PSXRECOMP_ROOT}/runtime/src")
target_compile_features(tm2-cdrom-regression PRIVATE c_std_11)

set(PSX_RECOMP_UI OFF CACHE BOOL "Minimal research runtime")
set(PSX_NETPLAY OFF CACHE BOOL "Local boot investigation")
set(PSX_REWIND OFF CACHE BOOL "No rewind dependency during boot investigation")
set(PSX_SETUP_WIZARD OFF CACHE BOOL "Prepared local inputs")
set(PSX_ENABLE_VULKAN OFF CACHE BOOL "Use the established GL/software paths")
set(PSX_DEBUG_TOOLS ON CACHE BOOL "Enable boot diagnostics")
set(PSX_EXECUTION_PROFILE REFERENCE CACHE STRING "Reference implementation for bring-up")
set(PSXRECOMP_BIOS_STEMS OpenBIOS CACHE STRING "Bundled BIOS backend")
set(PSXRECOMP_REQUIRE_GAME_C ON CACHE BOOL "Never silently build an empty setup host")
include("${PSXRECOMP_ROOT}/runtime/runtime.cmake")

psxrecomp_add_game_runtime(psx-runtime
    PRELOADED_MODS_DIR NONE
    WINDOW_TITLE "Tokimeki Memorial 2 - Recompilation Research"
    DEFAULT_GAME_CONFIG_PATH "${TM2_GAME_CONFIG}"
    MAX_PLAYERS 1
    GAME_OVERLAY_STATIC_C "${TM2_STATIC_OVERLAYS}"
    GEN_MARKER "${TM2_GENERATED_DIR}/boot-loaded.exe_dispatch.c"
    GEN_FULL_GLOB "${TM2_GENERATED_DIR}/boot-loaded.exe_full_*.c")

if(MSVC)
    # The pinned framework enables C11 atomics for audio_trace.c only, but
    # additional C translation units now use them. Keep this C-only in VS.
    foreach(_atomic_source guest_tty debug_server gpu_gl_renderer host_overlay
                           overlay_capture render_thread starvation_ring)
        set_property(SOURCE "${PSXRECOMP_ROOT}/runtime/src/${_atomic_source}.c"
                     APPEND PROPERTY COMPILE_OPTIONS /experimental:c11atomics)
    endforeach()
    if(MSVC_VERSION EQUAL 1939)
        # MSVC 19.39 crashes optimizing the shadow-cache memcpy functions.
        # Keep semantics intact and scope the workaround to this one file.
        set_property(SOURCE "${PSXRECOMP_ROOT}/runtime/src/psx_icache.c"
                     APPEND PROPERTY COMPILE_OPTIONS /Od)
    endif()
endif()
