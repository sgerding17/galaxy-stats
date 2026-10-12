import { createRequire } from "module";
import assert from "node:assert/strict";

const require = createRequire(import.meta.url);
const VoiceDsl = require("../docs/logger/voice.js");

const roster = ["1", "2", "3", "4", "5", "14", "21", "22", "25"];

const cases = [
  ["fga twenty one", "fga 21"],
  ["f g a twenty one", "fga 21"],
  ["three f g m o", "3fgm o"],
  ["i g twenty one twenty two five two twenty five", "ig 21 22 5 2 25"],
  ["o j fourteen arrow g", "oj 14 -> g"],
  ["d j five to o", "dj 5 -> o"],
  ["see fourteen thirty", "c 1430"],
  ["c one four three zero", "c 1430"],
  ["c nine zero zero", "c 0900"],
  ["t o", "t o"],
  ["two two", "to 2"],
  ["r galaxy", "r g"],
  ["p a e", "pae"],
];

for (const [spoken, line] of cases) {
  const parsed = VoiceDsl.parseUtterance(spoken, { players: roster });
  assert.equal(parsed.ok, true, spoken + ": " + parsed.error);
  assert.equal(parsed.line, line, spoken);
}

for (const spoken of ["fga ninety nine", "r potato", "fga 21 extra"]) {
  const parsed = VoiceDsl.parseUtterance(spoken, { players: roster });
  assert.equal(parsed.ok, false, spoken);
}

console.log(`${cases.length} voice parser cases: all match`);
