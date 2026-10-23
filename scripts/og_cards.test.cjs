// Share card text (make_og_cards.cjs). Run: node --test scripts/og_cards.test.cjs
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { workDate, cleanPara, sectionCards, retireLimit, WAY, TEMPLATE } = require('./make_og_cards.cjs');

test('work date slot takes only the date the work was written, never the edition', () => {
  assert.strictEqual(workDate(['Cyprian of Carthage (c. 200–258 AD)', 'Hartel (1868)']), '');
  assert.strictEqual(workDate(['John Davenant (1572–1641 AD)', 'Cambridge 1650']), '');
  assert.strictEqual(workDate(['Cyril of Alexandria (c. 376–444 AD)', 'written c. 412–444 AD', 'PG 77']), 'written c. 412–444 AD');
});

test('excerpt quotes lose note marks, section numbers and all-caps headings', () => {
  assert.strictEqual(cleanPara('TOWARD CARPOCRATES’ OPINION. [1] But the soul'), 'But the soul');
  assert.strictEqual(cleanPara('AGAINST PLATO: THAT THE LIVING ARE NOT MADE FROM THE DEAD. What is it?'), 'What is it?');
  assert.strictEqual(cleanPara('10.1. As, then,'), 'As, then,');
  assert.strictEqual(cleanPara('ON DREAMS.'), '');
});

test('section cards carry the free library and house style', () => {
  const by = Object.fromEntries(sectionCards().map(c => [c.slug, c]));
  const all = JSON.stringify(sectionCards());
  assert.doesNotMatch(all, /One payment|AD 180|Every Father, every work|Read free/);
  assert.ok(by.downloads.pages.includes('/downloads/logos/'));
  assert.match(by.creeds.data.line, /180 AD/);
  assert.strictEqual(by.help.data.eyebrow, 'Help us');
  assert.match(TEMPLATE, /How they spoke, acted, argued, lived and died\./);
  assert.doesNotMatch(TEMPLATE, /Read free/);
});

test('every way label is one of the five verbs', () => {
  const ok = new Set(['How they spoke', 'How they acted', 'How they argued', 'How they lived', 'How they died']);
  assert.deepStrictEqual(Object.entries(WAY).filter(([, v]) => !ok.has(v)), []);
});

test('the big letter skips small words like of and from', () => {
  for (const w of ['the', 'of', 'from', 'and', 'for', 'upon', 'fragment', 'letters']) assert.match(TEMPLATE, new RegExp(`SKIP_INITIAL = new Set\\([^)]*'${w}'`));
});

test('a partial dist cannot retire hundreds of cards', () => {
  assert.strictEqual(retireLimit(49, 1925, false), '');
  assert.notStrictEqual(retireLimit(1900, 1925, false), '');
  assert.strictEqual(retireLimit(1900, 1925, true), '');
  assert.notStrictEqual(retireLimit(5, 0, true), '');
  assert.strictEqual(retireLimit(0, 0, false), '');
});
