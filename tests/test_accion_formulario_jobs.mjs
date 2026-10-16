// Regression: an HTML submit button with no formaction must not replace the form action.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const source = fs.readFileSync(new URL('../app/static/enterprise/features/jobs.js', import.meta.url), 'utf8');
const start = source.indexOf('function prepareFormRequest(');
const end = source.indexOf('function initializeJobForms(');
assert.ok(start !== -1 && end > start);
const prepare = vm.runInNewContext(
  `${source.slice(start, end)}; prepareFormRequest`,
  {
    URL,
    FormData: class { entries() { return []; } },
    window: { location: { origin: 'https://example.org', href: 'https://example.org/admin/panel/sincronizacion' } },
  },
);
const form = {
  method: 'post', enctype: 'application/x-www-form-urlencoded',
  getAttribute(name) { return name === 'action' ? '/admin/panel/stock/run-incremental' : null; },
};
const ordinaryButton = {
  formAction: 'https://example.org/admin/panel/sincronizacion',
  hasAttribute() { return false; },
};
assert.equal(prepare(form, ordinaryButton).url, 'https://example.org/admin/panel/stock/run-incremental');
const overriddenButton = {
  hasAttribute(name) { return name === 'formaction'; },
  getAttribute() { return '/admin/panel/stock/run-now'; },
};
assert.equal(prepare(form, overriddenButton).url, 'https://example.org/admin/panel/stock/run-now');
console.log('OK: form.action defaults and explicit submitter overrides');
