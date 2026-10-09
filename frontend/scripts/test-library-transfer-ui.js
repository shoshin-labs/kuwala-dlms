const assert = require('node:assert/strict');
const test = require('node:test');
const babel = require('@babel/core');
const path = require('node:path');
const vm = require('node:vm');
const React = require('react');
const text = require('../src/js/locales/library-transfer.en.json').strings;

function harness(request, libraries = [{id: 10, folder_name: 'Farming'}]) {
  const values = []; let cursor = 0; let versionId = 42; const imports = [];
  class FormData { constructor() {this.values = new Map();} append(key, value) {this.values.set(key,value);} }
  const context = {exports:{}, FormData, Set, console, require(name) {
    if (name === 'react') return {...React, useState(initial) {
      const slot = cursor++; if (!(slot in values)) values[slot] = initial;
      return [values[slot], next => {values[slot] = typeof next === 'function' ? next(values[slot]) : next;}];
    }};
    if (name === '@material-ui/core') return Object.fromEntries(['Button','Dialog','DialogActions','DialogContent','DialogTitle','TextField'].map(key=>[key,key]));
    if (name === './manager_api') return {request};
    if (name === './library_transfer_strings') return {useLibraryTransferStrings:()=>text};
    throw new Error('Unexpected import: '+name);
  }};
  vm.runInNewContext(babel.transformFileSync(path.resolve(__dirname,'../src/js/manager_library_transfer.tsx'), {
    configFile:false,babelrc:false,presets:[[require.resolve('@babel/preset-env'),{targets:{node:'current'}}],require.resolve('@babel/preset-typescript'),require.resolve('@babel/preset-react')]
  }).code,context);
  function render() {cursor=0;return context.exports.default({versionId,libraries,selectedLibraryId:10,onImported:id=>imports.push(id)});}
  function nodes(node, predicate, result=[]) {
    if (!node || typeof node !== 'object') return result;
    if (predicate(node)) result.push(node);
    React.Children.forEach(node.props?.children, child => nodes(child,predicate,result));
    return result;
  }
  function button(label) {const found=nodes(render(),node=>node.props?.children===label && typeof node.props?.onClick==='function');assert.equal(found.length,1,`button ${label}`);return found[0];}
  function input() {return nodes(render(),node=>node.props?.id==='library-transfer-file')[0];}
  function choose(file) {input().props.onChange({target:{files:[file]}});}
  return {render,button,choose,imports,nodes,setVersion:id=>{versionId=id;}};
}
const zip = {name:'synthetic-library.zip',size:1000};
const plan = {bundle_sha256:'a'.repeat(64),library_name:'Farming',document_count:2,section_count:1,warnings:[]};

test('review is read-only, confirmation imports into the existing catalogue with the reviewed hash and unique name', async()=>{
  const calls=[];
  const ui=harness(async(url,method,body)=>{calls.push({url,method,body});return url.includes('dry_run')?plan:{library:{id:99,name:'Farming (imported 1)'}};});
  ui.button(text.import_library).props.onClick();ui.choose(zip);
  await ui.button(text.inspect).props.onClick();
  assert.equal(calls.length,1);assert.equal(calls[0].url,'/api/oasis/libraries/import/?dry_run=1');
  assert.equal(calls[0].body.values.get('catalogue_version'),'42');assert.equal(ui.imports.length,0);
  const confirm=ui.button(text.confirm_import);assert.equal(confirm.props.disabled,false);
  await confirm.props.onClick();
  assert.equal(calls[1].body.values.get('expected_sha256'),plan.bundle_sha256);
  assert.equal(calls[1].body.values.get('library_name'),'Farming (imported 1)');
  assert.equal(calls[1].body.values.get('confirmed'),'true');assert.deepEqual(ui.imports,[99]);
});

test('failed review retains the selected package for a retry',async()=>{
  let attempts=0;
  const ui=harness(async()=>{if(++attempts===1)throw new Error('Synthetic failure');return plan;});
  ui.button(text.import_library).props.onClick();ui.choose(zip);
  await ui.button(text.inspect).props.onClick();
  assert.equal(ui.button(text.inspect).props.disabled,false);
  await ui.button(text.inspect).props.onClick();assert.equal(attempts,2);
  assert.equal(ui.button(text.confirm_import).props.disabled,false);
});

test('failed apply keeps the reviewed package and chosen library name',async()=>{
  const ui=harness(async url=>{if(url.includes('dry_run'))return plan;throw new Error('Synthetic apply failure');});
  ui.button(text.import_library).props.onClick();ui.choose(zip);await ui.button(text.inspect).props.onClick();
  await ui.button(text.confirm_import).props.onClick();
  assert.equal(ui.button(text.confirm_import).props.disabled,false);
  const field=ui.nodes(ui.render(),node=>node.props?.label===text.import_as)[0];assert.equal(field.props.value,'Farming (imported 1)');
  assert.equal(ui.imports.length,0);
});

test('changing the file discards a previous review and oversized packages never upload',async()=>{
  let calls=0;const ui=harness(async()=>{calls++;return plan;});
  ui.button(text.import_library).props.onClick();ui.choose(zip);await ui.button(text.inspect).props.onClick();
  ui.choose({name:'other.zip',size:81*1024*1024});
  assert.equal(ui.nodes(ui.render(),node=>node.props?.children===text.confirm_import).length,0);
  await ui.button(text.inspect).props.onClick();assert.equal(calls,1);
  assert.equal(ui.nodes(ui.render(),node=>node.props?.role==='alert')[0].props.children,text.size_error);
});


test('a changed catalogue requires a fresh review instead of silently applying to a different target',async()=>{
  const calls=[];const ui=harness(async(url,method,body)=>{calls.push({url,body});return plan;});
  ui.button(text.import_library).props.onClick();ui.choose(zip);await ui.button(text.inspect).props.onClick();
  ui.setVersion(77);
  assert.equal(ui.nodes(ui.render(),node=>node.props?.children===text.confirm_import).length,0);
  assert.equal(ui.nodes(ui.render(),node=>node.props?.role==='alert')[0].props.children,text.target_changed);
  await ui.button(text.inspect).props.onClick();
  assert.equal(calls[1].body.values.get('catalogue_version'),'77');
  assert.equal(ui.button(text.confirm_import).props.disabled,false);
});
