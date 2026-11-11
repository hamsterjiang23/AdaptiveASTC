#include "prediction.h"
#include "labels.h"

#include <cfloat>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>

thread_local const TexNNConfiguration* texnn_active_configuration = nullptr;

namespace
{
void fail(const char* message)
{
    std::fprintf(stderr, "%s\n", message);
    std::exit(1);
}

std::uint32_t read_u32(FILE* input)
{
    unsigned char bytes[4];
    if (std::fread(bytes, 1, 4, input) != 4)
    {
        fail("Truncated TexNN prediction file");
    }
    return static_cast<std::uint32_t>(bytes[0])
        | (static_cast<std::uint32_t>(bytes[1]) << 8)
        | (static_cast<std::uint32_t>(bytes[2]) << 16)
        | (static_cast<std::uint32_t>(bytes[3]) << 24);
}

struct PredictionFile
{
    unsigned int width;
    unsigned int height;
    unsigned int block_x;
    unsigned int block_y;
    std::vector<std::vector<TexNNConfiguration>> blocks;

    PredictionFile()
    {
        const char* path = std::getenv("TEXNN_PREDICTIONS");
        if (path == nullptr)
        {
            fail("Missing TEXNN_PREDICTIONS");
        }
        FILE* input = std::fopen(path, "rb");
        if (input == nullptr)
        {
            fail("Cannot open TexNN predictions");
        }
        if (std::fseek(input, 0, SEEK_END) != 0)
        {
            fail("Cannot measure TexNN prediction file");
        }
        const long bytes = std::ftell(input);
        std::rewind(input);
        char magic[8];
        if (std::fread(magic, 1, 8, input) != 8 || std::memcmp(magic, "TXNP0001", 8) != 0)
        {
            fail("Invalid TexNN prediction header");
        }
        width = read_u32(input);
        height = read_u32(input);
        block_x = read_u32(input);
        block_y = read_u32(input);
        const unsigned int count = read_u32(input);
        if (width == 0 || height == 0 || width > 0xFFFFFF || height > 0xFFFFFF
            || block_x != block_y || (block_x != 4 && block_x != 6 && block_x != 8))
        {
            fail("Invalid TexNN prediction dimensions");
        }
        const std::uint64_t expected = static_cast<std::uint64_t>((width + block_x - 1) / block_x)
            * ((height + block_y - 1) / block_y);
        if (expected != count || bytes < 28
            || static_cast<std::uint64_t>(bytes - 28) < static_cast<std::uint64_t>(count) * 4)
        {
            fail("Invalid TexNN prediction block count");
        }
        blocks.resize(count);
        for (std::vector<TexNNConfiguration>& block : blocks)
        {
            const unsigned int candidates = read_u32(input);
            if (candidates > 1024)
            {
                fail("Too many TexNN candidates for one block");
            }
            block.resize(candidates);
            for (TexNNConfiguration& configuration : block)
            {
                configuration.partition_count = static_cast<int>(read_u32(input));
                configuration.partition_index = static_cast<int>(read_u32(input));
                configuration.block_mode = static_cast<int>(read_u32(input));
                configuration.dual_component = static_cast<int>(read_u32(input));
                for (int& mode : configuration.endpoint_modes)
                {
                    mode = static_cast<int>(read_u32(input));
                }
            }
        }
        if (std::fgetc(input) != EOF || std::ferror(input))
        {
            fail("Unexpected data in TexNN prediction file");
        }
        std::fclose(input);
    }
};

thread_local bool current_constant = false;
thread_local bool current_predicted = false;
thread_local std::size_t current_candidates = 0;
std::mutex output_mutex;

bool constant_block(const imageblock* pixels)
{
    return pixels->red_min == pixels->red_max && pixels->green_min == pixels->green_max
        && pixels->blue_min == pixels->blue_max && pixels->alpha_min == pixels->alpha_max;
}
}

bool texnn_feature_pass()
{
    return std::getenv("TEXNN_FEATURE_OUTPUT") != nullptr;
}

bool texnn_weight_mode_allowed(int block_mode)
{
    return texnn_active_configuration == nullptr
        || texnn_active_configuration->block_mode == block_mode;
}

void texnn_select_endpoint_formats(int block_x, int block_y, int block_z,
    const partition_info* partition, const imageblock* pixels, const error_weight_block* errors,
    const endpoints* ideal, int separate_component, const int* available_bits,
    const float* weight_errors, int formats[4][4], int modes[4], int quantization[4],
    int matched_quantization[4])
{
    if (texnn_active_configuration == nullptr)
    {
        determine_optimal_set_of_endpoint_formats_to_use(block_x, block_y, block_z, partition,
            pixels, errors, ideal, separate_component, available_bits, weight_errors,
            formats, modes, quantization, matched_quantization);
        return;
    }
    for (int trial = 0; trial < 4; ++trial)
    {
        modes[trial] = -1;
        quantization[trial] = 0;
        matched_quantization[trial] = 0;
        for (int part = 0; part < 4; ++part)
        {
            formats[trial][part] = 0;
        }
    }
    const TexNNConfiguration& choice = *texnn_active_configuration;
    if (weight_errors[choice.block_mode] >= 1e29f)
    {
        return;
    }
    int pairs = 0;
    for (int part = 0; part < choice.partition_count; ++part)
    {
        pairs += (choice.endpoint_modes[part] >> 2) + 1;
    }
    const int bits = available_bits[choice.block_mode];
    if (pairs < 1 || pairs > 9 || bits < 0 || bits >= 128)
    {
        return;
    }
    const int level = quantization_mode_table[pairs][bits];
    const int extra = choice.partition_count == 1 ? 0 : 3 * choice.partition_count - 4;
    if (level < 4 || bits + extra >= 128)
    {
        return;
    }
    modes[0] = choice.block_mode;
    quantization[0] = level;
    matched_quantization[0] = quantization_mode_table[pairs][bits + extra];
    for (int part = 0; part < choice.partition_count; ++part)
    {
        formats[0][part] = choice.endpoint_modes[part];
    }
}

