import type { Metadata } from "next";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/600.css";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";
import { TopNav } from "@/components/TopNav";
import { BottomNav } from "@/components/BottomNav";

export const metadata: Metadata = {
  title: "HIFY Option Selling — Dhool Chaat & Wheel Engine",
  description:
    "After-market NSE F&O Option Selling discipline engine with ₹25L Aukaat guardrails, Decay Lock, and isolated Paper Lab.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-[var(--hify-bg)] text-[var(--hify-text)]">
        <ThemeProvider>
          <div className="flex min-h-screen flex-col">
            <TopNav />
            <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 pb-20 sm:px-6 md:pb-8">
              {children}
            </main>
            <BottomNav />
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}
