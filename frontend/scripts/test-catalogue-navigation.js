const assert = require('node:assert/strict');
const test = require('node:test');
const babel = require('@babel/core');
const path = require('node:path');
const vm = require('node:vm');
const React = require('react');
const strings = require('../src/js/locales/en.json').strings;
const presets = [[require.resolve('@babel/preset-env'), {targets: {node: 'current'}}],
  require.resolve('@babel/preset-typescript'), require.resolve('@babel/preset-react')];

function compile(file, dependencies = {}) {
  const context = {exports: {}, Set, require(name) {
    if (name in dependencies) return dependencies[name];
    throw new Error('Unexpected import: ' + name);
  }};
  vm.runInNewContext(babel.transformFileSync(path.resolve(__dirname, file), {
    configFile: false, babelrc: false, presets,
  }).code, context);
  return context.exports;
}
const tree = compile('../src/js/catalogue_tree.ts');
const folder = (id, name, parent = null, count = 3) => ({
  id, folder_name: name, parent, document_count: count, direct_document_count: count, version: 9,
});
const farming = folder(10, 'Farming');
const health = folder(20, 'Health and wellbeing');
const water = folder(30, 'Water');
const mentalHealth = folder(21, 'Mental health', 20);
const nutrition = folder(22, 'Family nutrition', 20);
const childNutrition = folder(23, 'Child nutrition', 22);
const allFolders = [farming, health, water, mentalHealth, nutrition, childNutrition];

function harness(props = {}) {
  const values = []; let cursor = 0; let changed = false; let effects = [];
  const choices = [];
  let current = {id: 'synthetic-navigation', folders: allFolders,
    libraries: [farming, health, water], library: health, section: mentalHealth,
    onChoose: (root, child) => choices.push([root?.id, child?.id]), ...props};
  const hooks = {...React,
    useState(initial) {
      const slot = cursor++;
      if (!(slot in values)) values[slot] = typeof initial === 'function' ? initial() : initial;
      return [values[slot], next => {
        const value = typeof next === 'function' ? next(values[slot]) : next;
        if (value !== values[slot]) changed = true;
        values[slot] = value;
      }];
    },
    useRef(initial) {
      const slot = cursor++;
      if (!(slot in values)) values[slot] = {current: initial};
      return values[slot];
    },
    useEffect(effect, dependencies) {
      const slot = cursor++;
      const previous = values[slot];
      if (!previous || dependencies.some((value, index) => value !== previous[index])) effects.push(effect);
      values[slot] = dependencies;
    },
  };
  const component = compile('../src/js/catalogue_navigation.tsx', {
    react: hooks, './catalogue_tree': tree, './i18n': {useStrings: () => (key, args = {}) =>
      strings[key].replace(/\{(\w+)\}/g, (_, name) => String(args[name]))},
  }).default;
  function render() {
    let result; let passes = 0;
    do {
      changed = false; cursor = 0; effects = [];
      result = component(current);
      for (const effect of effects) effect();
      assert.ok(++passes < 10, 'effects settle');
    } while (changed);
    return result;
  }
  function nodes(node, predicate, found = []) {
    if (!node || typeof node !== 'object') return found;
    if (predicate(node)) found.push(node);
    React.Children.forEach(node.props?.children, child => nodes(child, predicate, found));
    return found;
  }
  function text(node) {
    if (node == null || typeof node === 'boolean') return '';
    if (typeof node === 'string' || typeof node === 'number') return String(node);
    return React.Children.toArray(node.props.children).map(text).join('');
  }
  function buttons() {return nodes(render(), node => node.type === 'button');}
  function button(name) {
    const result = buttons().filter(node => text(node.props.children[0]) === name);
    assert.equal(result.length, 1, 'button ' + name);
    return result[0];
  }
  function search(kind, value) {
    nodes(render(), node => node.props?.id === `synthetic-navigation-${kind}-search`)[0]
      .props.onChange({target: {value}});
  }
  function toggle(open) {render().props.onToggle({currentTarget: {open}});}
  return {render, nodes, text, buttons, button, search, toggle, choices,
    update: props => {current = {...current, ...props};}};
}

test('selected location starts compact; opening, closing and Escape preserve the committed scope', () => {
  const ui = harness();
  assert.equal(ui.render().props.open, false);
  const summary = ui.nodes(ui.render(), node => node.type === 'summary')[0];
  assert.match(ui.text(summary), /Health and wellbeing.*Mental health.*3 documents/);
  ui.toggle(true);
  ui.button('Farming').props.onClick(); // No sections: commits immediately.
  assert.deepEqual(ui.choices, [[10, undefined]]);
  ui.toggle(true);
  let focused = false; let prevented = false;
  ui.nodes(ui.render(), node => node.type === 'summary')[0].ref.current = {focus() {focused = true;}};
  ui.render().props.onKeyDown({key: 'Escape', preventDefault() {prevented = true;}});
  assert.equal(ui.render().props.open, false);
  assert.equal(prevented && focused, true);
});