bool texnn_process_block(const astc_codec_image* image, astc_decode_mode decode_mode,
    int block_x, int block_y, int block_z, const error_weighting_params* parameters,
    const imageblock* pixels, symbolic_compressed_block* result)
{
    if (std::getenv("TEXNN_PREDICTIONS") == nullptr)
    {
        return false;
    }
    static const PredictionFile predictions;
    if (predictions.width != static_cast<unsigned int>(image->xsize)
        || predictions.height != static_cast<unsigned int>(image->ysize)
        || predictions.block_x != static_cast<unsigned int>(block_x)
        || predictions.block_y != static_cast<unsigned int>(block_y) || block_z != 1)
    {
        fail("TexNN prediction file belongs to a different image or footprint");
    }
    const int columns = (image->xsize + block_x - 1) / block_x;
    const int index = (pixels->ypos / block_y) * columns + pixels->xpos / block_x;
    const std::vector<TexNNConfiguration>& choices = predictions.blocks[index];
    current_constant = constant_block(pixels);
    current_predicted = false;
    current_candidates = choices.size();
    if (current_constant)
    {
        return false;
    }
    if (texnn_feature_pass())
    {
        std::lock_guard<std::mutex> lock(output_mutex);
        static FILE* output = std::fopen(std::getenv("TEXNN_FEATURE_OUTPUT"), "wb");
        if (output == nullptr)
        {
            fail("Cannot open TexNN feature output");
        }
        for (std::size_t candidate = 0; candidate < choices.size(); ++candidate)
        {
            const TexNNConfiguration& choice = choices[candidate];
            if (choice.partition_count < 1 || choice.partition_count > 4
                || choice.partition_index < 0 || choice.partition_index >= PARTITION_COUNT
                || (choice.partition_count == 1 && choice.partition_index != 0))
            {
                fail("Invalid TexNN partition prediction");
            }
            const partition_info* partition = get_partition_table(
                block_x, block_y, block_z, choice.partition_count) + choice.partition_index;
            if (partition->partition_count != choice.partition_count)
            {
                fail("TexNN partition prediction is not supported by the reference codec");
            }
            float endpoints[24];
            texnn_ideal_endpoints(image, block_x, block_y, block_z, parameters, pixels,
                choice.partition_count, choice.partition_index, endpoints);
            std::fprintf(output, "{\"block\":%d,\"candidate\":%u,\"feature_protocol\":2,"
                "\"ideal_endpoints\":[", index, static_cast<unsigned int>(candidate));
            for (int feature = 0; feature < 24; ++feature)
            {
                const float value = endpoints[feature];
                if (!(value >= -FLT_MAX && value <= FLT_MAX))
                {
                    fail("Non-finite TexNN inference feature");
                }
                std::fprintf(output, "%s%.9g", feature == 0 ? "" : ",", static_cast<double>(value));
            }
            std::fprintf(output, "]}\n");
        }
        if (std::fflush(output) != 0 || std::ferror(output))
        {
            fail("Cannot write TexNN inference features");
        }
        std::memset(result, 0, sizeof(*result));
        result->block_mode = -2;
        result->constant_color[3] = 65535;
        return true;
    }
    current_predicted = texnn_solve_candidates(image, decode_mode, block_x, block_y, block_z,
        parameters, pixels, choices, result);
    return current_predicted;
}

void texnn_record_decision(const imageblock* pixels, const symbolic_compressed_block* result)
{
    const char* path = std::getenv("TEXNN_DECISIONS");
    if (path == nullptr || texnn_feature_pass())
    {
        return;
    }
    std::lock_guard<std::mutex> lock(output_mutex);
    static FILE* output = std::fopen(path, "wb");
    if (output == nullptr)
    {
        fail("Cannot open TexNN decision report");
    }
    std::fprintf(output, "{\"x\":%d,\"y\":%d,\"constant\":%s,\"predicted\":%s,"
        "\"fallback\":%s,\"candidates\":%u,\"partition_count\":%d,\"partition_index\":%d,"
        "\"block_mode\":%d,\"error\":%s}\n",
        pixels->xpos, pixels->ypos, current_constant ? "true" : "false",
        current_predicted ? "true" : "false", !current_constant && !current_predicted ? "true" : "false",
        static_cast<unsigned int>(current_candidates), result->partition_count,
        result->partition_count == 0 ? 0 : result->partition_index,
        result->block_mode, result->error_block ? "true" : "false");
    if (std::fflush(output) != 0 || std::ferror(output))
    {
        fail("Cannot write TexNN decision report");
    }
}
