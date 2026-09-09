// An independent graphics fixture, NOT Krunker code. Real shaders and pixels.
const canvas = new OffscreenCanvas(128, 128);
const gl = canvas.getContext('webgl');
if (!gl) throw Error('Native graphics unavailable');
function shader(type, source) {
  const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);
  if (!gl.getShaderParameter(s,gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(s));
  return s;
}
const vertex=shader(gl.VERTEX_SHADER,`attribute vec2 position;
varying vec3 color;
void main(){gl_Position=vec4(position,0.0,1.0);color=vec3(position.x*0.5+0.5,position.y*0.5+0.5,0.65);}`);
const fragment=shader(gl.FRAGMENT_SHADER,`precision mediump float;
varying vec3 color;void main(){gl_FragColor=vec4(color,1.0);}`);
const program=gl.createProgram();gl.attachShader(program,vertex);gl.attachShader(program,fragment);gl.linkProgram(program);
if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
gl.useProgram(program);
const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-0.8,-0.75,0.8,-0.75,0,0.8]),gl.STATIC_DRAW);
const position=gl.getAttribLocation(program,'position');
gl.enableVertexAttribArray(position);gl.vertexAttribPointer(position,2,gl.FLOAT,false,0,0);
gl.clearColor(0.025,0.03,0.045,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
gl.drawArrays(gl.TRIANGLES,0,3);
const pixels=new Uint8Array(canvas.width*canvas.height*4);
gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
if(gl.getError()!==gl.NO_ERROR)throw Error('Native graphics error');
console.log('FRAME_RGBA8',canvas.width,canvas.height);
for(let y=0;y<canvas.height;y++)console.log('ROW',y,Array.from(pixels.subarray(y*canvas.width*4,(y+1)*canvas.width*4),b=>b.toString(16).padStart(2,'0')).join(''));
