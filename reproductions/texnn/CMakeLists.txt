cmake_minimum_required(VERSION 3.16)
project(texnn_reference LANGUAGES C CXX)

set(REFERENCE_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/upstream/Source")
set(REFERENCE_FILES
    astc_averages_and_directions.cpp
    astc_block_sizes2.cpp
    astc_color_quantize.cpp
    astc_color_unquantize.cpp
    astc_decompress_symbolic.cpp
    astc_encoding_choice_error.cpp
    astc_find_best_partitioning.cpp
    astc_ideal_endpoints_and_weights.cpp
    astc_image_load_store.cpp
    astc_integer_sequence.cpp
    astc_ktx_dds.cpp
    astc_kmeans_partitioning.cpp
    astc_partition_tables.cpp
    astc_percentile_tables.cpp
    astc_pick_best_endpoint_format.cpp
    astc_quantization.cpp
    astc_stb_tga.cpp
    astc_symbolic_physical.cpp
    astc_weight_align.cpp
    astc_weight_quant_xfer_tables.cpp
    astc_compute_variance.cpp
    mathlib.cpp
    softfloat.cpp
    stb_image.c
)
list(TRANSFORM REFERENCE_FILES PREPEND "${REFERENCE_SOURCE}/")
add_library(texnn-codec OBJECT ${REFERENCE_FILES})
add_executable(texnn-reference "${REFERENCE_SOURCE}/astc_toplevel.cpp"
    "${REFERENCE_SOURCE}/astc_compress_symbolic.cpp"
    $<TARGET_OBJECTS:texnn-codec>)
add_executable(texnn-labels "${CMAKE_CURRENT_BINARY_DIR}/generated/astc_toplevel.cpp"
    "${REFERENCE_SOURCE}/astc_compress_symbolic.cpp"
    native/labels.cpp $<TARGET_OBJECTS:texnn-codec>)
add_executable(texnn-predict "${CMAKE_CURRENT_BINARY_DIR}/generated/astc_predict_toplevel.cpp"
    "${CMAKE_CURRENT_BINARY_DIR}/generated/astc_predict_compress.cpp"
    native/prediction.cpp native/labels.cpp $<TARGET_OBJECTS:texnn-codec>)
foreach(target texnn-codec texnn-reference texnn-labels texnn-predict)
    target_include_directories(${target} PRIVATE "${REFERENCE_SOURCE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/native")
    target_compile_features(${target} PRIVATE cxx_std_11)
    if(MSVC)
        target_compile_definitions(${target} PRIVATE WIN32 _CRT_SECURE_NO_WARNINGS _USE_MATH_DEFINES)
        target_compile_options(${target} PRIVATE /fp:precise)
    else()
        find_package(Threads REQUIRED)
        target_link_libraries(${target} PRIVATE Threads::Threads)
        target_compile_options(${target} PRIVATE -msse2 -mfpmath=sse)
    endif()
endforeach()
