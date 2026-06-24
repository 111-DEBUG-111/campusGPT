import React, { useEffect, useState } from 'react';
import { useAdminStore } from '../../stores/adminStore';
import {
  AlertCircle, ChevronDown, ChevronRight, Copy, Check, Search, Calendar,
  Loader2, ThumbsDown
} from 'lucide-react';

export const NegativeFeedbackList: React.FC = () => {
  const { negativeFeedback, loadNegativeFeedback, isLoading } = useAdminStore();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const limit = 10;

  useEffect(() => {
    loadNegativeFeedback(page, limit, search);
  }, [page, search]);

  const handleSearchChange = (val: string) => {
    setSearch(val);
    setPage(1);
  };

  const copyToClipboard = async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });

  const items = negativeFeedback?.items || [];
  const total = negativeFeedback?.total || 0;
  const pages = negativeFeedback?.pages || 1;

  return (
    <div className="space-y-4">
      {/* Header Info */}
      <div
        className="rounded-2xl p-5"
        style={{ background: 'rgba(239, 68, 68, 0.06)', border: '1px solid rgba(239, 68, 68, 0.2)' }}
      >
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-start gap-3">
            <div
              className="flex items-center justify-center w-10 h-10 rounded-xl flex-shrink-0"
              style={{ background: 'rgba(239, 68, 68, 0.15)' }}
            >
              <ThumbsDown size={20} style={{ color: '#ef4444' }} />
            </div>
            <div>
              <h2 className="font-semibold mb-1" style={{ color: '#f1f5f9' }}>
                Negative Feedback Log
              </h2>
              <p className="text-sm" style={{ color: '#94a3b8', maxWidth: '640px' }}>
                Review assistant responses marked as "Not Helpful". Inspect the user's question,
                the assistant's response, and copy them for analysis. Snapshot fields are preserved
                permanently even if the original conversation is deleted.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Search & Actions Bar */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="relative flex-1 max-w-md">
          <span className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none" style={{ color: '#475569' }}>
            <Search size={16} />
          </span>
          <input
            type="text"
            placeholder="Search question, response, or title..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="form-input pl-10 text-sm"
          />
        </div>
        
        {/* Pagination status */}
        <div className="text-xs font-mono" style={{ color: '#475569' }}>
          Showing {items.length} of {total} records
        </div>
      </div>

      {isLoading && items.length === 0 ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 size={24} className="animate-spin" style={{ color: '#6366f1' }} />
        </div>
      ) : items.length === 0 ? (
        <div
          className="rounded-2xl p-12 text-center"
          style={{ background: '#111318', border: '1px solid #1f2330' }}
        >
          <AlertCircle size={32} style={{ color: '#2a2d3a', margin: '0 auto 12px' }} />
          <p className="font-medium mb-2" style={{ color: '#475569' }}>
            No negative feedback records found
          </p>
          <p className="text-sm" style={{ color: '#2a2d3a' }}>
            {search ? 'Try adjusting your search query.' : 'Awesome! No negative feedback has been submitted.'}
          </p>
        </div>
      ) : (
        <div className="rounded-2xl" style={{ background: '#111318', border: '1px solid #1f2330' }}>
          <div className="overflow-x-auto">
            <table className="docs-table">
              <thead className="docs-table-head">
                <tr>
                  <th className="docs-table-th" style={{ width: '40px' }}></th>
                  <th className="docs-table-th">Timestamp</th>
                  <th className="docs-table-th">Conversation Title</th>
                  <th className="docs-table-th">User Question</th>
                  <th className="docs-table-th">Feedback Type</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const isExpanded = expandedId === item.id;
                  
                  return (
                    <React.Fragment key={item.id}>
                      <tr className="docs-table-row">
                        <td className="docs-table-td">
                          <button
                            type="button"
                            className="btn btn-secondary text-xs py-1 px-1.5"
                            onClick={() => setExpandedId(isExpanded ? null : item.id)}
                            aria-label={isExpanded ? 'Hide details' : 'Show details'}
                          >
                            {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                          </button>
                        </td>
                        <td className="docs-table-td text-xs" style={{ whiteSpace: 'nowrap' }}>
                          <span className="flex items-center gap-1.5" style={{ color: '#94a3b8' }}>
                            <Calendar size={12} />
                            {formatDate(item.created_at)}
                          </span>
                        </td>
                        <td className="docs-table-td text-sm font-medium" style={{ color: '#e2e8f0', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {item.conversation_title || 'Untitled Conversation'}
                        </td>
                        <td className="docs-table-td text-sm truncate" style={{ color: '#94a3b8', maxWidth: '350px' }}>
                          {item.user_question || 'N/A'}
                        </td>
                        <td className="docs-table-td">
                          <span
                            className="text-xs px-2 py-0.5 rounded-full font-medium inline-flex items-center gap-1"
                            style={{ background: 'rgba(239, 68, 68, 0.12)', color: '#ef4444' }}
                          >
                            <ThumbsDown size={10} />
                            Not Helpful
                          </span>
                        </td>
                      </tr>
                      
                      {isExpanded && (
                        <tr style={{ background: 'rgba(26, 29, 37, 0.5)' }}>
                          <td></td>
                          <td colSpan={4} className="docs-table-td p-5">
                            <div className="space-y-4">
                              {/* User Comment / Suggestion */}
                              {item.comment && (
                                <div className="rounded-xl p-4 mb-4" style={{ background: 'rgba(99, 102, 241, 0.05)', border: '1px solid rgba(99, 102, 241, 0.2)' }}>
                                  <div className="flex items-center justify-between mb-2">
                                    <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
                                      User Comment / Suggestion
                                    </span>
                                    <button
                                      className="btn btn-secondary text-xs py-1 px-2 flex items-center gap-1"
                                      onClick={() => copyToClipboard(item.comment || '', `${item.id}-c`)}
                                    >
                                      {copiedId === `${item.id}-c` ? <Check size={12} style={{ color: '#10b981' }} /> : <Copy size={12} />}
                                      {copiedId === `${item.id}-c` ? 'Copied' : 'Copy Feedback'}
                                    </button>
                                  </div>
                                  <p className="text-sm font-medium" style={{ color: '#e2e8f0', whiteSpace: 'pre-wrap' }}>
                                    {item.comment}
                                  </p>
                                </div>
                              )}

                              {/* User Question */}
                              <div className="rounded-xl p-4" style={{ background: '#16181f', border: '1px solid #222533' }}>
                                <div className="flex items-center justify-between mb-2">
                                  <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#4f46e5' }}>
                                    User Question
                                  </span>
                                  <button
                                    className="btn btn-secondary text-xs py-1 px-2 flex items-center gap-1"
                                    onClick={() => copyToClipboard(item.user_question || '', `${item.id}-q`)}
                                  >
                                    {copiedId === `${item.id}-q` ? <Check size={12} style={{ color: '#10b981' }} /> : <Copy size={12} />}
                                    {copiedId === `${item.id}-q` ? 'Copied' : 'Copy Question'}
                                  </button>
                                </div>
                                <p className="text-sm font-medium" style={{ color: '#e2e8f0', whiteSpace: 'pre-wrap' }}>
                                  {item.user_question || 'N/A'}
                                </p>
                              </div>

                              {/* Assistant Response */}
                              <div className="rounded-xl p-4" style={{ background: '#16181f', border: '1px solid #222533' }}>
                                <div className="flex items-center justify-between mb-2">
                                  <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#10b981' }}>
                                    Assistant Response
                                  </span>
                                  <button
                                    className="btn btn-secondary text-xs py-1 px-2 flex items-center gap-1"
                                    onClick={() => copyToClipboard(item.assistant_response || '', `${item.id}-a`)}
                                  >
                                    {copiedId === `${item.id}-a` ? <Check size={12} style={{ color: '#10b981' }} /> : <Copy size={12} />}
                                    {copiedId === `${item.id}-a` ? 'Copied' : 'Copy Answer'}
                                  </button>
                                </div>
                                <div className="text-sm" style={{ color: '#cbd5e1', whiteSpace: 'pre-wrap' }}>
                                  {item.assistant_response || 'N/A'}
                                </div>
                              </div>
                              
                              {/* Action Bar */}
                              <div className="flex items-center justify-end gap-2 text-xs">
                                <button
                                  className="btn btn-secondary py-1 px-2 text-xs flex items-center gap-1"
                                  onClick={() => copyToClipboard(`Q: ${item.user_question}\nA: ${item.assistant_response}`, `${item.id}-both`)}
                                >
                                  {copiedId === `${item.id}-both` ? <Check size={12} style={{ color: '#10b981' }} /> : <Copy size={12} />}
                                  {copiedId === `${item.id}-both` ? 'Copied Q&A' : 'Copy Both (Q&A)'}
                                </button>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {pages > 1 && (
            <div className="flex items-center justify-between px-5 py-4 border-t" style={{ borderColor: '#1f2330' }}>
              <div className="text-sm" style={{ color: '#475569' }}>
                Page <span className="font-semibold text-slate-300">{page}</span> of{' '}
                <span className="font-semibold text-slate-300">{pages}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="btn btn-secondary text-xs py-1.5 px-3"
                  onClick={() => setPage(page - 1)}
                  disabled={page === 1}
                >
                  Previous
                </button>
                <button
                  className="btn btn-secondary text-xs py-1.5 px-3"
                  onClick={() => setPage(page + 1)}
                  disabled={page === pages}
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
