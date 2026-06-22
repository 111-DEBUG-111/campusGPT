import React, { useState } from 'react';
import {
  AlertCircle, ChevronDown, ChevronRight, HelpCircle, Loader2, Upload,
} from 'lucide-react';
import type { KnowledgeGap } from '../../types';

interface Props {
  gaps: KnowledgeGap[];
  isLoading: boolean;
  onUploadClick: () => void;
}

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

const modeLabel: Record<string, string> = {
  hybrid: 'Hybrid',
  official: 'Official',
  experience: 'Experience',
};

export const KnowledgeGapsList: React.FC<Props> = ({ gaps, isLoading, onUploadClick }) => {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={24} className="animate-spin" style={{ color: '#6366f1' }} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div
        className="rounded-2xl p-5"
        style={{ background: 'rgba(245, 158, 11, 0.06)', border: '1px solid rgba(245, 158, 11, 0.2)' }}
      >
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-start gap-3">
            <div
              className="flex items-center justify-center w-10 h-10 rounded-xl flex-shrink-0"
              style={{ background: 'rgba(245, 158, 11, 0.15)' }}
            >
              <HelpCircle size={20} style={{ color: '#f59e0b' }} />
            </div>
            <div>
              <h2 className="font-semibold mb-1" style={{ color: '#f1f5f9' }}>
                Knowledge Gaps
              </h2>
              <p className="text-sm" style={{ color: '#94a3b8', maxWidth: '640px' }}>
                University questions CampusGPT could not fully answer because the knowledge base
                lacks the required information. Off-topic questions (e.g. recipes, general trivia)
                are excluded.
              </p>
            </div>
          </div>
          <button className="btn btn-primary text-xs" onClick={onUploadClick}>
            <Upload size={12} />
            Upload Document
          </button>
        </div>
      </div>

      {gaps.length === 0 ? (
        <div
          className="rounded-2xl p-12 text-center"
          style={{ background: '#111318', border: '1px solid #1f2330' }}
        >
          <AlertCircle size={32} style={{ color: '#2a2d3a', margin: '0 auto 12px' }} />
          <p className="font-medium mb-2" style={{ color: '#475569' }}>
            No knowledge gaps recorded yet
          </p>
          <p className="text-sm" style={{ color: '#2a2d3a' }}>
            When students ask on-topic questions the KB cannot answer, they will appear here.
          </p>
        </div>
      ) : (
        <div className="rounded-2xl" style={{ background: '#111318', border: '1px solid #1f2330' }}>
          <div className="px-5 py-4 border-b" style={{ borderColor: '#1f2330' }}>
            <h3 className="font-semibold" style={{ color: '#f1f5f9' }}>
              Unanswered Questions ({gaps.length})
            </h3>
          </div>

          <div className="overflow-x-auto">
            <table className="docs-table">
              <thead className="docs-table-head">
                <tr>
                  <th className="docs-table-th" style={{ width: '32px' }}></th>
                  <th className="docs-table-th">Question</th>
                  <th className="docs-table-th">Times Asked</th>
                  <th className="docs-table-th">Mode</th>
                  <th className="docs-table-th">Last Asked</th>
                </tr>
              </thead>
              <tbody>
                {gaps.map((gap) => {
                  const isExpanded = expandedId === gap.id;
                  const hasSnippet = Boolean(gap.last_answer_snippet);

                  return (
                    <React.Fragment key={gap.id}>
                      <tr className="docs-table-row">
                        <td className="docs-table-td">
                          {hasSnippet ? (
                            <button
                              type="button"
                              className="btn btn-secondary text-xs py-1 px-1.5"
                              onClick={() => setExpandedId(isExpanded ? null : gap.id)}
                              aria-label={isExpanded ? 'Collapse response' : 'Expand response'}
                            >
                              {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                            </button>
                          ) : null}
                        </td>
                        <td className="docs-table-td">
                          <span className="text-sm" style={{ color: '#f1f5f9' }}>
                            {gap.query}
                          </span>
                        </td>
                        <td className="docs-table-td font-mono text-xs">{gap.count}</td>
                        <td className="docs-table-td">
                          <span
                            className="text-xs px-2 py-1 rounded-lg"
                            style={{ background: 'rgba(99,102,241,0.1)', color: '#818cf8' }}
                          >
                            {modeLabel[gap.knowledge_mode] ?? gap.knowledge_mode}
                          </span>
                        </td>
                        <td className="docs-table-td text-xs">{formatDate(gap.last_seen_at)}</td>
                      </tr>
                      {isExpanded && hasSnippet && (
                        <tr style={{ background: 'rgba(26, 29, 37, 0.5)' }}>
                          <td></td>
                          <td colSpan={4} className="docs-table-td">
                            <p className="text-xs mb-1 font-semibold" style={{ color: '#475569' }}>
                              Last assistant response
                            </p>
                            <p className="text-sm" style={{ color: '#94a3b8', whiteSpace: 'pre-wrap' }}>
                              {gap.last_answer_snippet}
                            </p>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
