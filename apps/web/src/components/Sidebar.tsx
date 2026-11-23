import { BASEMAP_CREDITS } from "@/lib/map-config";
import ApiStatusBadge from "./ApiStatusBadge";

/**
 * Side panel. Everything here describes the real state of the project: no datasets are loaded
 * yet, so none are listed. Do not add placeholder statistics or boundaries.
 */
export default function Sidebar() {
  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-5 text-sm text-slate-700">
      <section aria-labelledby="about-heading">
        <h2 id="about-heading" className="text-base font-semibold text-slate-900">
          About this atlas
        </h2>
        <p className="mt-2 leading-relaxed">
          An open, nationwide geographic and knowledge platform for India. This is an early
          foundation release: the map is a general-purpose basemap and no Indian
          administrative datasets have been loaded yet.
        </p>
      </section>

      <section aria-labelledby="layers-heading">
        <h2 id="layers-heading" className="text-base font-semibold text-slate-900">
          Data layers
        </h2>
        <div className="mt-2 rounded-md border border-dashed border-slate-300 bg-slate-50 p-3">
          <p className="font-medium text-slate-800">No datasets loaded</p>
          <p className="mt-1 text-slate-600">
            Official boundaries and statistics will appear here once sourced from authoritative,
            openly licensed publishers, each with its source and licence shown.
          </p>
        </div>
      </section>

      <section aria-labelledby="status-heading">
        <h2 id="status-heading" className="text-base font-semibold text-slate-900">
          System status
        </h2>
        <div className="mt-2">
          <ApiStatusBadge />
        </div>
      </section>

      <section aria-labelledby="notice-heading" className="mt-auto">
        <h2 id="notice-heading" className="text-base font-semibold text-slate-900">
          Map notice
        </h2>
        <p className="mt-2 text-xs leading-relaxed text-slate-600">
          Borders and place names on the basemap come from OpenStreetMap contributors. They are
          shown for orientation only and may not match official Government of India depictions.
        </p>
        <p className="mt-3 text-xs text-slate-600">
          Basemap:{" "}
          {BASEMAP_CREDITS.map((credit, index) => (
            <span key={credit.href}>
              {index > 0 && " · "}
              <a
                href={credit.href}
                target="_blank"
                rel="noopener noreferrer"
                className="underline decoration-slate-400 underline-offset-2 hover:text-slate-900"
              >
                {credit.label}
              </a>
            </span>
          ))}
        </p>
      </section>
    </div>
  );
}
