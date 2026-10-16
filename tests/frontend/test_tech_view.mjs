import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
test('Driver-only app excludes retired Simulation and Technical views', async () => {
 const source = await readFile(new URL('../../backend/app/static/demo/js/app.js', import.meta.url), 'utf8');
 assert.doesNotMatch(source, /from ['"].*(?:sim_mode|tech_view)\.js/);
});
