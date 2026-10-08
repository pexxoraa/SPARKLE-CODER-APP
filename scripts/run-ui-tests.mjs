/**
 * Execute every standalone UI regression test, not just a manually maintained
 * list in package.json. Tests historically use Node's assert and execute as
 * scripts (they are not all node:test suites).
 */
import {readdirSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const testsDir = join(root, 'tests');
const tests = readdirSync(testsDir, {withFileTypes: true})
  .filter(entry => entry.isFile() && /^test_ui_[a-z0-9_-]+\.js$/.test(entry.name))
  .map(entry => entry.name)
  .sort();

if (!tests.length) {
  console.error('No UI regression tests found in tests/test_ui_*.js.');
  process.exitCode = 1;
} else {
  const failures = [];
  for (const test of tests) {
    console.log('\nUI TEST ' + test);
    const result = spawnSync(process.execPath, [join(testsDir, test)], {
      cwd: root,
      stdio: 'inherit',
      env: process.env,
      timeout: 120000,
    });
    if (result.error || result.status !== 0) {
      console.error('FAILED ' + test + ': ' +
        (result.error?.message || (result.signal ? 'signal ' + result.signal : 'exit ' + result.status)));
      failures.push(test);
    }
  }
  console.log('\nUI REGRESSION SUMMARY: ' + (tests.length - failures.length) + '/' + tests.length + ' passed');
  if (failures.length) {
    console.error('Failed tests: ' + failures.join(', '));
    process.exitCode = 1;
  }
}
