import assert from 'node:assert/strict';
import test from 'node:test';

import { createVisibleSlideMap } from '../src/slide-map.js';

test('maps public navigation around hidden physical slides', () => {
  assert.deepEqual(
    createVisibleSlideMap([{ hidden: false }, { hidden: true }, {}], 3),
    [0, 2],
  );
});

test('fails open when renderer metadata is absent or incomplete', () => {
  assert.deepEqual(createVisibleSlideMap(undefined, 3), [0, 1, 2]);
  assert.deepEqual(createVisibleSlideMap([{ hidden: true }], 3), [0, 1, 2]);
});

test('bounds metadata to physical slide count and requires boolean hidden', () => {
  assert.deepEqual(
    createVisibleSlideMap([{ hidden: 'false' }, {}, { hidden: true }], 2),
    [0, 1],
  );
  assert.deepEqual(createVisibleSlideMap([{ hidden: true }, { hidden: true }], 2), []);
  assert.deepEqual(createVisibleSlideMap([], -1), []);
});
