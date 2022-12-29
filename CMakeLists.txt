cmake_minimum_required(VERSION 3.5)

project(tcp_socket LANGUAGES CXX)

set(CMAKE_INCLUDE_CURRENT_DIR ON)

set(CMAKE_CXX_STANDARD_REQUIRED ON)

set( CMAKE_CXX_FLAGS "-std=c++14" )

set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ./lib/)
SET(EXECUTABLE_OUTPUT_PATH ./lib/) 

#find_package(OpenCV REQUIRED)
#import zeromq library
find_package(PkgConfig)

include_directories(  
    ${OpenCV_INCLUDE_DIRS}
    include
    /usr/include/python3.8 
)

link_directories(
    ./lib
    /usr/lib/**
)

add_library(tcp_socket SHARED
src/tcp_socket.cpp
)

add_executable(tcp_com
src/main_tcp_socket.cpp
)

target_link_libraries(tcp_socket -ljsoncpp  boost_system boost_thread rt )
target_link_libraries(tcp_com tcp_socket)
