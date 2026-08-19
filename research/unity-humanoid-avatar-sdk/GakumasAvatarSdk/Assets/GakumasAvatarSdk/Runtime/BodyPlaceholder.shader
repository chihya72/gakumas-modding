// Carrier for the three body textures — never rendered with.
//
// The runtime clones the game's own material (for its shader and shared ramps) and moves these
// textures onto it, so all this shader has to do is *declare the properties*. That is not cosmetic:
// Unity silently drops Material.SetTexture for a property the shader does not have, and with
// `Standard` as the fallback none of _BaseMap/_DefMap/_ShadeMap existed — so nothing referenced the
// PNGs, the packer left every Texture2D out of the bundle, and the costume came out wearing the
// replaced character's own body texture.
Shader "GakumasSdk/BodyPlaceholder"
{
    Properties
    {
        _BaseMap ("Base (col)", 2D) = "white" {}
        _DefMap ("Def", 2D) = "white" {}
        _ShadeMap ("Shade (sdw)", 2D) = "white" {}
    }
    SubShader
    {
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            sampler2D _BaseMap;

            struct v2f
            {
                float4 position : SV_POSITION;
                float2 uv : TEXCOORD0;
            };

            v2f vert(appdata_base input)
            {
                v2f output;
                output.position = UnityObjectToClipPos(input.vertex);
                output.uv = input.texcoord;
                return output;
            }

            fixed4 frag(v2f input) : SV_Target
            {
                return tex2D(_BaseMap, input.uv);
            }
            ENDCG
        }
    }
}
