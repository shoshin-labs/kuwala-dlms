const assert = require('node:assert/strict');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const babel = require('@babel/core');
const compiled = babel.transformFileSync(path.resolve(__dirname, '../src/js/version_move_safety.ts'), {
  configFile: false, babelrc: false,
  presets: [[require.resolve('@babel/preset-env'), { targets: { node: 'current' } }], require.resolve('@babel/preset-typescript')],
});
const context = { exports: {}, Set, Number, Promise };
vm.runInNewContext(compiled.code, context);
const { folderDestinationAllowed, transferMembership } = context.exports;

test('moving or copying into self and descendants is refused, including deeper sections', () => {
  const folders = [{ id: 1, parent: null }, { id: 2, parent: 1 }, { id: 3, parent: 2 }, { id: 4, parent: null }];
  assert.equal(folderDestinationAllowed(1, folders[0], folders), false);
  assert.equal(folderDestinationAllowed(1, folders[2], folders), false);
  assert.equal(folderDestinationAllowed(2, folders[2], folders), false);
  assert.equal(folderDestinationAllowed(2, folders[3], folders), true);
  assert.equal(folderDestinationAllowed(3, folders[1], folders), true);
});

test('missing and already-corrupt destination paths fail closed', () => {
  const folders = [{ id: 4, parent: 5 }, { id: 5, parent: 4 }, { id: 6, parent: 999 }];
  assert.equal(folderDestinationAllowed(1, folders[0], folders), false);
  assert.equal(folderDestinationAllowed(1, folders[2], folders), false);
  assert.equal(folderDestinationAllowed(1, { id: 0, parent: null }, folders), false);
  assert.equal(folderDestinationAllowed(1, { id: 8, parent: null, breadcrumb: [{ id: 1 }] }, folders), false);
});

test('failed destination write never removes the source membership', async () => {
  const memberships = new Set(['source']);
  await assert.rejects(transferMembership(async () => { throw new Error('destination failed'); }, async () => {
    memberships.delete('source');
  }), /destination failed/);
  assert.deepEqual([...memberships], ['source']);
});

test('failed source removal preserves both memberships so an original cannot disappear', async () => {
  const memberships = new Set(['source']);
  await assert.rejects(transferMembership(async () => { memberships.add('destination'); }, async () => {
    throw new Error('source removal failed');
  }), /source removal failed/);
  assert.deepEqual([...memberships], ['source', 'destination']);
});

test('successful transfer retains only the new membership after it has been established', async () => {
  const memberships = new Set(['source']);
  await transferMembership(async () => { memberships.add('destination'); }, async () => {
    assert.equal(memberships.has('destination'), true);
    memberships.delete('source');
  });
  assert.deepEqual([...memberships], ['destination']);
});
