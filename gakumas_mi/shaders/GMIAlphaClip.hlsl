cbuffer cb0 : register(b0)
{
    float4 cb0[141];
}

cbuffer cb1 : register(b1)
{
    float4 cb1[43];
}

cbuffer cb2 : register(b2)
{
    float4 cb2[18];
}

Texture2D<float4> GMIBaseColor : register(t0);
SamplerState GMIBaseColorSampler : register(s0);

#ifndef GMI_ALPHA_CUTOFF
#define GMI_ALPHA_CUTOFF 0.5
#endif

struct VSOut
{
    float4 pos : SV_Position0;
    float2 uv : TEXCOORD0;
};

#ifdef VERTEX_SHADER
void main(
    float4 position : POSITION0,
    float3 normal : NORMAL0,
    float4 tangent : TANGENT0,
    float4 texcoord0 : TEXCOORD0,
    float2 texcoord1 : TEXCOORD1,
    float4 color : COLOR0,
    float3 outlinePosition : TEXCOORD4,
    out VSOut output)
{
    output.uv = texcoord0.xy;

    float4 world;
    world.xyz = cb1[0].xyz * position.x + cb1[1].xyz * position.y
        + cb1[2].xyz * position.z + cb1[3].xyz;
    world.w = 1.0;

    output.pos = cb0[77] * world.x + cb0[78] * world.y
        + cb0[79] * world.z + cb0[80];
}
#endif

#ifdef PIXEL_SHADER
void main(VSOut input, out float4 output : SV_Target0)
{
    float4 color = GMIBaseColor.Sample(GMIBaseColorSampler, input.uv);
    clip(color.a - GMI_ALPHA_CUTOFF);
    color.a = 1.0;
    output = color;
}
#endif
