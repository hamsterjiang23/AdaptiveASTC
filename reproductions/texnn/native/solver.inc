// Included after the pinned codec's private fixed-partition solvers.
bool texnn_solve_candidates(const astc_codec_image* image, astc_decode_mode decode_mode,
    int block_x, int block_y, int block_z, const error_weighting_params* parameters,
    const imageblock* pixels, const std::vector<TexNNConfiguration>& candidates,
    symbolic_compressed_block* result)
{
    const block_size_descriptor* descriptor = get_block_size_descriptor(block_x, block_y, block_z);
    error_weight_block errors;
    error_weight_block_orig original_errors;
    prepare_error_weight_block(image, block_x, block_y, block_z, parameters, pixels,
        &errors, &original_errors);
    float best_error = 1e30f;
    bool found = false;
    for (const TexNNConfiguration& configuration : candidates)
    {
        const int count = configuration.partition_count;
        const int index = configuration.partition_index;
        const int mode_index = configuration.block_mode;
        if (count < 1 || count > 4 || index < 0 || index >= PARTITION_COUNT
            || (count == 1 && index != 0) || mode_index < 0 || mode_index >= MAX_WEIGHT_MODES
            || configuration.dual_component < -1 || configuration.dual_component > 3)
        {
            continue;
        }
        const partition_info* partition = get_partition_table(block_x, block_y, block_z, count);
        const block_mode& mode = descriptor->block_modes[mode_index];
        if (partition[index].partition_count != count || !mode.permit_encode
            || (mode.is_dual_plane != (configuration.dual_component >= 0))
            || (count == 4 && mode.is_dual_plane))
        {
            continue;
        }
        int minimum_class = 4;
        int maximum_class = 0;
        bool valid = true;
        for (int part = 0; part < count; ++part)
        {
            const int format = configuration.endpoint_modes[part];
            if (format != 0 && format != 4 && format != 6 && format != 8
                && format != 10 && format != 12)
            {
                valid = false;
            }
            const int format_class = format >> 2;
            minimum_class = MIN(minimum_class, format_class);
            maximum_class = MAX(maximum_class, format_class);
        }
        if (!valid || maximum_class - minimum_class > 1)
        {
            continue;
        }
        symbolic_compressed_block blocks[4] = {};
        texnn_active_configuration = &configuration;
        if (mode.is_dual_plane)
        {
            compress_symbolic_block_fixed_partition_2_planes(decode_mode, 1.0f,
                parameters->max_refinement_iters, block_x, block_y, block_z, count, index,
                configuration.dual_component, pixels, &errors, blocks);
        }
        else
        {
            compress_symbolic_block_fixed_partition_1_plane(decode_mode, 1.0f,
                parameters->max_refinement_iters, block_x, block_y, block_z, count, index,
                pixels, &errors, blocks);
        }
        texnn_active_configuration = nullptr;
        for (int trial = 0; trial < 4; ++trial)
        {
            if (blocks[trial].error_block)
            {
                continue;
            }
            imageblock decoded;
            decompress_symbolic_block(decode_mode, block_x, block_y, block_z,
                pixels->xpos, pixels->ypos, pixels->zpos, &blocks[trial], &decoded);
            const float error = compute_imageblock_difference(
                block_x, block_y, block_z, pixels, &decoded, &errors);
            if (error >= 0 && error < best_error)
            {
                best_error = error;
                *result = blocks[trial];
                found = true;
            }
        }
    }
    if (found)
    {
        const physical_compressed_block physical = symbolic_to_physical(
            block_x, block_y, block_z, result);
        physical_to_symbolic(block_x, block_y, block_z, physical, result);
        found = result->error_block == 0;
    }
    return found;
}
