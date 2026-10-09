const assert = require('node:assert/strict');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const babel = require('@babel/core');
const React = require('react');

const componentNames = ['Button', 'Grid', 'Link', 'TextField', 'Typography', 'ExpansionPanel', 'ExpansionPanelSummary', 'ExpansionPanelDetails', 'LinearProgress'];
const material = Object.fromEntries(componentNames.map(name => [name, function Component() {}]));
function ActionDialog() {}
function ActionPanel() {}
function KebabMenu() {}
function GridPlugin() {}
const grid = Object.fromEntries(['Grid', 'Table', 'TableHeaderRow', 'TableFilterRow', 'PagingPanel', 'FilteringState', 'PagingState', 'CustomPaging'].map(name => [name, GridPlugin]));
const strings = require('../src/js/locales/advanced-tabs.en.json');

function sourceModule(filename, dependencies) {
  const exports = {};
  const compiled = babel.transformFileSync(path.resolve(__dirname, '../src/js', filename), {
    configFile: false, babelrc: false,
    presets: [[require.resolve('@babel/preset-env'), { targets: {node: 'current'} }], require.resolve('@babel/preset-typescript'), require.resolve('@babel/preset-react')],
    plugins: [require.resolve('@babel/plugin-proposal-class-properties')],
  }).code;
  // Keep page objects in the same realm as the real Immer state helper.
  // Only the supplied dependencies can reach API code; no request is made.
  vm.runInThisContext('(function(require, exports) {\n' + compiled + '\n})', {filename})(dependencies, exports);
  return exports;
}

const utils = sourceModule('utils.ts', name => {
  if (name === './locales/manager.en.json') return require('../src/js/locales/manager.en.json');
  return require(name);
});

function page(filename, props) {
  const Constructor = sourceModule(filename, name => {
    if (name === 'react') return React;
    if (name === '@material-ui/core') return material;
    if (name === '@material-ui/icons/ExpandMore') return function ExpandMore() {};
    if (name.startsWith('@devexpress/')) return grid;
    if (name === './reusable/action_dialog') return ActionDialog;
    if (name === './reusable/action_panel') return ActionPanel;
    if (name === './reusable/kebab_menu') return KebabMenu;
    if (name === './utils') return utils;
    if (name === './urls') return { APP_URLS: { MODULE_FOLDER: 'http://127.0.0.1/media/modules/', METADATA_SHEET: name => '/metadata/' + encodeURIComponent(name) } };
    if (name === './locales/advanced-tabs.en.json') return strings;
    if (name === './locales/curator.en.json') return require('../src/js/locales/curator.en.json');
    return require(name);
  }).default;
  const instance = new Constructor(props);
  instance.setState = (change, done) => {
    const update = typeof change === 'function' ? change(instance.state, instance.props) : change;
    instance.state = { ...instance.state, ...update };
    if (done) done();
  };
  return instance;
}

function nodes(node) {
  if (Array.isArray(node)) return node.flatMap(nodes);
  if (!React.isValidElement(node)) return [];
  return [node, ...nodes(node.props.children)];
}
function dialog(instance) {
  const open = nodes(instance.render()).find(node => node.type === ActionDialog && node.props.open);
  assert.ok(open, 'The working dialog must remain available');
  return open;
}
async function submit(instance) {
  const actions = dialog(instance).props.get_actions({current: null});
  await actions[actions.length - 1].props.onClick();
  await new Promise(resolve => setImmediate(resolve));
}
function allText(node) {
  if (Array.isArray(node)) return node.map(allText).join(' ');
  if (React.isValidElement(node)) return allText(node.props.children);
  return typeof node === 'string' || typeof node === 'number' ? String(node) : '';
}
const syntheticVersion = {id: 12, library_name: 'Synthetic catalogue', version_number: 'test', library_banner: 0, created_by: 1, metadata_types: []};
const versionsState = (overrides = {}) => ({library_versions: [syntheticVersion], library_versions_page: 0, library_versions_page_size: 5, library_versions_count: 1, ...overrides});

test('metadata network failure keeps the entered name and dialog, then allows retry', async () => {
  let fail = true;
  const instance = page('metadata.tsx', {metadata_api: {state: {metadata_types: []}, add_metadata_type: async () => { if (fail) throw undefined; }}, show_toast_message() {}});
  await instance.update_state(draft => { draft.modals.create_type.is_open = true; draft.modals.create_type.type_name = 'Synthetic subject'; });
  await submit(instance);
  assert.equal(instance.state.modals.create_type.type_name, 'Synthetic subject');
  assert.equal(instance.state.modals.create_type.is_open, true);
  assert.equal(instance.state.busy, false);
  assert.equal(instance.state.error, strings.request_failed);
  fail = false;
  await submit(instance);
  assert.equal(instance.state.modals.create_type.is_open, false);
});

test('failed image deletion retains confirmation and displays the direct HTTP error', async () => {
  const instance = page('library_assets.tsx', {library_assets_api: {state: {assets_by_group: {}}, delete_library_asset: async () => {throw {data: {error: 'Synthetic image failure'}};}}});
  await instance.update_state(draft => {
    draft.modals.delete_asset.is_open = true;
    draft.modals.delete_asset.to_delete = {id: 6, image_group: 1, image_file: null, file_name: 'synthetic-logo.png'};
    draft.modals.delete_asset.confirm_filename.value = 'synthetic-logo.png';
  });
  await submit(instance);
  assert.equal(instance.state.modals.delete_asset.is_open, true);
  assert.equal(instance.state.modals.delete_asset.confirm_filename.value, 'synthetic-logo.png');
  assert.equal(instance.state.error, 'Synthetic image failure');
  assert.equal(instance.state.busy, false);
});

