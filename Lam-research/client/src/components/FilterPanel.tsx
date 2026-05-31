/*
 * ResearchAI — FilterPanel Component
 * Design: Precision Dark UI — slide-in drawer from right
 * Inspired by patent search systems (USPTO, FPO):
 * - Year range dual slider
 * - Publication type (conference / journal / preprint)
 * - Geographic region
 * - Citation count threshold slider
 * - Relevance sub-dimensions breakdown
 * - Primary + Secondary sort
 * - Active filter indicators
 */

import { useState, useCallback } from "react";
import { X, ChevronDown, ChevronUp, RotateCcw, Info } from "lucide-react";
import { cn } from "@/lib/utils";

export interface FilterState {
  yearRange: [number, number];
  publicationTypes: string[];
  regions: string[];
  minCitations: number;
  relevanceWeights: {
    keywordMatch: number;
    citationImpact: number;
    recency: number;
  };
  primarySort: string;
  secondarySort: string;
  primarySortDir: "desc" | "asc";
  secondarySortDir: "desc" | "asc";
}

export const DEFAULT_FILTERS: FilterState = {
  yearRange: [2015, 2025],
  publicationTypes: [],
  regions: [],
  minCitations: 0,
  relevanceWeights: {
    keywordMatch: 50,
    citationImpact: 30,
    recency: 20,
  },
  primarySort: "Relevance",
  secondarySort: "None",
  primarySortDir: "desc",
  secondarySortDir: "desc",
};

const SORT_OPTIONS = ["Relevance", "Citations", "H-Index", "Recent Activity", "Publications", "None"];
const PUBLICATION_TYPES = ["Conference Paper", "Journal Article", "Preprint / arXiv", "Book Chapter", "Workshop Paper"];
const REGIONS = ["North America", "Europe", "East Asia", "South Asia", "Middle East", "Latin America", "Oceania"];

interface RangeSliderProps {
  min: number;
  max: number;
  value: [number, number];
  onChange: (v: [number, number]) => void;
  step?: number;
  formatLabel?: (v: number) => string;
}

function RangeSlider({ min, max, value, onChange, step = 1, formatLabel }: RangeSliderProps) {
  const pct = (v: number) => ((v - min) / (max - min)) * 100;

  return (
    <div className="space-y-2">
      <div className="flex justify-between text-xs font-mono" style={{ color: "oklch(0.72 0.15 264)" }}>
        <span>{formatLabel ? formatLabel(value[0]) : value[0]}</span>
        <span>{formatLabel ? formatLabel(value[1]) : value[1]}</span>
      </div>
      <div className="relative h-5 flex items-center">
        {/* Track */}
        <div className="absolute w-full h-1 rounded-full" style={{ background: "oklch(1 0 0 / 10%)" }} />
        {/* Active range */}
        <div
          className="absolute h-1 rounded-full"
          style={{
            left: `${pct(value[0])}%`,
            width: `${pct(value[1]) - pct(value[0])}%`,
            background: "oklch(0.62 0.19 264)",
          }}
        />
        {/* Min thumb */}
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value[0]}
          onChange={e => {
            const v = Number(e.target.value);
            if (v < value[1]) onChange([v, value[1]]);
          }}
          className="absolute w-full h-full opacity-0 cursor-pointer"
          style={{ zIndex: value[0] > max - 10 ? 5 : 3 }}
        />
        {/* Max thumb */}
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value[1]}
          onChange={e => {
            const v = Number(e.target.value);
            if (v > value[0]) onChange([value[0], v]);
          }}
          className="absolute w-full h-full opacity-0 cursor-pointer"
          style={{ zIndex: 4 }}
        />
        {/* Visual thumbs */}
        <div
          className="absolute w-3.5 h-3.5 rounded-full border-2 pointer-events-none"
          style={{
            left: `calc(${pct(value[0])}% - 7px)`,
            background: "oklch(0.17 0.012 264)",
            borderColor: "oklch(0.62 0.19 264)",
            zIndex: 6,
          }}
        />
        <div
          className="absolute w-3.5 h-3.5 rounded-full border-2 pointer-events-none"
          style={{
            left: `calc(${pct(value[1])}% - 7px)`,
            background: "oklch(0.17 0.012 264)",
            borderColor: "oklch(0.62 0.19 264)",
            zIndex: 6,
          }}
        />
      </div>
    </div>
  );
}

interface SingleSliderProps {
  min: number;
  max: number;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  formatLabel?: (v: number) => string;
}

