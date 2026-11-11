#include "labels.h"

#include <cfloat>
#include <cstdio>
#include <cstdlib>
#include <mutex>

namespace
{
std::mutex output_mutex;

void write_catalog(int block_x, int block_y, int block_z,
    const block_size_descriptor* descriptor)
{
    static bool written = false;
    const char* path = std::getenv("TEXNN_CATALOG");
    if (written || path == nullptr)
    {
        return;
    }
    FILE* output = std::fopen(path, "wb");
    if (output == nullptr)
    {
        std::fprintf(stderr, "Cannot open TexNN configuration catalog\n");
        std::exit(1);
    }
    std::fprintf(output, "{\"footprint\":[%d,%d],\"partitions\":[", block_x, block_y);
    bool first = true;
    for (int count = 1; count <= 4; ++count)
    {
        const partition_info* partitions = get_partition_table(block_x, block_y, block_z, count);
        const int candidates = count == 1 ? 1 : PARTITION_COUNT;
        for (int index = 0; index < candidates; ++index)
        {
            if (partitions[index].partition_count == count)
            {
                std::fprintf(output, "%s[%d,%d]", first ? "" : ",", count, index);
                first = false;
            }
        }
    }
    std::fprintf(output, "],\"block_modes\":[");
    first = true;
    for (int index = 0; index < MAX_WEIGHT_MODES; ++index)
    {
        const block_mode& mode = descriptor->block_modes[index];
        if (mode.permit_encode)
        {
            std::fprintf(output, "%s{\"block_mode\":%d,\"decimation_mode\":%d,"
                "\"weight_quantization\":%d,\"dual_plane\":%s}",
                first ? "" : ",", index, mode.decimation_mode, mode.quantization_mode,
                mode.is_dual_plane ? "true" : "false");
            first = false;
        }
    }
    std::fprintf(output, "]}\n");
    const bool failed = std::ferror(output) != 0;
    if (std::fclose(output) != 0 || failed)
    {
        std::fprintf(stderr, "Failed to write TexNN configuration catalog\n");
        std::exit(1);
    }
    written = true;
}

void write_float(FILE* output, float value)
{
    if (!(value >= -FLT_MAX && value <= FLT_MAX))
    {
        std::fprintf(stderr, "Non-finite TexNN training feature\n");
        std::exit(1);
    }
    std::fprintf(output, "%.9g", static_cast<double>(value));
}
}

void texnn_export_block(const astc_codec_image* image, int block_x, int block_y, int block_z,
    const error_weighting_params* parameters, const imageblock* pixels,
    const symbolic_compressed_block* encoded)
{
    static const char* path = std::getenv("TEXNN_LABELS");
    if (path == nullptr)
    {
        return;
    }
    std::lock_guard<std::mutex> lock(output_mutex);
    static FILE* output = std::fopen(path, "wb");
    if (output == nullptr)
    {
        std::fprintf(stderr, "Cannot open TexNN label file\n");
        std::exit(1);
    }

    const bool constant = encoded->block_mode < 0;
    const int partition_count = constant ? 0 : encoded->partition_count;
    const int partition_index = constant ? 0 : encoded->partition_index;
    const block_size_descriptor* descriptor = get_block_size_descriptor(block_x, block_y, block_z);
    write_catalog(block_x, block_y, block_z, descriptor);
    int decimation_mode = -1;
    int weight_quantization = -1;
    int dual_component = -1;
    float ideal_endpoints[24] = {};
    if (!constant && !encoded->error_block)
    {
        const block_mode& mode = descriptor->block_modes[encoded->block_mode];
        decimation_mode = mode.decimation_mode;
        weight_quantization = mode.quantization_mode;
        dual_component = mode.is_dual_plane ? encoded->plane2_color_component : -1;
        const partition_info* partition = get_partition_table(
            block_x, block_y, block_z, encoded->partition_count) + encoded->partition_index;
        error_weight_block errors;
        error_weight_block_orig original_errors;
        prepare_error_weight_block(image, block_x, block_y, block_z, parameters, pixels,
            &errors, &original_errors);
        endpoints_and_weights first;
        endpoints_and_weights second;
        if (mode.is_dual_plane)
        {
            compute_endpoints_and_ideal_weights_2_planes(block_x, block_y, block_z,
                partition, pixels, &errors, dual_component, &first, &second);
        }
        else
        {
            compute_endpoints_and_ideal_weights_1_plane(block_x, block_y, block_z,
                partition, pixels, &errors, &first);
        }
        for (int index = 0; index < encoded->partition_count; ++index)
        {
            const float4 points[2] = {first.ep.endpt0[index], first.ep.endpt1[index]};
            for (int endpoint = 0; endpoint < 2; ++endpoint)
            {
                const float4& point = points[endpoint];
                const float rgb[3] = {point.x, point.y, point.z};
                for (int channel = 0; channel < 3; ++channel)
                {
                    float value = rgb[channel];
                    if (channel == dual_component)
                    {
                        const float4& alternate = endpoint == 0 ? second.ep.endpt0[index]
                            : second.ep.endpt1[index];
                        const float alternate_rgb[3] = {alternate.x, alternate.y, alternate.z};
                        value = alternate_rgb[channel];
                    }
                    ideal_endpoints[index * 6 + endpoint * 3 + channel] = value / 65535.0f;
                }
            }
        }
    }

    std::fprintf(output, "{\"x\":%d,\"y\":%d,\"z\":%d,\"width\":%d,\"height\":%d,"
        "\"block_x\":%d,\"block_y\":%d,\"constant\":%s,\"error\":%s,"
        "\"partition_count\":%d,\"partition_index\":%d,\"block_mode\":%d,"
        "\"decimation_mode\":%d,\"weight_quantization\":%d,\"dual_component\":%d,"
        "\"endpoint_modes\":[",
        pixels->xpos, pixels->ypos, pixels->zpos, image->xsize, image->ysize,
        block_x, block_y, constant ? "true" : "false", encoded->error_block ? "true" : "false",
        partition_count, partition_index, encoded->block_mode,
        decimation_mode, weight_quantization, dual_component);
    for (int index = 0; index < encoded->partition_count; ++index)
    {
        std::fprintf(output, "%s%d", index == 0 ? "" : ",", encoded->color_formats[index]);
    }
    std::fprintf(output, "],\"rgb\":[");
    const int count = block_x * block_y * block_z;
    for (int texel = 0; texel < count; ++texel)
    {
        for (int channel = 0; channel < 3; ++channel)
        {
            if (texel != 0 || channel != 0)
            {
                std::fputc(',', output);
            }
            write_float(output, pixels->orig_data[texel * 4 + channel]);
        }
    }
    std::fprintf(output, "],\"ideal_endpoints\":[");
    for (int index = 0; index < 24; ++index)
    {
        if (index != 0)
        {
            std::fputc(',', output);
        }
        write_float(output, ideal_endpoints[index]);
    }
    const physical_compressed_block physical = symbolic_to_physical(
        block_x, block_y, block_z, encoded);
    std::fprintf(output, "],\"astc_hex\":\"");
    for (int index = 0; index < 16; ++index)
    {
        std::fprintf(output, "%02x", physical.data[index]);
    }
    std::fprintf(output, "\"}\n");
    if (std::fflush(output) != 0 || std::ferror(output))
    {
        std::fprintf(stderr, "Failed to write TexNN label record\n");
        std::exit(1);
    }
}
