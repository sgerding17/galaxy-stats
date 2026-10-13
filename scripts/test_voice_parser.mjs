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
  ["eye gee one two three five fourteen", "ig 1 2 3 5 14"],
  ["o j fourteen arrow g", "oj 14 -> g"],
  ["o j fourteen ball g", "oj 14 -> g"],
  ["d j five to o", "dj 5 -> o"],
  ["j", "j"],
  ["o j fourteen", "oj 14"],
  ["d j five", "dj 5"],
  ["see fourteen thirty", "c 1430"],
  ["see twenty zero ball g", "c 2000 -> g"],
  ["c one four three zero", "c 1430"],
  ["c nine zero zero", "c 0900"],
  ["t o", "t o"],
  ["t o twenty two", "to 22"],
  ["t oh twenty two", "to 22"],
  ["tee o twenty two", "to 22"],
  ["tee oh twenty one", "to 21"],
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

const grammarPhrases = VoiceDsl.grammarPhrases({ players: roster });
const strictGrammarCases = [
  ["f g m five", "fgm 5"],
  ["f g a fourteen", "fga 14"],
  ["three f g m oh", "3fgm o"],
  ["three f g a twenty one", "3fga 21"],
  ["f t m twenty two", "ftm 22"],
  ["f t a oh", "fta o"],
  ["are galaxy", "r g"],
  ["ay fourteen", "a 14"],
  ["ess twenty two", "s 22"],
  ["bee three", "b 3"],
  ["tee oh twenty one", "to 21"],
  ["t o twenty two", "to 22"],
  ["j", "j"],
  ["j ball gee", "j -> g"],
  ["o jay fourteen", "oj 14"],
  ["o jay fourteen ball gee", "oj 14 -> g"],
  ["dee jay five", "dj 5"],
  ["dee jay five ball oh", "dj 5 -> o"],
  ["p ay e", "pae"],
  ["see fourteen thirty", "c 1430"],
  ["see twenty zero ball gee", "c 2000 -> g"],
];

assert.equal(grammarPhrases.includes("[unk]"), true, "grammar includes [unk]");
for (const [phrase, line] of strictGrammarCases) {
  assert.equal(grammarPhrases.includes(phrase), true, `grammar includes ${phrase}`);
  const parsed = VoiceDsl.parseUtterance(phrase, { players: roster });
  assert.equal(parsed.ok, true, `${phrase}: ${parsed.error}`);
  assert.equal(parsed.line, line, phrase);
}
const coveredEvents = new Set(strictGrammarCases.map(([, line]) => line.split(" ")[0]));
coveredEvents.add("ig"); // Lineups use the model builder's compact roster-state graph.
assert.deepEqual(
  [...coveredEvents].sort(),
  VoiceDsl._eventsForTest.filter((event) => event !== "t").sort(),
  "strict grammar coverage includes every dictated DSL event token",
);
for (const phrase of ["see one four three zero", "see nine zero zero"]) {
  assert.equal(grammarPhrases.includes(phrase), true, `grammar includes ${phrase}`);
}
assert.equal(grammarPhrases.includes("tee ay twenty five"), false, "grammar rejects T A");
assert.equal(grammarPhrases.includes("t o"), false, "opening tip is handled by game creation");
assert.equal(grammarPhrases.includes("tee gee"), false, "opening tip is not dictated");
assert.equal(grammarPhrases.includes("see twenty one"), false, "grammar rejects clocks after 20:00");
assert.equal(grammarPhrases.includes("five s"), false, "commands do not encode boundary bigrams");
assert.equal(grammarPhrases.some((phrase) => /\d/.test(phrase)), false, "grammar uses spoken numbers");
assert.equal(VoiceDsl.trimEdgeUnknowns("[unk] f g a fourteen [unk]"), "f g a fourteen");
assert.equal(VoiceDsl.trimEdgeUnknowns("[unk] [unk]"), "");
assert.deepEqual(
  VoiceDsl.recognizedSegments("[unk] f g a fourteen [unk] are oh [unk]"),
  ["f g a fourteen", "are oh"],
);

const grammarSequence = VoiceDsl.parseUtterance(
  "turnover five s twenty two f g a fourteen are oh",
  { players: roster },
);
assert.equal(grammarSequence.ok, true, grammarSequence.error);
assert.deepEqual(grammarSequence.lines, ["to 5", "s 22", "fga 14", "r o"]);

const boundarySequence = VoiceDsl.parseUtterance(
  "j o jay fourteen dee jay five see fourteen thirty tee oh five " +
    "see nine zero zero three f g a fourteen",
  { players: roster },
);
assert.equal(boundarySequence.ok, true, boundarySequence.error);
assert.deepEqual(boundarySequence.lines, [
  "j", "oj 14", "dj 5", "c 1430", "to 5", "c 0900", "3fga 14",
]);

const voskSequence = VoiceDsl.parseUtterance(
  "f g a oh bee three r three f g m three a twenty one",
  { players: roster },
);
assert.equal(voskSequence.ok, true, voskSequence.error);
assert.deepEqual(voskSequence.lines, ["fga o", "b 3", "r 3", "fgm 3", "a 21"]);

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

for (const spoken of ["fga ninety nine", "r potato", "fga 21 extra", "c 2001"]) {
  const parsed = VoiceDsl.parseUtterance(spoken, { players: roster });
  assert.equal(parsed.ok, false, spoken);
}

for (const spoken of ["t a twenty five", "tee ay twenty five"]) {
  const parsed = VoiceDsl.parseUtterance(spoken, { players: roster });
  assert.equal(parsed.ok, false, `${spoken} is not legal DSL`);
}

console.log(`${cases.length} voice parser cases: all match`);
