cmake_minimum_required(VERSION 3.16)

project(p05_rkllm_vlm_runners LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

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

if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64")
  set(RKLLM_RT_LIB "${RKLLM_API_PATH}/aarch64/librkllmrt.so")
else()
  set(RKLLM_RT_LIB "${RKLLM_API_PATH}/${CMAKE_SYSTEM_PROCESSOR}/librkllmrt.so")
endif()
if(NOT EXISTS "${RKLLM_RT_LIB}")
  message(FATAL_ERROR "librkllmrt.so not found at ${RKLLM_RT_LIB}")
endif()

find_path(RKNN_INCLUDE_DIR rknn_api.h
  PATHS
    /usr/include
    /usr/local/include
    /usr/include/rknn
    /usr/local/include/rknn
    /usr/include/rknpu2
    /usr/local/include/rknpu2
    /usr/local/rknn/include
    $ENV{RKNN_SDK_ROOT}/include
    $ENV{RKNN_SDK_ROOT}/runtime/RK3588/Linux/librknn_api/include
)
if(NOT RKNN_INCLUDE_DIR)
  message(FATAL_ERROR "rknn_api.h not found. Set RKNN_INCLUDE_DIR or RKNN_SDK_ROOT.")
endif()

find_library(RKNNRT_LIBRARY rknnrt
  PATHS
    /usr/lib
    /usr/local/lib
    /usr/lib/aarch64-linux-gnu
    /usr/local/lib/aarch64-linux-gnu
    /usr/local/rknn/lib
    $ENV{RKNN_SDK_ROOT}/lib
    $ENV{RKNN_SDK_ROOT}/runtime/RK3588/Linux/librknn_api/aarch64
    $ENV{RKNN_SDK_ROOT}/runtime/RK3588/Linux/librknn_api/aarch64/lib
  REQUIRED
)

find_package(OpenCV REQUIRED COMPONENTS core imgproc imgcodecs)

add_executable(rkllm_resident_vlm_server
  image_enc.cc
  rkllm_resident_vlm_server.cpp
)
target_include_directories(
  rkllm_resident_vlm_server
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${RKNN_INCLUDE_DIR}
    ${RKLLM_INCLUDE_DIR}
    ${OpenCV_INCLUDE_DIRS}
)
target_link_libraries(
  rkllm_resident_vlm_server
  PRIVATE
    ${OpenCV_LIBS}
    ${RKNNRT_LIBRARY}
    ${RKLLM_RT_LIB}
)