test('adding a ZIP uses the add-file input and preserves it after a rejected upload', async () => {
  const calls = [];
  const zip = {name: 'synthetic-module.zip', type: ''};
  const instance = page('library_modules.tsx', {
    library_assets_api: {state: {assets_by_group: {}}},
    library_modules_api: {state: {library_modules: []}, add_module: async (...args) => { calls.push(args); throw {response: {data: {error: 'Synthetic upload failure'}}}; }},
  });
  await instance.update_state(draft => { draft.modals.add_module.is_open = true; draft.modals.add_module.module_name.value = 'Synthetic module'; });
  instance.add_module_file_ref.current = {files: {item: () => zip}};
  await submit(instance);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], 'Synthetic module');
  assert.equal(calls[0][1], zip);
  assert.equal(instance.add_module_file_ref.current.files.item(0), zip);
  assert.equal(instance.state.modals.add_module.is_open, true);
  assert.equal(instance.state.modals.add_module.module_name.value, 'Synthetic module');
  assert.equal(instance.state.error, 'Synthetic upload failure');
  assert.equal(instance.state.busy, false);
});

test('an invalid replacement ZIP keeps the module dialog and never calls the API', async () => {
  let requests = 0;
  const instance = page('library_modules.tsx', {
    library_assets_api: {state: {assets_by_group: {}}},
    library_modules_api: {state: {library_modules: []}, edit_module: async () => {requests++;}},
  });
  await instance.update_state(draft => { draft.modals.edit_module.is_open = true; draft.modals.edit_module.module_name.value = 'Synthetic module'; });
  instance.edit_module_file_ref.current = {files: {item: () => ({name: 'synthetic.txt', type: 'text/plain'})}};
  await submit(instance);
  assert.equal(requests, 0);
  assert.equal(instance.state.modals.edit_module.is_open, true);
  assert.equal(instance.state.error, strings.modules_zip_only);
});

test('failed export retains confirmation and never emits a success notification', async () => {
  const notices = [];
  const instance = page('library_images.tsx', {library_versions_api: {state: versionsState(), build_version: async () => {throw {data: {error: {detail: ['Synthetic export failure']}}};}}, show_toast_message: (...args) => notices.push(args)});
  await instance.update_state(draft => { draft.modals.build_version.is_open = true; draft.modals.build_version.to_build = syntheticVersion; draft.modals.build_version.name.value = syntheticVersion.library_name; });
  await submit(instance);
  assert.equal(instance.state.modals.build_version.is_open, true);
  assert.equal(instance.state.modals.build_version.name.value, syntheticVersion.library_name);
  assert.equal(instance.state.error, 'Synthetic export failure');
  assert.equal(instance.state.busy, false);
  assert.equal(notices.length, 0);
});

test('pending metadata requests lock fields and actions until completion', async () => {
  let finish;
  const pending = new Promise(resolve => {finish = resolve;});
  const instance = page('metadata.tsx', {metadata_api: {state: {metadata_types: []}, add_metadata_type: () => pending}, show_toast_message() {}});
  await instance.update_state(draft => { draft.modals.create_type.is_open = true; draft.modals.create_type.type_name = 'Synthetic language'; });
  const request = submit(instance);
  await new Promise(resolve => setImmediate(resolve));
  const open = dialog(instance);
  assert.ok(nodes(open).filter(node => node.type === material.TextField).every(node => node.props.disabled));
  assert.ok(open.props.get_actions({current: null}).every(button => button.props.disabled));
  instance.close_modals();
  assert.equal(instance.state.modals.create_type.is_open, true);
  finish();
  await request;
  assert.equal(instance.state.modals.create_type.is_open, false);
});

test('export pagination exposes later versions and hides controls for a single page', async () => {
  const calls = [];
  const api = {state: versionsState(), set_page: async next => {calls.push(next); api.state.library_versions_page = next;}};
  const instance = page('library_images.tsx', {library_versions_api: api, show_toast_message() {}});
  assert.equal(nodes(instance.render()).some(node => node.type === 'nav'), false);
  api.state.library_versions_count = 11;
  let navigation = nodes(instance.render()).find(node => node.type === 'nav');
  let buttons = nodes(navigation).filter(node => node.type === material.Button);
  assert.equal(buttons[0].props.disabled, true);
  assert.equal(buttons[1].props.disabled, false);
  await buttons[1].props.onClick();
  assert.deepEqual(calls, [1]);
  assert.match(allText(instance.render()), /Page 2 of 3/);
  api.state.library_versions_page = 2;
  navigation = nodes(instance.render()).find(node => node.type === 'nav');
  buttons = nodes(navigation).filter(node => node.type === material.Button);
  assert.equal(buttons[1].props.disabled, true);
});

test('missing disk data stays unavailable and failed refresh does not invent zero-capacity figures', async () => {
  const instance = page('system_info.tsx', {utils_api: {state: {disk_used: 0, disk_free: 0, disk_total: 0}, get_disk_info: async () => {throw undefined;}}});
  assert.ok(allText(instance.render()).includes(strings.system_unavailable));
  assert.equal(nodes(instance.render()).some(node => node.type === material.LinearProgress), false);
  await instance.refresh();
  assert.equal(instance.state.refreshing, false);
  assert.equal(instance.state.error, strings.system_failed);
  assert.equal(nodes(instance.render()).some(node => node.type === material.LinearProgress), false);
  instance.props.utils_api.state = {disk_used: 0, disk_free: 100, disk_total: 100};
  assert.equal(nodes(instance.render()).find(node => node.type === material.LinearProgress).props.value, 0);
});
