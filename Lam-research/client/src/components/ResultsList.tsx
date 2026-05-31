/*
 * ResearchAI — ResultsList Component
 * Design: Precision Dark UI
 * - AI Summary header with result count
 * - Researcher cards with:
 *   - Avatar, name, affiliation, relevance score badge
 *   - Keywords
 *   - "Why matched" tag
 *   - AI Summary text
 *   - View Details + Save buttons (NO Compare)
 * - Active card has indigo left border
 * - Staggered fade-in animation
 */

import { useState } from "react";
import { Bookmark, BookmarkCheck, Eye, Sparkles, ChevronDown, ChevronUp, ArrowUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { type Researcher } from "@/lib/data";
import { toast } from "sonner";
import { type FilterState } from "./FilterPanel";

interface ResultsListProps {
  researchers: Researcher[];
  activeQuery: string;
  selectedId: string;
  onSelect: (r: Researcher) => void;
  savedResearchers: string[];
  onSave: (id: string) => void;
  filters: FilterState;
}

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 90 ? "oklch(0.62 0.19 264)" :
    score >= 80 ? "oklch(0.65 0.15 200)" :
    "oklch(0.65 0.12 150)";

  return (
    <div
      className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold score-badge shrink-0"
      style={{ background: `${color}20`, color, border: `1px solid ${color}40` }}
    >
      <span className="text-[10px] font-normal opacity-70">Relevance</span>
      <span>{score}</span>
    </div>
  );
}

