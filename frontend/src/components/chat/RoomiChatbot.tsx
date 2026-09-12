import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Send,
  X,
  RotateCcw,
  Sparkles,
  ExternalLink,
  RefreshCw,
  ChevronDown,
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { roomiService, type ChatMessage, type RoomiNavigationHint } from '../../services/roomiService';

interface ExtendedMessage extends ChatMessage {
  id: string;
  isError?: boolean;
  navigation?: RoomiNavigationHint;
  sources?: Array<{ label: string; snippet?: string }>;
}

const DEFAULT_SUGGESTIONS = [
  'How does Rooman Billing work?',
  'How do I create an invoice?',
  'Explain subscriptions',
  'How does proration work?',
  'How can I collect payments?',
  'Where can I find reports?',
];

const INITIAL_GREETING = `Hi! I'm Roomi 👋
I can help you understand Rooman Billing, find features, explain billing concepts, and guide you through the platform.

What would you like to know?`;

export function RoomiChatbot() {
  const { organization, membership } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [messages, setMessages] = useState<ExtendedMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [suggestions, setSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS);
  const [lastFailedPrompt, setLastFailedPrompt] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Initialize with greeting if empty
  useEffect(() => {
    if (messages.length === 0) {
      const welcome: ExtendedMessage = {
        id: 'msg-welcome',
        role: 'assistant',
        content: INITIAL_GREETING,
        timestamp: new Date().toISOString(),
      };
      setMessages([welcome]);
    }
  }, [messages.length]);

  // Auto-scroll to bottom on message update
  useEffect(() => {
    if (isOpen && !isMinimized) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isLoading, isOpen, isMinimized]);

  // Auto-focus input when opened
  useEffect(() => {
    if (isOpen && !isMinimized) {
      setTimeout(() => {
        inputRef.current?.focus();
      }, 150);
    }
  }, [isOpen, isMinimized]);

  const handleSend = async (textToSend?: string) => {
    const prompt = (textToSend || input).trim();
    if (!prompt || isLoading) return;

    setInput('');
    setLastFailedPrompt(null);

    const userMsg: ExtendedMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: prompt,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const historyContext: ChatMessage[] = messages
        .filter((m) => !m.isError && m.id !== 'msg-welcome')
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content }));

      const response = await roomiService.sendMessage({
        message: prompt,
        conversation_id: conversationId,
        current_route: location.pathname,
        history: historyContext,
      });

      setConversationId(response.conversation_id);

      const assistantMsg: ExtendedMessage = {
        id: `roomi-${Date.now()}`,
        role: 'assistant',
        content: response.reply,
        timestamp: new Date().toISOString(),
        navigation: response.navigation,
        sources: response.sources,
      };

      setMessages((prev) => [...prev, assistantMsg]);
      if (response.suggested_chips && response.suggested_chips.length > 0) {
        setSuggestions(response.suggested_chips);
      }
    } catch {
      setLastFailedPrompt(prompt);
      const errorMsg: ExtendedMessage = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: "Sorry, I couldn't connect right now. Please try again in a moment.",
        timestamp: new Date().toISOString(),
        isError: true,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClear = () => {
    setConversationId(undefined);
    setSuggestions(DEFAULT_SUGGESTIONS);
    setLastFailedPrompt(null);
    setMessages([
      {
        id: `welcome-${Date.now()}`,
        role: 'assistant',
        content: INITIAL_GREETING,
        timestamp: new Date().toISOString(),
      },
    ]);
  };

  const renderContent = (content: string) => {
    // Format markdown bold (**text**) and code (`text`) and line breaks
    const lines = content.split('\n');
    return lines.map((line, lIdx) => {
      // Bullet list item
      const isBullet = line.trim().startsWith('•') || line.trim().startsWith('-');
      const cleanLine = isBullet ? line.trim().replace(/^[•-]\s*/, '') : line;

      const formattedParts = cleanLine.split(/(\*\*.*?\*\*|`.*?`)/g).map((part, pIdx) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return (
            <strong key={pIdx} className="font-semibold text-slate-900">
              {part.slice(2, -2)}
            </strong>
          );
        }
        if (part.startsWith('`') && part.endsWith('`')) {
          return (
            <code key={pIdx} className="px-1.5 py-0.5 rounded text-xs font-mono bg-purple-50 text-purple-700 border border-purple-100">
              {part.slice(1, -1)}
            </code>
          );
        }
        return part;
      });

      return (
        <React.Fragment key={lIdx}>
          {isBullet ? (
            <div className="flex items-start gap-2 my-1">
              <span className="text-purple-500 font-bold leading-none mt-1.5">•</span>
              <span className="flex-1">{formattedParts}</span>
            </div>
          ) : (
            <p className={lIdx > 0 && lines[lIdx - 1] === '' ? 'mt-2' : 'min-h-[1rem]'}>{formattedParts}</p>
          )}
        </React.Fragment>
      );
    });
  };

  return (
    <aside aria-label="Roomi AI Assistant" className="fixed bottom-5 right-5 z-50 select-none font-sans">
      {/* Floating Closed Launcher Button */}
      {!isOpen && (
        <div className="relative group">
          {/* Subtle Hover Tooltip */}
          <div
            className="absolute -top-10 right-1/2 translate-x-1/2 opacity-0 group-hover:opacity-100 transition-all duration-200 pointer-events-none whitespace-nowrap bg-slate-900/90 backdrop-blur-sm text-white text-xs font-medium px-3 py-1 rounded-full shadow-lg border border-slate-700/50 flex items-center gap-1.5"
            role="tooltip"
          >
            <Sparkles className="w-3 h-3 text-purple-300" />
            <span>Ask Roomi</span>
          </div>

          {/* Trigger Button cleanly fixed in place */}
          <button
            onClick={() => setIsOpen(true)}
            aria-label="Open Roomi AI Assistant"
            className="relative flex items-center justify-center w-14 h-14 rounded-full overflow-hidden bg-slate-900 shadow-xl ring-2 ring-purple-500/40 hover:ring-purple-500/80 hover:shadow-2xl hover:scale-105 active:scale-95 transition-all duration-200 focus:outline-none focus:ring-4 focus:ring-purple-400/50"
            style={{
              boxShadow: '0 8px 24px 0 rgba(124, 58, 237, 0.25), 0 2px 6px 0 rgba(0, 0, 0, 0.1)',
            }}
          >
            {/* Roomi Official Mascot Image - Perfect Round Shape */}
            <img
              src="/logos/roomi.png"
              alt="Roomi AI Mascot"
              className="w-full h-full rounded-full object-cover"
            />

            {/* Ready Status Dot */}
            <span className="absolute bottom-1 right-1 w-3.5 h-3.5 bg-emerald-500 border-2 border-white rounded-full z-20 shadow-sm" />
          </button>
        </div>
      )}

      {/* Modern Expandable Chat Window */}
      {isOpen && (
        <div
          className={`bg-white/95 backdrop-blur-xl rounded-2xl shadow-2xl border border-slate-200/80 flex flex-col transition-all duration-300 overflow-hidden ${
            isMinimized
              ? 'w-72 sm:w-80 h-14'
              : 'w-[calc(100vw-2.5rem)] sm:w-[410px] h-[580px] max-h-[calc(100vh-6rem)]'
          }`}
          style={{
            boxShadow: '0 20px 45px -10px rgba(79, 70, 229, 0.2), 0 8px 24px -5px rgba(0, 0, 0, 0.08)',
          }}
        >
          {/* Header */}
          <div className="px-4 py-3 bg-gradient-to-r from-slate-900 via-indigo-950 to-purple-950 text-white flex items-center justify-between shadow-sm shrink-0 border-b border-white/10">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="relative shrink-0">
                <img
                  src="/logos/roomi.png"
                  alt="Roomi"
                  className="w-8 h-8 rounded-full object-cover border border-white/20 shadow-sm"
                />
                <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 bg-emerald-400 border-2 border-slate-900 rounded-full" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="font-semibold text-sm tracking-tight text-white">Roomi</span>
                  <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.2 bg-purple-500/30 text-purple-200 rounded border border-purple-400/20">
                    AI
                  </span>
                </div>
                {!isMinimized && (
                  <p className="text-[11px] text-purple-200/80 truncate">
                    {organization?.name ? `${organization.name} · Assistant` : 'Your Rooman Billing Assistant'}
                  </p>
                )}
              </div>
            </div>

            <div className="flex items-center gap-1">
              {!isMinimized && (
                <button
                  onClick={handleClear}
                  title="Clear conversation"
                  aria-label="Clear conversation"
                  className="p-1.5 rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              )}
              <button
                onClick={() => setIsMinimized((prev) => !prev)}
                title={isMinimized ? 'Expand' : 'Minimize'}
                aria-label={isMinimized ? 'Expand' : 'Minimize'}
                className="p-1.5 rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
              >
                <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${isMinimized ? 'rotate-180' : ''}`} />
              </button>
              <button
                onClick={() => {
                  setIsOpen(false);
                  setIsMinimized(false);
                }}
                title="Close Roomi"
                aria-label="Close Roomi"
                className="p-1.5 rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Chat Body (Hidden when minimized) */}
          {!isMinimized && (
            <>
              <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs sm:text-sm bg-gradient-to-b from-slate-50/50 to-white">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex items-start gap-2.5 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
                  >
                    {/* Assistant Avatar */}
                    {msg.role === 'assistant' && (
                      <div className="w-7 h-7 rounded-full shrink-0 shadow-xs overflow-hidden border border-purple-200">
                        <img src="/logos/roomi.png" alt="Roomi" className="w-full h-full rounded-full object-cover" />
                      </div>
                    )}

                    {/* Message Bubble */}
                    <div className="max-w-[84%] flex flex-col space-y-1">
                      <div
                        className={`px-3.5 py-2.5 rounded-2xl text-slate-800 leading-relaxed shadow-xs ${
                          msg.role === 'user'
                            ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-tr-xs'
                            : msg.isError
                            ? 'bg-rose-50 text-rose-800 border border-rose-200 rounded-tl-xs'
                            : 'bg-white text-slate-800 border border-slate-200/80 rounded-tl-xs'
                        }`}
                      >
                        {msg.role === 'user' ? (
                          <p className="whitespace-pre-wrap">{msg.content}</p>
                        ) : (
                          <div className="space-y-1">{renderContent(msg.content)}</div>
                        )}
                      </div>

                      {/* Navigation Action Hint */}
                      {msg.navigation && (
                        <div className="pt-1">
                          <button
                            onClick={() => {
                              navigate(msg.navigation!.route);
                            }}
                            className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-indigo-50 text-indigo-700 hover:bg-indigo-100 hover:text-indigo-800 border border-indigo-200 transition-colors shadow-2xs"
                          >
                            <span>Open {msg.navigation.label}</span>
                            <ExternalLink className="w-3 h-3" />
                          </button>
                        </div>
                      )}

                      {/* Retry Action for Error State */}
                      {msg.isError && lastFailedPrompt && (
                        <div className="pt-0.5">
                          <button
                            onClick={() => handleSend(lastFailedPrompt)}
                            className="inline-flex items-center gap-1 text-xs font-medium text-rose-600 hover:text-rose-700"
                          >
                            <RefreshCw className="w-3 h-3" />
                            <span>Retry</span>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {/* Loading / Typing Indicator */}
                {isLoading && (
                  <div className="flex items-start gap-2.5">
                    <div className="w-7 h-7 rounded-full shrink-0 shadow-xs overflow-hidden border border-purple-200">
                      <img src="/logos/roomi.png" alt="Roomi" className="w-full h-full rounded-full object-cover" />
                    </div>
                    <div className="px-3.5 py-2.5 rounded-2xl rounded-tl-xs bg-white border border-slate-200/80 shadow-xs flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-purple-600 animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-2 h-2 rounded-full bg-indigo-600 animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-2 h-2 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '300ms' }} />
                      <span className="text-xs text-slate-400 ml-1 font-medium">Roomi is thinking...</span>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Quick Suggestion Chips */}
              {suggestions.length > 0 && !isLoading && (
                <div className="px-3 py-2 bg-slate-50/80 border-t border-slate-100 overflow-x-auto shrink-0 flex items-center gap-1.5 scrollbar-none">
                  {suggestions.map((s, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(s)}
                      className="whitespace-nowrap px-2.5 py-1 rounded-full text-[11px] font-medium bg-white text-slate-700 hover:text-purple-700 hover:bg-purple-50 border border-slate-200 transition-colors shadow-2xs shrink-0"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}

              {/* Input Area */}
              <div className="p-3 bg-white border-t border-slate-200/80 shrink-0">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleSend();
                  }}
                  className="flex items-end gap-2"
                >
                  <div className="relative flex-1">
                    <textarea
                      ref={inputRef}
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Ask Roomi about billing, invoices, subscriptions..."
                      disabled={isLoading}
                      rows={1}
                      className="w-full resize-none rounded-xl border border-slate-300 px-3 py-2 text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 focus:border-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-500/20 disabled:bg-slate-50 disabled:opacity-60 max-h-24 overflow-y-auto"
                      style={{ minHeight: '38px' }}
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={!input.trim() || isLoading}
                    aria-label="Send message"
                    className="flex h-[38px] w-[38px] items-center justify-center rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 text-white shadow-xs hover:from-purple-700 hover:to-indigo-700 disabled:opacity-40 disabled:pointer-events-none transition-all duration-150 shrink-0"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </form>
                <div className="flex items-center justify-between text-[10px] text-slate-400 mt-1.5 px-1">
                  <span>Shift + Enter for new line</span>
                  <span>Internal Assistant · Role: {membership?.role ? membership.role.toUpperCase() : 'Authenticated'}</span>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </aside>
  );
}