test('previewing a library with sections does not change location; selecting a nested section commits stable IDs', () => {
  const ui = harness({library: farming, section: undefined});
  ui.toggle(true);
  ui.button('Health and wellbeing').props.onClick();
  assert.equal(ui.render().props.open, true);
  assert.deepEqual(ui.choices, []);
  assert.equal(ui.button('Farming').props['aria-current'], 'page');
  assert.equal(ui.button('Health and wellbeing').props['aria-current'], undefined);
  assert.equal(ui.button('Health and wellbeing').props['aria-pressed'], true);
  ui.button('Family nutrition / Child nutrition').props.onClick();
  assert.deepEqual(ui.choices, [[20, 23]]);
  assert.equal(ui.render().props.open, false);
});

test('All documents commits a previewed library; cancelling restores the current library on reopen', () => {
  const ui = harness({library: farming, section: undefined});
  ui.toggle(true); ui.button('Health and wellbeing').props.onClick();
  ui.toggle(false); ui.toggle(true);
  assert.equal(ui.button('Farming').props['aria-pressed'], true);
  assert.equal(ui.buttons().some(node => ui.text(node).includes('Child nutrition')), false);
  ui.button('Health and wellbeing').props.onClick();
  ui.button(strings.all_library_documents).props.onClick();
  assert.deepEqual(ui.choices, [[20, undefined]]);
});

test('a large catalogue and nested sections can be narrowed independently and empty matches are honest', () => {
  const libraries = Array.from({length: 50}, (_, index) => folder(100 + index, `Synthetic library ${index}`));
  const ui = harness({folders: [...allFolders, ...libraries], libraries: [...libraries, health], initialOpen: true});
  assert.equal(ui.render().props.open, true);
  ui.search('library', 'LIBRARY 49');
  assert.equal(ui.buttons().filter(node => ui.text(node).includes('Synthetic library')).length, 1);
  ui.search('section', 'CHILD NUTRITION');
  assert.equal(ui.buttons().filter(node => ui.text(node).includes('nutrition')).length, 1);
  ui.search('section', 'missing');
  assert.equal(ui.nodes(ui.render(), node => node.props?.role === 'status').some(node =>
    ui.text(node) === strings.no_matching_sections), true);
  ui.search('library', 'missing');
  assert.equal(ui.nodes(ui.render(), node => node.props?.role === 'status').some(node =>
    ui.text(node) === strings.no_matching_libraries), true);
  ui.toggle(false); ui.toggle(true);
  assert.equal(ui.buttons().filter(node => ui.text(node).includes('Synthetic library')).length, 50);
});

test('external URL scope changes cancel pending selection; curator All documents is retained', () => {
  const ui = harness({allDocuments: {name: 'All documents', count: 9}});
  ui.toggle(true); ui.search('library', 'water');
  ui.update({library: water, section: undefined});
  assert.equal(ui.render().props.open, false);
  ui.toggle(true); ui.button('All documents').props.onClick();
  assert.deepEqual(ui.choices, [[undefined, undefined]]);
  ui.update({library: undefined, allDocuments: {name: 'All documents', count: 0}, disabled: true});
  assert.equal(ui.render().props.open, false);
  assert.equal(ui.button('All documents').props.disabled, true);
  assert.match(ui.text(ui.nodes(ui.render(), node => node.type === 'summary')[0]), /All documents.*0 documents/);
});

test('returning to the visitor overview opens its library list again', () => {
  const ui = harness();
  ui.toggle(true); ui.search('library', 'water');
  ui.update({library: undefined, section: undefined, initialOpen: true});
  assert.equal(ui.render().props.open, true);
  assert.equal(ui.buttons().filter(node => ui.text(node).includes('Water')).length, 1);
  assert.equal(ui.buttons().filter(node => ui.text(node).includes('Farming')).length, 1);
  ui.update({library: health, section: mentalHealth, initialOpen: false});
  assert.equal(ui.render().props.open, false);
});

test('reselecting the current section returns focus to a visible disclosure', () => {
  const ui = harness();
  let focused = false;
  ui.nodes(ui.render(), node => node.type === 'summary')[0].ref.current = {focus() {focused = true;}};
  ui.toggle(true);
  ui.button('Mental health').props.onClick();
  assert.deepEqual(ui.choices, [[20, 21]]);
  assert.equal(ui.render().props.open, false);
  assert.equal(focused, true);
});

test('same-ID tree refreshes show current library names and counts while preserving a pending choice', () => {
  const ui = harness({library: farming, section: undefined});
  ui.toggle(true); ui.button('Health and wellbeing').props.onClick();
  const updatedHealth = {...health, folder_name: 'Community health', document_count: 42};
  ui.update({libraries: [farming, updatedHealth, water],
    folders: allFolders.map(item => item.id === health.id ? updatedHealth : item)});
  assert.equal(ui.button('Community health').props['aria-pressed'], true);
  assert.match(ui.text(ui.button(strings.all_library_documents)), /42 documents/);
  assert.equal(ui.nodes(ui.render(), node => node.type === 'h2').some(node =>
    ui.text(node).includes('Sections in Community health')), true);
  ui.toggle(false); ui.toggle(true);
  assert.equal(ui.button('Farming').props['aria-pressed'], true);
});
