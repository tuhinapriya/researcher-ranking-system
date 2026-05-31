/*
 * ResearchAI — SearchBar Component
 * Design: Precision Dark UI
 * - Top search bar with query input
 * - Sort by dropdown (primary sort from FilterPanel)
 * - Search button (indigo)
 * - Filters button with active count badge
 * - Sub-filter pills: Institution, Topic, Year, Country
 */

import { useState } from "react";
import { Search, SlidersHorizontal, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { type FilterState } from "./FilterPanel";
import { DEFAULT_FILTERS } from "./FilterPanel";

interface SearchBarProps {
  query: string;
  setQuery: (q: string) => void;
  onSearch: (q: string) => void;
  filters: FilterState;
  onChangeFilters: (filters: FilterState) => void;
  onOpenFilters: () => void;
}

const SORT_OPTIONS = ["Relevance", "Citations", "H-Index", "Recent Activity", "Publications"];
const QUICK_FILTERS = ["Institution", "Topic", "Year", "Country"];

export default function SearchBar({ query, setQuery, onSearch, filters, onChangeFilters, onOpenFilters }: SearchBarProps) {
  const [sortOpen, setSortOpen] = useState(false);
  const [activeQuick, setActiveQuick] = useState<string[]>([]);

  const handleSearch = () => {
    if (query.trim()) onSearch(query.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  const toggleQuick = (f: string) => {
    setActiveQuick(prev =>
      prev.includes(f) ? prev.filter(x => x !== f) : [...prev, f]
    );
    toast.info(`Quick filter "${f}" — use Advanced Filters for full control`);
  };

  // Count active non-default filters
  const activeFilterCount = [
    filters.yearRange[0] !== DEFAULT_FILTERS.yearRange[0] || filters.yearRange[1] !== DEFAULT_FILTERS.yearRange[1],
    filters.publicationTypes.length > 0,
    filters.regions.length > 0,
    filters.minCitations > 0,
    filters.primarySort !== "Relevance",
    filters.secondarySort !== "None",
    filters.relevanceWeights.keywordMatch !== DEFAULT_FILTERS.relevanceWeights.keywordMatch ||
      filters.relevanceWeights.citationImpact !== DEFAULT_FILTERS.relevanceWeights.citationImpact ||
      filters.relevanceWeights.recency !== DEFAULT_FILTERS.relevanceWeights.recency,
  ].filter(Boolean).length;

  return (
    <div
      className="shrink-0 border-b border-border px-4 py-3 space-y-2.5"
      style={{ background: "oklch(0.15 0.012 264)" }}
    >
      {/* Main search row */}
      <div className="flex items-center gap-3">
        {/* Search input */}
        <div
          className="flex-1 flex items-center gap-2.5 px-3.5 py-2 rounded-lg border border-border transition-all duration-150 focus-within:border-indigo-500/60"
          style={{ background: "oklch(0.13 0.012 264)" }}
        >
          <Search className="w-4 h-4 shrink-0 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search researchers, topics, papers..."
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none min-w-0"
          />
        </div>

        {/* Sort by */}
        <div className="relative">
          <div className="flex items-center gap-1.5 text-sm text-muted-foreground shrink-0">
            <span className="text-xs hidden sm:block">Sort by</span>
            <button
              onClick={() => setSortOpen(o => !o)}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-border text-foreground text-sm hover:bg-white/5 transition-colors"
              style={{ background: "oklch(0.13 0.012 264)" }}
            >
              <span className="max-w-24 truncate">{filters.primarySort}</span>
              <ChevronDown className={cn("w-3.5 h-3.5 transition-transform shrink-0", sortOpen && "rotate-180")} />
            </button>
          </div>
          {sortOpen && (
            <div
              className="absolute top-full right-0 mt-1 w-44 rounded-lg border border-border shadow-xl z-50 overflow-hidden"
              style={{ background: "oklch(0.19 0.012 264)" }}
            >
              {SORT_OPTIONS.map(opt => (
                <button
                  key={opt}
                  onClick={() => {
                    onChangeFilters({ ...filters, primarySort: opt });
                    setSortOpen(false);
                  }}
                  className={cn(
                    "w-full text-left px-3 py-2 text-sm transition-colors hover:bg-white/5",
                    filters.primarySort === opt ? "text-foreground font-medium" : "text-muted-foreground"
                  )}
                >
                  {opt}
                  {filters.primarySort === opt && (
                    <span className="ml-2 text-[10px]" style={{ color: "oklch(0.62 0.19 264)" }}>✓</span>
                  )}
                </button>
              ))}
              <div className="border-t border-border">
                <button
                  onClick={() => { onOpenFilters(); setSortOpen(false); }}
                  className="w-full text-left px-3 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
                  style={{ color: "oklch(0.72 0.15 264)" }}
                >
                  Advanced sort options →
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Search button */}
        <button
          onClick={handleSearch}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-white transition-all duration-150 shrink-0"
          style={{ background: "oklch(0.62 0.19 264)" }}
          onMouseEnter={e => (e.currentTarget.style.background = "oklch(0.55 0.19 264)")}
          onMouseLeave={e => (e.currentTarget.style.background = "oklch(0.62 0.19 264)")}
        >
          <Search className="w-3.5 h-3.5" />
          Search
        </button>

        {/* Filters button with badge */}
        <button
          onClick={onOpenFilters}
          className="relative flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border transition-colors shrink-0"
          style={
            activeFilterCount > 0
              ? {
                  background: "oklch(0.62 0.19 264 / 12%)",
                  color: "oklch(0.78 0.12 264)",
                  borderColor: "oklch(0.62 0.19 264 / 30%)",
                }
              : {
                  background: "oklch(0.13 0.012 264)",
                  color: "oklch(0.55 0.01 264)",
                  borderColor: "oklch(1 0 0 / 8%)",
                }
          }
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          Filters
          {activeFilterCount > 0 && (
            <span
              className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full text-[9px] font-bold flex items-center justify-center text-white"
              style={{ background: "oklch(0.62 0.19 264)" }}
            >
              {activeFilterCount}
            </span>
          )}
        </button>
      </div>

      {/* Quick filter pills row */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-muted-foreground shrink-0">Quick filter:</span>
        <div className="flex items-center gap-1.5 flex-wrap">
          {QUICK_FILTERS.map(f => (
            <button
              key={f}
              onClick={() => toggleQuick(f)}
              className={cn(
                "flex items-center gap-1 px-2.5 py-1 rounded-full text-xs border transition-all duration-150",
                activeQuick.includes(f)
                  ? "border-indigo-500/50 text-indigo-300 bg-indigo-500/10"
                  : "border-border text-muted-foreground hover:text-foreground hover:bg-white/5"
              )}
            >
              {f}
              <ChevronDown className="w-3 h-3" />
            </button>
          ))}
          <button
            onClick={onOpenFilters}
            className="flex items-center gap-1 px-2.5 py-1 rounded-full text-xs border border-dashed border-border text-muted-foreground hover:text-foreground hover:border-indigo-500/40 transition-all duration-150"
          >
            + More filters
          </button>
        </div>
      </div>
    </div>
  );
}
