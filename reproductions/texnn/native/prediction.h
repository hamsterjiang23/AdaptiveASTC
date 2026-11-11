#pragma once

#include "astc_codec_internals.h"
#include <vector>

struct TexNNConfiguration
{
    int partition_count;
    int partition_index;
    int block_mode;
    int dual_component;
    int endpoint_modes[4];
};

extern thread_local const TexNNConfiguration* texnn_active_configuration;

bool texnn_feature_pass();
bool texnn_weight_mode_allowed(int block_mode);
bool texnn_process_block(const astc_codec_image* image, astc_decode_mode decode_mode,
    int block_x, int block_y, int block_z, const error_weighting_params* parameters,
    const imageblock* pixels, symbolic_compressed_block* result);
void texnn_record_decision(const imageblock* pixels, const symbolic_compressed_block* result);

bool texnn_solve_candidates(const astc_codec_image* image, astc_decode_mode decode_mode,
    int block_x, int block_y, int block_z, const error_weighting_params* parameters,
    const imageblock* pixels, const std::vector<TexNNConfiguration>& candidates,
    symbolic_compressed_block* result);

void texnn_select_endpoint_formats(int block_x, int block_y, int block_z,
    const partition_info* partition, const imageblock* pixels, const error_weight_block* errors,
    const endpoints* ideal, int separate_component, const int* available_bits,
    const float* weight_errors, int formats[4][4], int modes[4], int quantization[4],
    int matched_quantization[4]);
