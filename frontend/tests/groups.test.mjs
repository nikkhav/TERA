import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const source = await readFile(new URL("../src/features/summary/groups.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const {expenseRows, reviewTasks} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const warning = "Möglicherweise dieselbe Ausgabe wie ein weiterer Beleg; gemeinsam prüfen.";
function summary() {
  const documents = ["a", "b"].map((id, index) => ({document_id: id, facts: {document_kind: index ? "receipt" : "invoice"}, related_document_ids: [index ? "a" : "b"], warnings: [warning]}));
  return {documents, expenses: documents.map((d) => ({document_id: d.document_id, amount: "50.58", currency: "AUD", category: "Transport", status: "needs_review"})), warnings: documents.map((d) => ({document_id: d.document_id})), totals: {in_review: "101.16"}};
}
test("one candidate row and one task for two matching documents; totals unchanged", () => {
  const value = summary();
  const before = structuredClone(value);
  assert.equal(reviewTasks(value).length, 1);
  const rows = expenseRows(value);
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0].documentIds, ["a", "b"]);
  assert.equal(rows[0].possibleMatch, true);
  assert.deepEqual(value, before);
});
test("different amounts and multi-category invoices remain individually visible", () => {
  const value = summary();
  value.expenses[1].amount = "51.58";
  assert.equal(expenseRows(value).length, 2);
  assert.equal(reviewTasks(value).length, 1);
  value.expenses[1].amount = "50.58";
  value.expenses.push({...value.expenses[0], category: "Verpflegung", amount: "1.00"});
  assert.equal(expenseRows(value).length, 3);
});
test("explicitly separate expenses are not collapsed despite retained document links", () => {
  const value = summary();
  value.documents.forEach((d) => {d.warnings = [];});
  value.warnings = [];
  value.expenses.forEach((e) => {e.status = "extracted";});
  assert.equal(expenseRows(value).length, 2);
  assert.equal(reviewTasks(value).length, 0);
});
test("a grouped task preserves other findings on either document", () => {
  const value = summary();
  value.documents[0].warnings = ["Gesamtbetrag bitte prüfen."];
  const tasks = reviewTasks(value);
  assert.equal(tasks.length, 1);
  assert.equal(tasks[0].documents.length, 2);
  assert.ok(tasks[0].documents[0].warnings[0].includes("Gesamtbetrag"));
});
test("reviewed expenses are not presented as one unresolved candidate", () => {
  const value = summary();
  value.expenses.forEach((e) => {e.status = "approved";});
  assert.equal(expenseRows(value).length, 2);
});

test("a confirmed shared expense shows both retained source documents", () => {
  const value = summary();
  value.documents.forEach((d) => {d.warnings = [];});
  value.documents[1].duplicate_of = "a";
  value.expenses = [value.expenses[0]];
  value.expenses[0].status = "extracted";
  const rows = expenseRows(value);
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0].documentIds, ["a", "b"]);
  assert.equal(rows[0].possibleMatch, false);
});
test("unknown currencies do not collapse amounts into one expense row", () => {
  const value = summary();
  value.expenses.forEach((e) => {e.currency = null;});
  assert.equal(expenseRows(value).length, 2);
});
