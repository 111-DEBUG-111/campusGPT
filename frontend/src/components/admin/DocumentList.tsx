import React, { useState } from 'react';
import {
  FileText, Trash2, Loader2, RefreshCw,
  CheckCircle, AlertCircle, Clock,
  Pencil, X, Check, ShieldCheck, GraduationCap,
} from 'lucide-react';
import { useAdminStore } from '../../stores/adminStore';
import type { Document, DocumentSourceType } from '../../types';

// ── Status badge ──────────────────────────────────────────────────────────────

const StatusBadge: React.FC<{ status: Document['status'] }> = ({ status }) => {
  const config = {
    indexed:  { icon: <CheckCircle size={12} />, label: 'Indexed',   class: 'status-indexed'  },
    indexing: { icon: <Loader2 size={12} className="animate-spin" />, label: 'Indexing…', class: 'status-indexing' },
    pending:  { icon: <Clock size={12} />,       label: 'Pending',   class: 'status-pending'  },
    error:    { icon: <AlertCircle size={12} />, label: 'Error',     class: 'status-error'    },
  }[status];

  return (
    <span className={`status-badge ${config.class}`}>
      {config.icon}
      {config.label}
    </span>
  );
};

// ── Source badge ──────────────────────────────────────────────────────────────

const SourceBadge: React.FC<{ sourceType: DocumentSourceType; author?: string | null }> = ({
  sourceType,
  author,
}) => {
  if (sourceType === 'experience') {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: '4px',
        fontSize: '10px', fontWeight: 600, padding: '2px 8px', borderRadius: '6px',
        background: 'rgba(251,146,60,0.12)', color: '#fb923c',
        border: '1px solid rgba(251,146,60,0.25)', whiteSpace: 'nowrap',
      }}>
        <GraduationCap size={10} />
        {author ? `Student · ${author}` : 'Student Exp.'}
      </span>
    );
  }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      fontSize: '10px', fontWeight: 600, padding: '2px 8px', borderRadius: '6px',
      background: 'rgba(56,189,248,0.1)', color: '#38bdf8',
      border: '1px solid rgba(56,189,248,0.22)', whiteSpace: 'nowrap',
    }}>
      <ShieldCheck size={10} />
      Official
    </span>
  );
};

// ── Inline edit row ────────────────────────────────────────────────────────────

interface EditRowProps {
  doc: Document;
  onSave: (patch: { source_type?: DocumentSourceType; author?: string | null }) => void;
  onCancel: () => void;
}

const EditSourceRow: React.FC<EditRowProps> = ({ doc, onSave, onCancel }) => {
  const [sourceType, setSourceType] = useState<DocumentSourceType>(doc.source_type);
  const [author, setAuthor] = useState(doc.author ?? '');

  return (
    <td colSpan={8} style={{ padding: '8px 16px' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: '10px',
        background: 'rgba(99,102,241,0.06)',
        border: '1px solid rgba(99,102,241,0.2)',
        borderRadius: '10px', padding: '10px 14px',
      }}>
        <span style={{ color: '#94a3b8', fontSize: '12px', fontWeight: 600, minWidth: '90px' }}>
          Knowledge Source
        </span>

        {/* Source type toggle */}
        <div style={{ display: 'flex', gap: '6px' }}>
          {(['official', 'experience'] as DocumentSourceType[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setSourceType(t)}
              style={{
                display: 'flex', alignItems: 'center', gap: '5px',
                fontSize: '11px', fontWeight: 600, padding: '4px 10px',
                borderRadius: '7px', border: 'none', cursor: 'pointer',
                background: sourceType === t
                  ? (t === 'official' ? 'rgba(56,189,248,0.2)' : 'rgba(251,146,60,0.2)')
                  : 'rgba(255,255,255,0.04)',
                color: sourceType === t
                  ? (t === 'official' ? '#38bdf8' : '#fb923c')
                  : '#64748b',
                transition: 'all 0.15s',
              }}
            >
              {t === 'official' ? <ShieldCheck size={12} /> : <GraduationCap size={12} />}
              {t === 'official' ? 'Official' : 'Student Exp.'}
            </button>
          ))}
        </div>

        {/* Author field — only for experience */}
        {sourceType === 'experience' && (
          <input
            type="text"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            placeholder="Author (optional)"
            maxLength={255}
            style={{
              flex: 1, background: 'rgba(255,255,255,0.04)',
              border: '1px solid #1f2330', borderRadius: '7px',
              padding: '4px 10px', fontSize: '12px', color: '#f1f5f9',
              outline: 'none',
            }}
          />
        )}

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: '6px', marginLeft: 'auto' }}>
          <button
            type="button"
            onClick={() =>
              onSave({
                source_type: sourceType,
                author: sourceType === 'experience' ? author.trim() || null : null,
              })
            }
            style={{
              display: 'flex', alignItems: 'center', gap: '4px',
              fontSize: '11px', fontWeight: 600, padding: '4px 10px',
              borderRadius: '7px', border: 'none', cursor: 'pointer',
              background: 'rgba(99,102,241,0.2)', color: '#818cf8',
            }}
          >
            <Check size={12} /> Save
          </button>
          <button
            type="button"
            onClick={onCancel}
            style={{
              display: 'flex', alignItems: 'center', gap: '4px',
              fontSize: '11px', padding: '4px 10px',
              borderRadius: '7px', border: 'none', cursor: 'pointer',
              background: 'rgba(255,255,255,0.04)', color: '#64748b',
            }}
          >
            <X size={12} /> Cancel
          </button>
        </div>
      </div>
    </td>
  );
};

