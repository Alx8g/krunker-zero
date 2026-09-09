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
  const apply = Reflect.apply;
  const ownKeys = Reflect.ownKeys;
  const descriptor = Object.getOwnPropertyDescriptor;
  const property = Object.defineProperty;
  const arraySort = Array.prototype.sort;
  const string = String;
  const wellFormed = String.prototype.toWellFormed;
  // Define own array elements rather than invoking guest-replaced array methods
  // or inherited numeric setters on the private query list.
  const put = (list, value) => property(list, list.length, {
    value, writable: true, enumerable: true, configurable: true
  });
  const isObject = value => value !== null &&
    (typeof value === 'object' || typeof value === 'function');
  // Web IDL sequence conversion: get the iterator/next method once, and convert
  // each element before requesting the following element. Do not spread first.
  const sequence = (value, method, convert) => {
    if (typeof method !== 'function') throw new TypeError('Expected an iterable');
    const iterator = apply(method, value, []);
    if (!isObject(iterator)) throw new TypeError('Expected an iterator object');
    const next = iterator.next;
    const result = [];
    while (true) {
      const step = apply(next, iterator, []);
      if (!isObject(step)) throw new TypeError('Expected an iterator result object');
      if (step.done) return result;
      put(result, convert(step.value));
    }
  };
  const usv = value => {
    if (typeof value === 'symbol') throw new TypeError('Cannot convert Symbol to string');
    return apply(wellFormed, string(value), []);
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
      if (isObject(init)) {
        const method = init[Symbol.iterator];
        if (method !== undefined && method !== null) {
          const pairs = sequence(init, method, pair => {
            if (!isObject(pair)) throw new TypeError('Expected an iterable pair');
            return sequence(pair, pair[Symbol.iterator], usv);
          });
          for (let i = 0; i < pairs.length; i++) {
            if (pairs[i].length !== 2) throw new TypeError('Expected exactly two items');
            put(this.#pairs, pairs[i]);
          }
        } else {
          const keys = ownKeys(init);
          for (let i = 0; i < keys.length; i++) {
            const key = keys[i];
            if (!descriptor(init, key)?.enumerable) continue;
            // Record keys are converted before reading their value. USVString
            // normalization may make two JS keys equal; last value wins in place.
            const name = usv(key), value = usv(init[key]);
            let found = false;
            for (let j = 0; j < this.#pairs.length; j++) {
              if (this.#pairs[j][0] === name) {
                this.#pairs[j][1] = value; found = true; break;
              }
            }
            if (!found) put(this.#pairs, [name, value]);
          }
        }
      } else {
        let query = init === null ? '' : usv(init);
        if (query.startsWith('?')) query = query.slice(1);
        for (const part of query.split('&')) {
          if (!part) continue;
          const split = part.indexOf('=');
          put(this.#pairs, [decodeQuery(split < 0 ? part : part.slice(0, split)),
            decodeQuery(split < 0 ? '' : part.slice(split + 1))]);
        }
      }
    }
    get size() { return this.#pairs.length; }
    append(name, value) {
      const pairs = this.#pairs; // Brand-check before guest argument conversion.
      if (arguments.length < 2) throw new TypeError('Expected name and value');
      name = usv(name); value = usv(value);
      put(pairs, [name, value]);
    }
    get(name) {
      const pairs = this.#pairs;
      if (!arguments.length) throw new TypeError('Expected name');
      name = usv(name);
      for (let i = 0; i < pairs.length; i++) if (pairs[i][0] === name) return pairs[i][1];
      return null;
    }
    getAll(name) {
      const pairs = this.#pairs;
      if (!arguments.length) throw new TypeError('Expected name');
      name = usv(name); const result = [];
      for (let i = 0; i < pairs.length; i++) if (pairs[i][0] === name) put(result, pairs[i][1]);
      return result;
    }
    has(name, value) {
      const pairs = this.#pairs;
      if (!arguments.length) throw new TypeError('Expected name');
      name = usv(name); if (value !== undefined) value = usv(value);
      for (let i = 0; i < pairs.length; i++)
        if (pairs[i][0] === name && (value === undefined || pairs[i][1] === value)) return true;
      return false;
    }
    delete(name, value) {
      const pairs = this.#pairs;
      if (!arguments.length) throw new TypeError('Expected name');
      name = usv(name); if (value !== undefined) value = usv(value);
      // Keep list identity stable: a coercion or live iterator may retain it.
      let write = 0;
      for (let i = 0; i < pairs.length; i++)
        if (pairs[i][0] !== name || (value !== undefined && pairs[i][1] !== value))
          pairs[write++] = pairs[i];
      pairs.length = write;
    }
    set(name, value) {
      const pairs = this.#pairs;
      if (arguments.length < 2) throw new TypeError('Expected name and value');
      name = usv(name); value = usv(value); let found = false, write = 0;
      for (let i = 0; i < pairs.length; i++) {
        const pair = pairs[i];
        if (pair[0] === name) {
          if (found) continue;
          pair[1] = value; found = true;
        }
        pairs[write++] = pair;
      }
      pairs.length = write;
      if (!found) put(pairs, [name, value]);
    }
    sort() {
      apply(arraySort, this.#pairs, [(a,b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0]);
    }
    entries() {
      const pairs = this.#pairs; // Validate now, not at the generator's first next().
      return (function* () {
        for (let i = 0; i < pairs.length; i++) yield [pairs[i][0], pairs[i][1]];
      })();
    }
    keys() {
      const pairs = this.#pairs;
      return (function* () { for (let i = 0; i < pairs.length; i++) yield pairs[i][0]; })();
    }
    values() {
      const pairs = this.#pairs;
      return (function* () { for (let i = 0; i < pairs.length; i++) yield pairs[i][1]; })();
    }
    forEach(callback, thisArg) {
      const pairs = this.#pairs;
      if (typeof callback !== 'function') throw new TypeError('Expected callback');
      for (let i = 0; i < pairs.length; i++)
        apply(callback, thisArg, [pairs[i][1], pairs[i][0], this]);
    }
    toString() {
      const pairs = this.#pairs; let result = '';
      for (let i = 0; i < pairs.length; i++)
        result += (i ? '&' : '') + encodeQuery(pairs[i][0]) + '=' + encodeQuery(pairs[i][1]);
      return result;
    }
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
