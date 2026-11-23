"use client";

import { useEffect, useState } from "react";
import { type ApiState, type ApiStatus, fetchApiStatus } from "@/lib/api";

const STYLES: Record<ApiState | "checking", { dot: string; label: string }> = {
  checking: { dot: "bg-slate-400", label: "Checking API…" },
  online: { dot: "bg-emerald-500", label: "API online" },
  degraded: { dot: "bg-amber-500", label: "API degraded" },
  offline: { dot: "bg-rose-500", label: "API offline" },
};

export default function ApiStatusBadge() {
  const [status, setStatus] = useState<ApiStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchApiStatus().then((result) => {
      if (!cancelled) setStatus(result);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const key = status ? status.state : "checking";
  const { dot, label } = STYLES[key];

  return (
    <span
      className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700"
      role="status"
      title={status?.detail}
      data-state={key}
    >
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
      {label}
    </span>
  );
}
