// Original fe50b7a82b0f37be body VS with only surface reconstruction injected.
cbuffer cb2 : register(b2)
{
  float4 cb2[18];
}

cbuffer cb1 : register(b1)
{
  float4 cb1[43];
}

cbuffer cb0 : register(b0)
{
  float4 cb0[141];
}

#define cmp -
ByteAddressBuffer AnimatedSource : register(t120);
Buffer<uint> SurfaceMap : register(t121);
Texture2D<float4> StereoParams : register(t125);

float3 SourcePosition(uint index)
{
  return asfloat(AnimatedSource.Load3(index * 40));
}

float3 SourceNormal(uint index)
{
  return asfloat(AnimatedSource.Load3(index * 40 + 12));
}

void main(
  float4 v0 : POSITION0,
  float3 v1 : NORMAL0,
  float4 v2 : TANGENT0,
  float4 v3 : TEXCOORD0,
  float2 v4 : TEXCOORD1,
  float4 v5 : COLOR0,
  float3 v6 : TEXCOORD4,
  uint vertexId : SV_VertexID,
  out float4 o0 : TEXCOORD0,
  out float3 o1 : TEXCOORD1,
  out float4 o2 : COLOR0,
  out float4 o3 : TEXCOORD2,
  out float4 o4 : TEXCOORD3,
  out float4 o5 : TEXCOORD4,
  out float4 o6 : TEXCOORD6,
  out float4 o7 : TEXCOORD7,
  out float4 o8 : TEXCOORD8,
  out float4 o9 : SV_POSITION0)
{
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
  float3 p0 = SourcePosition(sourceIndex.x);
  float3 p1 = SourcePosition(sourceIndex.y);
  float3 p2 = SourcePosition(sourceIndex.z);
  // Identity diagnostic: preserve the game's original IA normal while only
  // reconstructing position. This isolates raw-SRV normal reads from mapping.
  float3 offsetNormal = normalize(v1);
  v0.xyz = p0 * weight.x + p1 * weight.y + p2 * weight.z + offsetNormal * normalOffset;
  float4 r0,r1,r2,r3;
  uint4 bitmask, uiDest;
  float4 fDest;

  o0.xy = v3.xy * cb2[0].xy + cb2[0].zw;
  o0.zw = v4.xy;
  r0.xyz = cb1[1].xyz * v0.yyy;
  r0.xyz = cb1[0].xyz * v0.xxx + r0.xyz;
  r0.xyz = cb1[2].xyz * v0.zzz + r0.xyz;
  r0.xyz = cb1[3].xyz + r0.xyz;
  o1.xyz = r0.xyz;
  r1.xyzw = v5.xyzw * float4(15.9375,15.9375,15.9375,15.9375) + float4(0.03125,0.03125,0.03125,0.03125);
  r1.xyzw = floor(r1.xyzw);
  r2.xyzw = float4(16,16,16,16) * r1.xyzw;
  r2.xyzw = v5.xzyw * float4(255,255,255,255) + -r2.xzyw;
  r3.yw = r2.xz;
  r3.xz = r1.xy;
  r2.xz = r1.zw;
  o3.xyzw = float4(0.0666666701,0.0666666701,0.0666666701,0.0666666701) * r2.xyzw;
  o2.xyzw = float4(0.0666666701,0.0666666701,0.0666666701,0.0666666701) * r3.xyzw;
  r1.x = dot(v1.xyz, cb1[4].xyz);
  r1.y = dot(v1.xyz, cb1[5].xyz);
  r1.z = dot(v1.xyz, cb1[6].xyz);
  r0.w = dot(r1.xyz, r1.xyz);
  r0.w = max(1.17549435e-38, r0.w);
  r0.w = rsqrt(r0.w);
  o4.xyz = r1.xyz * r0.www;
  r1.xyz = cb2[10].xyz * v1.yyy;
  r1.xyz = cb2[9].xyz * v1.xxx + r1.xyz;
  o5.xyz = cb2[11].xyz * v1.zzz + r1.xyz;
  r1.xyz = cb0[138].xyz * r0.yyy;
  r1.xyz = cb0[137].xyz * r0.xxx + r1.xyz;
  r1.xyz = cb0[139].xyz * r0.zzz + r1.xyz;
  o6.xyz = cb0[140].xyz + r1.xyz;
  o6.w = 0;
  r1.xyzw = cb1[1].xyzw * v0.yyyy;
  r1.xyzw = cb1[0].xyzw * v0.xxxx + r1.xyzw;
  r1.xyzw = cb1[2].xyzw * v0.zzzz + r1.xyzw;
  r1.xyzw = cb1[3].xyzw + r1.xyzw;
  r2.xyzw = cb0[93].xyzw * r1.yyyy;
  r2.xyzw = cb0[92].xyzw * r1.xxxx + r2.xyzw;
  r2.xyzw = cb0[94].xyzw * r1.zzzz + r2.xyzw;
  o7.xyzw = cb0[95].xyzw * r1.wwww + r2.xyzw;
  r0.w = cb2[17].z + cb1[42].x;
  r0.w = cmp(r0.w >= 1);
  r1.xyz = r0.www ? v6.xyz : v0.xyz;
  r2.xyzw = cb1[35].xyzw * r1.yyyy;
  r2.xyzw = cb1[34].xyzw * r1.xxxx + r2.xyzw;
  r1.xyzw = cb1[36].xyzw * r1.zzzz + r2.xyzw;
  r1.xyzw = cb1[37].xyzw + r1.xyzw;
  r2.xyzw = cb0[89].xyzw * r1.yyyy;
  r2.xyzw = cb0[88].xyzw * r1.xxxx + r2.xyzw;
  r2.xyzw = cb0[90].xyzw * r1.zzzz + r2.xyzw;
  o8.xyzw = cb0[91].xyzw * r1.wwww + r2.xyzw;
  r1.xyzw = cb0[78].xyzw * r0.yyyy;
  r1.xyzw = cb0[77].xyzw * r0.xxxx + r1.xyzw;
  r0.xyzw = cb0[79].xyzw * r0.zzzz + r1.xyzw;
  o9.xyzw = cb0[80].xyzw + r0.xyzw;
  return;
}
