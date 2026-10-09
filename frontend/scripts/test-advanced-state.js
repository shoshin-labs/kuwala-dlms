const assert = require('node:assert/strict');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const babel = require('@babel/core');
const React = require('react');

function adapter(axios) {
  class FormData { constructor() { this.values = new Map(); } append(key, value) { this.values.set(key, value); } }
  const urls = { LIBRARY_VERSION_CLONE: id => `/clone/${id}`, LIBRARY_MODULE: id => `/module/${id}`, CSRF_TOKEN: '/csrf', LIBRARY_VERSIONS: () => '/versions', LIBRARY_ASSETS: '/assets' };
  const context = { exports: {}, FormData, console: {log() {}, error() {}}, require(name) {
    if (name === 'axios') return axios;
    if (name === 'react') return React;
    if (name === '../urls') return {APP_URLS: urls, get_data: async url => (await axios.get(url)).data.data};
    if (name === '../utils' || name === '@devexpress/dx-react-grid' || name === 'date-fns') return {};
    if (name === '../locales/curator.en.json') return require('../src/js/locales/curator.en.json');
    if (name === 'lodash') return require('lodash');
    throw new Error(`Unexpected import: ${name}`);
  }};
  vm.runInNewContext(babel.transformFileSync(path.resolve(__dirname, '../src/js/context/global_state.tsx'), {
    configFile: false, babelrc: false,
    plugins: [require.resolve('@babel/plugin-proposal-class-properties')],
    presets: [[require.resolve('@babel/preset-env'), {targets: {node: 'current'}}], require.resolve('@babel/preset-typescript'), require.resolve('@babel/preset-react')]
  }).code, context);
  return Object.create(context.exports.default.prototype);
}

test('copying a version from the unopened list never loads the nonexistent version zero', async () => {
  const calls = [];
  const api = adapter({get: async url => calls.push(url)});
  api.state = {library_versions_api: {current_version: {id: 0}}};
  api.refresh_library_versions = async () => calls.push('list');
  for (const name of ['refresh_current_directory', 'refresh_folders_in_current_version', 'refresh_modules_in_current_version']) {
    api[name] = async () => {throw new Error('Unexpected directory request');};
  }
  await api.clone_version({id: 42});
  assert.deepEqual(calls, ['/clone/42', 'list']);
});

test('editing a module includes a normal application/zip replacement and retains the file when omitted', async () => {
  const payloads = [];
  const api = adapter({patch: async (url, payload) => payloads.push({url, payload})});
  api.refresh_library_modules = async () => {};
  const zip = {name: 'synthetic.zip', type: 'application/zip'};
  await api.edit_module({id: 7}, 'Synthetic module', zip);
  assert.equal(payloads[0].url, '/module/7');
  assert.equal(payloads[0].payload.values.get('module_file'), zip);
  await api.edit_module({id: 7}, 'Renamed module');
  assert.equal(payloads[1].payload.values.has('module_file'), false);
});

test('failed startup requests show a load error instead of empty catalogue tools', async () => {
  const api = adapter({get: async () => ({data: {data: 'synthetic-csrf'}}), defaults: {headers: {common: {}}}});
  api.state = {initializing: true, initialization_error: false};
  api.update_state = async change => change(api.state);
  for (const name of ['refresh_metadata', 'load_content_rows', 'refresh_library_versions', 'refresh_users', 'refresh_library_modules', 'update_version_autocomplete', 'get_disk_info']) api[name] = async () => {};
  api.refresh_assets = async () => {throw new Error('Unavailable');};
  api.componentDidMount();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(api.state.initializing, false);
  assert.equal(api.state.initialization_error, true);
  assert.equal(api.render().props.children[0].props.role, 'alert');
});


test('catalogue list HTTP failures propagate into the workspace load error', async () => {
  const failure = {data: {error: {detail: 'Synthetic unavailable response'}}};
  const api = adapter({get: async () => {throw failure;}});
  api.state = {library_versions_api: {library_versions_page: 0, library_versions_page_size: 5}};
  await assert.rejects(api.refresh_library_versions(), error => error === failure);
});


test('asset loading awaits its request and propagates failures rather than claiming an empty library', async () => {
  const failure = {data: {error: {detail: 'Synthetic asset failure'}}};
  const api = adapter({get: async () => {throw failure;}});
  await assert.rejects(api.refresh_assets(), error => error === failure);
});
