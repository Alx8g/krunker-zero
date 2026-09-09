// Optional diagnostic profile. This is NOT a Window/DOM implementation.
// Only this closure can reach the native binding after bootstrap completes.
(() => {
  'use strict';
  const host = globalThis.__zeroNative;
  delete globalThis.__zeroNative;
  const define = (name, value) => Object.defineProperty(globalThis, name, {
    value, writable: true, configurable: true, enumerable: false
  });
  const functionOnly = (fn, name) => {
    if (typeof fn !== 'function')
      throw new TypeError(`${name}: only function callbacks are implemented`);
    return fn;
  };
  const delay = value => {
    const n = Number(value);
    return !Number.isFinite(n) || n < 0 || n > 2147483647 ? 0 : Math.trunc(n);
  };
  const cancel = id => {
    const n = Number(id);
    if (Number.isSafeInteger(n) && n > 0) host.cancel(n);
  };
  define('console', Object.freeze(Object.fromEntries(
    ['log', 'info', 'warn', 'error'].map(level =>
      [level, (...args) => host.log(level, args.map(String).join(' '))])
  )));
  define('performance', Object.freeze({now: () => host.now()}));
  define('setTimeout', (fn, ms = 0, ...args) => {
    functionOnly(fn, 'setTimeout');
    return host.schedule(() => Reflect.apply(fn, globalThis, args), delay(ms), false, false);
  });
  define('setInterval', (fn, ms = 0, ...args) => {
    functionOnly(fn, 'setInterval');
    return host.schedule(() => Reflect.apply(fn, globalThis, args), delay(ms), true, false);
  });
  define('clearTimeout', cancel);
  define('clearInterval', cancel);
  define('requestAnimationFrame', fn => {
    functionOnly(fn, 'requestAnimationFrame');
    return host.schedule(fn, 0, false, true);
  });
  define('cancelAnimationFrame', cancel);
  // These two aliases do not pretend to implement the Window interface.
  define('window', globalThis);
  define('self', globalThis);
})();
