// Independent native-window fixture. NOT Krunker or browser API conformance.
// Visible for 300 scheduled frames or until Esc/window close. Click to capture
// the pointer while foreground; Escape or focus loss releases it.
'use strict';
const canvas = zeroWindow.create(640, 480);
const gl = canvas.getContext('webgl');
function shader(type, source) {
  const s = gl.createShader(type);
  gl.shaderSource(s, source); gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(s));
  return s;
}
const program = gl.createProgram();
gl.attachShader(program, shader(gl.VERTEX_SHADER,
  'attribute vec2 pos;uniform vec4 shift;void main(){gl_Position=vec4(pos+shift.xy,0.0,1.0);}'));
gl.attachShader(program, shader(gl.FRAGMENT_SHADER,
  'precision mediump float;uniform vec4 tint;void main(){gl_FragColor=tint;}'));
gl.linkProgram(program);
if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program));
gl.useProgram(program);
const buffer=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-.65,-.6,.65,-.6,0,.65]),gl.STATIC_DRAW);
const position=gl.getAttribLocation(program,'pos'); gl.enableVertexAttribArray(position);
gl.vertexAttribPointer(position,2,gl.FLOAT,false,0,0);
const phase=gl.getUniformLocation(program,'shift'),tint=gl.getUniformLocation(program,'tint');
let frames=0, inputEvents=0, rawMouseEvents=0;
function frame(now) {
  for (const event of zeroWindow.pollEvents()) {
    inputEvents++;
    if (event.type==='rawmousemove') rawMouseEvents++;
    if (event.type==='mousedown' && event.code===0) zeroWindow.capturePointer(true);
    if (event.type==='keydown' && event.code===27) {
      zeroWindow.capturePointer(false); zeroWindow.close(); return;
    }
  }
  gl.viewport(0,0,canvas.width,canvas.height);
  gl.clearColor(.02,.025,.04,1); gl.clear(gl.COLOR_BUFFER_BIT);
  gl.uniform4f(phase,.15*Math.sin(now/500),0,0,0); gl.uniform4f(tint,.2,.55+.35*Math.sin(now/900),.95,1);
  gl.drawArrays(gl.TRIANGLES,0,3);
  if(gl.getError()!==gl.NO_ERROR) throw Error('native window rendering error');
  zeroWindow.present(canvas);
  if (++frames < 300) requestAnimationFrame(frame);
  else {
    zeroWindow.capturePointer(false);
    console.log('WINDOW_FIXTURE_FINISHED',JSON.stringify({scheduledFrames:frames,inputEvents,rawMouseEvents}));
  }
}
requestAnimationFrame(frame);
