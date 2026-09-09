// Synthetic fixture, NOT a graphics/FPS benchmark.
console.log('boot');
Promise.resolve().then(() => console.log('microtask'));
setTimeout(() => console.log('timer', performance.now()), 5);
requestAnimationFrame(timestamp => console.log('frame', timestamp));
