const assert = require('node:assert/strict');
const test = require('node:test');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const babel = require('@babel/core');

const directory = path.resolve(__dirname, '../src/js');
const compiled = new Map();
function harness(base, origin = 'https://box001.kuwala.space') {
  const calls = [];
  const modules = new Map();
  const document = {querySelector(selector) {
    assert.equal(selector, 'meta[name="oasis-app-base"]');
    return base === undefined ? null : {getAttribute: () => base};
  }};
  const environment = {URL, document, window: {location: {origin}},
    __webpack_public_path__: 'static/', FormData: class FormData {},
    fetch: async (url, options) => {
      calls.push({url, ...options});
      const data = url.includes('get_csrf') ? 'synthetic-csrf-token' : {id: 57};
      return {ok: true, status: 200, text: async () => JSON.stringify({success: true, data})};
    }};
  function load(name) {
    if (modules.has(name)) return modules.get(name).exports;
    const filename = path.join(directory, name + (name === 'urls' ? '.tsx' : '.ts'));
    if (!compiled.has(name)) compiled.set(name, babel.transformFileSync(filename, {
      configFile: false, babelrc: false,
      presets: [[require.resolve('@babel/preset-env'), {targets: {node: 'current'}}],
        require.resolve('@babel/preset-typescript')],
    }).code);
    const context = {...environment, exports: {}, require(dependency) {
      if (dependency === 'axios') return {get: async (url, options) => {
        calls.push({url, options});
        return {data: {success: true, data: {id: 57}}};
      }};
      if (dependency.endsWith('.json')) return require(path.join(directory, dependency));
      if (dependency.startsWith('./')) return load(dependency.slice(2));
      return require(dependency);
    }};
    modules.set(name, context);
    vm.runInNewContext(compiled.get(name), context, {filename});
    return context.exports;
  }
  return {load, calls, context: name => modules.get(name)};
}

for (const base of ['/', '/manage/']) {
  const prefix = base === '/' ? '' : '/manage';
  test(`${base}: root/relative/already-mounted API and media URLs remain on the app origin`, () => {
    const {load} = harness(base);
    const {appUrl, appPath, staticBase} = load('app_paths');
    for (const value of ['api/contents/57/', '/api/contents/57/',
      `${prefix}/api/contents/57/`, `https://box001.kuwala.space${prefix}/api/contents/57/`]) {
      assert.equal(appUrl(value), `https://box001.kuwala.space${prefix}/api/contents/57/`);
    }
    assert.equal(appPath('/media/contents/water%20guide.pdf#page=9'), `${prefix}/media/contents/water%20guide.pdf#page=9`);
    assert.equal(appPath(`${prefix}/media/contents/water.pdf?download=1#page=3`), `${prefix}/media/contents/water.pdf?download=1#page=3`);
    assert.equal(appPath('/?tab=contents'), `${base}?tab=contents`);
    assert.equal(appPath('?workspace=curator'), `${base}?workspace=curator`);
    assert.equal(staticBase(), `${prefix}/static/`);
  });

  test(`${base}: modern catalogue and legacy Axios endpoints preserve IDs, filters and one prefix`, async () => {
    const {load, calls} = harness(base);
    const {APP_URLS, get_data} = load('urls');
    assert.equal(APP_URLS.CONTENT_ITEM(57), `https://box001.kuwala.space${prefix}/api/contents/57/`);
    assert.equal(APP_URLS.CONTENT_FOLDER, `https://box001.kuwala.space${prefix}/media/contents/`);
    const modern = load('catalogue_tree').catalogueQuery('/api/oasis/catalogue/documents/', {
      catalogue_version: 6, folder_id: 18, q: 'maize & water', page: 2, empty: '', omitted: undefined,
    });
    const url = new URL(modern);
    assert.equal(url.pathname, `${prefix}/api/oasis/catalogue/documents/`);
    assert.equal(url.searchParams.get('folder_id'), '18');
    assert.equal(url.searchParams.get('q'), 'maize & water');
    assert.equal(url.searchParams.has('omitted'), false);
    assert.equal(url.searchParams.has('empty'), false);
    await get_data(modern);
    await get_data('/api/oasis/config/');
    assert.equal(calls[0].url, modern);
    assert.equal(calls[1].url, `https://box001.kuwala.space${prefix}/api/oasis/config/`);
  });

  test(`${base}: manager reads, CSRF and writes share the same mounted route`, async () => {
    const {load, calls} = harness(base);
    const api = load('manager_api');
    await api.request('/api/oasis/documents/57/', 'PATCH', {display_title: 'Water'});
    assert.equal(calls[0].url, `https://box001.kuwala.space${prefix}/api/get_csrf/`);
    assert.equal(calls[1].url, `https://box001.kuwala.space${prefix}/api/oasis/documents/57/`);
    assert.equal(calls[1].headers['X-CSRFToken'], 'synthetic-csrf-token');
    assert.equal(calls[1].credentials, 'same-origin');
    assert.equal(calls[1].body, '{"display_title":"Water"}');
    await api.request(`https://box001.kuwala.space${prefix}/api/oasis/documents/57/`);
    assert.equal(calls[2].url, calls[1].url);
    assert.equal(api.originalUrl({file_name: 'water guide.pdf'}), `${prefix}/media/contents/water%20guide.pdf`);
  });

  test(`${base}: original PDFs and stored asset responses are local, with already-mounted values retained`, () => {
    const {load} = harness(base);
    const {originalDocumentUrl, localResourceUrl} = load('app_paths');
    assert.equal(originalDocumentUrl({content_file: '/media/contents/source.pdf', file_name: 'other.pdf'}), `${prefix}/media/contents/source.pdf`);
    assert.equal(originalDocumentUrl({content_file: `https://box001.kuwala.space${prefix}/media/contents/source.pdf`}), `${prefix}/media/contents/source.pdf`);
    assert.equal(originalDocumentUrl({content_file: 'https://publisher.example/media/contents/not-local.pdf', file_name: 'local.pdf'}), `${prefix}/media/contents/local.pdf`);
    assert.equal(originalDocumentUrl({content_file: '/api/not-an-original/'}), '');
    assert.equal(originalDocumentUrl({}), '');
    assert.equal(localResourceUrl('/media/layout/banner.png'), `${prefix}/media/layout/banner.png`);
    assert.equal(localResourceUrl(`https://box001.kuwala.space${prefix}/media/layout/banner.png`), `${prefix}/media/layout/banner.png`);
    assert.equal(localResourceUrl('https://publisher.example/banner.png'), '');
  });

  test(`${base}: lazy-chunk public path is initialized before the application imports`, () => {
    const ui = harness(base);
    ui.load('runtime_paths');
    assert.equal(ui.context('runtime_paths').__webpack_public_path__, `${prefix}/static/`);
    const config = require('../webpack.config');
    assert.ok(config.entry.indexOf('./src/js/runtime_paths.ts') < config.entry.indexOf('./src/js/index.tsx'));
  });
}

