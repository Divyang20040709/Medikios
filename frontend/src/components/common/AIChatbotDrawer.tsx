'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  MessageSquare,
  Bot,
  Send,
  X,
  Sparkles,
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  RefreshCw,
  AlertTriangle,
  ChevronDown,
  User,
  Check,
  Copy
} from 'lucide-react';
import { useToast } from '@/components/common/Toast';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  alerts?: any[];
  engine?: string | null;
}

// QA BUG-006: translate the engine actually used by the backend into an honest
// provenance label. Never name a commercial model unless it produced the text.
function engineLabel(engine: string | null | undefined, model?: string | null): string {
  switch (engine) {
    case 'openrouter':
      return model ? `Live LLM \u00b7 ${model}` : 'Live LLM (OpenRouter)';
    case 'local':
      return 'Local on-device LLM';
    case 'deterministic_fallback':
      return 'Deterministic clinical fallback (no LLM configured)';
    default:
      return 'Clinical AI Assistant';
  }
}

interface AIChatbotDrawerProps {
  initialRole?: 'patient' | 'doctor' | 'general';
  initialLanguage?: string;
  sessionId?: string;
  encounterId?: string;
  patientName?: string;
  defaultOpen?: boolean;
}

export const AIChatbotDrawer: React.FC<AIChatbotDrawerProps> = ({
  initialRole = 'general',
  initialLanguage = 'en',
  sessionId,
  encounterId,
  patientName,
  defaultOpen = false,
}) => {
  const toast = useToast();
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const [role, setRole] = useState<'patient' | 'doctor' | 'general'>(initialRole);
  const [language, setLanguage] = useState<string>(initialLanguage);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [speechSynthesisEnabled, setSpeechSynthesisEnabled] = useState(false);
  const [prompts, setPrompts] = useState<any[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  // QA BUG-006: last engine reported by the backend, used for honest header/loading labels.
  const [engineState, setEngineState] = useState<string | null>(null);
  const [modelState, setModelState] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // QA BUG-009: de-duplicate /api/chat/prompts fetches (React StrictMode double-effect).
  const promptsFetchedKeyRef = useRef<string | null>(null);

  // Initial welcome message
  useEffect(() => {
    const welcome = role === 'doctor'
      ? `Hello Doctor. I am your MediKiosk Clinical AI Copilot. How can I assist with differential diagnosis, drug monographs, or clinical guidelines today?`
      : `Namaste! I am the MediKiosk AI Assistant. I can help guide your hospital visit, explain symptoms, or take your OPD clinical intake. What brings you in today?`;

    setMessages([
      {
        id: 'welcome-1',
        role: 'assistant',
        content: welcome,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);

    // Load suggested prompts (BUG-009: skip if this role/language was already fetched this session)
    const fetchKey = `${role}:${language}`;
    if (promptsFetchedKeyRef.current === fetchKey) return;
    promptsFetchedKeyRef.current = fetchKey;
    fetch(`/api/chat/prompts?role=${role}&language=${language}`)
      .then((res) => res.json())
      .then((data) => setPrompts(data))
      .catch(() => { promptsFetchedKeyRef.current = null; });
  }, [role, language]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [isOpen]);

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || inputMessage).trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      id: 'msg-' + Date.now(),
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInputMessage('');
    setLoading(true);

    try {
      const historyPayload = messages.slice(-5).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await fetch('/api/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          role: role,
          language: language,
          session_id: sessionId,
          encounter_id: encounterId,
          chat_history: historyPayload,
        }),
      });

      const data = await res.json();
      if (data.engine) {
        setEngineState(data.engine);
        setModelState(data.model || null);
      }
      const botMsg: ChatMessage = {
        id: 'bot-' + Date.now(),
        role: 'assistant',
        content: data.reply || 'Thank you. Your message has been noted.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        alerts: data.red_flags || [],
        engine: data.engine || null,
      };

      setMessages((prev) => [...prev, botMsg]);

      // Optional TTS speak
      if (speechSynthesisEnabled && typeof window !== 'undefined' && 'speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(botMsg.content);
        utterance.lang = language === 'hi' ? 'hi-IN' : (language === 'gu' ? 'gu-IN' : 'en-US');
        window.speechSynthesis.speak(utterance);
      }
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          id: 'err-' + Date.now(),
          role: 'assistant',
          content: 'MediKiosk Assistant: I am temporarily operating in offline mode. Your symptoms have been logged for the attending clinician.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  // Web Speech STT
  const toggleVoiceInput = () => {
    if (typeof window === 'undefined') return;
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      toast.warning('Voice input unavailable', { description: 'This browser does not support speech recognition — please type your message instead.' });
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.lang = language === 'hi' ? 'hi-IN' : (language === 'gu' ? 'gu-IN' : 'en-US');
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    recognition.onerror = () => setIsListening(false);
    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setInputMessage(transcript);
      handleSendMessage(transcript);
    };

    recognition.start();
  };

  const copyToClipboard = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const clearChat = () => {
    setMessages([
      {
        id: 'welcome-reset',
        role: 'assistant',
        content: role === 'doctor'
          ? 'Chat reset. How can I assist you with clinical inquiry?'
          : 'Chat reset. Please describe your symptoms or ask a question.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);
  };

  return (
    <>
      {/* FLOATING LAUNCHER BUTTON (Bottom-Right) */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          aria-label="Open MediKiosk AI Chatbot"
          className="fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3.5 rounded-full liquid-glass liquid-glass-hover border border-cyan-400/50 shadow-[0_0_25px_rgba(0,242,254,0.35)] text-white hover:scale-105 transition-all duration-300 group"
        >
          <div className="relative">
            <div className="h-9 w-9 rounded-full bg-gradient-to-tr from-cyan-500 to-teal-400 flex items-center justify-center text-slate-950 font-bold shadow-md">
              <Sparkles className="h-5 w-5" />
            </div>
            <span className="absolute -top-1 -right-1 flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-teal-500"></span>
            </span>
          </div>
          <div className="text-left">
            <span className="block text-xs font-semibold tracking-wide text-cyan-300 group-hover:text-cyan-200">
              MediKiosk AI Copilot
            </span>
            <span className="block text-[10px] text-white/60 font-light">
              {engineLabel(engineState, modelState)}
            </span>
          </div>
        </button>
      )}

      {/* CHATBOT DRAWER / MODAL */}
      {isOpen && (
        <div className="fixed bottom-4 right-4 sm:bottom-6 sm:right-6 z-50 w-[95vw] sm:w-[440px] h-[640px] max-h-[90vh] flex flex-col rounded-3xl liquid-glass border border-cyan-400/40 shadow-[0_10px_50px_rgba(0,0,0,0.8)] backdrop-blur-2xl overflow-hidden animate-in slide-in-from-bottom-5 duration-300">
          
          {/* DRAWER HEADER */}
          <div className="px-5 py-4 border-b border-white/10 bg-slate-950/60 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-2xl bg-cyan-500/20 border border-cyan-400/40 flex items-center justify-center text-cyan-300">
                <Bot className="h-5 w-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-medium text-white tracking-tight">MediKiosk AI Copilot</h3>
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                    Live
                  </span>
                </div>
                <span className="text-[11px] text-white/50 block">
                  {role === 'doctor' ? 'Physician Clinical Workspace' : 'Multilingual Patient Intake'}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-1.5">
              {/* Audio TTS toggle */}
              <button
                onClick={() => setSpeechSynthesisEnabled(!speechSynthesisEnabled)}
                title={speechSynthesisEnabled ? 'Mute AI Voice' : 'Enable AI Voice (TTS)'}
                className={`p-2 rounded-xl transition-colors ${
                  speechSynthesisEnabled ? 'text-teal-300 bg-teal-500/20' : 'text-white/40 hover:text-white'
                }`}
              >
                {speechSynthesisEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
              </button>

              {/* Clear chat */}
              <button
                onClick={clearChat}
                title="Reset Conversation"
                className="p-2 rounded-xl text-white/40 hover:text-white transition-colors"
              >
                <RefreshCw className="h-4 w-4" />
              </button>

              {/* Close Drawer */}
              <button
                onClick={() => setIsOpen(false)}
                title="Minimize Chatbot"
                className="p-2 rounded-xl text-white/60 hover:text-white hover:bg-white/10 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* CONTROLS BAR: ROLE & LANGUAGE */}
          <div className="px-5 py-2.5 bg-white/[0.02] border-b border-white/5 flex items-center justify-between text-xs">
            {/* Role switch */}
            <div className="flex items-center gap-1 bg-white/5 p-1 rounded-full">
              <button
                onClick={() => setRole('patient')}
                className={`px-3 py-1 rounded-full transition-all text-[11px] ${
                  role === 'patient' ? 'bg-cyan-500/30 text-cyan-200 font-medium' : 'text-white/50 hover:text-white'
                }`}
              >
                Patient
              </button>
              <button
                onClick={() => setRole('doctor')}
                className={`px-3 py-1 rounded-full transition-all text-[11px] ${
                  role === 'doctor' ? 'bg-indigo-500/30 text-indigo-200 font-medium' : 'text-white/50 hover:text-white'
                }`}
              >
                Doctor
              </button>
            </div>

            {/* Language picker */}
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              aria-label="Select Chat Language"
              className="bg-[#0b1322] border border-white/10 text-white/80 rounded-xl px-2.5 py-1 text-[11px] focus:outline-none focus:border-cyan-400"
            >
              <option value="en">English</option>
              <option value="hi">हिन्दी (Hindi)</option>
              <option value="gu">ગુજરાતી (Gujarati)</option>
            </select>
          </div>

          {/* MESSAGES SCROLL AREA */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3.5 text-sm custom-scrollbar bg-slate-950/20">
            {messages.map((msg) => {
              const isUser = msg.role === 'user';
              return (
                <div
                  key={msg.id}
                  className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} animate-in fade-in duration-200`}
                >
                  <div className="flex items-center gap-1.5 mb-1 px-1 text-[10px] text-white/40">
                    {isUser ? (
                      <>
                        <span>You</span>
                        <span>•</span>
                        <span>{msg.timestamp}</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-3 w-3 text-cyan-400" />
                        <span className="text-cyan-400 font-medium">MediKiosk AI</span>
                        <span>•</span>
                        <span>{msg.timestamp}</span>
                      </>
                    )}
                  </div>

                  <div
                    className={`relative group max-w-[85%] rounded-2xl px-4 py-3 text-xs sm:text-sm leading-relaxed ${
                      isUser
                        ? 'bg-gradient-to-r from-cyan-600 to-teal-600 text-white rounded-tr-sm shadow-md'
                        : 'bg-white/[0.06] border border-white/10 text-white/90 rounded-tl-sm backdrop-blur-sm'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{msg.content}</p>

                    {/* Copy Button */}
                    <button
                      onClick={() => copyToClipboard(msg.id, msg.content)}
                      title="Copy response"
                      className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 p-1 rounded-md bg-black/40 text-white/60 hover:text-white transition-opacity"
                    >
                      {copiedId === msg.id ? <Check className="h-3 w-3 text-teal-400" /> : <Copy className="h-3 w-3" />}
                    </button>
                  </div>

                  {/* Red-Flag Alerts triggered */}
                  {msg.alerts && msg.alerts.length > 0 && (
                    <div className="mt-1.5 p-2 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-200 text-[11px] flex items-center gap-2 max-w-[85%]">
                      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
                      <span><strong>Triage Priority Escalated:</strong> Clinician notified for urgent review.</span>
                    </div>
                  )}

                  {/* QA BUG-006: honest provenance for AI-generated replies */}
                  {!isUser && msg.engine && (
                    <div className="mt-1 text-[10px] text-white/40 font-light max-w-[85%] flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-white/30 inline-block" />
                      <span>Source: {engineLabel(msg.engine, msg.engine === 'openrouter' ? modelState : null)}</span>
                    </div>
                  )}
                </div>
              );
            })}

            {loading && (
              <div className="flex items-center gap-2 p-3 rounded-2xl bg-white/[0.04] border border-white/5 w-fit">
                <div className="flex gap-1">
                  <div className="h-2 w-2 rounded-full bg-cyan-400 animate-bounce"></div>
                  <div className="h-2 w-2 rounded-full bg-cyan-400 animate-bounce [animation-delay:0.2s]"></div>
                  <div className="h-2 w-2 rounded-full bg-cyan-400 animate-bounce [animation-delay:0.4s]"></div>
                </div>
                <span className="text-[11px] text-white/50 font-light ml-1">
                  Composing clinical response...
                </span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* QUICK PROMPT SUGGESTIONS */}
          {messages.length <= 2 && prompts.length > 0 && (
            <div className="px-4 py-2 bg-slate-950/40 border-t border-white/5 flex gap-1.5 overflow-x-auto no-scrollbar">
              {prompts.slice(0, 3).map((p) => (
                <button
                  key={p.id}
                  onClick={() => handleSendMessage(p.text)}
                  className="whitespace-nowrap px-3 py-1.5 rounded-full text-[10px] bg-white/5 hover:bg-cyan-500/20 text-white/70 hover:text-cyan-200 border border-white/10 hover:border-cyan-400/40 transition-all shrink-0"
                >
                  {p.text}
                </button>
              ))}
            </div>
          )}

          {/* INPUT FORM */}
          <div className="p-3 bg-slate-950/80 border-t border-white/10 flex items-center gap-2">
            {/* Speech to text */}
            <button
              type="button"
              onClick={toggleVoiceInput}
              title={isListening ? 'Stop Listening' : 'Speak Message'}
              className={`p-2.5 rounded-2xl transition-all ${
                isListening
                  ? 'bg-rose-500 text-white animate-pulse shadow-[0_0_15px_#f43f5e]'
                  : 'bg-white/5 text-cyan-300 hover:bg-cyan-500/20 border border-white/10'
              }`}
            >
              {isListening ? <Mic className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            </button>

            <input
              ref={inputRef}
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage();
                }
              }}
              placeholder={
                language === 'hi'
                  ? 'लक्षण बताएं या प्रश्न पूछें...'
                  : language === 'gu'
                  ? 'લક્ષણો જણાવો અથવા પ્રશ્ન પૂછો...'
                  : 'Describe symptoms or ask clinical questions...'
              }
              className="flex-1 px-4 py-2.5 rounded-2xl bg-white/[0.04] border border-white/10 text-white text-xs sm:text-sm placeholder:text-white/30 focus:border-cyan-400 focus:outline-none"
            />

            <button
              onClick={() => handleSendMessage()}
              disabled={!inputMessage.trim() || loading}
              className="p-2.5 rounded-2xl bg-gradient-to-r from-cyan-500 to-teal-500 text-slate-950 font-bold disabled:opacity-40 disabled:hover:scale-100 hover:scale-105 transition-all shadow-md"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );
};
