import React from 'react';
import { FileText, Trash2, Loader2, RefreshCw, CheckCircle, AlertCircle, Clock } from 'lucide-react';
import { useAdminStore } from '../../stores/adminStore';
import type { Document } from '../../types';

const StatusBadge: React.FC<{ status: Document['status'] }> = ({ status }) => {
  const config = {
    indexed: { icon: <CheckCircle size={12} />, label: 'Indexed', class: 'status-indexed' },
    indexing: { icon: <Loader2 size={12} className="animate-spin" />, label: 'Indexing…', class: 'status-indexing' },
    pending: { icon: <Clock size={12} />, label: 'Pending', class: 'status-pending' },
    error: { icon: <AlertCircle size={12} />, label: 'Error', class: 'status-error' },
  }[status];

  return (
    <span className={`status-badge ${config.class}`}>
      {config.icon}
      {config.label}
    </span>
  );
};

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatDate = (dateStr: string) =>
  new Date(dateStr).toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
  });

export const DocumentList: React.FC = () => {
  const { documents, deleteDocument, reindex, isLoading } = useAdminStore();

  const handleDelete = async (id: number, name: string) => {
    if (confirm(`Delete "${name}"? This will remove it from the knowledge base.`)) {
      await deleteDocument(id);
    }
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
              <tr key={doc.id} className="docs-table-row">
                <td className="docs-table-td">
                  <div className="flex items-center gap-2">
                    <FileText size={14} style={{ color: '#6366f1', flexShrink: 0 }} />
                    <span
                      className="font-medium"
                      style={{ color: '#f1f5f9', maxWidth: '200px', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      title={doc.original_filename}
                    >
                      {doc.original_filename}
                    </span>
                  </div>
                </td>
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
                <td className="docs-table-td">
                  <button
                    className="btn btn-danger text-xs py-1 px-2"
                    onClick={() => handleDelete(doc.id, doc.original_filename)}
                    aria-label={`Delete ${doc.original_filename}`}
                  >
                    <Trash2 size={12} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
