export interface ResearchPaper {
  id: string;
  title: string;
  year: number;
  venue: string;
  venueType: string;
  citations: number;
  recentCitations?: number;
  citationYearCounts?: Array<{ year: number; citations: number }>;
  concept: string;
  abstract: string;
  embeddingId?: string;
  url?: string;
  downloads?: number;
}

export interface ResearchCollaborator {
  name: string;
  type: string;
  sharedPapers: number;
}

export interface ResearcherRecord {
  id: string;
  name: string;
  initials: string;
  institution: string;
  institutionId: string;
  matchedInstitution?: string;
  matchedInstitutionId?: string;
  matchedInstitutionCountry?: string;
  currentInstitution?: string;
  currentInstitutionId?: string;
  currentInstitutionCountry?: string;
  country: string;
  region: string;
  totalWorks: number;
  totalCitations: number;
  recentCitations?: number;
  citationStartYear?: number;
  citationEndYear?: number;
  hIndex: number;
  i10Index: number;
  careerStartYear: number;
  yearsActive: number;
  qScore: number;
  recencyScore: number;
  seniorityScore?: number;
  compositeScore: number;
  primaryTopic: string;
  topics: string[];
  subfield: string;
  field: string;
  domain: string;
  authorUrl?: string;
  googleUrl?: string;
  scholarUrl?: string;
  coAuthorCount?: number;
  coAuthorIds?: string[];
  papers: ResearchPaper[];
  collaborators: ResearchCollaborator[];
  affiliation?: string;
  role?: string;
  avatar?: string;
  keywords?: string[];
  relevanceScore?: number;
  queryRelevanceScore?: number;
  queryRelevanceNorm?: number;
  recentCitationImpactNorm?: number;
  finalScore?: number;
  whyMatched?: string;
  matchSource?: "exact-name" | "author-search" | "institution-search" | "works-search" | "topic-relevance";
  matchReason?: string;
  searchMode?: "author" | "institution" | "topic";
  aiSummary?: string;
  fullBio?: string;
  topPapers?: ResearchPaper[];
  researchThemes?: string[];
  relatedResearchers?: string[];
  publications?: number;
}

export type Researcher = ResearcherRecord & {
  affiliation: string;
  role: string;
  avatar: string;
  keywords: string[];
  relevanceScore: number;
  whyMatched: string;
  aiSummary: string;
  fullBio: string;
  topPapers: ResearchPaper[];
  researchThemes: string[];
  relatedResearchers: string[];
  publications: number;
};

export const researchers: ResearcherRecord[] = [];

export const searchHistory = [
  "quantum computing algorithms",
  "quantum machine learning",
  "post-quantum cryptography",
  "thermal properties of materials",
];

export const trendingTopics = [
  "Quantum computing algorithms",
  "AI in healthcare",
  "Post-quantum cryptography",
  "Vision-language models",
  "Smart agriculture AI",
];
