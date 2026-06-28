cbuffer cb0 : register(b0) { float4 cb0[141]; }
cbuffer cb1 : register(b1) { float4 cb1[43]; }
Texture2D<float4> GMIBaseColor  : register(t0);
Texture2D<float4> GMIPackedMask : register(t1);
Texture2D<float4> GMIShadeColor : register(t4);
SamplerState GMISampler : register(s0);

#define GMI_ALPHA_FLOOR  0.02
#define GMI_SHADE        0.90
#define GMI_AO           0.4
#define GMI_HILIGHT_CAP  0.70

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
  float4 base=GMIBaseColor.Sample(GMISampler,i.uv);
  clip(base.a-GMI_ALPHA_FLOOR);
  float4 pm=GMIPackedMask.Sample(GMISampler,i.uv);
  float4 sc=GMIShadeColor.Sample(GMISampler,i.uv);
  float3 col=base.rgb;
  col=lerp(col, col*sc.rgb, sc.a);
  col*=lerp(1.0, 1.0-pm.a, GMI_AO);
  col*=GMI_SHADE;
  float m=max(col.r,max(col.g,col.b));
  if(m>GMI_HILIGHT_CAP) col*=GMI_HILIGHT_CAP/m;
  o0=float4(0,0,16376.0*sqrt(saturate(i.pos.z)),256.0);
  o1=float4(col*base.a, base.a);
}
#endif
