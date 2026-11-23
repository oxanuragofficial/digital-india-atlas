"use client";

import { useId, useState } from "react";
import MapLoader from "./map/MapLoader";
import Sidebar from "./Sidebar";

/**
 * Map-first layout.
 * - Desktop (md+): fixed-width side panel on the left, map fills the rest.
 * - Mobile: the map fills the screen; the panel is a toggleable sheet over the lower part.
 */
export default function AtlasShell() {
  const [panelOpen, setPanelOpen] = useState(false);
  const panelId = useId();

  return (
    <div className="flex h-dvh flex-col bg-white text-slate-900">
      <header className="flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold tracking-tight">Digital India Atlas</h1>
          <p className="hidden truncate text-xs text-slate-500 sm:block">
            Open geographic knowledge platform · Foundation release
          </p>
        </div>
        <button
          type="button"
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 md:hidden"
          aria-expanded={panelOpen}
          aria-controls={panelId}
          onClick={() => setPanelOpen((open) => !open)}
        >
          {panelOpen ? "Hide info" : "Info"}
        </button>
      </header>

      <div className="relative flex min-h-0 flex-1">
        <aside
          id={panelId}
          aria-label="Atlas information"
          className={[
            "z-20 border-slate-200 bg-white",
            "md:static md:block md:w-80 md:shrink-0 md:border-r lg:w-96",
            panelOpen
              ? "absolute inset-x-0 bottom-0 block max-h-[65%] rounded-t-xl border-t shadow-2xl"
              : "hidden",
          ].join(" ")}
        >
          <Sidebar />
        </aside>

        <main className="relative min-w-0 flex-1">
          <MapLoader />
        </main>
      </div>
    </div>
  );
}
