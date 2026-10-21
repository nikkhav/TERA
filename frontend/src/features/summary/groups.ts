import type {
  DocumentResult,
  Expense,
  Summary,
} from "../../shared/types/domain";

export const duplicateWarning = (text: string) =>
  /Doppelbeleg|dieselbe Ausgabe|Zusammengehörige Belege|Gemeinsame Referenz/i.test(
    text,
  );

export function relatedGroup(summary: Summary, id: string): DocumentResult[] {
  const ids = new Set([id]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const doc of summary.documents) {
      if (
        ["payment", "booking", "supporting"].includes(
          doc.facts.document_kind ?? "",
        )
      )
        continue;
      if (
        ids.has(doc.document_id) ||
        doc.related_document_ids?.some((i) => ids.has(i))
      ) {
        for (const i of [
          doc.document_id,
          ...(doc.related_document_ids ?? []),
        ]) {
          if (!ids.has(i)) {
            ids.add(i);
            changed = true;
          }
        }
      }
    }
  }
  return summary.documents.filter(
    (d) =>
      ids.has(d.document_id) &&
      !["payment", "booking", "supporting"].includes(
        d.facts.document_kind ?? "",
      ),
  );
}

export function reviewTasks(summary: Summary) {
  const visited = new Set<string>();
  const active = new Set(summary.warnings.map((w) => w.document_id));
  const tasks: { documents: DocumentResult[]; isRelationship: boolean }[] = [];
  for (const doc of summary.documents) {
    if (
      visited.has(doc.document_id) ||
      !active.has(doc.document_id) ||
      !doc.warnings.some(duplicateWarning)
    )
      continue;
    const documents = relatedGroup(summary, doc.document_id);
    if (documents.length > 1) {
      documents.forEach((d) => visited.add(d.document_id));
      tasks.push({ documents, isRelationship: true });
    }
  }
  for (const doc of summary.documents) {
    if (!visited.has(doc.document_id) && active.has(doc.document_id))
      tasks.push({ documents: [doc], isRelationship: false });
  }
  return tasks;
}

export type ExpenseRow = {
  expense: Expense;
  documentIds: string[];
  possibleMatch: boolean;
};
export function expenseRows(summary: Summary): ExpenseRow[] {
  const visited = new Set<string>();
  return summary.expenses.flatMap((expense, index) => {
    if (visited.has(`${index}`)) return [];
    const doc = summary.documents.find(
      (d) => d.document_id === expense.document_id,
    );
    const related = doc?.warnings.some(duplicateWarning)
      ? relatedGroup(summary, expense.document_id)
      : [];
    const ids = new Set(related.map((d) => d.document_id));
    const candidates = summary.expenses
      .map((e, i) => ({ e, i }))
      .filter(({ e }) => ids.has(e.document_id));
    const canGroup =
      related.length > 1 &&
      expense.currency !== null &&
      candidates.length === related.length &&
      candidates.every(
        ({ e }) =>
          e.status !== "approved" &&
          e.status !== "rejected" &&
          e.category === expense.category &&
          e.currency === expense.currency &&
          e.amount !== null &&
          Number(e.amount) === Number(expense.amount),
      );
    const supporting = summary.documents
      .filter((d) => d.duplicate_of === expense.document_id)
      .map((d) => d.document_id);
    const documentIds = canGroup
      ? related.map((d) => d.document_id)
      : [expense.document_id, ...supporting];
    if (canGroup) candidates.forEach(({ i }) => visited.add(`${i}`));
    visited.add(`${index}`);
    return [{ expense, documentIds, possibleMatch: canGroup }];
  });
}
