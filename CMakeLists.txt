cmake_minimum_required(VERSION 3.10)
project(uma_ai)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(uma_ai
    cpp_cores/simulator.cpp
    cpp_cores/main.cpp
)

# MinGW: 靜態連結執行期 DLL，讓執行檔在沒有 MinGW 路徑的環境也能直接跑
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_link_options(uma_ai PRIVATE -static -static-libgcc -static-libstdc++)
endif()