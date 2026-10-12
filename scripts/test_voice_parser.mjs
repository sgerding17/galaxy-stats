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
  ["TG", "t g"],
  ["R3", "r 3"],
  ["FGA21", "fga 21"],
  ["3FGA21", "3fga 21"],
  ["C0900", "c 0900"],
  ["205", "to 5"],
  ["214", "to 14"],
];

for (const [spoken, line] of cases) {
  const parsed = VoiceDsl.parseUtterance(spoken, { players: roster });
  assert.equal(parsed.ok, true, spoken + ": " + parsed.error);
  assert.equal(parsed.line, line, spoken);
}

const sequence = VoiceDsl.parseUtterance("FGAO B3 R3 FGM3 A21", { players: roster });
assert.equal(sequence.ok, true, sequence.error);
assert.deepEqual(sequence.lines, ["fga o", "b 3", "r 3", "fgm 3", "a 21"]);

const androidSequence = VoiceDsl.parseUtterance("205 s22 fga-14 Ro", { players: roster });
assert.equal(androidSequence.ok, true, androidSequence.error);
assert.deepEqual(androidSequence.lines, ["to 5", "s 22", "fga 14", "r o"]);

const clockAtTwoOhFive = VoiceDsl.parseUtterance("c 205", { players: roster });
assert.equal(clockAtTwoOhFive.ok, true, clockAtTwoOhFive.error);
assert.equal(clockAtTwoOhFive.line, "c 0205");

assert.deepEqual(VoiceDsl.withoutOverlap(["fga 14"], ["fga 14"]), []);
assert.deepEqual(
  VoiceDsl.withoutOverlap(["fga 14", "b 3"], ["b 3", "r 3"]),
  ["r 3"],
);
assert.deepEqual(
  VoiceDsl.withoutOverlap(
    ["fga 14", "b 3", "r 3"],
    ["fga 14", "b 3", "r 3", "fgm 3"],
  ),
  ["fgm 3"],
);

assert.equal(VoiceDsl.parseLine("R3", { players: roster }).line, "r 3");
assert.throws(
  () => VoiceDsl.parseLine("R3 FGM3", { players: roster }),
  /Extra words:/,
  "the event editor accepts exactly one DSL line",
);

for (const spoken of ["fga ninety nine", "r potato", "fga 21 extra"]) {
  const parsed = VoiceDsl.parseUtterance(spoken, { players: roster });
  assert.equal(parsed.ok, false, spoken);
}

console.log(`${cases.length} voice parser cases: all match`);
