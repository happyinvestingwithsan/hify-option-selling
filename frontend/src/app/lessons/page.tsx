"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  Plus,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { ApiError, apiFetch } from "@/lib/api";
import { LessonItem, LessonsListResponse } from "@/lib/types";
import { SortableTh, useTableSort } from "@/components/SortableTh";

const CATEGORIES = [
  "DISCIPLINE",
  "IMPATIENCE",
  "FEAR",
  "GREED",
  "DECAY_LOCK_OVERRIDE",
  "ROLLOVER",
  "LIQUIDITY",
];

export default function LessonsPage() {
  const [lessons, setLessons] = useState<LessonItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // Create Lesson Modal & Form state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [category, setCategory] = useState("DISCIPLINE");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [mistakeType, setMistakeType] = useState("");
  const [ruleAdded, setRuleAdded] = useState("");
  const [appendToDoc, setAppendToDoc] = useState(false);

  const loadLessons = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<LessonsListResponse>("/api/lessons");
      setLessons(res.lessons);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to load lessons log."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLessons();
  }, [loadLessons]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setBanner(null);
    try {
      await apiFetch("/api/lessons", {
        method: "POST",
        body: JSON.stringify({
          category,
          title: title.trim(),
          description: description.trim(),
          mistake_type: mistakeType.trim(),
          rule_added: ruleAdded.trim(),
          append_to_doc: appendToDoc,
        }),
      });
      setTitle("");
      setDescription("");
      setMistakeType("");
      setRuleAdded("");
      setAppendToDoc(false);
      setShowCreateModal(false);
      setBanner(
        appendToDoc
          ? "Lesson saved to SQLite and appended to docs/LESSONS_LEARNT.md."
          : "Lesson saved to SQLite."
      );
      await loadLessons();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save lesson.");
    } finally {
      setSubmitting(false);
    }
  }

  const lessonsSort = useTableSort(lessons, "id", "desc", {
    id: (r) => r.id,
    category: (r) => r.category,
    title: (r) => r.title,
    created_at: (r) => r.created_at,
    rule_added: (r) => r.rule_added || "",
  });

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight text-[var(--hify-text)]">
          Lessons &amp; Guardrails ({lessons.length})
        </h1>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={loadLessons}
            disabled={loading}
            className="inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-3 text-xs font-medium text-[var(--hify-text)] transition-colors hover:bg-[var(--hify-bg)] disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>

          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg bg-[#C8A951] px-4 text-xs font-semibold text-[#18181B] transition-colors hover:bg-[#B6933A]"
          >
            <Plus className="h-4 w-4" />
            <span>Log Lesson</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-[var(--hify-error)]/40 bg-[var(--hify-surface)] p-4 text-sm text-[var(--hify-error)]">
          {error}
        </div>
      )}

      {banner && (
        <div className="rounded-xl border border-[var(--hify-success)]/40 bg-[var(--hify-surface)] p-3 text-xs font-medium text-[var(--hify-success)]">
          {banner}
        </div>
      )}

      {/* Expandable Lessons Table */}
      <section className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)]">
        {!loading && lessons.length === 0 ? (
          <div className="p-6 text-center text-xs text-[var(--hify-text-secondary)]">
            No lessons or Decay Lock overrides logged yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-xs">
              <thead>
                <tr className="border-b border-[var(--hify-border)] text-[var(--hify-text-secondary)]">
                  <SortableTh label="ID" columnKey="id" activeKey={lessonsSort.sortKey} dir={lessonsSort.sortDir} onSort={lessonsSort.toggleSort} className="px-4 py-2.5" />
                  <SortableTh label="Category" columnKey="category" activeKey={lessonsSort.sortKey} dir={lessonsSort.sortDir} onSort={lessonsSort.toggleSort} className="px-3 py-2.5" />
                  <SortableTh label="Title" columnKey="title" activeKey={lessonsSort.sortKey} dir={lessonsSort.sortDir} onSort={lessonsSort.toggleSort} className="px-3 py-2.5" />
                  <SortableTh label="Date" columnKey="created_at" activeKey={lessonsSort.sortKey} dir={lessonsSort.sortDir} onSort={lessonsSort.toggleSort} className="px-3 py-2.5" />
                  <SortableTh label="Guardrail" columnKey="rule_added" activeKey={lessonsSort.sortKey} dir={lessonsSort.sortDir} onSort={lessonsSort.toggleSort} className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--hify-border)]/60">
                {lessonsSort.sortedRows.map((lesson) => {
                  const isExpanded = expandedId === lesson.id;
                  return (
                    <React.Fragment key={lesson.id}>
                      <tr
                        onClick={() =>
                          setExpandedId(isExpanded ? null : lesson.id)
                        }
                        className="cursor-pointer hover:bg-[var(--hify-bg)]/60"
                      >
                        <td className="px-4 py-3 font-mono font-mono-num font-semibold text-[#8E6C20] dark:text-[#C8A951]">
                          <div className="flex min-h-[24px] items-center gap-1.5">
                            {isExpanded ? (
                              <ChevronDown className="h-3.5 w-3.5 shrink-0" />
                            ) : (
                              <ChevronRight className="h-3.5 w-3.5 shrink-0" />
                            )}
                            <span>LL-{String(lesson.id).padStart(3, "0")}</span>
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <span className="inline-flex rounded-full border border-[var(--hify-border)] px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--hify-text)]">
                            {lesson.category}
                          </span>
                        </td>
                        <td className="px-3 py-3 font-medium text-[var(--hify-text)]">
                          {lesson.title}
                        </td>
                        <td className="px-3 py-3 font-mono font-mono-num text-[11px] text-[var(--hify-text-secondary)]">
                          {lesson.created_at}
                        </td>
                        <td className="px-4 py-3 text-[var(--hify-text-secondary)]">
                          {lesson.rule_added ? (
                            <span className="inline-flex items-center gap-1.5 text-[var(--hify-text)]">
                              <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-[var(--hify-success)]" />
                              <span className="line-clamp-1">{lesson.rule_added}</span>
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="bg-[var(--hify-bg)]/50">
                          <td colSpan={5} className="px-4 py-3">
                            <div className="space-y-2 text-xs">
                              {lesson.mistake_type && (
                                <div>
                                  <span className="rounded border border-[var(--hify-warning)]/40 px-2 py-0.5 font-mono text-[10px] font-medium text-[var(--hify-warning)]">
                                    {lesson.mistake_type}
                                  </span>
                                </div>
                              )}
                              <p className="text-[var(--hify-text-secondary)]">
                                {lesson.description}
                              </p>
                              {lesson.rule_added && (
                                <div className="flex items-start gap-2 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] p-2.5 text-xs text-[var(--hify-text)]">
                                  <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--hify-success)]" />
                                  <span>
                                    <strong className="text-[#8E6C20] dark:text-[#C8A951]">
                                      Guardrail:
                                    </strong>{" "}
                                    {lesson.rule_added}
                                  </span>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Log New Lesson Modal */}
      {showCreateModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-lesson-modal-title"
        >
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-5 shadow-xl">
            <div className="mb-4 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-[#8E6C20] dark:text-[#C8A951]" />
                <h2
                  id="create-lesson-modal-title"
                  className="text-base font-semibold text-[var(--hify-text)]"
                >
                  Log New Mistake / Lesson
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[var(--hify-text-secondary)] hover:bg-[var(--hify-bg)]"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-xs">
                <span className="text-[var(--hify-text-secondary)]">Category</span>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm text-[var(--hify-text)]"
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1 text-xs">
                <span className="text-[var(--hify-text-secondary)]">
                  Mistake / Trigger Type (Optional)
                </span>
                <input
                  type="text"
                  placeholder="e.g. EARLY_EXIT, ROLL_DOWN_STRIKE"
                  value={mistakeType}
                  onChange={(e) => setMistakeType(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono text-sm text-[var(--hify-text)]"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs sm:col-span-2">
                <span className="text-[var(--hify-text-secondary)]">Title</span>
                <input
                  type="text"
                  required
                  placeholder="e.g. Booked DABUR 510 PE at 20% decay out of impatience"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm text-[var(--hify-text)]"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs sm:col-span-2">
                <span className="text-[var(--hify-text-secondary)]">What Happened</span>
                <textarea
                  required
                  rows={3}
                  placeholder="Describe the context, emotion, and market move..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-3 text-sm text-[var(--hify-text)]"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs sm:col-span-2">
                <span className="text-[var(--hify-text-secondary)]">
                  Guardrail / Rule to Enforce
                </span>
                <input
                  type="text"
                  placeholder="e.g. Require Decay Lock override note before closing < 50% GTT"
                  value={ruleAdded}
                  onChange={(e) => setRuleAdded(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm text-[var(--hify-text)]"
                />
              </label>

              <label className="flex min-h-[44px] items-center gap-2 text-xs text-[var(--hify-text)] sm:col-span-2">
                <input
                  type="checkbox"
                  checked={appendToDoc}
                  onChange={(e) => setAppendToDoc(e.target.checked)}
                  className="h-4 w-4"
                />
                <span>Also append to docs/LESSONS_LEARNT.md</span>
              </label>

              <div className="flex flex-col-reverse gap-2 pt-2 sm:col-span-2 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] px-4 text-xs font-medium text-[var(--hify-text)]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[#C8A951] px-5 text-xs font-semibold text-[#18181B] transition-colors hover:bg-[#B6933A] disabled:opacity-50"
                >
                  <Plus className="h-4 w-4" />
                  <span>{submitting ? "Saving..." : "Log Lesson"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
