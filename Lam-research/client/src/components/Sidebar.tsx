/*
 * ResearchAI — Sidebar Component
 * Design: Precision Dark UI
 * - Logo with Space Grotesk font
 * - New Search button (indigo accent)
 * - Search History list
 * - Saved Researchers list (single, no duplicates)
 * - Saved Papers section
 * Width: 240px fixed
 */

import { useState } from "react";
import { Search, Clock, BookmarkCheck, FileText, Plus, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { type Researcher, searchHistory } from "@/lib/data";
import { toast } from "sonner";

interface SidebarProps {
  savedResearchers: string[];
  allResearchers: Researcher[];
  onSelectResearcher: (r: Researcher) => void;
  selectedId: string;
}

export default function Sidebar({ savedResearchers, allResearchers, onSelectResearcher, selectedId }: SidebarProps) {
  const [historyOpen, setHistoryOpen] = useState(true);
  const [savedOpen, setSavedOpen] = useState(true);

  const savedList = allResearchers.filter(r => savedResearchers.includes(r.id));

  return (
    <aside
      className="flex flex-col shrink-0 overflow-hidden border-r border-border"
      style={{ width: 240, background: "oklch(0.15 0.012 264)" }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-4 border-b border-border">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: "oklch(0.62 0.19 264)" }}
        >
          <Search className="w-4 h-4 text-white" />
        </div>
        <div>
          <div
            className="text-sm font-bold leading-tight text-foreground"
            style={{ fontFamily: "'Space Grotesk', sans-serif" }}
          >
            ResearchAI
          </div>
          <div className="text-[10px] text-muted-foreground leading-tight">Search Assistant</div>
        </div>
      </div>

      {/* New Search Button */}
      <div className="px-3 py-3">
        <button
          onClick={() => toast.info("Start a new search in the search bar above")}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
          style={{
            background: "oklch(0.62 0.19 264 / 15%)",
            color: "oklch(0.78 0.12 264)",
            border: "1px solid oklch(0.62 0.19 264 / 25%)",
          }}
          onMouseEnter={e => {
            (e.currentTarget as HTMLButtonElement).style.background = "oklch(0.62 0.19 264 / 25%)";
          }}
          onMouseLeave={e => {
            (e.currentTarget as HTMLButtonElement).style.background = "oklch(0.62 0.19 264 / 15%)";
          }}
        >
          <Plus className="w-4 h-4" />
          New Search
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-1">

        {/* Search History */}
        <div>
          <button
            onClick={() => setHistoryOpen(o => !o)}
            className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
          >
            {historyOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            <Clock className="w-3 h-3" />
            Search History
          </button>
          {historyOpen && (
            <div className="mt-1 space-y-0.5 pl-2">
              {searchHistory.map((item, i) => (
                <button
                  key={i}
                  onClick={() => toast.info(`Searching: "${item}"`)}
                  className={cn(
                    "w-full text-left px-2 py-1.5 rounded text-xs text-muted-foreground hover:text-foreground hover:bg-white/5 transition-all duration-100 truncate",
                    i === 0 && "text-foreground bg-white/5"
                  )}
                >
                  {item}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Divider */}
        <div className="h-px bg-border my-2" />

        {/* Saved Researchers */}
        <div>
          <button
            onClick={() => setSavedOpen(o => !o)}
            className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
          >
            {savedOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            <BookmarkCheck className="w-3 h-3" />
            Saved Researchers
          </button>
          {savedOpen && (
            <div className="mt-1 space-y-0.5 pl-2">
              {savedList.length === 0 ? (
                <p className="px-2 py-1.5 text-xs text-muted-foreground italic">No saved researchers</p>
              ) : (
                savedList.map(r => (
                  <button
                    key={r.id}
                    onClick={() => onSelectResearcher(r)}
                    className={cn(
                      "w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs transition-all duration-100",
                      selectedId === r.id
                        ? "text-foreground bg-white/8"
                        : "text-muted-foreground hover:text-foreground hover:bg-white/5"
                    )}
                  >
                    <img
                      src={r.avatar}
                      alt={r.name}
                      className="w-5 h-5 rounded-full object-cover shrink-0"
                    />
                    <span className="truncate">{r.name}</span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Divider */}
        <div className="h-px bg-border my-2" />

        {/* Saved Papers */}
        <div>
          <button
            onClick={() => toast.info("Saved Papers feature coming soon")}
            className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
          >
            <FileText className="w-3 h-3" />
            Saved Papers
          </button>
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-border">
        <div className="flex items-center justify-between text-[10px] text-muted-foreground">
          <span>1 conversation</span>
          <span>Stored locally</span>
        </div>
      </div>
    </aside>
  );
}
