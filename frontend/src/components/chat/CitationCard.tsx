import React, { useState } from 'react';
import type { SourceCitation } from '../../types';
import { ChevronDown, ChevronUp, FileText, Table, BookOpen } from 'lucide-react';

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

/** Icon that reflects the chunk type returned by the semantic chunker. */
const ChunkTypeIcon: React.FC<{ chunkType?: string | null }> = ({ chunkType }) => {
  if (chunkType === 'table') return <Table size={13} className="citation-chunk-icon citation-chunk-table" />;
  if (chunkType === 'heading_intro') return <BookOpen size={13} className="citation-chunk-icon citation-chunk-heading" />;
  return <FileText size={14} />;
};

/** Pill badge showing whether a source is official or student experience. */
const SourceBadge: React.FC<{ sourceType?: string | null; author?: string | null }> = ({
  sourceType,
  author,
}) => {
  if (sourceType === 'experience') {
    const label = author ? `🎓 ${author}` : '🎓 Student Experience';
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '3px',
          fontSize: '10px',
          fontWeight: 600,
          padding: '2px 7px',
          borderRadius: '6px',
          background: 'rgba(251, 146, 60, 0.15)',
          color: '#fb923c',
          border: '1px solid rgba(251, 146, 60, 0.25)',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </span>
    );
  }

  // Default: official
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '3px',
        fontSize: '10px',
        fontWeight: 600,
        padding: '2px 7px',
        borderRadius: '6px',
        background: 'rgba(56, 189, 248, 0.12)',
        color: '#38bdf8',
        border: '1px solid rgba(56, 189, 248, 0.22)',
        whiteSpace: 'nowrap',
      }}
    >
      📄 Official
    </span>
  );
};

export const CitationCard: React.FC<CitationCardProps> = ({ citation, index }) => {
  const [expanded, setExpanded] = useState(false);
  const colorClass = CATEGORY_COLORS[citation.category] || 'citation-general';

  // Use section_path breadcrumb when available, fall back to section_title
  const sectionLabel = citation.section_path || citation.section_title || null;

  return (
    <div className={`citation-card ${colorClass}`}>
      <button
        className="citation-header"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <div className="citation-header-left">
          <span className="citation-index">[{index}]</span>
          <ChunkTypeIcon chunkType={citation.chunk_type} />
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

      {/* Source type badge — always visible */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '4px 12px 4px',
        }}
      >
        <SourceBadge sourceType={citation.source_type} author={citation.author} />
        {/* Section breadcrumb */}
        {sectionLabel && (
          <div className="citation-section-path" title={sectionLabel}>
            <BookOpen size={11} />
            <span>{sectionLabel}</span>
          </div>
        )}
      </div>

      {expanded && (
        <div className="citation-excerpt">
          <p>{citation.chunk_text}</p>
        </div>
      )}
    </div>
  );
};
