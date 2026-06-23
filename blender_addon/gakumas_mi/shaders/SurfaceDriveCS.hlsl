ByteAddressBuffer AnimatedSource : register(t0);

Buffer<uint> SurfaceMap : register(t1);
RWBuffer<uint> DrivenVB0 : register(u0);

static const uint VertexCount = 17615;

float3 SourcePosition(uint index)
{
  return asfloat(AnimatedSource.Load3(index * 40));
}

float3 SourceNormal(uint index)
{
  return asfloat(AnimatedSource.Load3(index * 40 + 12));
}

float4 SourceTangent(uint index)
{
  return asfloat(AnimatedSource.Load4(index * 40 + 24));
}

[numthreads(64, 1, 1)]
void main(uint3 dispatchThreadId : SV_DispatchThreadID)
{
  uint vertexId = dispatchThreadId.x;
  if (vertexId >= VertexCount)
    return;

  uint mapElement = vertexId * 8;
  uint3 sourceIndex = uint3(
    SurfaceMap[mapElement],
    SurfaceMap[mapElement + 1],
    SurfaceMap[mapElement + 2]);
  float3 weight = asfloat(uint3(
    SurfaceMap[mapElement + 3],
    SurfaceMap[mapElement + 4],
    SurfaceMap[mapElement + 5]));
  float normalOffset = asfloat(SurfaceMap[mapElement + 6]);

  float3 position =
    SourcePosition(sourceIndex.x) * weight.x +
    SourcePosition(sourceIndex.y) * weight.y +
    SourcePosition(sourceIndex.z) * weight.z;
  float3 normal =
    SourceNormal(sourceIndex.x) * weight.x +
    SourceNormal(sourceIndex.y) * weight.y +
    SourceNormal(sourceIndex.z) * weight.z;
  float4 tangent =
    SourceTangent(sourceIndex.x) * weight.x +
    SourceTangent(sourceIndex.y) * weight.y +
    SourceTangent(sourceIndex.z) * weight.z;
  position += normalize(normal) * normalOffset;

  uint outputElement = vertexId * 10;
  DrivenVB0[outputElement] = asuint(position.x);
  DrivenVB0[outputElement + 1] = asuint(position.y);
  DrivenVB0[outputElement + 2] = asuint(position.z);
  DrivenVB0[outputElement + 3] = asuint(normal.x);
  DrivenVB0[outputElement + 4] = asuint(normal.y);
  DrivenVB0[outputElement + 5] = asuint(normal.z);
  DrivenVB0[outputElement + 6] = asuint(tangent.x);
  DrivenVB0[outputElement + 7] = asuint(tangent.y);
  DrivenVB0[outputElement + 8] = asuint(tangent.z);
  DrivenVB0[outputElement + 9] = asuint(tangent.w);
}
