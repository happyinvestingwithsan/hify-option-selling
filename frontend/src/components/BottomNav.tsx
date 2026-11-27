"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MoreHorizontal, X } from "lucide-react";
import { NAV_ITEMS } from "@/lib/nav";

const PRIMARY_HREFS = new Set(["/", "/scanner", "/positions", "/retrospective"]);

export function BottomNav() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);

  const primaryItems = NAV_ITEMS.filter((item) => PRIMARY_HREFS.has(item.href));
  const secondaryItems = NAV_ITEMS.filter((item) => !PRIMARY_HREFS.has(item.href));
  const isSecondaryActive = secondaryItems.some((item) =>
    pathname.startsWith(item.href)
  );

  return (
    <>
      {moreOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/40 md:hidden"
          onClick={() => setMoreOpen(false)}
        >
          <div
            className="absolute inset-x-0 bottom-14 rounded-t-2xl border-t border-[var(--hify-border)] bg-[var(--hify-surface)] p-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--hify-text-secondary)]">
                More Workspace
              </span>
              <button
                type="button"
                onClick={() => setMoreOpen(false)}
                aria-label="Close menu"
                className="flex h-10 w-10 items-center justify-center rounded-lg text-[var(--hify-text-secondary)]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {secondaryItems.map((item) => {
                const isActive = pathname.startsWith(item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMoreOpen(false)}
                    className={`flex min-h-[56px] flex-col items-center justify-center gap-1.5 rounded-xl border p-2 text-xs font-medium ${
                      isActive
                        ? "border-[#C8A951] bg-[var(--hify-surface-raised)] text-[#8E6C20] dark:text-[#C8A951]"
                        : "border-[var(--hify-border)] bg-[var(--hify-bg)] text-[var(--hify-text)]"
                    }`}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <nav
        aria-label="Mobile navigation"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-[var(--hify-border)] bg-[var(--hify-surface)] md:hidden"
      >
        <div className="grid grid-cols-5 items-stretch">
          {primaryItems.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            const Icon = item.icon;

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMoreOpen(false)}
                className={`relative flex min-h-[48px] flex-col items-center justify-center gap-0.5 px-1 py-1.5 text-[10px] font-medium transition-colors ${
                  isActive
                    ? "text-[#8E6C20] dark:text-[#C8A951]"
                    : "text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
                }`}
              >
                {isActive && (
                  <span
                    aria-hidden="true"
                    className="absolute inset-x-2 top-0 h-0.5 rounded-full bg-[#C8A951]"
                  />
                )}
                <Icon className="h-4 w-4 shrink-0" />
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}

          <button
            type="button"
            onClick={() => setMoreOpen((prev) => !prev)}
            className={`relative flex min-h-[48px] flex-col items-center justify-center gap-0.5 px-1 py-1.5 text-[10px] font-medium transition-colors ${
              isSecondaryActive || moreOpen
                ? "text-[#8E6C20] dark:text-[#C8A951]"
                : "text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
            }`}
          >
            {isSecondaryActive && (
              <span
                aria-hidden="true"
                className="absolute inset-x-2 top-0 h-0.5 rounded-full bg-[#C8A951]"
              />
            )}
            <MoreHorizontal className="h-4 w-4 shrink-0" />
            <span>More</span>
          </button>
        </div>
      </nav>
    </>
  );
}
