import type { ResearcherRecord } from "@/lib/data";

function normalizeSearchText(value: string | number | undefined) {
  return String(value ?? "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, " ")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, " ");
}

function queryTokens(query: string) {
  const stop = new Set(["paper", "papers", "researcher", "researchers", "institution", "institutions", "query", "the", "and", "for"]);
  return normalizeSearchText(query).split(/\s+/).map((token) => token.trim()).filter((token) => token.length > 1 && !stop.has(token));
}

function researcherSearchFields(researcher: ResearcherRecord) {
  return [
    researcher.id,
    researcher.name,
    researcher.initials,
    researcher.institution,
    researcher.institutionId,
    researcher.country,
    researcher.region,
    researcher.primaryTopic,
    researcher.subfield,
    researcher.field,
    researcher.domain,
    researcher.authorUrl,
    researcher.googleUrl,
    researcher.scholarUrl,
    researcher.affiliation,
    researcher.role,
    researcher.aiSummary,
    researcher.fullBio,
    ...(researcher.topics ?? []),
    ...(researcher.keywords ?? []),
    ...(researcher.researchThemes ?? []),
    ...(researcher.collaborators ?? []).map((collaborator) => collaborator.name),
    ...(researcher.papers ?? []).flatMap((paper) => [paper.id, paper.title, paper.venue, paper.concept, paper.abstract, String(paper.year)]),
  ];
}

export function matchesResearcher(researcher: ResearcherRecord, query: string) {
  const tokens = queryTokens(query);
  if (tokens.length === 0) return true;
  const phrase = normalizeSearchText(query);
  const haystack = normalizeSearchText(researcherSearchFields(researcher).join(" "));
  return haystack.includes(phrase) || tokens.every((token) => haystack.includes(token));
}

export function matchesResearcherName(researcher: ResearcherRecord, query: string) {
  const tokens = queryTokens(query);
  if (tokens.length === 0) return false;
  const phrase = normalizeSearchText(query);
  const haystack = normalizeSearchText([researcher.name, researcher.initials].join(" "));
  return haystack.includes(phrase) || tokens.every((token) => haystack.includes(token));
}

export function matchesDirectRecord(researcher: ResearcherRecord, query: string) {
  const tokens = queryTokens(query);
  if (tokens.length === 0) return false;
  const phrase = normalizeSearchText(query);
  const haystack = normalizeSearchText([
    researcher.id,
    researcher.name,
    researcher.initials,
    researcher.institution,
    researcher.institutionId,
    ...(researcher.collaborators ?? []).map((collaborator) => collaborator.name),
    ...(researcher.papers ?? []).flatMap((paper) => [paper.id, paper.title]),
  ].join(" "));
  return haystack.includes(phrase) || tokens.every((token) => haystack.includes(token));
}

function fieldMatchScore(values: Array<string | number | undefined>, phrase: string, tokens: string[], weight: number) {
  const haystack = normalizeSearchText(values.join(" "));
  if (!haystack) return 0;
  if (haystack === phrase) return weight * 4;
  if (phrase && haystack.includes(phrase)) return weight * 3;
  if (tokens.length > 0 && tokens.every((token) => haystack.includes(token))) return weight * 2;
  return 0;
}

export function searchRelevance(researcher: ResearcherRecord, query: string) {
  const phrase = normalizeSearchText(query);
  const tokens = queryTokens(query);
  if (!phrase && tokens.length === 0) return 0;
  const groups = [
    { values: [researcher.id, researcher.name, researcher.initials], weight: 100000 },
    { values: [researcher.institution, researcher.institutionId, researcher.affiliation], weight: 60000 },
    { values: (researcher.papers ?? []).flatMap((paper) => [paper.id, paper.title]), weight: 65000 },
    { values: [researcher.primaryTopic, researcher.subfield, researcher.field, researcher.domain, ...(researcher.topics ?? []), ...(researcher.keywords ?? []), ...(researcher.researchThemes ?? [])], weight: 80000 },
    { values: (researcher.papers ?? []).flatMap((paper) => [paper.venue, paper.concept, paper.abstract, String(paper.year)]), weight: 10000 },
  ];
  const phraseScore = Math.max(...groups.map((group) => fieldMatchScore(group.values, phrase, tokens, group.weight)));
  const tokenScore = tokens.reduce((sum, token) => {
    const bestField = Math.max(...groups.map((group) => normalizeSearchText(group.values.join(" ")).includes(token) ? group.weight : 0));
    return sum + bestField;
  }, 0);
  return Math.max(phraseScore, tokenScore);
}
