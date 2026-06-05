import React, { useState } from 'react';
import type { SourceCitation } from '../../types';
import { ChevronDown, ChevronUp, FileText, ExternalLink } from 'lucide-react';

interface CitationCardProps {
  citation: SourceCitation;
  index: number;
}

const CATEGORY_COLORS: Record<string, string> = {
  academics: 'citation-academics',
  placements: 'citation-placements',
  hostel: 'citation-hostel',
  clubs: 'citation-clubs',
  policies: 'citation-policies',
  faq: 'citation-faq',
  internships: 'citation-internships',
  general: 'citation-general',
};

export const CitationCard: React.FC<CitationCardProps> = ({ citation, index }) => {
  const [expanded, setExpanded] = useState(false);
  const colorClass = CATEGORY_COLORS[citation.category] || 'citation-general';

  return (
    <div className={`citation-card ${colorClass}`}>
      <button
        className="citation-header"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <div className="citation-header-left">
          <span className="citation-index">[{index}]</span>
          <FileText size={14} />
          <span className="citation-filename" title={citation.filename}>
            {citation.filename.length > 35
              ? citation.filename.substring(0, 35) + '…'
              : citation.filename}
          </span>
          {citation.page_number && (
            <span className="citation-page">p. {citation.page_number}</span>
          )}
          <span className={`citation-category-badge`}>{citation.category}</span>
        </div>
        <div className="citation-header-right">
          <span className="citation-score">
            {Math.round(citation.relevance_score * 100)}%
          </span>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>
      {expanded && (
        <div className="citation-excerpt">
          <p>{citation.chunk_text}</p>
        </div>
      )}
    </div>
  );
};
