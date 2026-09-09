// Synthetic engine fixture, not Krunker source.
const bytes = new Uint8Array(
  '0061736d010000000105016000017f03020100070a0106616e7377657200000a06010400412a0b'
    .match(/../g).map(hex => parseInt(hex, 16)));
WebAssembly.instantiate(bytes).then(({instance}) => console.log('wasm', instance.exports.answer()));