function SingleSlider({ min, max, value, onChange, step = 1, formatLabel }: SingleSliderProps) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{formatLabel ? formatLabel(min) : min}</span>
        <span className="font-mono font-medium" style={{ color: "oklch(0.72 0.15 264)" }}>
          {formatLabel ? formatLabel(value) : value}+
        </span>
        <span className="text-muted-foreground">{formatLabel ? formatLabel(max) : max}</span>
      </div>
      <div className="relative h-5 flex items-center">
        <div className="absolute w-full h-1 rounded-full" style={{ background: "oklch(1 0 0 / 10%)" }} />
        <div
          className="absolute h-1 rounded-full"
          style={{ width: `${pct}%`, background: "oklch(0.62 0.19 264)" }}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={e => onChange(Number(e.target.value))}
          className="absolute w-full h-full opacity-0 cursor-pointer"
          style={{ zIndex: 3 }}
        />
        <div
          className="absolute w-3.5 h-3.5 rounded-full border-2 pointer-events-none"
          style={{
            left: `calc(${pct}% - 7px)`,
            background: "oklch(0.17 0.012 264)",
            borderColor: "oklch(0.62 0.19 264)",
            zIndex: 4,
          }}
        />
      </div>
    </div>
  );
}

interface RelevanceWeightSliderProps {
  label: string;
  description: string;
  value: number;
  onChange: (v: number) => void;
  color: string;
}

function RelevanceWeightSlider({ label, description, value, onChange, color }: RelevanceWeightSliderProps) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full" style={{ background: color }} />
          <span className="text-xs font-medium text-foreground">{label}</span>
          <div className="group relative">
            <Info className="w-3 h-3 text-muted-foreground cursor-help" />
            <div
              className="absolute left-4 top-0 w-48 p-2 rounded-lg text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50"
              style={{ background: "oklch(0.22 0.015 264)", border: "1px solid oklch(1 0 0 / 10%)" }}
            >
              {description}
            </div>
          </div>
        </div>
        <span className="text-xs font-mono font-bold" style={{ color }}>{value}%</span>
      </div>
      <div className="relative h-4 flex items-center">
        <div className="absolute w-full h-1 rounded-full" style={{ background: "oklch(1 0 0 / 10%)" }} />
        <div
          className="absolute h-1 rounded-full"
          style={{ width: `${value}%`, background: color }}
        />
        <input
          type="range"
          min={0}
          max={100}
          value={value}
          onChange={e => onChange(Number(e.target.value))}
          className="absolute w-full h-full opacity-0 cursor-pointer"
        />
        <div
          className="absolute w-3 h-3 rounded-full border-2 pointer-events-none"
          style={{
            left: `calc(${value}% - 6px)`,
            background: "oklch(0.17 0.012 264)",
            borderColor: color,
          }}
        />
      </div>
    </div>
  );
}

interface SectionProps {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

function Section({ title, children, defaultOpen = true }: SectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-border pb-4">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
      >
        {title}
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>
      {open && <div className="space-y-3">{children}</div>}
    </div>
  );
}

interface FilterPanelProps {
  open: boolean;
  onClose: () => void;
  filters: FilterState;
  onChange: (f: FilterState) => void;
}