test('missing legacy base metadata retains root preview; malformed mounts fail closed', () => {
  assert.equal(harness(undefined).load('app_paths').appBase(), '/');
  for (const base of ['', '/manage', '/other/', '/manage/other/', '//external/', 'https://external/', '/../', '/%2e/', '/manage/?x=1']) {
    assert.throws(() => harness(base).load('app_paths').appBase(), /Invalid application base/);
  }
});

test('request resolution rejects off-origin URLs and traversal rather than leaking credentials or escaping the mount', async () => {
  const ui = harness('/manage/');
  const {appUrl} = ui.load('app_paths');
  for (const value of ['https://external.example/api/', '//external.example/api/', 'javascript:alert(1)',
    'http://box001.kuwala.space/api/', 'https://user:password@box001.kuwala.space/api/',
    '../api/', '/manage/../api/', '/manage/%2e%2e/api/', '/media/%2fprivate.pdf',
    '/media/%5cprivate.pdf', '\\external.example', '\n/api/', ' /api/']) {
    assert.throws(() => appUrl(value), undefined, value);
  }
  await assert.rejects(ui.load('manager_api').request('https://external.example/api/'));
  assert.equal(ui.calls.length, 0);
});

test('one emitted HTML shell resolves initial scripts and browser icons at root and mounted URLs', () => {
  const html = readFileSync(path.resolve(__dirname, '../static/index.html'), 'utf8');
  const urls = [...html.matchAll(/(?:src|href)="([^"]+)"/g)].map(match => match[1]);
  assert.ok(urls.some(value => /^static\/js\/.+\.bundle\.js$/.test(value)), 'emitted startup bundle');
  assert.ok(urls.some(value => value === 'static/images/favicon.ico'), 'native icon');
  for (const value of urls) {
    assert.ok(value.startsWith('static/'), value);
    for (const base of ['/', '/manage/']) {
      assert.equal(new URL(value, 'https://box001.kuwala.space' + base).pathname, base + value);
    }
  }
  assert.match(html, /name="oasis-app-base" content="\{% url 'oasis-home' %\}"/);
});
