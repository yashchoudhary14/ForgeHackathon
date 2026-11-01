import { useEffect, useRef, useState } from "react";
import { LocateFixed } from "lucide-react";
import type { CivicReportOut } from "../api/civic";
import "leaflet/dist/leaflet.css";

const INDIA_CENTER: [number, number] = [25.6, 82.0];

function pinColor(status: string): { bg: string; fg: string } {
  const s = (status || "open").toLowerCase();
  if (s === "citizen_verified" || s === "resolved")
    return { bg: "#155C42", fg: "#ffffff" };
  if (s === "filed" || s === "in_progress")
    return { bg: "#3D7BEA", fg: "#ffffff" };
  if (s === "still_broken" || s === "escalated")
    return { bg: "#E03A2E", fg: "#ffffff" };
  return { bg: "#E8731C", fg: "#ffffff" };
}

export default function CivicMap({
  reports,
  onSelect,
  onNearMe,
}: {
  reports: CivicReportOut[];
  onSelect?: (report: CivicReportOut) => void;
  onNearMe?: (lat: number, lng: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const layerRef = useRef<import("leaflet").LayerGroup | null>(null);
  const [locating, setLocating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const el = containerRef.current;
    if (!el || typeof window === "undefined") return;
    void import("leaflet").then((L) => {
      if (cancelled || !containerRef.current || mapRef.current) return;
      const map = L.map(containerRef.current, {
        center: INDIA_CENTER,
        zoom: 5,
        scrollWheelZoom: false,
      });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
        maxZoom: 19,
      }).addTo(map);
      const group = L.layerGroup().addTo(map);
      mapRef.current = map;
      layerRef.current = group;
      renderPins(L, map, group, reports, onSelect);
    });
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const group = layerRef.current;
    if (!map || !group || typeof window === "undefined") return;
    void import("leaflet").then((L) => {
      if (!mapRef.current || !layerRef.current) return;
      renderPins(L, mapRef.current, layerRef.current, reports, onSelect);
    });
  }, [reports, onSelect]);

  function locateUser() {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        const { latitude, longitude } = pos.coords;
        mapRef.current?.setView([latitude, longitude], 13);
        onNearMe?.(latitude, longitude);
      },
      () => setLocating(false),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  return (
    <div className="relative min-h-[420px] overflow-hidden rounded-[28px] bg-[#e9e3d5] shadow-[inset_0_0_0_1px_#ede5da]">
      <div
        ref={containerRef}
        aria-label="Civic issues map"
        className="h-[440px] w-full z-0"
      />
      <div className="pointer-events-none absolute inset-x-3.5 top-3.5 z-[400] flex flex-wrap items-center justify-between gap-2">
        <span className="rounded-full bg-white/95 px-3.5 py-2 text-xs font-semibold text-ink shadow-sm">
          OpenStreetMap · {reports.filter((r) => r.lat != null && r.lng != null).length} geotagged reports
        </span>
        {typeof navigator !== "undefined" && !!navigator.geolocation && (
          <button
            type="button"
            disabled={locating}
            onClick={locateUser}
            className="pointer-events-auto secondary !min-h-10 !px-3.5 !py-1.5 text-xs shadow-sm"
          >
            <LocateFixed size={15} aria-hidden="true" />
            {locating ? "Locating…" : "Near me"}
          </button>
        )}
      </div>
      <div className="pointer-events-none absolute bottom-3.5 left-3.5 z-[400] flex flex-wrap gap-3 rounded-2xl bg-white/95 px-3.5 py-2 text-xs font-semibold text-ink shadow-sm">
        <span className="inline-flex items-center gap-1.5">
          <i className="inline-block h-2.5 w-2.5 rounded-full bg-[#E8731C]" />
          Open / escalated
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i className="inline-block h-2.5 w-2.5 rounded-full bg-[#3D7BEA]" />
          Filed on CPGRAMS
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i className="inline-block h-2.5 w-2.5 rounded-full bg-[#155C42]" />
          Citizen verified
        </span>
      </div>
    </div>
  );
}

function renderPins(
  L: typeof import("leaflet"),
  map: import("leaflet").Map,
  group: import("leaflet").LayerGroup,
  reports: CivicReportOut[],
  onSelect?: (report: CivicReportOut) => void,
) {
  group.clearLayers();
  const coords: [number, number][] = [];
  for (const r of reports) {
    if (typeof r.lat !== "number" || typeof r.lng !== "number") continue;
    coords.push([r.lat, r.lng]);
    const { bg, fg } = pinColor(r.status);
    const icon = L.divIcon({
      className: "civic-pin",
      html: `<div style="background:${bg};color:${fg};min-width:34px;height:34px;padding:0 8px;border-radius:999px;display:grid;place-items:center;font-weight:700;font-size:13px;border:3px solid #fff;box-shadow:0 6px 14px rgba(0,0,0,0.22);">${r.upvotes ?? 1}</div>`,
      iconSize: [34, 34],
      iconAnchor: [17, 17],
    });
    const marker = L.marker([r.lat, r.lng], { icon });
    marker.bindPopup(
      `<strong>${escapeHtml(r.title)}</strong><br/><small>${escapeHtml(r.department || r.category)} · 👍 ${r.upvotes ?? 1}</small>`,
    );
    if (onSelect) marker.on("click", () => onSelect(r));
    marker.addTo(group);
  }
  if (coords.length === 1) {
    map.setView(coords[0], 13);
  } else if (coords.length > 1) {
    map.fitBounds(coords, { padding: [36, 36], maxZoom: 13 });
  }
}

function escapeHtml(text: string): string {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
