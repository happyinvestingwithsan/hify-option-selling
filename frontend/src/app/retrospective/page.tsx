"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  BookPlus,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  RefreshCw,
} from "lucide-react";
import { ApiError, apiFetch } from "@/lib/api";
import {
  AuditFinding,
  RetrospectiveAuditResponse,
  formatINR,
} from "@/lib/types";
import { SortableTh, useTableSort } from "@/components/SortableTh";

interface RuleGroup {
  rule: string;
  missedProfit: number;
  count: number;
}

export default function RetrospectivePage() {
  const [audit, setAudit] = useState<RetrospectiveAuditResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loggingId, setLoggingId] = useState<string | null>(null);
  const [loggedIds, setLoggedIds] = useState<Record<string, boolean>>({});
  const [expandedIds, setExpandedIds] = useState<Record<string, boolean>>({});
  const [banner, setBanner] = useState<string | null>(null);

  const loadAudit = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<RetrospectiveAuditResponse>(
        "/api/retrospective/audit"
      );
      setAudit(data);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to load rulebook retrospective audit."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAudit();
  }, [loadAudit]);

  async function handleLogAsLesson(finding: AuditFinding) {
    setLoggingId(finding.id);
    setBanner(null);
    try {
      await apiFetch("/api/lessons", {
        method: "POST",
        body: JSON.stringify({
          category: finding.rule_violated,
          title: `${finding.symbol} ${finding.rule_violated}`,
          description: finding.what_happened,
          mistake_type: finding.rule_violated,
          rule_added: finding.better_action,
          append_to_doc: false,
        }),
      });
      setLoggedIds((prev) => ({ ...prev, [finding.id]: true }));
      setBanner(
        `Logged "${finding.symbol} ${finding.rule_violated}" to Lessons Learnt.`
      );
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to log finding as a lesson."
      );
    } finally {
      setLoggingId(null);
    }
  }

  function toggleExpand(id: string) {
    setExpandedIds((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  const score = Math.max(0, Math.min(100, audit?.discipline_score_pct ?? 100));
  const scoreColor =
    score >= 85
      ? "text-[var(--hify-success)]"
      : score >= 60
      ? "text-[#8E6C20] dark:text-[#C8A951]"
      : "text-[var(--hify-error)]";
  const gaugeStroke =
    score >= 85 ? "#10B981" : score >= 60 ? "#C8A951" : "#F43F5E";

  const ruleGroups = useMemo<RuleGroup[]>(() => {
    if (!audit?.findings.length) return [];
    const map = new Map<string, { missedProfit: number; count: number }>();
    for (const f of audit.findings) {
      const existing = map.get(f.rule_violated) ?? {
        missedProfit: 0,
        count: 0,
      };
      existing.missedProfit += f.missed_profit_inr || 0;
      existing.count += 1;
      map.set(f.rule_violated, existing);
    }
    return Array.from(map.entries())
      .map(([rule, vals]) => ({
        rule,
        missedProfit: vals.missedProfit,
        count: vals.count,
      }))
      .sort((a, b) => b.missedProfit - a.missedProfit || b.count - a.count);
  }, [audit]);

  const maxRuleMissed = useMemo(() => {
    if (!ruleGroups.length) return 1;
    return Math.max(...ruleGroups.map((g) => g.missedProfit), 1);
  }, [ruleGroups]);

  const decayFindings = useMemo(() => {
    if (!audit?.findings.length) return [];
    return audit.findings.filter(
      (f) => f.actual_decay_pct !== null || f.expected_target_pct !== null
    );
  }, [audit]);

  const findingsSort = useTableSort(audit?.findings ?? [], "missed_profit_inr", "desc", {
    symbol: (r) => `${r.symbol} ${r.strike} ${r.option_type}`,
    rule_violated: (r) => r.rule_violated,
    actual_decay_pct: (r) => r.actual_decay_pct ?? -1,
    missed_profit_inr: (r) => r.missed_profit_inr,
  });

  // Donut geometry
  const radius = 44;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - score / 100);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-[var(--hify-text)]">
            Rulebook Analysis
          </h1>
          <p className="mt-0.5 text-xs text-[var(--hify-text-secondary)]">
            Audited against{" "}
            <span className="text-[#8E6C20] dark:text-[#C8A951]">
              STRATEGY_RULEBOOK.md
            </span>
          </p>
        </div>

        <button
          type="button"
          onClick={loadAudit}
          disabled={loading}
          className="flex min-h-[44px] items-center gap-2 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-4 text-sm font-medium text-[var(--hify-text)] transition-colors hover:bg-[var(--hify-bg)] disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          <span>Re-Run Audit</span>
        </button>
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

      {/* Tier 1: Summary KPIs (Compact, no redundant subtitles) */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
          <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--hify-text-secondary)]">
            Discipline Score
          </div>
          <div
            className={`mt-1 font-mono font-mono-num text-2xl font-semibold ${scoreColor}`}
          >
            {audit ? `${audit.discipline_score_pct.toFixed(1)}%` : "—"}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
          <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--hify-text-secondary)]">
            Missed Profit
          </div>
          <div className="mt-1 font-mono font-mono-num text-2xl font-semibold text-[var(--hify-error)]">
            {audit ? formatINR(audit.total_missed_profit_inr) : "—"}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
          <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--hify-text-secondary)]">
            Violations
          </div>
          <div className="mt-1 font-mono font-mono-num text-2xl font-semibold text-[var(--hify-warning)]">
            {audit ? audit.violations_count : "—"}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
          <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--hify-text-secondary)]">
            Trades Audited
          </div>
          <div className="mt-1 font-mono font-mono-num text-2xl font-semibold text-[var(--hify-text)]">
            {audit ? audit.total_trades_audited : "—"}
          </div>
        </div>
      </div>

      {/* Visual Analytics Row (Analysis-only inline SVGs) */}
      {!loading && audit && (
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* 1. Discipline Score Gauge / Donut */}
          <div className="flex flex-col justify-between rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--hify-text-secondary)]">
                Discipline Gauge
              </h2>
              <span className="font-mono font-mono-num text-[11px] text-[var(--hify-text-secondary)]">
                {audit.violations_count} / {audit.total_trades_audited} flagged
              </span>
            </div>

            <div className="my-3 flex items-center justify-center">
              <svg
                viewBox="0 0 120 120"
                className="h-36 w-36"
                role="img"
                aria-label={`Discipline Score ${score.toFixed(1)}%`}
              >
                <circle
                  cx="60"
                  cy="60"
                  r={radius}
                  fill="none"
                  stroke="var(--hify-border)"
                  strokeWidth="10"
                />
                <circle
                  cx="60"
                  cy="60"
                  r={radius}
                  fill="none"
                  stroke={gaugeStroke}
                  strokeWidth="10"
                  strokeLinecap="round"
                  strokeDasharray={circumference}
                  strokeDashoffset={dashOffset}
                  transform="rotate(-90 60 60)"
                />
                <text
                  x="60"
                  y="58"
                  textAnchor="middle"
                  className="fill-[var(--hify-text)] font-mono text-lg font-bold"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {score.toFixed(0)}%
                </text>
                <text
                  x="60"
                  y="74"
                  textAnchor="middle"
                  className="fill-[var(--hify-text-secondary)] text-[9px] uppercase tracking-wider"
                >
                  {score >= 85 ? "Disciplined" : score >= 60 ? "Caution" : "At Risk"}
                </text>
              </svg>
            </div>

            <div className="flex items-center justify-between border-t border-[var(--hify-border)] pt-2.5 text-[11px] text-[var(--hify-text-secondary)]">
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full bg-[#10B981]" />
                85%+
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full bg-[#C8A951]" />
                60–84%
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full bg-[#F43F5E]" />
                &lt;60%
              </span>
            </div>
          </div>

          {/* 2. Missed Profit by Rule Violated */}
          <div className="flex flex-col rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--hify-text-secondary)]">
                Missed Profit by Rule
              </h2>
              <span className="font-mono font-mono-num text-[11px] text-[var(--hify-error)]">
                {formatINR(audit.total_missed_profit_inr)}
              </span>
            </div>

            {ruleGroups.length === 0 ? (
              <div className="flex flex-1 items-center justify-center py-8 text-xs text-[var(--hify-text-secondary)]">
                No rule violations recorded.
              </div>
            ) : (
              <div className="mt-3 flex-1 space-y-3">
                {ruleGroups.map((group, idx) => {
                  const pct =
                    maxRuleMissed > 0
                      ? Math.max(4, (group.missedProfit / maxRuleMissed) * 100)
                      : 0;
                  const barColor =
                    idx === 0
                      ? "#F43F5E"
                      : idx === 1
                      ? "#EA580C"
                      : "#C8A951";
                  return (
                    <div key={group.rule} className="space-y-1">
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="truncate font-medium text-[var(--hify-text)]">
                          {group.rule}{" "}
                          <span className="font-mono font-mono-num text-[10px] text-[var(--hify-text-secondary)]">
                            ({group.count})
                          </span>
                        </span>
                        <span className="shrink-0 font-mono font-mono-num text-xs font-semibold text-[var(--hify-text)]">
                          {formatINR(group.missedProfit)}
                        </span>
                      </div>
                      <svg
                        viewBox="0 0 200 10"
                        className="h-2.5 w-full"
                        preserveAspectRatio="none"
                        role="img"
                        aria-label={`${group.rule}: ${formatINR(group.missedProfit)}`}
                      >
                        <rect
                          x="0"
                          y="0"
                          width="200"
                          height="10"
                          rx="5"
                          fill="var(--hify-border)"
                          opacity="0.45"
                        />
                        <rect
                          x="0"
                          y="0"
                          width={(pct / 100) * 200}
                          height="10"
                          rx="5"
                          fill={barColor}
                        />
                      </svg>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 3. Actual vs Target Decay Comparison */}
          <div className="flex flex-col rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--hify-text-secondary)]">
                Actual vs Target Decay
              </h2>
              <div className="flex items-center gap-3 text-[10px] text-[var(--hify-text-secondary)]">
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-sm bg-[#10B981]" />
                  Actual
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-sm bg-[#C8A951]" />
                  Target
                </span>
              </div>
            </div>

            {decayFindings.length === 0 ? (
              <div className="flex flex-1 items-center justify-center py-8 text-xs text-[var(--hify-text-secondary)]">
                No decay target variances to plot.
              </div>
            ) : (
              <div className="mt-3 max-h-48 space-y-2.5 overflow-y-auto pr-1">
                {decayFindings.map((f) => {
                  const actual = Math.max(0, Math.min(100, f.actual_decay_pct ?? 0));
                  const target = Math.max(
                    0,
                    Math.min(100, f.expected_target_pct ?? 0)
                  );
                  const metTarget =
                    f.actual_decay_pct !== null &&
                    f.expected_target_pct !== null &&
                    f.actual_decay_pct >= f.expected_target_pct;
                  const actualColor = metTarget ? "#10B981" : "#F43F5E";
                  return (
                    <div key={f.id} className="space-y-1">
                      <div className="flex items-center justify-between gap-2 text-[11px]">
                        <span className="truncate font-mono font-mono-num font-medium text-[var(--hify-text)]">
                          {f.symbol} {f.strike > 0 ? f.strike : ""} {f.option_type}
                        </span>
                        <span className="shrink-0 font-mono font-mono-num text-[11px] text-[var(--hify-text-secondary)]">
                          {f.actual_decay_pct !== null
                            ? `${f.actual_decay_pct.toFixed(0)}%`
                            : "—"}{" "}
                          /{" "}
                          {f.expected_target_pct !== null
                            ? `${f.expected_target_pct.toFixed(0)}%`
                            : "—"}
                        </span>
                      </div>
                      <svg
                        viewBox="0 0 200 14"
                        className="h-3.5 w-full"
                        preserveAspectRatio="none"
                        role="img"
                        aria-label={`${f.symbol} actual ${actual}% vs target ${target}%`}
                      >
                        <rect
                          x="0"
                          y="0"
                          width="200"
                          height="6"
                          rx="3"
                          fill="var(--hify-border)"
                          opacity="0.4"
                        />
                        <rect
                          x="0"
                          y="0"
                          width={(actual / 100) * 200}
                          height="6"
                          rx="3"
                          fill={actualColor}
                        />
                        <rect
                          x="0"
                          y="8"
                          width="200"
                          height="6"
                          rx="3"
                          fill="var(--hify-border)"
                          opacity="0.4"
                        />
                        <rect
                          x="0"
                          y="8"
                          width={(target / 100) * 200}
                          height="6"
                          rx="3"
                          fill="#C8A951"
                        />
                      </svg>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Recommendations Strip */}
      {audit && audit.recommendations.length > 0 && (
        <section className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[#8E6C20] dark:text-[#C8A951]">
            Rulebook Takeaways
          </h2>
          <ul className="mt-2 space-y-1.5 text-xs text-[var(--hify-text)]">
            {audit.recommendations.map((rec) => (
              <li key={rec} className="flex items-start gap-2">
                <ClipboardCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#8E6C20] dark:text-[#C8A951]" />
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Tier 2 & 3: Compact Scannable Audit Findings Table + Expandable Detail */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[var(--hify-text)]">
            Audit Findings
          </h2>
          {audit && audit.findings.length > 0 && (
            <span className="text-[11px] text-[var(--hify-text-secondary)]">
              Tap a row for details
            </span>
          )}
        </div>

        {loading && (
          <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-6 text-center text-xs text-[var(--hify-text-secondary)]">
            Running rulebook retrospective audit...
          </div>
        )}

        {!loading && audit && audit.findings.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-8 text-center">
            <CheckCircle2 className="h-8 w-8 text-[var(--hify-success)]" />
            <p className="mt-2 text-sm font-semibold text-[var(--hify-text)]">
              Clean Execution — 100% Rulebook Discipline
            </p>
            <p className="mt-1 text-xs text-[var(--hify-text-secondary)]">
              No premature exits, wide spreads, naked calls, or Aukaat breaches detected.
            </p>
          </div>
        )}

        {!loading && audit && audit.findings.length > 0 && (
          <>
            {/* Desktop Table */}
            <div className="hidden overflow-x-auto rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] md:block">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-[var(--hify-border)] text-[11px] font-medium uppercase tracking-wider text-[var(--hify-text-secondary)]">
                    <SortableTh label="Contract" columnKey="symbol" activeKey={findingsSort.sortKey} dir={findingsSort.sortDir} onSort={findingsSort.toggleSort} className="px-4 py-3" />
                    <SortableTh label="Rule" columnKey="rule_violated" activeKey={findingsSort.sortKey} dir={findingsSort.sortDir} onSort={findingsSort.toggleSort} className="px-4 py-3" />
                    <SortableTh label="Decay (Actual / Target)" columnKey="actual_decay_pct" activeKey={findingsSort.sortKey} dir={findingsSort.sortDir} onSort={findingsSort.toggleSort} align="right" className="px-4 py-3" />
                    <SortableTh label="Missed Profit" columnKey="missed_profit_inr" activeKey={findingsSort.sortKey} dir={findingsSort.sortDir} onSort={findingsSort.toggleSort} align="right" className="px-4 py-3" />
                    <th className="px-4 py-3 text-right">Log Lesson</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--hify-border)]">
                  {findingsSort.sortedRows.map((finding) => {
                    const isLogged = Boolean(loggedIds[finding.id]);
                    const isExpanded = Boolean(expandedIds[finding.id]);
                    return (
                      <React.Fragment key={finding.id}>
                        <tr
                          onClick={() => toggleExpand(finding.id)}
                          className="cursor-pointer transition-colors hover:bg-[var(--hify-bg)]"
                        >
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              {isExpanded ? (
                                <ChevronDown className="h-4 w-4 shrink-0 text-[var(--hify-text-secondary)]" />
                              ) : (
                                <ChevronRight className="h-4 w-4 shrink-0 text-[var(--hify-text-secondary)]" />
                              )}
                              <span className="font-mono font-mono-num font-semibold text-[var(--hify-text)]">
                                {finding.symbol}{" "}
                                {finding.strike > 0 ? `${finding.strike} ` : ""}
                                {finding.option_type}
                              </span>
                              <span className="rounded border border-[var(--hify-border)] px-1.5 py-0.5 text-[10px] text-[var(--hify-text-secondary)]">
                                {finding.expiry}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <span className="inline-block rounded-full border border-[var(--hify-error)]/40 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--hify-error)]">
                              {finding.rule_violated}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right font-mono font-mono-num text-[var(--hify-text)]">
                            {finding.actual_decay_pct !== null
                              ? `${finding.actual_decay_pct.toFixed(1)}%`
                              : "—"}
                            {" / "}
                            {finding.expected_target_pct !== null
                              ? `${finding.expected_target_pct.toFixed(1)}%`
                              : "—"}
                          </td>
                          <td className="px-4 py-3 text-right font-mono font-mono-num font-semibold text-[var(--hify-error)]">
                            {formatINR(finding.missed_profit_inr)}
                          </td>
                          <td
                            className="px-4 py-2 text-right"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button
                              type="button"
                              disabled={loggingId === finding.id || isLogged}
                              onClick={() => handleLogAsLesson(finding)}
                              className="inline-flex min-h-[36px] items-center gap-1.5 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface-raised)] px-3 text-xs font-medium text-[var(--hify-text)] transition-colors hover:bg-[var(--hify-bg)] disabled:opacity-60"
                            >
                              <BookPlus className="h-3.5 w-3.5 text-[#8E6C20] dark:text-[#C8A951]" />
                              <span>
                                {isLogged
                                  ? "Logged"
                                  : loggingId === finding.id
                                  ? "Logging..."
                                  : "Log Lesson"}
                              </span>
                            </button>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr className="bg-[var(--hify-bg)]/60">
                            <td colSpan={5} className="px-6 py-3">
                              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                                <div>
                                  <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--hify-text-secondary)]">
                                    What Happened
                                  </div>
                                  <p className="mt-1 text-xs text-[var(--hify-text)]">
                                    {finding.what_happened}
                                  </p>
                                </div>
                                <div>
                                  <div className="text-[10px] font-semibold uppercase tracking-wider text-[#8E6C20] dark:text-[#C8A951]">
                                    Better Action
                                  </div>
                                  <p className="mt-1 text-xs text-[var(--hify-text)]">
                                    {finding.better_action}
                                  </p>
                                </div>
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

            {/* Mobile Compact List (< md) */}
            <div className="divide-y divide-[var(--hify-border)] overflow-hidden rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] md:hidden">
              {audit.findings.map((finding) => {
                const isLogged = Boolean(loggedIds[finding.id]);
                const isExpanded = Boolean(expandedIds[finding.id]);
                return (
                  <div key={finding.id} className="p-3.5">
                    <button
                      type="button"
                      onClick={() => toggleExpand(finding.id)}
                      className="flex min-h-[44px] w-full items-center justify-between gap-2 text-left"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4 shrink-0 text-[var(--hify-text-secondary)]" />
                          ) : (
                            <ChevronRight className="h-4 w-4 shrink-0 text-[var(--hify-text-secondary)]" />
                          )}
                          <span className="truncate font-mono font-mono-num text-xs font-semibold text-[var(--hify-text)]">
                            {finding.symbol}{" "}
                            {finding.strike > 0 ? `${finding.strike} ` : ""}
                            {finding.option_type}
                          </span>
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5 pl-5">
                          <span className="rounded-full border border-[var(--hify-error)]/40 px-2 py-0.5 text-[10px] font-semibold uppercase text-[var(--hify-error)]">
                            {finding.rule_violated}
                          </span>
                          <span className="font-mono font-mono-num text-[11px] text-[var(--hify-text-secondary)]">
                            {finding.actual_decay_pct !== null
                              ? `${finding.actual_decay_pct.toFixed(0)}%`
                              : "—"}
                            /
                            {finding.expected_target_pct !== null
                              ? `${finding.expected_target_pct.toFixed(0)}%`
                              : "—"}
                          </span>
                        </div>
                      </div>
                      <span className="shrink-0 font-mono font-mono-num text-xs font-semibold text-[var(--hify-error)]">
                        {formatINR(finding.missed_profit_inr)}
                      </span>
                    </button>

                    {isExpanded && (
                      <div className="mt-3 space-y-2.5 border-t border-[var(--hify-border)] pt-3">
                        <div>
                          <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--hify-text-secondary)]">
                            What Happened
                          </div>
                          <p className="mt-0.5 text-xs text-[var(--hify-text)]">
                            {finding.what_happened}
                          </p>
                        </div>
                        <div>
                          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#8E6C20] dark:text-[#C8A951]">
                            Better Action
                          </div>
                          <p className="mt-0.5 text-xs text-[var(--hify-text)]">
                            {finding.better_action}
                          </p>
                        </div>
                        <button
                          type="button"
                          disabled={loggingId === finding.id || isLogged}
                          onClick={() => handleLogAsLesson(finding)}
                          className="flex min-h-[44px] w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface-raised)] px-3 text-xs font-medium text-[var(--hify-text)] transition-colors hover:bg-[var(--hify-bg)] disabled:opacity-60"
                        >
                          <BookPlus className="h-3.5 w-3.5 text-[#8E6C20] dark:text-[#C8A951]" />
                          <span>
                            {isLogged
                              ? "Logged to Lessons"
                              : loggingId === finding.id
                              ? "Logging..."
                              : "Log Lesson"}
                          </span>
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
