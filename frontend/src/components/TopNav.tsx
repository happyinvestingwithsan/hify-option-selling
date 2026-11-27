"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Moon, Sun } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { NAV_ITEMS } from "@/lib/nav";
import { useTheme } from "@/components/ThemeProvider";

interface KiteStatusResponse {
  connected: boolean;
  mode: string;
  is_dry_run: boolean;
  user_id?: string;
}

type ConnectionState = "loading" | "live" | "dry_run" | "offline";

function HifyLogoMark() {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 28 28"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      className="shrink-0"
    >
      <defs>
        <linearGradient id="hify-logo-gold" x1="0" y1="28" x2="28" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#C8A951" />
          <stop offset="100%" stopColor="#DFBF69" />
        </linearGradient>
      </defs>
      <rect
        x="1"
        y="1"
        width="26"
        height="26"
        rx="7"
        className="fill-[var(--hify-surface-raised)] stroke-[var(--hify-border)]"
        strokeWidth="1"
      />
      <rect x="6.5" y="15" width="3.5" height="7" rx="1" fill="url(#hify-logo-gold)" />
      <rect x="12.25" y="10.5" width="3.5" height="11.5" rx="1" fill="url(#hify-logo-gold)" />
      <rect x="18" y="6" width="3.5" height="16" rx="1" fill="url(#hify-logo-gold)" />
    </svg>
  );
}

export function TopNav() {
  const pathname = usePathname();
  const { theme, mounted, toggleTheme } = useTheme();
  const [kiteState, setKiteState] = useState<ConnectionState>("loading");

  useEffect(() => {
    let active = true;

    async function loadKiteStatus() {
      try {
        const data = await apiFetch<KiteStatusResponse>("/api/kite/status");
        if (!active) return;
        setKiteState(data.connected ? "live" : "dry_run");
      } catch {
        if (!active) return;
        setKiteState("offline");
      }
    }

    loadKiteStatus();
    return () => {
      active = false;
    };
  }, []);

  const statusConfig: Record<
    ConnectionState,
    { label: string; dotClass: string }
  > = {
    loading: {
      label: "Checking",
      dotClass: "bg-[var(--hify-benchmark)]",
    },
    live: {
      label: "Kite Live",
      dotClass: "bg-[var(--hify-success)]",
    },
    dry_run: {
      label: "Dry-Run",
      dotClass: "bg-[var(--hify-warning)]",
    },
    offline: {
      label: "Offline",
      dotClass: "bg-[var(--hify-error)]",
    },
  };

  const status = statusConfig[kiteState];

  return (
    <header className="sticky top-0 z-40 border-b border-[var(--hify-border)] bg-[var(--hify-surface)]">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
        {/* Brand */}
        <Link
          href="/"
          className="flex min-h-[44px] items-center gap-2.5 pr-2 text-[var(--hify-text)]"
        >
          <HifyLogoMark />
          <span className="text-sm font-semibold tracking-tight">HIFY</span>
        </Link>

        {/* Desktop Navigation */}
        <nav
          aria-label="Primary navigation"
          className="hidden items-center gap-1 md:flex"
        >
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`relative flex min-h-[44px] items-center gap-1.5 rounded-lg px-3 text-sm font-medium transition-colors ${
                  isActive
                    ? "text-[#8E6C20] dark:text-[#C8A951]"
                    : "text-[var(--hify-text-secondary)] hover:bg-[var(--hify-bg)] hover:text-[var(--hify-text)]"
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span>{item.label}</span>
                {isActive && (
                  <span
                    aria-hidden="true"
                    className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-[#C8A951]"
                  />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Right Controls: Kite Status Pill + Theme Toggle */}
        <div className="flex items-center gap-2">
          <div
            className="flex min-h-[36px] items-center gap-2 rounded-full border border-[var(--hify-border)] bg-[var(--hify-surface-raised)] px-3 py-1 text-xs font-medium text-[var(--hify-text)]"
            title="Zerodha Kite connection status"
          >
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${status.dotClass}`}
              aria-hidden="true"
            />
            <span className="whitespace-nowrap">{status.label}</span>
          </div>

          <button
            type="button"
            onClick={toggleTheme}
            aria-label={
              mounted && theme === "dark"
                ? "Switch to light mode"
                : "Switch to dark mode"
            }
            className="flex h-11 w-11 items-center justify-center rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] text-[var(--hify-text)] transition-colors hover:bg-[var(--hify-bg)]"
          >
            {mounted && theme === "dark" ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
