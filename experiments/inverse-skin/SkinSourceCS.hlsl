#define SOURCE_VERTEX_COUNT 17615

// 72-byte bind vertex:
// position.xyz, normal.xyz, tangent.xyzw, bone_indices.xyzw, weights.xyzw
Buffer<uint> BindVertices : register(t0);
Buffer<uint> RecoveredMatrices : register(t1);
RWBuffer<uint> SkinnedVB : register(u0);

float3 LoadMatrixRow(uint bone, uint row)
{
    const uint source = (bone * 4 + row) * 3;
    return asfloat(uint3(
        RecoveredMatrices[source],
        RecoveredMatrices[source + 1],
        RecoveredMatrices[source + 2]));
}

[numthreads(64, 1, 1)]
void main(uint3 dispatch_id : SV_DispatchThreadID)
{
    const uint vertex = dispatch_id.x;
    if (vertex >= SOURCE_VERTEX_COUNT)
        return;

    const uint input_base = vertex * 18;
    const float3 position = asfloat(uint3(BindVertices[input_base], BindVertices[input_base + 1], BindVertices[input_base + 2]));
    const float3 normal = asfloat(uint3(BindVertices[input_base + 3], BindVertices[input_base + 4], BindVertices[input_base + 5]));
    const float4 tangent = asfloat(uint4(BindVertices[input_base + 6], BindVertices[input_base + 7], BindVertices[input_base + 8], BindVertices[input_base + 9]));
    const uint4 bones = uint4(BindVertices[input_base + 10], BindVertices[input_base + 11], BindVertices[input_base + 12], BindVertices[input_base + 13]);
    const float4 weights = asfloat(uint4(BindVertices[input_base + 14], BindVertices[input_base + 15], BindVertices[input_base + 16], BindVertices[input_base + 17]));

    float3 skinned_position = 0.0;
    float3 skinned_normal = 0.0;
    float3 skinned_tangent = 0.0;
    [unroll]
    for (uint influence = 0; influence < 4; ++influence)
    {
        const float weight = weights[influence];
        if (weight <= 0.0)
            continue;
        const uint bone = bones[influence];
        const float3 row0 = LoadMatrixRow(bone, 0);
        const float3 row1 = LoadMatrixRow(bone, 1);
        const float3 row2 = LoadMatrixRow(bone, 2);
        const float3 row3 = LoadMatrixRow(bone, 3);
        skinned_position += weight * (position.x * row0 + position.y * row1 + position.z * row2 + row3);
        skinned_normal += weight * (normal.x * row0 + normal.y * row1 + normal.z * row2);
        skinned_tangent += weight * (tangent.x * row0 + tangent.y * row1 + tangent.z * row2);
    }

    skinned_normal = normalize(skinned_normal);
    skinned_tangent = normalize(skinned_tangent);
    const uint output_base = vertex * 10;
    const uint3 packed_position = asuint(skinned_position);
    const uint3 packed_normal = asuint(skinned_normal);
    const uint4 packed_tangent = asuint(float4(skinned_tangent, tangent.w));
    SkinnedVB[output_base] = packed_position.x;
    SkinnedVB[output_base + 1] = packed_position.y;
    SkinnedVB[output_base + 2] = packed_position.z;
    SkinnedVB[output_base + 3] = packed_normal.x;
    SkinnedVB[output_base + 4] = packed_normal.y;
    SkinnedVB[output_base + 5] = packed_normal.z;
    SkinnedVB[output_base + 6] = packed_tangent.x;
    SkinnedVB[output_base + 7] = packed_tangent.y;
    SkinnedVB[output_base + 8] = packed_tangent.z;
    SkinnedVB[output_base + 9] = packed_tangent.w;
}
