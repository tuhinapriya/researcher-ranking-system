/*
 * ResearchAI — ActiveFilterBar Component
 * Design: Precision Dark UI
 * Shows active filters as removable pill tags below the search bar
 * Includes sort indicators and filter count badge
 */

import { X, ArrowUpDown } from "lucide-react";
import { type FilterState, DEFAULT_FILTERS } from "./FilterPanel";

interface ActiveFilterBarProps {
  filters: FilterState;
  onChange: (f: FilterState) => void;
  resultCount: number;
}

interface FilterTag {
  label: string;
  key: string;
  onRemove: () => void;
  color?: string;
}

export default function ActiveFilterBar({ filters, onChange, resultCount }: ActiveFilterBarProps) {
  const tags: FilterTag[] = [];

  // Sort tags
  if (filters.primarySort !== "Relevance") {
    tags.push({
      label: `Sort: ${filters.primarySort} ${filters.primarySortDir === "desc" ? "↓" : "↑"}`,
      key: "primarySort",
      onRemove: () => onChange({ ...filters, primarySort: "Relevance", primarySortDir: "desc" }),
      color: "oklch(0.62 0.19 264)",
    });
  }
  if (filters.secondarySort !== "None") {
    tags.push({
      label: `Then: ${filters.secondarySort} ${filters.secondarySortDir === "desc" ? "↓" : "↑"}`,
      key: "secondarySort",
      onRemove: () => onChange({ ...filters, secondarySort: "None" }),
      color: "oklch(0.62 0.19 264)",
    });
  }

  // Year range
  if (filters.yearRange[0] !== DEFAULT_FILTERS.yearRange[0] || filters.yearRange[1] !== DEFAULT_FILTERS.yearRange[1]) {
    tags.push({
      label: `${filters.yearRange[0]}–${filters.yearRange[1]}`,
      key: "yearRange",
      onRemove: () => onChange({ ...filters, yearRange: DEFAULT_FILTERS.yearRange }),
      color: "oklch(0.70 0.15 50)",
    });
  }

  // Min citations
  if (filters.minCitations > 0) {
    const label = filters.minCitations >= 1000
      ? `≥ ${filters.minCitations / 1000}k citations`
      : `≥ ${filters.minCitations} citations`;
    tags.push({
      label,
      key: "minCitations",
      onRemove: () => onChange({ ...filters, minCitations: 0 }),
      color: "oklch(0.65 0.18 160)",
    });
  }

  // Publication types
  filters.publicationTypes.forEach(pt => {
    tags.push({
      label: pt,
      key: `pt-${pt}`,
      onRemove: () => onChange({ ...filters, publicationTypes: filters.publicationTypes.filter(x => x !== pt) }),
      color: "oklch(0.68 0.15 200)",
    });
  });

  // Regions
  filters.regions.forEach(r => {
    tags.push({
      label: r,
      key: `region-${r}`,
      onRemove: () => onChange({ ...filters, regions: filters.regions.filter(x => x !== r) }),
      color: "oklch(0.65 0.15 280)",
    });
  });

  // Relevance weight changes
  const weightChanged =
    filters.relevanceWeights.keywordMatch !== DEFAULT_FILTERS.relevanceWeights.keywordMatch ||
    filters.relevanceWeights.citationImpact !== DEFAULT_FILTERS.relevanceWeights.citationImpact ||
    filters.relevanceWeights.recency !== DEFAULT_FILTERS.relevanceWeights.recency;
  if (weightChanged) {
    tags.push({
      label: `Relevance: ${filters.relevanceWeights.keywordMatch}% kw / ${filters.relevanceWeights.citationImpact}% cite / ${filters.relevanceWeights.recency}% recent`,
      key: "relevanceWeights",
      onRemove: () => onChange({ ...filters, relevanceWeights: DEFAULT_FILTERS.relevanceWeights }),
      color: "oklch(0.62 0.19 264)",
    });
  }

  if (tags.length === 0) return null;

  return (
    <div
      className="flex items-center gap-2 px-4 py-2 border-b border-border flex-wrap"
      style={{ background: "oklch(0.14 0.012 264)" }}
    >
      {/* Sort indicator icon */}
      <div className="flex items-center gap-1 text-[10px] text-muted-foreground shrink-0">
        <ArrowUpDown className="w-3 h-3" />
        <span>Active:</span>
      </div>

      {/* Filter tags */}
      {tags.map(tag => (
        <div
          key={tag.key}
          className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium"
          style={{
            background: `${tag.color}15`,
            color: tag.color,
            border: `1px solid ${tag.color}30`,
          }}
        >
          <span>{tag.label}</span>
          <button
            onClick={tag.onRemove}
            className="ml-0.5 opacity-60 hover:opacity-100 transition-opacity"
          >
            <X className="w-2.5 h-2.5" />
          </button>
        </div>
      ))}

      {/* Result count */}
      <div className="ml-auto text-[10px] text-muted-foreground shrink-0">
        {resultCount} result{resultCount !== 1 ? "s" : ""}
      </div>

      {/* Clear all */}
      <button
        onClick={() => onChange(DEFAULT_FILTERS)}
        className="text-[10px] text-muted-foreground hover:text-foreground transition-colors shrink-0 underline underline-offset-2"
      >
        Clear all
      </button>
    </div>
  );
}
