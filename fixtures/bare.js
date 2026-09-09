// Synthetic fixture. ECMAScript itself needs no browser host.
const vertices = new Float32Array([0, 0, 0, 1, 0, 0]);
if (vertices.length !== 6) throw new Error('typed array failed');
if (typeof document !== 'undefined') throw new Error('unexpected DOM');
