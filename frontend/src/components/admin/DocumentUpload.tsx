import React, { useState, useRef } from 'react';
import { Upload, FileText, X, Loader2, ShieldCheck, GraduationCap } from 'lucide-react';
import { useAdminStore } from '../../stores/adminStore';
import { DOCUMENT_CATEGORIES } from '../../types';
import type { DocumentSourceType } from '../../types';

export const DocumentUpload: React.FC = () => {
  const { uploadDocument, isUploading } = useAdminStore();
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState('general');
  const [description, setDescription] = useState('');
  const [sourceType, setSourceType] = useState<DocumentSourceType>('official');
  const [author, setAuthor] = useState('');
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (selectedFile: File) => {
    const allowed = ['.pdf', '.txt', '.md'];
    const ext = '.' + selectedFile.name.split('.').pop()?.toLowerCase();
    if (!allowed.includes(ext)) {
      alert(`Unsupported file type. Allowed: ${allowed.join(', ')}`);
      return;
    }
    if (selectedFile.size > 50 * 1024 * 1024) {
      alert('File too large. Maximum size: 50MB');
      return;
    }
    setFile(selectedFile);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFileSelect(dropped);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    await uploadDocument(
      file,
      category,
      description,
      sourceType,
      sourceType === 'experience' ? author.trim() || undefined : undefined,
    );
    setFile(null);
    setDescription('');
    setCategory('general');
    setSourceType('official');
    setAuthor('');
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="rounded-2xl p-6" style={{ background: '#111318', border: '1px solid #1f2330' }}>
      <h2 className="text-lg font-semibold mb-5" style={{ color: '#f1f5f9' }}>
        Upload Document
      </h2>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Drop zone */}
        {!file ? (
          <div
            className={`upload-zone ${dragging ? 'dragging' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            aria-label="Upload document drop zone"
          >
            <div className="upload-zone-icon">
              <Upload size={28} />
            </div>
            <p className="font-semibold mb-1" style={{ color: '#f1f5f9' }}>
              Drop your file here
            </p>
            <p className="text-sm mb-3" style={{ color: '#475569' }}>
              or click to browse
            </p>
            <p className="text-xs" style={{ color: '#2a2d3a' }}>
              Supports PDF, TXT, MD · Max 50MB
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt,.md"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
              id="file-upload-input"
            />
          </div>
        ) : (
          <div
            className="flex items-center gap-3 p-4 rounded-xl"
            style={{ background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.2)' }}
          >
            <FileText size={20} style={{ color: '#6366f1' }} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate" style={{ color: '#f1f5f9' }}>
                {file.name}
              </p>
              <p className="text-xs" style={{ color: '#6366f1' }}>
                {formatSize(file.size)}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setFile(null)}
              className="p-1 rounded-lg"
              style={{ color: '#475569' }}
              aria-label="Remove file"
            >
              <X size={16} />
            </button>
          </div>
        )}

        {/* Knowledge Source — required */}
        <div>
          <label className="form-label" htmlFor="doc-source-type">
            Knowledge Source <span style={{ color: '#ef4444', marginLeft: '2px' }}>*</span>
          </label>
          <div className="upload-source-options">
            {/* Official option */}
            <button
              type="button"
              id="source-official"
              onClick={() => setSourceType('official')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 14px',
                borderRadius: '10px',
                border: sourceType === 'official'
                  ? '2px solid #38bdf8'
                  : '1px solid #1f2330',
                background: sourceType === 'official'
                  ? 'rgba(56, 189, 248, 0.1)'
                  : 'rgba(255,255,255,0.02)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <ShieldCheck
                size={16}
                style={{ color: sourceType === 'official' ? '#38bdf8' : '#475569', flexShrink: 0 }}
              />
              <div style={{ textAlign: 'left' }}>
                <p style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  color: sourceType === 'official' ? '#38bdf8' : '#94a3b8',
                  lineHeight: 1.2,
                }}>
                  Official Document
                </p>
                <p style={{ fontSize: '10px', color: '#475569', lineHeight: 1.3, marginTop: '2px' }}>
                  Policies, handbooks, rules
                </p>
              </div>
            </button>

            {/* Student Experience option */}
            <button
              type="button"
              id="source-experience"
              onClick={() => setSourceType('experience')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 14px',
                borderRadius: '10px',
                border: sourceType === 'experience'
                  ? '2px solid #fb923c'
                  : '1px solid #1f2330',
                background: sourceType === 'experience'
                  ? 'rgba(251, 146, 60, 0.1)'
                  : 'rgba(255,255,255,0.02)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <GraduationCap
                size={16}
                style={{ color: sourceType === 'experience' ? '#fb923c' : '#475569', flexShrink: 0 }}
              />
              <div style={{ textAlign: 'left' }}>
                <p style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  color: sourceType === 'experience' ? '#fb923c' : '#94a3b8',
                  lineHeight: 1.2,
                }}>
                  Student Experience
                </p>
                <p style={{ fontSize: '10px', color: '#475569', lineHeight: 1.3, marginTop: '2px' }}>
                  Personal insights, tips
                </p>
              </div>
            </button>
          </div>
        </div>

        {/* Author — only shown for Student Experience */}
        {sourceType === 'experience' && (
          <div>
            <label className="form-label" htmlFor="doc-author">
              Author <span style={{ color: '#475569' }}>(optional)</span>
            </label>
            <input
              id="doc-author"
              type="text"
              className="form-input"
              placeholder="e.g. Divyansh Rathore"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              maxLength={255}
            />
          </div>
        )}

        {/* Category */}
        <div>
          <label className="form-label" htmlFor="doc-category">Category</label>
          <select
            id="doc-category"
            className="form-select"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {DOCUMENT_CATEGORIES.map((cat) => (
              <option key={cat} value={cat}>
                {cat.charAt(0).toUpperCase() + cat.slice(1)}
              </option>
            ))}
          </select>
        </div>

        {/* Description */}
        <div>
          <label className="form-label" htmlFor="doc-description">
            Description <span style={{ color: '#475569' }}>(optional)</span>
          </label>
          <input
            id="doc-description"
            type="text"
            className="form-input"
            placeholder="e.g. Academic Handbook 2024-25"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        {/* Submit */}
        <button
          type="submit"
          id="upload-submit-btn"
          className="btn btn-primary w-full justify-center py-3"
          disabled={!file || isUploading}
        >
          {isUploading ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              Uploading &amp; Indexing…
            </>
          ) : (
            <>
              <Upload size={16} />
              Upload &amp; Index Document
            </>
          )}
        </button>
      </form>
    </div>
  );
};
