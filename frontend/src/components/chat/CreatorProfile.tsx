import React, { useState } from 'react';
import {
  Github,
  Linkedin,
  Instagram,
  Mail,
  ExternalLink,
  X,
  MessageSquare,
  Send,
  Sparkles,
  ChevronDown,
  ChevronUp,
  GraduationCap
} from 'lucide-react';
import { chatApi } from '../../api/chat';
import toast from 'react-hot-toast';

interface CreatorProfileProps {
  view: 'sidebar' | 'mobile';
}

export const CreatorProfile: React.FC<CreatorProfileProps> = ({ view }) => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState<'story' | 'why' | 'roadmap' | 'feedback'>('story');

  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const openModalAtTab = (tab: 'story' | 'why' | 'roadmap' | 'feedback') => {
    setActiveTab(tab);
    setIsModalOpen(true);
  };

  const handleFeedbackSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!comment.trim()) return;

    setSubmitting(true);
    try {
      await chatApi.submitFeedback(null, 'not_helpful', comment.trim());
      toast.success('Thank you! Your feedback has been logged.');
      setComment('');
      // Optionally stay on tab but show success toast
    } catch (err) {
      console.error(err);
      toast.error('Failed to submit feedback. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const creatorAvatar = '/creator_avatar.jpeg';

  if (view === 'mobile') {
    return (
      <>
        {/* Mobile Banner */}
        <div className={`mobile-creator-banner md:hidden ${isCollapsed ? 'collapsed' : ''}`}>
          <div className="banner-header">
            <div className="banner-creator-info" onClick={() => openModalAtTab('story')}>
              <img
                src={creatorAvatar}
                alt="Divyansh Rathore"
                className="banner-avatar"
                onError={(e) => {
                  (e.target as HTMLImageElement).src = 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=80&h=80&q=80';
                }}
              />
              <div>
                <p className="banner-name">Divyansh Rathore <span className="banner-badge">Creator</span></p>
                <p className="banner-subtitle">B.Tech CS & Data Science, Rishihood</p>
              </div>
            </div>
            
            <div className="banner-actions">
              <button 
                onClick={() => openModalAtTab('story')} 
                className="banner-meet-btn text-xs font-semibold"
              >
                Meet Creator
              </button>
              <button
                className="banner-toggle"
                onClick={() => setIsCollapsed(!isCollapsed)}
                aria-label={isCollapsed ? "Expand banner" : "Collapse banner"}
              >
                {isCollapsed ? <ChevronDown size={18} /> : <ChevronUp size={18} />}
              </button>
            </div>
          </div>

          {!isCollapsed && (
            <div className="banner-content">
              <p className="banner-welcome">
                "Hey juniors! I'm Divyansh, call me Debug. Ask CampusGPT anything about academics, hostel life, sports, clubs, placements, or campus life, I'm here to help."
              </p>
              <div className="banner-footer-row">
                <span className="banner-feedback-cta">
                  Suggestions?{' '}
                  <button onClick={() => openModalAtTab('feedback')} className="underline-link">
                    Let me know
                  </button>
                </span>
                <div className="banner-socials">
                  <a href="https://www.linkedin.com/in/divyansh-rathore-ba8b0a271/" target="_blank" rel="noopener noreferrer" aria-label="LinkedIn">
                    <Linkedin size={14} />
                  </a>
                  <a href="https://github.com/111-DEBUG-111" target="_blank" rel="noopener noreferrer" aria-label="GitHub">
                    <Github size={14} />
                  </a>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal render */}
        {isModalOpen && renderModal()}
      </>
    );
  }

  // Desktop Sidebar Card
  return (
    <>
      <div className="sidebar-creator-card" onClick={() => openModalAtTab('story')}>
        <div className="sidebar-creator-header">
          <img
            src={creatorAvatar}
            alt="Divyansh Rathore"
            className="sidebar-creator-avatar"
            onError={(e) => {
              (e.target as HTMLImageElement).src = 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=80&h=80&q=80';
            }}
          />
          <div className="sidebar-creator-meta">
            <p className="sidebar-creator-name">Divyansh Rathore</p>
            <p className="sidebar-creator-role">Creator of CampusGPT</p>
            <p className="sidebar-creator-edu">B.Tech CS & Data Science, RU</p>
          </div>
        </div>

        <p className="sidebar-creator-welcome">
          "Hey juniors! I'm Divyansh, call me Debug. Ask CampusGPT anything about academics, hostel life, sports, clubs, placements..."
        </p>

        <div className="sidebar-creator-footer" onClick={(e) => e.stopPropagation()}>
          <button onClick={() => openModalAtTab('feedback')} className="sidebar-creator-feedback">
            Suggestions? <span className="underline-link">Let me know</span>
          </button>
          
          <div className="sidebar-creator-links">
            <a href="https://www.linkedin.com/in/divyansh-rathore-ba8b0a271/" target="_blank" rel="noopener noreferrer" title="LinkedIn">
              <Linkedin size={14} />
            </a>
            <a href="https://github.com/111-DEBUG-111" target="_blank" rel="noopener noreferrer" title="GitHub">
              <Github size={14} />
            </a>
          </div>
        </div>
      </div>

      {/* Modal render */}
      {isModalOpen && renderModal()}
    </>
  );

  function renderModal() {
    return (
      <div className="creator-modal-overlay" onClick={() => setIsModalOpen(false)}>
        <div className="creator-modal-container" onClick={(e) => e.stopPropagation()}>
          {/* Close button */}
          <button
            className="creator-modal-close"
            onClick={() => setIsModalOpen(false)}
            aria-label="Close modal"
          >
            <X size={18} />
          </button>

          {/* Modal Header */}
          <div className="creator-modal-header">
            <img
              src={creatorAvatar}
              alt="Divyansh Rathore"
              className="modal-creator-avatar"
              onError={(e) => {
                (e.target as HTMLImageElement).src = 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=120&h=120&q=80';
              }}
            />
            <div className="modal-creator-details">
              <div className="flex items-center gap-2">
                <h2 className="modal-creator-name text-2xl font-bold">Divyansh Rathore</h2>
                <span className="modal-badge-glow">Debug</span>
              </div>
              <p className="modal-creator-role text-indigo-400 font-medium">Creator of CampusGPT</p>
              <p className="modal-creator-edu text-sm text-slate-400">B.Tech CS & Data Science, Rishihood University</p>
            </div>
          </div>

          {/* Modal Tabs */}
          <div className="creator-modal-tabs">
            <button
              className={`creator-modal-tab ${activeTab === 'story' ? 'active' : ''}`}
              onClick={() => setActiveTab('story')}
            >
              My Story
            </button>
            <button
              className={`creator-modal-tab ${activeTab === 'why' ? 'active' : ''}`}
              onClick={() => setActiveTab('why')}
            >
              Why I Built It
            </button>
            <button
              className={`creator-modal-tab ${activeTab === 'roadmap' ? 'active' : ''}`}
              onClick={() => setActiveTab('roadmap')}
            >
              Roadmap
            </button>
            <button
              className={`creator-modal-tab ${activeTab === 'feedback' ? 'active' : ''}`}
              onClick={() => setActiveTab('feedback')}
            >
              Feedback & Contact
            </button>
          </div>

          {/* Modal Body Content */}
          <div className="creator-modal-body">
            {activeTab === 'story' && (
              <div className="modal-tab-content animate-fade-in text-slate-300 leading-relaxed text-sm space-y-4">
                <p>
                  Hi, I'm Divyansh, though there's a good chance you'll hear people call me <strong>Debug</strong>.
                </p>
                <p>
                  I spend most of my time doing three things: <strong>learning, building, and teaching</strong>. I've been teaching since I was young. I'm fascinated by technology and AI, I enjoy public speaking, sports, philosophy, and understanding how the world works.
                </p>
                <div className="story-highlights-grid grid grid-cols-2 gap-3 mt-4 pt-4 border-t border-slate-800/60">
                  <div className="highlight-item p-3 rounded-xl bg-slate-900/40 border border-slate-800/40">
                    <span className="text-xl block mb-1">🎙️</span>
                    <strong className="text-white text-xs block">Public Speaking</strong>
                    <span className="text-slate-400 text-xs">Passion for sharing ideas & leading discussions.</span>
                  </div>
                  <div className="highlight-item p-3 rounded-xl bg-slate-900/40 border border-slate-800/40">
                    <span className="text-xl block mb-1">💻</span>
                    <strong className="text-white text-xs block">Technology & AI</strong>
                    <span className="text-slate-400 text-xs">Deep-diving into coding, RAG, and AI agent frameworks.</span>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'why' && (
              <div className="modal-tab-content animate-fade-in text-slate-300 leading-relaxed text-sm space-y-4 max-h-[300px] overflow-y-auto pr-1">
                <p>One day, I realized I was doing the same job as a chatbot.</p>
                <p>
                  As the President of the Public Policy Club and a student at Rishihood University, I regularly received messages from prospective students:
                </p>
                <blockquote className="border-l-2 border-indigo-500 bg-indigo-500/5 p-3 rounded-r-xl text-slate-400 text-xs space-y-1 italic my-3">
                  <p>• "How are the placements?"</p>
                  <p>• "How is campus life?"</p>
                  <p>• "How difficult is the admission process?"</p>
                  <p>• "What is Newton School of Technology actually like?"</p>
                </blockquote>
                <p>
                  The problem was that the information was scattered across websites, PDFs, brochures, videos, WhatsApp chats, and personal experiences. So I decided to build a solution.
                </p>
                <p>
                  Over the last few weeks, I built an AI-powered university assistant that allows students to ask questions in natural language and receive answers grounded in university information.
                </p>
                <p>
                  But the interesting part wasn't building the chatbot. The interesting part was discovering how often AI gets things wrong. I went down the rabbit hole of:
                </p>
                <ul className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-400 list-inside list-disc text-xs bg-slate-900/35 p-3 rounded-xl border border-slate-800/40 my-3">
                  <li>Retrieval-Augmented Generation</li>
                  <li>Vector databases</li>
                  <li>Embeddings & Hybrid search</li>
                  <li>Reranking & Caching</li>
                  <li>Hallucination reduction</li>
                </ul>
                <p>
                  What started as a simple idea turned into one of the most challenging engineering projects I've worked on.
                </p>
              </div>
            )}

            {activeTab === 'roadmap' && (
              <div className="modal-tab-content animate-fade-in text-slate-300 leading-relaxed text-sm space-y-4">
                <p className="font-semibold text-white text-base">🚀 What's next for CampusGPT?</p>
                <p className="text-slate-400 text-xs">Here are the features I'm actively working on to take this project forward:</p>
                <div className="space-y-3 mt-2">
                  <div className="roadmap-step flex items-start gap-3">
                    <span className="roadmap-icon flex-shrink-0 w-6 h-6 rounded-full bg-indigo-500/10 text-indigo-400 text-xs flex items-center justify-center font-bold">1</span>
                    <div>
                      <strong className="text-white text-sm block">More University Documents</strong>
                      <span className="text-slate-400 text-xs">Ingesting deeper academics, course curriculum, and events details.</span>
                    </div>
                  </div>
                  <div className="roadmap-step flex items-start gap-3">
                    <span className="roadmap-icon flex-shrink-0 w-6 h-6 rounded-full bg-indigo-500/10 text-indigo-400 text-xs flex items-center justify-center font-bold">2</span>
                    <div>
                      <strong className="text-white text-sm block">Better Retrieval Quality</strong>
                      <span className="text-slate-400 text-xs">Improving chunking, reranking parameters, and query expansion.</span>
                    </div>
                  </div>
                  <div className="roadmap-step flex items-start gap-3">
                    <span className="roadmap-icon flex-shrink-0 w-6 h-6 rounded-full bg-indigo-500/10 text-indigo-400 text-xs flex items-center justify-center font-bold">3</span>
                    <div>
                      <strong className="text-white text-sm block">Student Feedback System</strong>
                      <span className="text-slate-400 text-xs">Allowing users to flag incorrect answers or add missing context.</span>
                    </div>
                  </div>
                  <div className="roadmap-step flex items-start gap-3">
                    <span className="roadmap-icon flex-shrink-0 w-6 h-6 rounded-full bg-indigo-500/10 text-indigo-400 text-xs flex items-center justify-center font-bold">4</span>
                    <div>
                      <strong className="text-white text-sm block">Multi-University Support</strong>
                      <span className="text-slate-400 text-xs">Expanding the RAG infrastructure to host databases for other campuses.</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'feedback' && (
              <div className="modal-tab-content animate-fade-in space-y-4">
                <div className="bg-indigo-500/5 border border-indigo-500/10 p-3.5 rounded-xl">
                  <p className="text-indigo-300 font-semibold text-sm flex items-center gap-1.5 mb-1">
                    <Sparkles size={16} /> Have suggestions or found an issue?
                  </p>
                  <p className="text-slate-400 text-xs">
                    Please submit your suggestions, questions, or bug reports here. They will be logged directly into the admin dashboard so I can review them and improve the knowledge base.
                  </p>
                </div>

                {/* Feedback Textbox Form */}
                <form onSubmit={handleFeedbackSubmit} className="space-y-3">
                  <textarea
                    className="w-full h-24 rounded-xl p-3 bg-slate-900 border border-slate-800 text-slate-200 placeholder-slate-500 text-xs focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 resize-none transition-colors"
                    placeholder="Type your suggestions, issues or feature requests here..."
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    disabled={submitting}
                  />
                  <div className="flex justify-end">
                    <button
                      type="submit"
                      className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-colors"
                      disabled={submitting || !comment.trim()}
                    >
                      {submitting ? 'Submitting...' : 'Submit Feedback'}
                      <Send size={12} />
                    </button>
                  </div>
                </form>

                {/* Socials & Contact section */}
                <div className="pt-3 border-t border-slate-800/60">
                  <p className="text-slate-400 text-xs font-medium mb-3">Connect with me:</p>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <a
                      href="https://www.linkedin.com/in/divyansh-rathore-ba8b0a271/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 p-2 rounded-xl bg-slate-900/60 border border-slate-800/40 text-slate-300 hover:text-white hover:border-slate-700 hover:bg-slate-900 transition-all text-xs"
                    >
                      <Linkedin size={14} className="text-indigo-400" />
                      <span>LinkedIn</span>
                    </a>
                    <a
                      href="https://github.com/111-DEBUG-111"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 p-2 rounded-xl bg-slate-900/60 border border-slate-800/40 text-slate-300 hover:text-white hover:border-slate-700 hover:bg-slate-900 transition-all text-xs"
                    >
                      <Github size={14} className="text-slate-200" />
                      <span>GitHub</span>
                    </a>
                    <a
                      href="https://www.instagram.com/debugrathore/?hl=en"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 p-2 rounded-xl bg-slate-900/60 border border-slate-800/40 text-slate-300 hover:text-white hover:border-slate-700 hover:bg-slate-900 transition-all text-xs"
                    >
                      <Instagram size={14} className="text-pink-400" />
                      <span>Instagram</span>
                    </a>
                    <a
                      href="mailto:divyansh.rathore@rishihood.edu.in"
                      className="flex items-center gap-2 p-2 rounded-xl bg-slate-900/60 border border-slate-800/40 text-slate-300 hover:text-white hover:border-slate-700 hover:bg-slate-900 transition-all text-xs"
                    >
                      <Mail size={14} className="text-teal-400" />
                      <span>Email</span>
                    </a>
                  </div>
                  
                  {/* Optional Portfolio */}
                  <div className="mt-3 text-center">
                    <a
                      href="https://dva-portfolio-blush.vercel.app/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                    >
                      Visit My Portfolio <ExternalLink size={12} />
                    </a>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }
};
