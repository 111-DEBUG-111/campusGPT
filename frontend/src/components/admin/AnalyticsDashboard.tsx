import React from 'react';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts';
import {
  MessageSquare, BookOpen, FileText, ThumbsUp,
  ThumbsDown, Clock, TrendingUp, Hash
} from 'lucide-react';
import type { AnalyticsSummary } from '../../types';

interface Props {
  analytics: AnalyticsSummary;
}

const CHART_COLORS = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#ec4899'];

const StatCard: React.FC<{
  icon: React.ReactNode;
  label: string;
  value: string | number;
  iconBg: string;
  iconColor: string;
}> = ({ icon, label, value, iconBg, iconColor }) => (
  <div className="stat-card">
    <div className="stat-icon" style={{ background: iconBg }}>
      <span style={{ color: iconColor }}>{icon}</span>
    </div>
    <p className="stat-value">{value}</p>
    <p className="stat-label">{label}</p>
  </div>
);

const CustomTooltip: React.FC<any> = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="px-3 py-2 rounded-xl text-sm"
      style={{ background: '#1a1d25', border: '1px solid #2a2d3a', color: '#f1f5f9' }}
    >
      <p style={{ color: '#94a3b8', marginBottom: '4px' }}>{label}</p>
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color }}>
          {p.name}: <strong>{p.value}</strong>
        </p>
      ))}
    </div>
  );
};

export const AnalyticsDashboard: React.FC<Props> = ({ analytics }) => {
  const feedbackTotal = analytics.helpful_count + analytics.not_helpful_count;
  const helpfulPct =
    feedbackTotal > 0 ? Math.round((analytics.helpful_count / feedbackTotal) * 100) : 0;

  const feedbackPieData = [
    { name: 'Helpful', value: analytics.helpful_count },
    { name: 'Not Helpful', value: analytics.not_helpful_count },
  ];

  return (
    <div className="space-y-6">
      {/* Stat Cards */}
      <div className="stats-grid">
        <StatCard
          icon={<MessageSquare size={20} />}
          label="Total Questions"
          value={analytics.total_questions.toLocaleString()}
          iconBg="rgba(99, 102, 241, 0.15)"
          iconColor="#6366f1"
        />
        <StatCard
          icon={<BookOpen size={20} />}
          label="Conversations"
          value={analytics.total_conversations.toLocaleString()}
          iconBg="rgba(6, 182, 212, 0.15)"
          iconColor="#06b6d4"
        />
        <StatCard
          icon={<FileText size={20} />}
          label="Documents"
          value={`${analytics.total_documents} (${analytics.total_chunks.toLocaleString()} chunks)`}
          iconBg="rgba(16, 185, 129, 0.15)"
          iconColor="#10b981"
        />
        <StatCard
          icon={<Clock size={20} />}
          label="Avg Response Time"
          value={`${analytics.avg_response_time_ms.toFixed(0)}ms`}
          iconBg="rgba(245, 158, 11, 0.15)"
          iconColor="#f59e0b"
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Questions per day */}
        <div
          className="lg:col-span-2 rounded-2xl p-5"
          style={{ background: '#111318', border: '1px solid #1f2330' }}
        >
          <h3 className="font-semibold mb-4 flex items-center gap-2" style={{ color: '#f1f5f9' }}>
            <TrendingUp size={16} style={{ color: '#6366f1' }} />
            Questions Per Day (Last 30 Days)
          </h3>
          {analytics.questions_by_day.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={analytics.questions_by_day}>
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fill: '#475569' }}
                  tickFormatter={(d) => d.slice(5)}
                />
                <YAxis tick={{ fontSize: 11, fill: '#475569' }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} name="Questions" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-48 flex items-center justify-center" style={{ color: '#2a2d3a' }}>
              No data yet
            </div>
          )}
        </div>

        {/* Feedback pie */}
        <div
          className="rounded-2xl p-5"
          style={{ background: '#111318', border: '1px solid #1f2330' }}
        >
          <h3 className="font-semibold mb-4 flex items-center gap-2" style={{ color: '#f1f5f9' }}>
            <ThumbsUp size={16} style={{ color: '#10b981' }} />
            Feedback Quality
          </h3>
          {feedbackTotal > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={140}>
                <PieChart>
                  <Pie
                    data={feedbackPieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={45}
                    outerRadius={65}
                    paddingAngle={4}
                    dataKey="value"
                  >
                    <Cell fill="#10b981" />
                    <Cell fill="#ef4444" />
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex justify-center gap-6 mt-2">
                <div className="text-center">
                  <p className="text-2xl font-bold" style={{ color: '#10b981' }}>{helpfulPct}%</p>
                  <p className="text-xs" style={{ color: '#475569' }}>Helpful</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold" style={{ color: '#ef4444' }}>{100 - helpfulPct}%</p>
                  <p className="text-xs" style={{ color: '#475569' }}>Not Helpful</p>
                </div>
              </div>
            </>
          ) : (
            <div className="h-48 flex items-center justify-center" style={{ color: '#2a2d3a' }}>
              No feedback yet
            </div>
          )}
        </div>
      </div>

      {/* Top queries */}
      {analytics.top_queries.length > 0 && (
        <div
          className="rounded-2xl p-5"
          style={{ background: '#111318', border: '1px solid #1f2330' }}
        >
          <h3 className="font-semibold mb-4 flex items-center gap-2" style={{ color: '#f1f5f9' }}>
            <Hash size={16} style={{ color: '#06b6d4' }} />
            Most Common Questions
          </h3>
          <div className="space-y-2">
            {analytics.top_queries.slice(0, 8).map((q, i) => (
              <div key={i} className="flex items-center gap-3">
                <span
                  className="text-xs font-mono font-bold w-5 text-right flex-shrink-0"
                  style={{ color: '#6366f1' }}
                >
                  {i + 1}.
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    {/*
                      * SECURITY: Render query text via JSX interpolation only.
                      * Do NOT switch to dangerouslySetInnerHTML here — top_queries
                      * data originates from user input and must never be rendered
                      * as raw HTML regardless of any backend sanitization in place.
                      */}
                    <span className="text-sm truncate" style={{ color: '#94a3b8' }}>
                      {q.query}
                    </span>
                    <span
                      className="text-xs ml-2 flex-shrink-0 font-mono"
                      style={{ color: '#475569' }}
                    >
                      ×{q.count}
                    </span>
                  </div>
                  <div
                    className="h-1.5 rounded-full"
                    style={{ background: '#1f2330' }}
                  >
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${(q.count / analytics.top_queries[0].count) * 100}%`,
                        background: `hsl(${240 - i * 20}, 70%, 65%)`,
                        transition: 'width 0.5s ease',
                      }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
