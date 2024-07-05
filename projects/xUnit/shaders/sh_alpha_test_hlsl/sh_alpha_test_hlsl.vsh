//
// Simple passthrough vertex shader (HLSL 11)
//

struct VertexShaderInput {
    float4 vPosition : POSITION;
    float4 vColor    : COLOR0;
    float2 vTexcoord : TEXCOORD0;
};

struct VertexShaderOutput {
    float4 vPosition : SV_POSITION;
    float4 vColor    : COLOR0;
    float2 vTexcoord : TEXCOORD0;
};

int u_expected_alpha_test_enabled;
int u_expected_alpha_ref_value;


VertexShaderOutput main(VertexShaderInput INPUT) {
    VertexShaderOutput OUTPUT;

    float4 matrixWVP = mul(gm_Matrices[MATRIX_WORLD_VIEW_PROJECTION], INPUT.vPosition);

    OUTPUT.vPosition = matrixWVP;
    OUTPUT.vColor    = INPUT.vColor;
    OUTPUT.vTexcoord = INPUT.vTexcoord; 

    return OUTPUT;
}