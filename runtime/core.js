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

  // Observed FRVR channel detection contract. No URL/location/DOM is invented.
  // Query parsing follows application/x-www-form-urlencoded with forgiving UTF-8.
  const usv = value => {
    if (typeof value === 'symbol') throw new TypeError('Cannot convert Symbol to string');
    return String(value).toWellFormed();
  };
  const decodeQuery = text => {
    // Preserve percent-encoded bytes from the input, including malformed UTF-8.
    const bytes = [];
    const source = text.replace(/\+/g, ' ');
    for (let i = 0; i < source.length;) {
      if (source[i] === '%' && /^[0-9a-f]{2}$/i.test(source.slice(i + 1, i + 3))) {
        bytes.push(parseInt(source.slice(i + 1, i + 3), 16)); i += 3;
      } else {
        const cp = source.codePointAt(i); i += cp > 65535 ? 2 : 1;
        for (const part of encodeURIComponent(String.fromCodePoint(cp)).match(/%[0-9A-F]{2}|./g))
          bytes.push(part[0] === '%' ? parseInt(part.slice(1), 16) : part.charCodeAt(0));
      }
    }
    let out = '', needed = 0, seen = 0, point = 0, lower = 128, upper = 191;
    for (let i = 0; i < bytes.length; i++) {
      const b = bytes[i];
      if (!needed) {
        if (b <= 127) { out += String.fromCharCode(b); continue; }
        if (b >= 194 && b <= 223) { needed = 1; point = b & 31; }
        else if (b >= 224 && b <= 239) {
          needed = 2; point = b & 15;
          if (b === 224) lower = 160;
          if (b === 237) upper = 159;
        } else if (b >= 240 && b <= 244) {
          needed = 3; point = b & 7;
          if (b === 240) lower = 144;
          if (b === 244) upper = 143;
        } else out += '\uFFFD';
      } else if (b < lower || b > upper) {
        needed = seen = point = 0; lower = 128; upper = 191;
        out += '\uFFFD'; i--;
      } else {
        lower = 128; upper = 191; point = (point << 6) | (b & 63);
        if (++seen === needed) {
          out += String.fromCodePoint(point); needed = seen = point = 0;
        }
      }
    }
    if (needed) out += '\uFFFD';
    return out;
  };
  const encodeQuery = value => encodeURIComponent(value).replace(/[!'()~]/g,
    c => '%' + c.charCodeAt(0).toString(16).toUpperCase()).replace(/%20/g, '+');
  class URLSearchParams {
    #pairs = [];
    constructor(init = '') {
      if (init !== null && typeof init === 'object') {
        if (init[Symbol.iterator] !== undefined) {
          for (const pair of init) {
            if (pair === null || typeof pair !== 'object' || !pair[Symbol.iterator])
              throw new TypeError('Expected an iterable pair');
            const values = [...pair];
            if (values.length !== 2) throw new TypeError('Expected exactly two items');
            this.#pairs.push([usv(values[0]), usv(values[1])]);
          }
        } else for (const key of Object.keys(init)) this.#pairs.push([usv(key), usv(init[key])]);
      } else {
        let query = init === null ? '' : usv(init);
        if (query.startsWith('?')) query = query.slice(1);
        for (const part of query.split('&')) {
          if (!part) continue;
          const split = part.indexOf('=');
          this.#pairs.push([decodeQuery(split < 0 ? part : part.slice(0, split)),
            decodeQuery(split < 0 ? '' : part.slice(split + 1))]);
        }
      }
    }
    get size() { return this.#pairs.length; }
    append(name, value) {
      if (arguments.length < 2) throw new TypeError('Expected name and value');
      this.#pairs.push([usv(name), usv(value)]);
    }
    get(name) {
      if (!arguments.length) throw new TypeError('Expected name');
      name = usv(name); return this.#pairs.find(p => p[0] === name)?.[1] ?? null;
    }
    getAll(name) {
      if (!arguments.length) throw new TypeError('Expected name');
      name = usv(name); return this.#pairs.filter(p => p[0] === name).map(p => p[1]);
    }
    has(name, value) {
      if (!arguments.length) throw new TypeError('Expected name');
      name = usv(name); if (value !== undefined) value = usv(value);
      return this.#pairs.some(p => p[0] === name && (value === undefined || p[1] === value));
    }
    delete(name, value) {
      if (!arguments.length) throw new TypeError('Expected name');
      name = usv(name); if (value !== undefined) value = usv(value);
      this.#pairs = this.#pairs.filter(p => p[0] !== name || (value !== undefined && p[1] !== value));
    }
    set(name, value) {
      if (arguments.length < 2) throw new TypeError('Expected name and value');
      name = usv(name); value = usv(value); let found = false;
      this.#pairs = this.#pairs.filter(p => {
        if (p[0] !== name) return true;
        if (found) return false;
        p[1] = value; found = true; return true;
      });
      if (!found) this.#pairs.push([name, value]);
    }
    sort() { this.#pairs.sort((a,b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0); }
    *entries() { for (let i=0;i<this.#pairs.length;i++) yield [...this.#pairs[i]]; }
    *keys() { for (const pair of this.entries()) yield pair[0]; }
    *values() { for (const pair of this.entries()) yield pair[1]; }
    forEach(callback, thisArg) {
      if (typeof callback !== 'function') throw new TypeError('Expected callback');
      for (const [name,value] of this.entries()) Reflect.apply(callback,thisArg,[value,name,this]);
    }
    toString() { return this.#pairs.map(p => encodeQuery(p[0])+'='+encodeQuery(p[1])).join('&'); }
  }
  Object.defineProperty(URLSearchParams.prototype, Symbol.iterator, {value: URLSearchParams.prototype.entries, writable:true, configurable:true});
  Object.defineProperty(URLSearchParams.prototype, Symbol.toStringTag, {value:'URLSearchParams', configurable:true});
  define('URLSearchParams', URLSearchParams);

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
