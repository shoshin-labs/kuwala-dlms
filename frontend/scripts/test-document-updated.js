const assert = require("node:assert/strict");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const babel = require("@babel/core");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const frontend = path.resolve(__dirname, "..");
const compiled = babel.transformFileSync(
  path.join(frontend, "src/js/document_updated_date.ts"),
  {
    configFile: false,
    babelrc: false,
    presets: [require.resolve("@babel/preset-env"), require.resolve("@babel/preset-typescript")],
  },
);
const context = { exports: {}, Intl, Date };
vm.runInNewContext(compiled.code, context);
const format = context.exports.documentUpdatedDate;
const component = { exports: {}, require(name) {
  if (name === "react") return React;
  if (name === "./i18n") return { LocaleContext: React.createContext("en") };
  if (name === "./document_updated_date") return context.exports;
  throw new Error("Unexpected date component import: " + name);
} };
vm.runInNewContext(babel.transformFileSync(path.join(frontend, "src/js/document_updated.tsx"), {
  configFile: false,
  babelrc: false,
  presets: ["@babel/preset-env", "@babel/preset-typescript", "@babel/preset-react"].map(require.resolve),
}).code, component);

test("actual UTC timestamps retain their exact machine value and format in the selected locale", () => {
  const value = "2026-10-09T08:02:22.681330Z";
  assert.equal(format(value, "en").dateTime, value);
  assert.equal(format(value, "en").text, "October 9, 2026");
  assert.equal(format(value, "fr").text, "9 octobre 2026");
  assert.equal(format("2026-10-09T00:00:00+00:00", "en").text, "October 9, 2026");
});

test("missing, review-only, invalid and unzoned values never become an update date", () => {
  for (const value of [undefined, null, "", 123, "2026-10-08", "2026-10-09T08:02:22",
    "2026-02-30T00:00:00Z", "2026-10-09T24:00:00Z", "2026-10-09T00:61:00Z",
    "2026-10-09T00:00:60Z", "0000-01-01T00:00:00Z", "2026-10-09T01:00:00+01:00",
    '<script>alert(1)</script>']) {
    assert.equal(format(value, "en"), null, String(value));
  }
});

test("display dates are UTC and independent of a visitor's browser time zone", () => {
  const previous = process.env.TZ;
  try {
    process.env.TZ = "America/Los_Angeles";
    assert.equal(format("2026-10-09T00:02:22Z", "en").text, "October 9, 2026");
    process.env.TZ = "Pacific/Auckland";
    assert.equal(format("2026-10-09T23:59:59Z", "en").text, "October 9, 2026");
  } finally {
    if (previous === undefined) delete process.env.TZ;
    else process.env.TZ = previous;
  }
});

test("the listing uses a machine-readable time element and omits unknown updates", () => {
  const props = {
    label: "Last updated in this library",
    description: "Publication, rights review and indexing dates are separate.",
    value: "2026-10-09T08:02:22.681330Z",
  };
  const render = (value) => renderToStaticMarkup(React.createElement(component.exports.default, value));
  const html = render(props);
  assert.match(html, /<time datetime="2026-10-09T08:02:22\.681330Z">October 9, 2026<\/time>/i);
  assert.match(html, /Last updated in this library:/);
  assert.match(html, /Publication, rights review and indexing dates are separate/);
  assert.equal(render({ ...props, value: undefined, reviewed_on: "2026-10-08" }), "");
  assert.equal(render({ ...props, value: "2026-02-30T00:00:00Z" }), "");
});
