"use client";

import dynamic from "next/dynamic";

/** MapLibre needs the browser (WebGL, window), so it is never rendered on the server. */
const AtlasMap = dynamic(() => import("./AtlasMap"), {
  ssr: false,
  loading: () => (
    <div className="grid h-full w-full place-items-center bg-slate-100 text-sm text-slate-600">
      Loading map…
    </div>
  ),
});

export default function MapLoader() {
  return <AtlasMap />;
}
