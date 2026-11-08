// Run with: node --test scripts/tracks-to-mp3.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { baseTitle, parseDuration, pickBestMatch, searchQuery, safeFilename } from './tracks-to-mp3.mjs';

// Real YouTube results for "djnoone Dale Candela" (Nov 2026)
const results = [
  { id: 'p63v0n73aMg', title: 'Dale Candela', channel: 'djnoone', duration: 196 },
  { id: 'BSubfESgZmE', title: 'DJNoone - Dale Candela | Get Up and Move', channel: 'Vibes 5606', duration: 196 },
  { id: 'YOqbB130CK8', title: 'Dale Candela Boom', channel: 'Release - Topic', duration: 93 },
  { id: 'Z5wnoWa_Vpg', title: 'djnoone - Dale Candela (Latin, World) (free music with license)', channel: 'Unbound Harmonies', duration: 196 },
  { id: 'TUHya_Bfc6c', title: 'Dale Candela', channel: 'Ragamuzi - Topic', duration: 168 },
  { id: 'f8LZWEkltFU', title: 'Candy (Instrumental Version)', channel: 'djnoone', duration: 182 },
  { id: '0FImB64Q3yM', title: 'Dale Candela (Instrumental Mix)', channel: 'PolyRhythm', duration: 463 },
  { id: '1ju-davw9Pw', title: 'LUNAY - YA NO ME MUERDO (Karaoke/Instrumental)', channel: '[FKM]', duration: 149 },
];

test('parseDuration handles clock and ISO formats', () => {
  assert.equal(parseDuration('03:15'), 195);
  assert.equal(parseDuration('1:02:03'), 3723);
  assert.equal(parseDuration('PT3M15S'), 195);
  assert.equal(parseDuration('PT1H'), 3600);
  assert.equal(parseDuration(undefined), null);
});

test('baseTitle strips version suffixes', () => {
  assert.equal(baseTitle('Dale Candela - Instrumental version'), 'Dale Candela');
  assert.equal(baseTitle('Dale Candela (Instrumental Version)'), 'Dale Candela');
  assert.equal(baseTitle('Dale Candela'), 'Dale Candela');
});

test("picks the artist's own upload for the original track", () => {
  const match = pickBestMatch({ title: 'Dale Candela', artist: 'djnoone', duration: 195 }, results);
  assert.equal(match.id, 'p63v0n73aMg');
});

test('never substitutes the vocal version or another mix for an instrumental', () => {
  const match = pickBestMatch(
    { title: 'Dale Candela - Instrumental version', artist: 'djnoone', duration: 194 },
    results,
  );
  assert.equal(match, null);
});

test('rejects same-name songs with a different duration', () => {
  const match = pickBestMatch({ title: 'Dale Candela', artist: 'someone else', duration: 120 }, results);
  assert.equal(match, null);
});

test('accepts an instrumental upload when it exists', () => {
  const match = pickBestMatch(
    { title: 'Candy - Instrumental version', artist: 'djnoone', duration: 181 },
    results,
  );
  assert.equal(match.id, 'f8LZWEkltFU');
});

test('searchQuery and safeFilename', () => {
  assert.equal(
    searchQuery({ title: 'Dale Candela - Instrumental version', artist: 'djnoone' }),
    'djnoone Dale Candela instrumental',
  );
  assert.equal(safeFilename('a/b: c?'), 'a_b_ c_');
});
