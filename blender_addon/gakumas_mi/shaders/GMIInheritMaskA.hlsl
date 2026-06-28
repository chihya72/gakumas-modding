cbuffer cb0 : register(b0) { float4 cb0[141]; }
cbuffer cb1 : register(b1) { float4 cb1[43]; }
Texture2D<float4> GMIBaseColor : register(t0);
SamplerState GMISampler : register(s0);

#define GMI_ALPHA_FLOOR 0.02

struct VSOut { float4 pos:SV_Position0; float2 uv:TEXCOORD0; };
#ifdef VERTEX_SHADER
void main(float4 position:POSITION0, float3 n:NORMAL0, float4 t:TANGENT0,
  float4 tc0:TEXCOORD0, float2 tc1:TEXCOORD1, float4 c:COLOR0, float3 op:TEXCOORD4, out VSOut o){
  o.uv=tc0.xy;
  float4 w; w.xyz=cb1[0].xyz*position.x+cb1[1].xyz*position.y+cb1[2].xyz*position.z+cb1[3].xyz; w.w=1;
  o.pos=cb0[77]*w.x+cb0[78]*w.y+cb0[79]*w.z+cb0[80];
}
#endif
#ifdef PIXEL_SHADER
void main(VSOut i, out float4 o0:SV_Target0, out float4 o1:SV_Target1){
  float a=GMIBaseColor.Sample(GMISampler,i.uv).a;
  clip(a-GMI_ALPHA_FLOOR);
  o0=float4(0,0,0,0);
  o1=float4(0,0,0,0);
}
#endif
