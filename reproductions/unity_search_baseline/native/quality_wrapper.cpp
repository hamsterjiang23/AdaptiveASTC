// The engine functions are extracted verbatim into the local build directory.
extern "C" __declspec(dllexport) int unity_astc_quality(
    const UInt8* original, const UInt8* decoded, int width, int height,
    bool rgbOnly, bool computeSsim, bool computeNormal, int mipCount, float* output)
{
    if (!original || !decoded || !output || width < 1 || height < 1 ||
        static_cast<long long>(width) * height > 536870911LL)
        return 1;
    try
    {
        output[0] = CalculatePSNR(original, decoded, width, height, &output[1], rgbOnly);
        output[2] = computeSsim ? CalculateMSSSIMDb_Luma(original, decoded, width, height) : 0.0f;
        output[3] = output[4] = 0.0f;
        if (computeNormal)
        {
            const auto angles = CalculateNormalAngularErrorMip0To3(
                original, decoded, width, height, mipCount);
            output[3] = angles.meanWavgDeg;
            output[4] = angles.p95WavgDeg;
        }
        return 0;
    }
    catch (...)
    {
        return 2;
    }
}
