import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";
import ts from "typescript";
const source = await readFile(new URL("../src/features/summary/review.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const {reviewSummary} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
test("missing date evidence identifies the date and a concrete review action", () => {
  const [message] = reviewSummary({warnings: ["Rechnungsdatum nicht eindeutig im Beleg nachgewiesen."]});
  assert.match(message, /Belegdatum/);
  assert.match(message, /Original prüfen/);
  assert.doesNotMatch(message, /Einige Beträge/);
});
test("unsupported invoice total remains identifiable instead of becoming generic", () => {
  const warning = "Gesamtbetrag nicht eindeutig im Beleg nachgewiesen.";
  assert.deepEqual(reviewSummary({warnings: [warning]}), [warning]);
});
test("repetitive item evidence warnings collapse and punctuation is not a finding", () => {
  const warnings = Array.from({length: 18}, (_, i) => `Position ${i + 1}: Bruttobetrag nicht eindeutig im Beleg nachgewiesen.`);
  assert.equal(reviewSummary({warnings}).length, 1);
  assert.deepEqual(reviewSummary({warnings: ["-", " ", "•"]}), []);
});