function ResearcherCard({
  researcher,
  isSelected,
  isSaved,
  onSelect,
  onSave,
  index,
}: {
  researcher: Researcher;
  isSelected: boolean;
  isSaved: boolean;
  onSelect: () => void;
  onSave: () => void;
  index: number;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={cn(
        "relative rounded-lg border transition-all duration-150 cursor-pointer group",
        isSelected
          ? "border-indigo-500/40 bg-indigo-500/5"
          : "border-border hover:border-border/80 hover:bg-white/3"
      )}
      style={{
        borderLeftWidth: isSelected ? 2 : 1,
        borderLeftColor: isSelected ? "oklch(0.62 0.19 264)" : undefined,
        animationDelay: `${index * 40}ms`,
        background: isSelected ? "oklch(0.19 0.015 264)" : "oklch(0.17 0.012 264)",
      }}
      onClick={onSelect}
    >
      <div className="p-4">
        {/* Header row */}
        <div className="flex items-start gap-3">
          <img
            src={researcher.avatar}
            alt={researcher.name}
            className="w-10 h-10 rounded-full object-cover shrink-0 ring-1 ring-white/10"
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <h3
                  className="text-sm font-semibold text-foreground truncate"
                  style={{ fontFamily: "'Sora', sans-serif" }}
                >
                  {researcher.name}
                </h3>
                <p className="text-xs text-muted-foreground truncate">{researcher.affiliation}</p>
              </div>
              <ScoreBadge score={researcher.relevanceScore} />
            </div>

            {/* Keywords */}
            <div className="flex flex-wrap gap-1 mt-2">
              <span className="text-[10px] text-muted-foreground mr-0.5">Keywords</span>
              {researcher.keywords.map(kw => (
                <span
                  key={kw}
                  className="text-[10px] px-1.5 py-0.5 rounded text-muted-foreground"
                  style={{ background: "oklch(1 0 0 / 5%)", border: "1px solid oklch(1 0 0 / 8%)" }}
                >
                  {kw}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Why matched */}
        <div className="mt-3 flex items-start gap-2">
          <span
            className="text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0"
            style={{
              background: "oklch(0.65 0.15 140 / 15%)",
              color: "oklch(0.72 0.15 140)",
              border: "1px solid oklch(0.65 0.15 140 / 25%)",
            }}
          >
            Why matched
          </span>
          <p className="text-xs text-muted-foreground leading-relaxed">{researcher.whyMatched}</p>
        </div>

        {/* AI Summary */}
        <div
          className="mt-2.5 px-3 py-2 rounded-md"
          style={{ background: "oklch(0.62 0.19 264 / 6%)", border: "1px solid oklch(0.62 0.19 264 / 12%)" }}
        >
          <div className="flex items-start gap-1.5">
            <Sparkles className="w-3 h-3 shrink-0 mt-0.5" style={{ color: "oklch(0.72 0.15 264)" }} />
            <p className="text-xs text-muted-foreground leading-relaxed">
              <span className="font-medium" style={{ color: "oklch(0.72 0.15 264)" }}>AI Summary: </span>
              {expanded ? researcher.fullBio : researcher.aiSummary}
            </p>
          </div>
          {researcher.fullBio !== researcher.aiSummary && (
            <button
              onClick={e => { e.stopPropagation(); setExpanded(o => !o); }}
              className="mt-1 flex items-center gap-0.5 text-[10px] text-muted-foreground hover:text-foreground transition-colors ml-5"
            >
              {expanded ? <><ChevronUp className="w-3 h-3" />Show less</> : <><ChevronDown className="w-3 h-3" />Read more</>}
            </button>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 mt-3" onClick={e => e.stopPropagation()}>
          <button
            onClick={onSelect}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
            style={{
              background: "oklch(0.62 0.19 264 / 12%)",
              color: "oklch(0.78 0.12 264)",
              border: "1px solid oklch(0.62 0.19 264 / 20%)",
            }}
            onMouseEnter={e => (e.currentTarget.style.background = "oklch(0.62 0.19 264 / 22%)")}
            onMouseLeave={e => (e.currentTarget.style.background = "oklch(0.62 0.19 264 / 12%)")}
          >
            <Eye className="w-3 h-3" />
            View Details
          </button>
          <button
            onClick={() => { onSave(); toast.success(isSaved ? `Removed ${researcher.name}` : `Saved ${researcher.name}`); }}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 border",
              isSaved
                ? "text-indigo-300 border-indigo-500/30 bg-indigo-500/10"
                : "text-muted-foreground border-border hover:text-foreground hover:bg-white/5"
            )}
          >
            {isSaved ? <BookmarkCheck className="w-3 h-3" /> : <Bookmark className="w-3 h-3" />}
            {isSaved ? "Saved" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ResultsList({
  researchers,
  activeQuery,
  selectedId,
  onSelect,
  savedResearchers,
  onSave,
  filters,
}: ResultsListProps) {
  // Sorting is already applied in Home.tsx via applyFiltersAndSort
  const sorted = researchers;

  return (
    <div className="flex-1 overflow-y-auto min-w-0" style={{ background: "oklch(0.13 0.012 264)" }}>
      <div className="p-4 space-y-3">
        {/* Header */}
        <div
          className="rounded-lg p-4 border border-border"
          style={{ background: "oklch(0.17 0.012 264)" }}
        >
          <h2
            className="text-base font-semibold text-foreground mb-1"
            style={{ fontFamily: "'Sora', sans-serif" }}
          >
            Top Researchers for "{activeQuery}"
          </h2>
          <div className="flex items-start gap-1.5">
            <Sparkles className="w-3.5 h-3.5 shrink-0 mt-0.5" style={{ color: "oklch(0.72 0.15 264)" }} />
            <p className="text-xs text-muted-foreground leading-relaxed">
              <span className="font-medium" style={{ color: "oklch(0.72 0.15 264)" }}>AI Summary: </span>
              These are the top researchers who have made significant contributions to transformer architecture, ranked by topic relevance, publication influence, and recent activity.
            </p>
          </div>
          <div className="flex items-center justify-between mt-3">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">{sorted.length} results</span>
              <div className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px]" style={{ background: "oklch(0.62 0.19 264 / 10%)", color: "oklch(0.72 0.15 264)" }}>
                <ArrowUpDown className="w-2.5 h-2.5" />
                <span>{filters.primarySort}{filters.secondarySort !== "None" ? ` → ${filters.secondarySort}` : ""}</span>
              </div>
            </div>
            <div className="flex gap-1">
              <button
                className="w-5 h-5 rounded flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
                style={{ background: "oklch(1 0 0 / 5%)" }}
                onClick={() => toast.info("Grid view coming soon")}
              >
                <svg viewBox="0 0 12 12" className="w-3 h-3 fill-current">
                  <rect x="0" y="0" width="5" height="5" rx="0.5" />
                  <rect x="7" y="0" width="5" height="5" rx="0.5" />
                  <rect x="0" y="7" width="5" height="5" rx="0.5" />
                  <rect x="7" y="7" width="5" height="5" rx="0.5" />
                </svg>
              </button>
              <button
                className="w-5 h-5 rounded flex items-center justify-center text-foreground transition-colors"
                style={{ background: "oklch(0.62 0.19 264 / 20%)" }}
              >
                <svg viewBox="0 0 12 12" className="w-3 h-3 fill-current">
                  <rect x="0" y="0" width="12" height="2" rx="0.5" />
                  <rect x="0" y="5" width="12" height="2" rx="0.5" />
                  <rect x="0" y="10" width="12" height="2" rx="0.5" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* Cards */}
        {sorted.map((r, i) => (
          <ResearcherCard
            key={r.id}
            researcher={r}
            isSelected={selectedId === r.id}
            isSaved={savedResearchers.includes(r.id)}
            onSelect={() => onSelect(r)}
            onSave={() => onSave(r.id)}
            index={i}
          />
        ))}
      </div>
    </div>
  );
}
