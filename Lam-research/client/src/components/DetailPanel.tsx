/*
 * ResearchAI — DetailPanel Component
 * Design: Precision Dark UI
 * Right panel (320px fixed) showing selected researcher details:
 * - Avatar, name, affiliation, role
 * - Save button (NO Compare)
 * - AI Research Summary
 * - Stats: H-Index, Citations, Publications
 * - Top Papers with citation counts
 * - Research Themes tags
 * - Related Researchers
 */

import { Bookmark, BookmarkCheck, Sparkles, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { type Researcher, researchers } from "@/lib/data";
import { toast } from "sonner";

interface DetailPanelProps {
  researcher: Researcher;
  isSaved: boolean;
  onSave: () => void;
}

function StatBox({ label, value }: { label: string; value: string | number }) {
  return (
    <div
      className="flex-1 rounded-lg p-3 text-center"
      style={{ background: "oklch(0.13 0.012 264)", border: "1px solid oklch(1 0 0 / 6%)" }}
    >
      <div className="text-lg font-bold score-badge text-foreground">{value}</div>
      <div className="text-[10px] text-muted-foreground mt-0.5">{label}</div>
    </div>
  );
}

function formatCitations(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(0)}k`;
  return n.toString();
}

export default function DetailPanel({ researcher, isSaved, onSave }: DetailPanelProps) {
  const relatedList = researchers.filter(r =>
    researcher.relatedResearchers.includes(r.id)
  );

  return (
    <aside
      className="shrink-0 overflow-y-auto border-l border-border"
      style={{ width: 320, background: "oklch(0.15 0.012 264)" }}
    >
      <div className="p-4 space-y-4">
        {/* Researcher Header */}
        <div
          className="rounded-xl p-4 border border-border"
          style={{ background: "oklch(0.17 0.012 264)" }}
        >
          <div className="flex items-start gap-3">
            <div className="relative shrink-0">
              <img
                src={researcher.avatar}
                alt={researcher.name}
                className="w-14 h-14 rounded-xl object-cover ring-2 ring-indigo-500/30"
              />
              <div
                className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full flex items-center justify-center"
                style={{ background: "oklch(0.62 0.19 264)", border: "2px solid oklch(0.17 0.012 264)" }}
              >
                <Sparkles className="w-2.5 h-2.5 text-white" />
              </div>
            </div>
            <div className="flex-1 min-w-0">
              <h2
                className="text-sm font-bold text-foreground leading-tight"
                style={{ fontFamily: "'Sora', sans-serif" }}
              >
                {researcher.name}
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">{researcher.affiliation}</p>
              <p
                className="text-xs mt-1 font-medium"
                style={{ color: "oklch(0.72 0.15 264)" }}
              >
                {researcher.role}
              </p>
            </div>
          </div>

          {/* Save button only (no Compare) */}
          <div className="mt-3">
            <button
              onClick={() => { onSave(); toast.success(isSaved ? `Removed ${researcher.name}` : `Saved ${researcher.name}`); }}
              className={cn(
                "w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-150 border",
                isSaved
                  ? "text-indigo-300 border-indigo-500/40 bg-indigo-500/10"
                  : "text-muted-foreground border-border hover:text-foreground hover:bg-white/5"
              )}
            >
              {isSaved ? <BookmarkCheck className="w-4 h-4" /> : <Bookmark className="w-4 h-4" />}
              {isSaved ? "Saved" : "Save Researcher"}
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="flex gap-2">
          <StatBox label="H-Index" value={researcher.hIndex} />
          <StatBox label="Citations" value={formatCitations(researcher.totalCitations)} />
          <StatBox label="Papers" value={researcher.publications} />
        </div>

        {/* AI Research Summary */}
        <div
          className="rounded-xl p-4 border border-border"
          style={{ background: "oklch(0.17 0.012 264)" }}
        >
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="w-3.5 h-3.5" style={{ color: "oklch(0.72 0.15 264)" }} />
            <h3 className="text-xs font-semibold text-foreground uppercase tracking-wider">AI Research Summary</h3>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">{researcher.fullBio}</p>
        </div>

        {/* Top Papers */}
        <div
          className="rounded-xl p-4 border border-border"
          style={{ background: "oklch(0.17 0.012 264)" }}
        >
          <h3 className="text-xs font-semibold text-foreground uppercase tracking-wider mb-3">Top Papers</h3>
          <div className="space-y-3">
            {researcher.topPapers.map((paper, i) => (
              <div key={i} className="flex items-start justify-between gap-2 group">
                <div className="flex-1 min-w-0">
                  <button
                    onClick={() => toast.info(`Opening: ${paper.title}`)}
                    className="text-xs font-medium text-foreground hover:text-indigo-300 transition-colors text-left leading-snug flex items-start gap-1"
                  >
                    <span className="shrink-0 mt-0.5">•</span>
                    <span>{paper.title}</span>
                    <ExternalLink className="w-2.5 h-2.5 shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </button>
                  <p className="text-[10px] text-muted-foreground mt-0.5 pl-3">{paper.venue}</p>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-xs font-bold score-badge text-foreground">{paper.citations.toLocaleString()}</div>
                  <div className="text-[10px] text-muted-foreground">{paper.downloads}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Research Themes */}
        <div
          className="rounded-xl p-4 border border-border"
          style={{ background: "oklch(0.17 0.012 264)" }}
        >
          <h3 className="text-xs font-semibold text-foreground uppercase tracking-wider mb-3">Research Themes</h3>
          <div className="flex flex-wrap gap-1.5">
            {researcher.researchThemes.map(theme => (
              <button
                key={theme}
                onClick={() => toast.info(`Filter by theme: ${theme}`)}
                className="flex items-center gap-1 px-2.5 py-1 rounded-full text-xs transition-all duration-150"
                style={{
                  background: "oklch(0.62 0.19 264 / 12%)",
                  color: "oklch(0.78 0.12 264)",
                  border: "1px solid oklch(0.62 0.19 264 / 20%)",
                }}
                onMouseEnter={e => (e.currentTarget.style.background = "oklch(0.62 0.19 264 / 22%)")}
                onMouseLeave={e => (e.currentTarget.style.background = "oklch(0.62 0.19 264 / 12%)")}
              >
                {theme}
                <svg viewBox="0 0 8 8" className="w-2 h-2 fill-current opacity-60">
                  <path d="M4 0L8 4L4 8L0 4Z" />
                </svg>
              </button>
            ))}
          </div>
        </div>

        {/* Related Researchers */}
        {relatedList.length > 0 && (
          <div
            className="rounded-xl p-4 border border-border"
            style={{ background: "oklch(0.17 0.012 264)" }}
          >
            <h3 className="text-xs font-semibold text-foreground uppercase tracking-wider mb-3">Related Researchers</h3>
            <div className="flex flex-wrap gap-2">
              {relatedList.map(r => (
                <button
                  key={r.id}
                  onClick={() => toast.info(`View profile: ${r.name}`)}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground transition-all duration-150"
                  style={{
                    background: "oklch(0.13 0.012 264)",
                    border: "1px solid oklch(1 0 0 / 6%)",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.borderColor = "oklch(0.62 0.19 264 / 30%)")}
                  onMouseLeave={e => (e.currentTarget.style.borderColor = "oklch(1 0 0 / 6%)")}
                >
                  <img src={r.avatar} alt={r.name} className="w-4 h-4 rounded-full object-cover" />
                  {r.name.split(" ")[0]} {r.name.split(" ").slice(-1)[0]}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
