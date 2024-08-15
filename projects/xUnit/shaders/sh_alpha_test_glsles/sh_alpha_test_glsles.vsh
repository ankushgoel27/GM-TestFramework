// This shader tests the gm_AlphaTestEnabled/gm_AlphaRefValue built-in uniforms by tinting the output green if gm_AlphaTestEnabled is true,
// And making any pixels that have an alpha value under gm_AlphaRefValue completely transparent
// Vertex Shader

// Input values
attribute vec3 in_Position;                  // (x,y,z)
attribute vec4 in_Colour;                    // (r,g,b,a)
attribute vec2 in_TextureCoord;              // (u,v)

// Output values
varying vec2 v_vTexcoord;
varying vec4 v_vColour;


void main()
{
	// Calculate the vertex's position on screen using the world_view_projection matrix
    vec4 object_space_pos = vec4( in_Position.x, in_Position.y, in_Position.z, 1.0);
    gl_Position = gm_Matrices[MATRIX_WORLD_VIEW_PROJECTION] * object_space_pos;
    
	// Pass the vertex colour and texture coordinate to the fragment shader
    v_vColour = in_Colour;
    v_vTexcoord = in_TextureCoord;
}