// ── Helpers ───────────────────────────────────────────────────────────────────

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatDate = (dateStr: string) =>
  new Date(dateStr).toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
  });

// ── Main component ────────────────────────────────────────────────────────────

export const DocumentList: React.FC = () => {
  const { documents, deleteDocument, updateDocument, reindex, isLoading } = useAdminStore();
  const [editingId, setEditingId] = useState<number | null>(null);

  const handleDelete = async (id: number, name: string) => {
    if (confirm(`Delete "${name}"? This will remove it from the knowledge base.`)) {
      await deleteDocument(id);
    }
  };

  const handleSave = async (
    id: number,
    patch: { source_type?: DocumentSourceType; author?: string | null },
  ) => {
    await updateDocument(id, patch);
    setEditingId(null);
  };

  if (documents.length === 0) {
    return (
      <div
        className="rounded-2xl p-12 text-center"
        style={{ background: '#111318', border: '1px solid #1f2330' }}
      >
        <FileText size={32} style={{ color: '#2a2d3a', margin: '0 auto 12px' }} />
        <p className="font-medium mb-2" style={{ color: '#475569' }}>No documents yet</p>
        <p className="text-sm" style={{ color: '#2a2d3a' }}>
          Upload a PDF, TXT, or MD file to get started.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl" style={{ background: '#111318', border: '1px solid #1f2330' }}>
      <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: '#1f2330' }}>
        <h2 className="font-semibold" style={{ color: '#f1f5f9' }}>
          Knowledge Base ({documents.length} documents)
        </h2>
        <button
          id="reindex-btn"
          className="btn btn-secondary text-xs py-1.5"
          onClick={reindex}
          disabled={isLoading}
        >
          {isLoading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          Rebuild BM25 Index
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="docs-table">
          <thead className="docs-table-head">
            <tr>
              <th className="docs-table-th">Document</th>
              <th className="docs-table-th">Knowledge Source</th>
              <th className="docs-table-th">Category</th>
              <th className="docs-table-th">Chunks</th>
              <th className="docs-table-th">Size</th>
              <th className="docs-table-th">Uploaded</th>
              <th className="docs-table-th">Status</th>
              <th className="docs-table-th"></th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <React.Fragment key={doc.id}>
                <tr className="docs-table-row">
                  {/* Document name */}
                  <td className="docs-table-td">
                    <div className="flex items-center gap-2">
                      <FileText size={14} style={{ color: '#6366f1', flexShrink: 0 }} />
                      <span
                        className="font-medium"
                        style={{
                          color: '#f1f5f9',
                          maxWidth: '180px',
                          display: 'block',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                        title={doc.original_filename}
                      >
                        {doc.original_filename}
                      </span>
                    </div>
                  </td>

                  {/* Knowledge Source badge */}
                  <td className="docs-table-td">
                    <SourceBadge sourceType={doc.source_type} author={doc.author} />
                  </td>

                  {/* Category */}
                  <td className="docs-table-td">
                    <span
                      className="text-xs px-2 py-1 rounded-lg"
                      style={{ background: 'rgba(99,102,241,0.1)', color: '#818cf8' }}
                    >
                      {doc.category}
                    </span>
                  </td>

                  <td className="docs-table-td font-mono text-xs">{doc.chunk_count}</td>
                  <td className="docs-table-td text-xs">{formatSize(doc.file_size_bytes)}</td>
                  <td className="docs-table-td text-xs">{formatDate(doc.uploaded_at)}</td>
                  <td className="docs-table-td"><StatusBadge status={doc.status} /></td>

                  {/* Actions */}
                  <td className="docs-table-td">
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <button
                        className="btn btn-secondary text-xs py-1 px-2"
                        onClick={() => setEditingId(editingId === doc.id ? null : doc.id)}
                        title="Edit source classification"
                        aria-label={`Edit source of ${doc.original_filename}`}
                      >
                        <Pencil size={12} />
                      </button>
                      <button
                        className="btn btn-danger text-xs py-1 px-2"
                        onClick={() => handleDelete(doc.id, doc.original_filename)}
                        aria-label={`Delete ${doc.original_filename}`}
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </td>
                </tr>

                {/* Inline edit row — expands below the target row */}
                {editingId === doc.id && (
                  <tr style={{ background: 'rgba(99,102,241,0.03)' }}>
                    <EditSourceRow
                      doc={doc}
                      onSave={(patch) => handleSave(doc.id, patch)}
                      onCancel={() => setEditingId(null)}
                    />
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
