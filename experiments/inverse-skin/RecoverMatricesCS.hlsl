#define SOURCE_VERTEX_COUNT 17615
#define COEFFICIENT_COUNT 608

Buffer<uint> PosedVB : register(t0);
Buffer<float> InverseOperator : register(t1);
RWBuffer<uint> RecoveredMatrices : register(u0);

groupshared float3 Partial[256];

[numthreads(256, 1, 1)]
void main(uint3 group_id : SV_GroupID, uint group_index : SV_GroupIndex)
{
    const uint coefficient = group_id.x;
    if (coefficient >= COEFFICIENT_COUNT)
        return;

    float3 sum = 0.0;
    for (uint vertex = group_index; vertex < SOURCE_VERTEX_COUNT; vertex += 256)
    {
        const float weight = InverseOperator[coefficient * SOURCE_VERTEX_COUNT + vertex];
        const uint source = vertex * 10;
        const float3 position = asfloat(uint3(PosedVB[source], PosedVB[source + 1], PosedVB[source + 2]));
        sum += weight * position;
    }
    Partial[group_index] = sum;
    GroupMemoryBarrierWithGroupSync();

    for (uint width = 128; width > 0; width >>= 1)
    {
        if (group_index < width)
            Partial[group_index] += Partial[group_index + width];
        GroupMemoryBarrierWithGroupSync();
    }

    if (group_index == 0)
    {
        const uint destination = coefficient * 3;
        const uint3 value = asuint(Partial[0]);
        RecoveredMatrices[destination] = value.x;
        RecoveredMatrices[destination + 1] = value.y;
        RecoveredMatrices[destination + 2] = value.z;
    }
}
