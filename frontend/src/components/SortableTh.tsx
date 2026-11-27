"use client";

import React, { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

export type SortDir = "asc" | "desc";

export type SortGetters<T, K extends string> = Record<
  K,
  (row: T) => string | number | boolean | null | undefined
>;

export function useTableSort<T, K extends string>(
  rows: T[],
  defaultKey: NoInfer<K>,
  defaultDir: SortDir,
  getters: SortGetters<T, K>
) {
  const [sortKey, setSortKey] = useState<K>(defaultKey);
  const [sortDir, setSortDir] = useState<SortDir>(defaultDir);

  function toggleSort(key: K) {
    if (sortKey === key) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const sortedRows = useMemo(() => {
    const getter = getters[sortKey];
    if (!getter) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const va = getter(a);
      const vb = getter(b);
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;

      let cmp = 0;
      if (typeof va === "number" && typeof vb === "number") {
        cmp = va - vb;
      } else if (typeof va === "boolean" && typeof vb === "boolean") {
        cmp = Number(va) - Number(vb);
      } else {
        cmp = String(va).localeCompare(String(vb), undefined, {
          numeric: true,
          sensitivity: "base",
        });
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [rows, sortKey, sortDir, getters]);

  return { sortedRows, sortKey, sortDir, toggleSort };
}

interface SortableThProps<K extends string> {
  label: string;
  columnKey: K;
  activeKey: K;
  dir: SortDir;
  onSort: (key: K) => void;
  align?: "left" | "right";
  className?: string;
}

export function SortableTh<K extends string>({
  label,
  columnKey,
  activeKey,
  dir,
  onSort,
  align = "left",
  className = "",
}: SortableThProps<K>) {
  const isActive = activeKey === columnKey;
  return (
    <th
      className={`${align === "right" ? "text-right" : "text-left"} font-medium ${className}`}
    >
      <button
        type="button"
        onClick={() => onSort(columnKey)}
        className={`inline-flex items-center gap-1 transition-colors hover:text-[var(--hify-text)] ${
          isActive ? "text-[var(--hify-text)]" : ""
        } ${align === "right" ? "justify-end" : ""}`}
      >
        <span>{label}</span>
        {isActive ? (
          dir === "asc" ? (
            <ArrowUp className="h-3 w-3 text-[var(--hify-gold-deep)] dark:text-[var(--hify-gold)]" />
          ) : (
            <ArrowDown className="h-3 w-3 text-[var(--hify-gold-deep)] dark:text-[var(--hify-gold)]" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-45" />
        )}
      </button>
    </th>
  );
}
