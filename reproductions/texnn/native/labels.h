#pragma once

#include "astc_codec_internals.h"

void texnn_ideal_endpoints(const astc_codec_image* image, int block_x, int block_y, int block_z,
    const error_weighting_params* parameters, const imageblock* pixels,
    int partition_count, int partition_index, float output[24]);

void texnn_export_block(const astc_codec_image* image, int block_x, int block_y, int block_z,
    const error_weighting_params* parameters, const imageblock* pixels,
    const symbolic_compressed_block* encoded);
