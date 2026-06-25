import React from 'react';
import type { KnowledgeMode } from '../../types';
import { useChatStore } from '../../stores/chatStore';

interface ModeOption {
  value: KnowledgeMode;
  label: string;
  icon: string;
  tooltip: string;
  activeColor: string;
  activeGradient: string;
}

const MODES: ModeOption[] = [
  {
    value: 'hybrid',
    label: 'Hybrid',
    icon: '🔀',
    tooltip: 'Draw from both official documents and student experiences',
    activeColor: '#818cf8',
    activeGradient: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
  },
  {
    value: 'official',
    label: 'Official',
    icon: '📄',
    tooltip: 'Only official university documents — policies, handbooks, regulations',
    activeColor: '#38bdf8',
    activeGradient: 'linear-gradient(135deg, #0ea5e9, #2563eb)',
  },
  {
    value: 'experience',
    label: 'Student',
    icon: '🎓',
    tooltip: 'Only student experiences and personal insights',
    activeColor: '#fb923c',
    activeGradient: 'linear-gradient(135deg, #f97316, #dc2626)',
  },
];

export const KnowledgeModeSelector: React.FC = () => {
  const { knowledgeMode, setKnowledgeMode } = useChatStore();

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
        background: 'rgba(255,255,255,0.04)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '12px',
        padding: '3px',
      }}
      role="group"
      aria-label="Knowledge source mode"
    >
      {MODES.map((mode) => {
        const isActive = knowledgeMode === mode.value;
        return (
          <button
            key={mode.value}
            id={`knowledge-mode-${mode.value}`}
            title={mode.tooltip}
            aria-pressed={isActive}
            onClick={() => setKnowledgeMode(mode.value)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              padding: '4px 10px',
              borderRadius: '9px',
              border: 'none',
              cursor: 'pointer',
              fontSize: '11px',
              fontWeight: isActive ? 600 : 400,
              letterSpacing: '0.01em',
              transition: 'all 0.18s ease',
              background: isActive ? mode.activeGradient : 'transparent',
              color: isActive ? '#fff' : '#64748b',
              boxShadow: isActive
                ? `0 2px 8px ${mode.activeColor}40`
                : 'none',
              transform: isActive ? 'scale(1.02)' : 'scale(1)',
            }}
          >
            <span style={{ fontSize: '12px', lineHeight: 1 }}>{mode.icon}</span>
            <span className="hidden sm:inline">{mode.label}</span>
          </button>
        );
      })}
    </div>
  );
};
