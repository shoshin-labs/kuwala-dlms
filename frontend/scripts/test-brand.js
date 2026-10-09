const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { createHash } = require('node:crypto');

const root = resolve(__dirname, '../..');
const images = resolve(root, 'frontend/src/images');
const builtImages = resolve(root, 'frontend/static/images');
const bytes = (path) => readFileSync(path);
const hash = (value) => createHash('sha256').update(value).digest('hex');
const icons = ['favicon.svg', 'favicon-32.png', 'favicon.ico', 'apple-touch-icon.png'];

test('the manager uses the exact approved vector and generated icon copies', () => {
  const canonical = bytes(resolve(root, 'design/brand/kuwala-oasis.svg'));
  assert.equal(hash(canonical), '3fa3bf3bd3c07191e2180d05c016fc8faa1df72f0489edbc24dfa76d9fb7fce1');
  assert.deepEqual(bytes(resolve(images, 'kuwala-oasis.svg')), canonical);
  assert.deepEqual(bytes(resolve(images, 'favicon.svg')), bytes(resolve(root, 'design/brand/favicon.svg')));
  const expected = {
    'favicon.svg': 'fe083ab9dde0087ba89d4076d73caf49f6d215140154cd5d9e5032c99a1ec2c2',
    'favicon-32.png': 'a547cc0cfb5316d7790894cd22bb76a39e03894832d5be7c1e21031922438fef',
    'favicon.ico': '70de76efc49b7bd9d40d97b179f123993446ef3d8655ffcd7612f5a6ee29fc7e',
    'apple-touch-icon.png': 'a8fe64a8c7ac5eeafa22433aa81eff13dc00e8d2758395f117bdf7af7e385649',
  };
  for (const name of icons) assert.equal(hash(bytes(resolve(images, name))), expected[name], name);
});

test('the production build copies every approved asset without rewriting it', () => {
  for (const name of ['kuwala-oasis.svg', ...icons]) {
    assert.deepEqual(bytes(resolve(builtImages, name)), bytes(resolve(images, name)), name);
  }
  const html = bytes(resolve(root, 'frontend/static/index.html')).toString('utf8');
  for (const name of icons) assert.match(html, new RegExp(`href="/static/images/${name.replace('.', '\\.') }"`));
  assert.doesNotMatch(html, /href="[^"\s]*(?:https?:|\/\/)[^"\s]*favicon/);
});

test('browser icons contain the expected native pixel sizes', () => {
  for (const [name, size] of [['favicon-32.png', 32], ['apple-touch-icon.png', 180]]) {
    const png = bytes(resolve(images, name));
    assert.deepEqual(png.subarray(0, 8), Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
    assert.equal(png.readUInt32BE(16), size);
    assert.equal(png.readUInt32BE(20), size);
  }
  const ico = bytes(resolve(images, 'favicon.ico'));
  assert.equal(ico.readUInt16LE(0), 0);
  assert.equal(ico.readUInt16LE(2), 1);
  assert.equal(ico.readUInt16LE(4), 3);
  for (const [index, size] of [16, 32, 48].entries()) {
    const entry = 6 + index * 16;
    assert.equal(ico[entry], size);
    assert.equal(ico[entry + 1], size);
    const length = ico.readUInt32LE(entry + 8);
    const offset = ico.readUInt32LE(entry + 12);
    assert.ok(offset >= 54 && offset + length <= ico.length);
    assert.equal(ico.readUInt32BE(offset + 16), size);
    assert.equal(ico.readUInt32BE(offset + 20), size);
  }
});

test('the app logo is decorative and retains the readable product label', () => {
  const shell = bytes(resolve(root, 'frontend/src/js/oasis_app.tsx')).toString('utf8');
  assert.match(shell, /<img\s+className="brand-logo"\s+src="\/static\/images\/kuwala-oasis\.svg"\s+alt=""\s+aria-hidden="true"/);
  assert.match(shell, /<span className="brand-name">\{s\("product"\)\}<\/span>/);
});
