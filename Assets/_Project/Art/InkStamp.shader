// Shader tối giản để "chấm mực" vào RenderTexture qua Graphics.DrawTexture.
// Chạy trực tiếp bằng GL low-level nên hoạt động độc lập với render pipeline (URP an toàn).
// Alpha lấy từ kênh alpha của stamp (vết mực mềm), màu lấy từ _Color.
Shader "ARtifact/InkStamp"
{
    Properties
    {
        _MainTex ("Stamp (alpha)", 2D) = "white" {}
        _Color ("Ink Color", Color) = (0.09, 0.07, 0.06, 1)
    }
    SubShader
    {
        Tags { "Queue" = "Transparent" "RenderType" = "Transparent" }
        Blend SrcAlpha OneMinusSrcAlpha
        Cull Off
        ZWrite Off
        ZTest Always

        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            struct appdata
            {
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;
            };

            struct v2f
            {
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
            };

            sampler2D _MainTex;
            float4 _MainTex_ST;
            fixed4 _Color;

            v2f vert(appdata v)
            {
                v2f o;
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                return o;
            }

            fixed4 frag(v2f i) : SV_Target
            {
                fixed a = tex2D(_MainTex, i.uv).a * _Color.a;
                return fixed4(_Color.rgb, a);
            }
            ENDCG
        }
    }
}
