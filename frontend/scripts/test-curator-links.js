const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');
const vm = require('node:vm');
const {readFileSync} = require('node:fs');
const babel = require('@babel/core');
const React = require('react');
const english = require('../src/js/locales/en.json').strings;

function links(base, strings = english) {
  const context = {exports: {}, require(name) {
    if (name === 'react') return React;
    if (name === './app_paths') return {appBase: () => base};
    if (name === './i18n') return {useStrings: () => key => strings[key]};
    throw new Error('Unexpected import: ' + name);
  }};
  vm.runInNewContext(babel.transformFileSync(path.resolve(__dirname, '../src/js/curator_links.tsx'), {
    configFile: false, babelrc: false,
    presets: [[require.resolve('@babel/preset-env'), {targets: {node: 'current'}}],
      require.resolve('@babel/preset-typescript'), require.resolve('@babel/preset-react')],
  }).code, context);
  return React.Children.toArray(context.exports.default().props.children);
}

test('manager links reach local Oasis on the box and the existing Oasis origin in root deployments', () => {
  for (const [base, expected] of [['/manage/', '/'], ['/', 'https://oasis.kuwala.space/']]) {
    const [oasis, central] = links(base);
    assert.equal(oasis.type, 'a');
    assert.equal(oasis.props.href, expected);
    assert.equal(central.type, 'a');
    assert.equal(central.props.href, 'https://library.kuwala.space/');
    for (const item of [oasis, central]) {
      assert.equal(item.props.target, '_blank');
      assert.equal(item.props.rel, 'noopener noreferrer');
      assert.equal(item.props.className, 'nav-button');
      assert.equal(item.props['aria-label'], item.props.title);
    }
  }
});

test('central library navigation uses language resources and describes discovery and drafts honestly', () => {
  assert.match(english.central_library_help, /discover sources.*pack drafts/);
  assert.match(english.central_library_help, /Internet and curator sign-in/);
  assert.doesNotMatch(english.central_library_help, /install|publish|sync|download/i);
  const translated = {...english, central_library: 'Synthetic translated label', central_library_help: 'Synthetic translated explanation'};
  const central = links('/manage/', translated)[1];
  const label = React.Children.toArray(central.props.children).find(node => node.type === 'span');
  assert.equal(label.props.children, translated.central_library);
  assert.equal(central.props.title, translated.central_library_help);
  const shell = readFileSync(path.resolve(__dirname, '../src/js/oasis_app.tsx'), 'utf8');
  assert.match(shell, /config\.curator_enabled && <CuratorLinks\s*\/>/);
});
