// Optional Node-based checks of the exact browser-side extraction resource.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../focusassistant/extract_text.js'), 'utf8');
const text = value => ({nodeType:3, nodeValue:value});
function element(tag, children=[], options={}) {
    return {nodeType:1, tagName:tag, childNodes:children, hidden:!!options.hidden,
        isContentEditable:!!options.editable, getAttribute:key => options[key],
        style: {display:'block', visibility:'visible', opacity:'1', ...options.style}};
}
function extract(body) {
    return JSON.parse(vm.runInNewContext(code, {
        document:{body, title:'Fixture title'}, location:{href:'https://example.org/fixture'},
        window:{getComputedStyle:node=>node.style}, crypto:require('node:crypto').webcrypto
    }, {timeout:1000}));
}
let passed = 0;
function check(name, test) { test(); passed++; console.log('PASS:', name); }
check('DFS preserves natural text order', () => {
    assert.equal(extract(element('BODY', [text(' first '), element('DIV',[text('second')]),text('third')])).text, 'first second third');
});
check('hidden, editable, script, input and frame nodes excluded', () => {
    const body = element('BODY', [text('visible'), element('SCRIPT',[text('script')]),
        element('INPUT',[text('secret')]), element('IFRAME',[text('frame')]),
        element('DIV',[text('editable')],{editable:true}), element('DIV',[text('hidden')],{hidden:true}),
        element('DIV',[text('aria')],{'aria-hidden':'true'}), element('DIV',[text('styled')],{style:{display:'none'}})]);
    assert.equal(extract(body).text, 'visible');
});
check('text bounded to 24000 characters', () => {
    assert.equal(extract(element('BODY',[text('x'.repeat(40000))])).text.length,24000);
});
check('large child lists stop at node budget', () => {
    const result = extract(element('BODY',Array.from({length:20000},()=>text('x'))));
    assert.equal(result.text.split(' ').length,8999);
});
check('deep nesting bounded without recursion', () => {
    let root = element('DIV',[text('too deep')]);
    for(let i=0;i<10000;i++) root=element('DIV',[root]);
    assert.equal(extract(root).text,'');
});
check('empty document and metadata', () => {
    const result = extract(null);
    assert.equal(result.text,'');
    assert.equal(result.url,'https://example.org/fixture');
    assert.equal(result.title,'Fixture title');
});
console.log(`${passed} extraction checks passed`);