export default function FilterPanel({ open, onClose, filters, onChange }: FilterPanelProps) {
  const update = useCallback(
    <K extends keyof FilterState>(key: K, value: FilterState[K]) => {
      onChange({ ...filters, [key]: value });
    },
    [filters, onChange]
  );

  const toggleMulti = (key: "publicationTypes" | "regions", val: string) => {
    const arr = filters[key];
    update(key, arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val]);
  };

  const rawTotalWeight =
    filters.relevanceWeights.keywordMatch +
    filters.relevanceWeights.citationImpact +
    filters.relevanceWeights.recency;
  const totalWeight = rawTotalWeight > 0 ? rawTotalWeight : 1;

  const activeCount = [
    filters.yearRange[0] !== 2015 || filters.yearRange[1] !== 2025,
    filters.publicationTypes.length > 0,
    filters.regions.length > 0,
    filters.minCitations > 0,
    filters.primarySort !== "Relevance",
    filters.secondarySort !== "None",
  ].filter(Boolean).length;

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      {/* Drawer */}
      <div
        className={cn(
          "fixed top-0 right-0 h-full z-50 flex flex-col overflow-hidden transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full"
        )}
        style={{
          width: 360,
          background: "oklch(0.15 0.012 264)",
          borderLeft: "1px solid oklch(1 0 0 / 8%)",
          boxShadow: "-20px 0 60px oklch(0 0 0 / 40%)",
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-foreground" style={{ fontFamily: "'Sora', sans-serif" }}>
              Advanced Filters
            </h2>
            {activeCount > 0 && (
              <p className="text-[10px] text-muted-foreground mt-0.5">
                {activeCount} filter{activeCount > 1 ? "s" : ""} active
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => onChange(DEFAULT_FILTERS)}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              Reset
            </button>
            <button
              onClick={onClose}
              className="w-7 h-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-5 space-y-0">

          {/* Sort Order */}
          <Section title="Sort Order">
            <div className="space-y-3">
              {/* Primary Sort */}
              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1.5 block">Primary Sort</label>
                <div className="flex gap-2">
                  <select
                    value={filters.primarySort}
                    onChange={e => update("primarySort", e.target.value)}
                    className="flex-1 px-2.5 py-2 rounded-md text-xs text-foreground border border-border outline-none"
                    style={{ background: "oklch(0.13 0.012 264)" }}
                  >
                    {SORT_OPTIONS.filter(o => o !== "None").map(o => (
                      <option key={o} value={o}>{o}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => update("primarySortDir", filters.primarySortDir === "desc" ? "asc" : "desc")}
                    className="px-2.5 py-2 rounded-md text-xs border border-border text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors shrink-0"
                    style={{ background: "oklch(0.13 0.012 264)" }}
                  >
                    {filters.primarySortDir === "desc" ? "↓ High→Low" : "↑ Low→High"}
                  </button>
                </div>
              </div>

              {/* Secondary Sort */}
              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1.5 block">Secondary Sort (tiebreaker)</label>
                <div className="flex gap-2">
                  <select
                    value={filters.secondarySort}
                    onChange={e => update("secondarySort", e.target.value)}
                    className="flex-1 px-2.5 py-2 rounded-md text-xs text-foreground border border-border outline-none"
                    style={{ background: "oklch(0.13 0.012 264)" }}
                  >
                    {SORT_OPTIONS.map(o => (
                      <option key={o} value={o}>{o}</option>
                    ))}
                  </select>
                  {filters.secondarySort !== "None" && (
                    <button
                      onClick={() => update("secondarySortDir", filters.secondarySortDir === "desc" ? "asc" : "desc")}
                      className="px-2.5 py-2 rounded-md text-xs border border-border text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors shrink-0"
                      style={{ background: "oklch(0.13 0.012 264)" }}
                    >
                      {filters.secondarySortDir === "desc" ? "↓ High→Low" : "↑ Low→High"}
                    </button>
                  )}
                </div>
              </div>
            </div>
          </Section>

          {/* Relevance Breakdown */}
          <Section title="Relevance Weighting">
            <div className="space-y-1 mb-2">
              <p className="text-[10px] text-muted-foreground leading-relaxed">
                Adjust how relevance score is calculated. Weights are relative — they define the proportion of each factor.
              </p>
              <div
                className="flex h-2 rounded-full overflow-hidden mt-2"
                style={{ background: "oklch(1 0 0 / 5%)" }}
              >
                <div style={{ width: `${(filters.relevanceWeights.keywordMatch / totalWeight) * 100}%`, background: "oklch(0.62 0.19 264)", transition: "width 0.2s" }} />
                <div style={{ width: `${(filters.relevanceWeights.citationImpact / totalWeight) * 100}%`, background: "oklch(0.65 0.18 160)", transition: "width 0.2s" }} />
                <div style={{ width: `${(filters.relevanceWeights.recency / totalWeight) * 100}%`, background: "oklch(0.70 0.15 50)", transition: "width 0.2s" }} />
              </div>
            </div>
            <RelevanceWeightSlider
              label="Keyword Match"
              description="How closely the researcher's topics match your search terms"
              value={filters.relevanceWeights.keywordMatch}
              onChange={v => update("relevanceWeights", { ...filters.relevanceWeights, keywordMatch: v })}
              color="oklch(0.62 0.19 264)"
            />
            <RelevanceWeightSlider
              label="Citation Impact"
              description="Overall influence measured by citation counts and h-index"
              value={filters.relevanceWeights.citationImpact}
              onChange={v => update("relevanceWeights", { ...filters.relevanceWeights, citationImpact: v })}
              color="oklch(0.65 0.18 160)"
            />
            <RelevanceWeightSlider
              label="Recency"
              description="How recently the researcher has been active in this area"
              value={filters.relevanceWeights.recency}
              onChange={v => update("relevanceWeights", { ...filters.relevanceWeights, recency: v })}
              color="oklch(0.70 0.15 50)"
            />
          </Section>

          {/* Year Range */}
          <Section title="Publication Year Range">
            <RangeSlider
              min={1990}
              max={2025}
              value={filters.yearRange}
              onChange={v => update("yearRange", v)}
            />
            <div className="flex gap-2 mt-2">
              {[
                { label: "Last 5 yrs", range: [2020, 2025] as [number, number] },
                { label: "Last 10 yrs", range: [2015, 2025] as [number, number] },
                { label: "2010–2020", range: [2010, 2020] as [number, number] },
                { label: "All time", range: [1990, 2025] as [number, number] },
              ].map(preset => (
                <button
                  key={preset.label}
                  onClick={() => update("yearRange", preset.range)}
                  className={cn(
                    "flex-1 py-1 rounded text-[10px] border transition-colors",
                    filters.yearRange[0] === preset.range[0] && filters.yearRange[1] === preset.range[1]
                      ? "text-indigo-300 border-indigo-500/40 bg-indigo-500/10"
                      : "text-muted-foreground border-border hover:text-foreground hover:bg-white/5"
                  )}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </Section>

          {/* Minimum Citations */}
          <Section title="Minimum Citation Count">
            <SingleSlider
              min={0}
              max={10000}
              step={100}
              value={filters.minCitations}
              onChange={v => update("minCitations", v)}
              formatLabel={v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v.toString()}
            />
            <div className="flex gap-2 mt-2">
              {[0, 100, 500, 1000, 5000].map(n => (
                <button
                  key={n}
                  onClick={() => update("minCitations", n)}
                  className={cn(
                    "flex-1 py-1 rounded text-[10px] border transition-colors",
                    filters.minCitations === n
                      ? "text-indigo-300 border-indigo-500/40 bg-indigo-500/10"
                      : "text-muted-foreground border-border hover:text-foreground hover:bg-white/5"
                  )}
                >
                  {n === 0 ? "Any" : n >= 1000 ? `${n / 1000}k+` : `${n}+`}
                </button>
              ))}
            </div>
          </Section>

          {/* Publication Type */}
          <Section title="Publication Type">
            <div className="space-y-1.5">
              {PUBLICATION_TYPES.map(type => (
                <label
                  key={type}
                  className="flex items-center gap-2.5 cursor-pointer group"
                >
                  <div
                    onClick={() => toggleMulti("publicationTypes", type)}
                    className={cn(
                      "w-4 h-4 rounded border flex items-center justify-center transition-all shrink-0",
                      filters.publicationTypes.includes(type)
                        ? "border-indigo-500 bg-indigo-500"
                        : "border-border group-hover:border-indigo-500/50"
                    )}
                    style={filters.publicationTypes.includes(type) ? { background: "oklch(0.62 0.19 264)", borderColor: "oklch(0.62 0.19 264)" } : {}}
                  >
                    {filters.publicationTypes.includes(type) && (
                      <svg viewBox="0 0 10 8" className="w-2.5 h-2 fill-white">
                        <path d="M1 4L4 7L9 1" stroke="white" strokeWidth="1.5" fill="none" strokeLinecap="round" />
                      </svg>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground group-hover:text-foreground transition-colors">{type}</span>
                </label>
              ))}
            </div>
          </Section>

          {/* Geographic Region */}
          <Section title="Geographic Region" defaultOpen={false}>
            <div className="space-y-1.5">
              {REGIONS.map(region => (
                <label
                  key={region}
                  className="flex items-center gap-2.5 cursor-pointer group"
                >
                  <div
                    onClick={() => toggleMulti("regions", region)}
                    className={cn(
                      "w-4 h-4 rounded border flex items-center justify-center transition-all shrink-0",
                      filters.regions.includes(region)
                        ? "border-indigo-500 bg-indigo-500"
                        : "border-border group-hover:border-indigo-500/50"
                    )}
                    style={filters.regions.includes(region) ? { background: "oklch(0.62 0.19 264)", borderColor: "oklch(0.62 0.19 264)" } : {}}
                  >
                    {filters.regions.includes(region) && (
                      <svg viewBox="0 0 10 8" className="w-2.5 h-2 fill-white">
                        <path d="M1 4L4 7L9 1" stroke="white" strokeWidth="1.5" fill="none" strokeLinecap="round" />
                      </svg>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground group-hover:text-foreground transition-colors">{region}</span>
                </label>
              ))}
            </div>
          </Section>

          {/* Bottom padding */}
          <div className="h-6" />
        </div>

        {/* Apply button */}
        <div className="px-5 py-4 border-t border-border shrink-0">
          <button
            onClick={onClose}
            className="w-full py-2.5 rounded-lg text-sm font-medium text-white transition-all duration-150"
            style={{ background: "oklch(0.62 0.19 264)" }}
            onMouseEnter={e => (e.currentTarget.style.background = "oklch(0.55 0.19 264)")}
            onMouseLeave={e => (e.currentTarget.style.background = "oklch(0.62 0.19 264)")}
          >
            Apply Filters
          </button>
        </div>
      </div>
    </>
  );
}
