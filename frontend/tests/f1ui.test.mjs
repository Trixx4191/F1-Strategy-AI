import test from "node:test";
import assert from "node:assert/strict";
import { strategyCompounds, formatRaceTime } from "../src/f1ui.ts";

test("ordered stints take precedence over compound summaries, including repeated tyres", () => {
  assert.deepEqual(
    strategyCompounds({
      strategy: "SOFT(20) → HARD(18) → HARD(19)",
      compound_sequence: ["HARD + SOFT"],
    }),
    ["SOFT", "HARD", "HARD"],
  );
  assert.deepEqual(
    strategyCompounds({
      strategy: "MEDIUM(25) → HARD(32)",
      compound_sequence: ["HARD", "MEDIUM"],
    }),
    ["MEDIUM", "HARD"],
  );
});

test("legacy sequences and empty results remain usable", () => {
  assert.deepEqual(strategyCompounds({ compound_sequence: ["SOFT", "HARD"] }), [
    "SOFT",
    "HARD",
  ]);
  assert.deepEqual(strategyCompounds({ compound_sequence: ["HARD + SOFT"] }), [
    "HARD",
    "SOFT",
  ]);
  assert.deepEqual(strategyCompounds({}), []);
});

test("race time formatting carries rounded seconds into minutes and hours", () => {
  assert.equal(formatRaceTime(5457.8154), "1:30:57.8");
  assert.equal(formatRaceTime(59.99), "01:00.0");
  assert.equal(formatRaceTime(3599.99), "1:00:00.0");
  assert.equal(formatRaceTime(null), "—");
  assert.equal(formatRaceTime(NaN), "—");
});
