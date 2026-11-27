import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BookOpen,
  ClipboardCheck,
  FileSpreadsheet,
  FlaskConical,
  LayoutDashboard,
  Radar,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Cockpit", icon: LayoutDashboard },
  { href: "/scanner", label: "Scanner", icon: Radar },
  { href: "/positions", label: "Positions", icon: Activity },
  { href: "/paper-lab", label: "Paper Lab", icon: FlaskConical },
  { href: "/retrospective", label: "Audit", icon: ClipboardCheck },
  { href: "/backoffice", label: "Back Office", icon: FileSpreadsheet },
  { href: "/lessons", label: "Lessons", icon: BookOpen },
];
