#ifndef TARGET_VERTEX_COUNT
#define TARGET_VERTEX_COUNT 1
#endif

Buffer<uint> BindVertices : register(t0);
Buffer<uint> RecoveredMatrices : register(t1);
Buffer<float> BoneCorrections : register(t2);
RWBuffer<uint> SkinnedVB : register(u0);

float3 LoadMatrixRow(uint bone, uint row)
{
    const uint source = (bone * 4 + row) * 3;
    return asfloat(uint3(RecoveredMatrices[source], RecoveredMatrices[source + 1], RecoveredMatrices[source + 2]));
}

float3 LoadCorrectionRow(uint correction, uint row)
{
    const uint source = (correction * 4 + row) * 3;
    return float3(BoneCorrections[source], BoneCorrections[source + 1], BoneCorrections[source + 2]);
}

[numthreads(64, 1, 1)]
void main(uint3 dispatch_id : SV_DispatchThreadID)
{
    const uint vertex = dispatch_id.x;
    if (vertex >= TARGET_VERTEX_COUNT)
        return;
    const uint input_base = vertex * 22;
    const float3 position = asfloat(uint3(BindVertices[input_base], BindVertices[input_base + 1], BindVertices[input_base + 2]));
    const float3 normal = asfloat(uint3(BindVertices[input_base + 3], BindVertices[input_base + 4], BindVertices[input_base + 5]));
    const float4 tangent = asfloat(uint4(BindVertices[input_base + 6], BindVertices[input_base + 7], BindVertices[input_base + 8], BindVertices[input_base + 9]));
    const uint4 bones = uint4(BindVertices[input_base + 10], BindVertices[input_base + 11], BindVertices[input_base + 12], BindVertices[input_base + 13]);
    const uint4 corrections = uint4(BindVertices[input_base + 14], BindVertices[input_base + 15], BindVertices[input_base + 16], BindVertices[input_base + 17]);
    const float4 weights = asfloat(uint4(BindVertices[input_base + 18], BindVertices[input_base + 19], BindVertices[input_base + 20], BindVertices[input_base + 21]));
    float3 p = 0.0, n = 0.0, t = 0.0;
    [unroll]
    for (uint influence = 0; influence < 4; ++influence)
    {
        const float w = weights[influence];
        if (w <= 0.0) continue;
        const uint bone = bones[influence];
        const uint correction = corrections[influence];
        const float3 c0 = LoadCorrectionRow(correction, 0), c1 = LoadCorrectionRow(correction, 1);
        const float3 c2 = LoadCorrectionRow(correction, 2), c3 = LoadCorrectionRow(correction, 3);
        const float3 corrected_position = position.x * c0 + position.y * c1 + position.z * c2 + c3;
        const float3 corrected_normal = normal.x * c0 + normal.y * c1 + normal.z * c2;
        const float3 corrected_tangent = tangent.x * c0 + tangent.y * c1 + tangent.z * c2;
        const float3 r0 = LoadMatrixRow(bone, 0), r1 = LoadMatrixRow(bone, 1);
        const float3 r2 = LoadMatrixRow(bone, 2), r3 = LoadMatrixRow(bone, 3);
        p += w * (corrected_position.x * r0 + corrected_position.y * r1 + corrected_position.z * r2 + r3);
        n += w * (corrected_normal.x * r0 + corrected_normal.y * r1 + corrected_normal.z * r2);
        t += w * (corrected_tangent.x * r0 + corrected_tangent.y * r1 + corrected_tangent.z * r2);
    }
    n = normalize(n);
    t = normalize(t);
    const uint output_base = vertex * 10;
    const uint3 pp = asuint(p), nn = asuint(n);
    const uint4 tt = asuint(float4(t, tangent.w));
    SkinnedVB[output_base] = pp.x; SkinnedVB[output_base + 1] = pp.y; SkinnedVB[output_base + 2] = pp.z;
    SkinnedVB[output_base + 3] = nn.x; SkinnedVB[output_base + 4] = nn.y; SkinnedVB[output_base + 5] = nn.z;
    SkinnedVB[output_base + 6] = tt.x; SkinnedVB[output_base + 7] = tt.y;
    SkinnedVB[output_base + 8] = tt.z; SkinnedVB[output_base + 9] = tt.w;
}
