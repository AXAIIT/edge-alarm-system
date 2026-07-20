cmake_minimum_required(VERSION 3.10)
project(p05_rkllm_text_runners)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED RKLLM_API_PATH)
  set(PROJECT_ROOT "${CMAKE_SOURCE_DIR}/../../../..")
  set(RKLLM_API_PATH "${PROJECT_ROOT}/third_party/rknn-llm/rkllm-runtime/rknn-llm-release-v1.3.0/rkllm-runtime/Linux/librkllm_api")
endif()

if(NOT IS_ABSOLUTE "${RKLLM_API_PATH}")
  get_filename_component(RKLLM_API_PATH "${RKLLM_API_PATH}" ABSOLUTE BASE_DIR "${CMAKE_SOURCE_DIR}")
endif()

set(RKLLM_INCLUDE_DIR "${RKLLM_API_PATH}/include")
if(NOT EXISTS "${RKLLM_INCLUDE_DIR}/rkllm.h")
  message(FATAL_ERROR "rkllm.h not found under ${RKLLM_INCLUDE_DIR}")
endif()

include_directories("${RKLLM_API_PATH}/include")

if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64")
  set(RKLLM_RT_LIB "${RKLLM_API_PATH}/aarch64/librkllmrt.so")
else()
  set(RKLLM_RT_LIB "${RKLLM_API_PATH}/${CMAKE_SYSTEM_PROCESSOR}/librkllmrt.so")
endif()

if(NOT EXISTS "${RKLLM_RT_LIB}")
  message(FATAL_ERROR "librkllmrt.so not found at ${RKLLM_RT_LIB}")
endif()

add_executable(rkllm_single_turn rkllm_single_turn.cpp)
target_link_libraries(rkllm_single_turn "${RKLLM_RT_LIB}")

add_executable(rkllm_resident_text_server rkllm_resident_text_server.cpp)
target_link_libraries(rkllm_resident_text_server "${RKLLM_RT_LIB}")
