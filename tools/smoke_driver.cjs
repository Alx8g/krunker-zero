'use strict';
// One guest run per process. Node is only a development fixture runner.
const fs = require('node:fs');
const path = require('node:path');
const binding = require(path.resolve(process.argv[2]));
try {
  const input = fs.readFileSync(0, 'utf8');
  const report = binding.run(input);
  process.stdout.write(report + '\n');
  process.exitCode = JSON.parse(report).exit_code;
} catch (error) {
  process.stderr.write(String(error.stack || error) + '\n');
  process.exitCode = 70;
}
