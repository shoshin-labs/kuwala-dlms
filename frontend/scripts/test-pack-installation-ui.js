const assert = require('node:assert/strict');
const test = require('node:test');
const babel = require('@babel/core');
const vm = require('node:vm');
const path = require('node:path');
const React = require('react');
const strings = require('../src/js/locales/manager.en.json').strings;

function harness(request) {
  const values = [], effects = [], timers = new Map(); let cursor = 0, nextTimer = 1;
  const react = {...React,
    useState(initial) { const slot = cursor++; if (!(slot in values)) values[slot] = initial;
      return [values[slot], next => { values[slot] = typeof next === 'function' ? next(values[slot]) : next; }]; },
    useRef(initial) { const slot = cursor++; if (!(slot in values)) values[slot] = {current: initial}; return values[slot]; },
    useEffect(callback, deps) { const slot = cursor++, old = values[slot];
      if (!old || deps.some((value, index) => !Object.is(value, old.deps[index]))) {
        effects.push(() => { old?.cleanup?.(); values[slot] = {deps, cleanup: callback()}; });
      }
    }
  };
  const context = {exports: {}, Set, console, crypto: {randomUUID: () => 'synthetic-request-id'},
    window: {setInterval(callback) {const id = nextTimer++; timers.set(id, callback); return id;}, clearInterval: id => timers.delete(id)},
    require(name) {
      if (name === 'react') return react;
      if (name === './manager_api') return {request};
      if (name === './manager_strings') return {useManagerStrings: () => key => strings[key]};
      throw new Error(name);
    }};
  vm.runInNewContext(babel.transformFileSync(path.resolve(__dirname, '../src/js/manager_packs.tsx'), {
    configFile: false, babelrc: false, presets: [[require.resolve('@babel/preset-env'), {targets:{node:'current'}}],
      require.resolve('@babel/preset-typescript'), require.resolve('@babel/preset-react')]
  }).code, context);
  function render() {cursor = 0; const result = context.exports.default(); while (effects.length) effects.shift()(); return result;}
  function nodes(node, predicate, found = []) {
    if (!node || typeof node !== 'object') return found;
    if (predicate(node)) found.push(node);
    React.Children.forEach(node.props?.children, child => nodes(child, predicate, found)); return found;
  }
  function button(label) {const found = nodes(render(), node => node.type === 'button' && node.props.children === label);
    assert.equal(found.length, 1, label); return found[0];}
  const inputs = () => nodes(render(), node => node.type === 'input');
  async function settle() {for (let count=0; count<4; count++) await Promise.resolve(); render();}
  async function open() {render().props.onToggle({currentTarget:{open:true}}); render(); await settle();}
  return {render, nodes, button, inputs, open, settle};
}
const pack = {pack_id:'malawi-farming', title:'Synthetic Malawi farming', release_id:'fixture-one', document_count:1, bytes:1000};
const available = {configured:true, packs:[pack], publication_sha256:'a'.repeat(64), free_bytes:20*1024**3, page:1, has_more:false};

test('opening is read-only; installation requires an explicit selection and restart acknowledgement', async () => {
  const calls=[];
  const ui=harness(async (url, method, body) => {calls.push({url,method,body}); return method==='POST' ? {...available, job:{phase:'queued'}} : available;});
  ui.render(); assert.equal(calls.length,0);
  await ui.open(); assert.equal(calls.length,1); assert.equal(calls[0].url,'/api/oasis/packs/?page=1');
  assert.equal(ui.button(strings.packs_install).props.disabled,true);
  ui.inputs()[0].props.onChange({target:{checked:true}});
  assert.equal(ui.button(strings.packs_install).props.disabled,true);
  ui.inputs().at(-1).props.onChange({target:{checked:true}});
  assert.equal(ui.button(strings.packs_install).props.disabled,false);
  await ui.button(strings.packs_install).props.onClick(); await ui.settle();
  assert.equal(calls.filter(call=>call.method==='POST').length,1);
  assert.equal(calls[1].body.publication_sha256,available.publication_sha256);
  assert.deepEqual(Array.from(calls[1].body.pack_ids),['malawi-farming']);
  assert.equal(ui.button(strings.packs_install).props.disabled,true);
});

test('selection survives bounded pack pages and a new publication requires review again', async () => {
  const ui=harness(async (url, method) => method==='POST' ? {...available,publication_sha256:'b'.repeat(64)} :
    url.endsWith('page=2') ? {...available,packs:[{...pack,pack_id:'another-pack'}],page:2} : {...available,has_more:true});
  await ui.open(); ui.inputs()[0].props.onChange({target:{checked:true}});
  ui.inputs().at(-1).props.onChange({target:{checked:true}});
  ui.button(strings.next_page).props.onClick(); ui.render(); await ui.settle();
  assert.equal(ui.inputs()[0].props.checked,false);
  assert.equal(ui.button(strings.packs_install).props.disabled,false);
  await ui.button(strings.packs_refresh).props.onClick(); await ui.settle();
  assert.equal(ui.inputs()[0].props.checked,false);
  assert.equal(ui.button(strings.packs_install).props.disabled,true);
});

test('unknown install outcome is checked without resubmitting the operation', async () => {
  let posted=0;
  const ui=harness(async (url,method) => {if(method==='POST'){posted++;throw new Error('Synthetic connection lost');}
    return posted ? {...available,job:{phase:'downloading',download_bytes:1000},received_bytes:512} : available;});
  await ui.open(); ui.inputs()[0].props.onChange({target:{checked:true}}); ui.inputs().at(-1).props.onChange({target:{checked:true}});
  await ui.button(strings.packs_install).props.onClick(); await ui.settle();
  assert.equal(posted,1); assert.equal(ui.button(strings.packs_install).props.disabled,true);
  assert.equal(ui.nodes(ui.render(),node=>node.props?.role==='alert')[0].props.children,'Synthetic connection lost');
});

test('an uncommissioned installer is explicit and offers no install or rollback action', async () => {
  const ui=harness(async()=>({configured:false,packs:[],blocked_reason:'Synthetic installer unavailable'}));
  await ui.open();
  assert.equal(ui.nodes(ui.render(),node=>node.props?.children==='Synthetic installer unavailable').length,1);
  assert.equal(ui.nodes(ui.render(),node=>node.type==='button'&&node.props.children===strings.packs_install).length,0);
});
