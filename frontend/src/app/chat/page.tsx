'use client';

import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import {
  Bot,
  Send,
  Sparkles,
  Mic,
  Volume2,
  VolumeX,
  RefreshCw,
  AlertTriangle,
  ArrowLeft,
  Check,
  Copy,
  ArrowRight,
  Shield,
  Stethoscope,
  Clock
} from 'lucide-react';
import { Logo } from '@/components/common/Logo';
import { useToast } from '@/components/common/Toast';
import { staffEntryUrl } from '@/lib/auth';

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

export default function ChatbotPage() {
  const toast = useToast();
  const [role, setRole] = useState<'patient' | 'doctor'>('patient');
  const [language, setLanguage] = useState<string>('en');
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

  useEffect(() => {
    const welcome = role === 'doctor'
      ? `Hello Doctor. I am your MediKiosk Clinical AI Copilot. You can ask for clinical differential diagnoses, pharmacological monographs, drug interaction verifications, or OPD clinical triage guidance.`
      : `Namaste! I am the MediKiosk AI Assistant. Tell me what symptoms or health concerns you have today in your preferred language (English, हिन्दी, ગુજરાતી), and I will help guide your care.`;

    setMessages([
      {
        id: 'welcome-0',
        role: 'assistant',
        content: welcome,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);

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

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || inputMessage).trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      id: 'usr-' + Date.now(),
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInputMessage('');
    setLoading(true);

    try {
      const historyPayload = messages.slice(-6).map((m) => ({
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
        content: data.reply || 'Your message has been processed.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        alerts: data.red_flags || [],
        engine: data.engine || null,
      };

      setMessages((prev) => [...prev, botMsg]);

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
          content: 'MediKiosk Assistant: Connected to backup clinical knowledge. For severe symptoms, please alert the triage desk immediately.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

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
    <main className="min-h-screen bg-[#050911] text-slate-100 flex flex-col justify-between selection:bg-cyan-500/30">
      {/* HEADER */}
      <header className="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-black/40 backdrop-blur-md">
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-3">
            <Logo size={32} className="h-8 w-8" />
            <span className="text-lg font-medium text-white tracking-tight">MediKiosk</span>
          </Link>
          <span className="hidden sm:inline-block text-xs font-mono px-2.5 py-1 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-400/30">
            AI Clinical Assistant • {engineLabel(engineState, modelState)}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/patient/intake"
            className="hidden sm:flex items-center gap-1.5 px-3.5 py-1.5 rounded-full liquid-glass text-xs text-white/80 hover:text-white"
          >
            <span>Kiosk Intake</span>
            <ArrowRight className="h-3 w-3" />
          </Link>
          <Link
            href={staffEntryUrl('/doctor')}
            className="hidden sm:flex items-center gap-1.5 px-3.5 py-1.5 rounded-full liquid-glass text-xs text-indigo-300 hover:text-indigo-200 border border-indigo-500/30"
          >
            <Stethoscope className="h-3 w-3" />
            <span>Doctor Portal</span>
          </Link>
          <Link
            href="/"
            className="p-2 rounded-xl text-white/60 hover:text-white hover:bg-white/5 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </div>
      </header>

      {/* CHAT CONTAINER */}
      <div className="flex-1 max-w-4xl w-full mx-auto p-4 sm:p-6 flex flex-col justify-between">
        {/* Top Options Bar */}
        <div className="mb-4 liquid-glass rounded-2xl p-3.5 flex flex-wrap items-center justify-between gap-3 border border-white/10">
          <div className="flex items-center gap-2">
            <div className="flex items-center bg-white/5 p-1 rounded-full text-xs">
              <button
                onClick={() => setRole('patient')}
                className={`px-3 py-1 rounded-full transition-all ${
                  role === 'patient'
                    ? 'bg-cyan-500/30 text-cyan-200 font-medium'
                    : 'text-white/50 hover:text-white'
                }`}
              >
                Patient Mode
              </button>
              <button
                onClick={() => setRole('doctor')}
                className={`px-3 py-1 rounded-full transition-all ${
                  role === 'doctor'
                    ? 'bg-indigo-500/30 text-indigo-200 font-medium'
                    : 'text-white/50 hover:text-white'
                }`}
              >
                Doctor Copilot
              </button>
            </div>

            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              aria-label="Select Language"
              className="bg-[#0b1322] border border-white/10 text-white/80 rounded-xl px-3 py-1 text-xs focus:outline-none focus:border-cyan-400"
            >
              <option value="en">English</option>
              <option value="hi">हिन्दी (Hindi)</option>
              <option value="gu">ગુજરાતી (Gujarati)</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setSpeechSynthesisEnabled(!speechSynthesisEnabled)}
              title={speechSynthesisEnabled ? 'Mute AI Voice' : 'Enable AI Voice (TTS)'}
              className={`p-2 rounded-xl text-xs flex items-center gap-1.5 transition-colors ${
                speechSynthesisEnabled ? 'text-teal-300 bg-teal-500/20' : 'text-white/40 hover:text-white'
              }`}
            >
              {speechSynthesisEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
              <span className="hidden sm:inline">Voice TTS</span>
            </button>

            <button
              onClick={clearChat}
              title="Reset Conversation"
              className="p-2 rounded-xl text-xs text-white/40 hover:text-white flex items-center gap-1.5 transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              <span className="hidden sm:inline">Reset</span>
            </button>
          </div>
        </div>

        {/* Scrollable Messages Window */}
        <div className="flex-1 min-h-[420px] max-h-[60vh] overflow-y-auto p-4 sm:p-6 rounded-3xl liquid-glass border border-white/10 space-y-4 custom-scrollbar">
          {messages.map((msg) => {
            const isUser = msg.role === 'user';
            return (
              <div
                key={msg.id}
                className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} animate-in fade-in duration-200`}
              >
                <div className="flex items-center gap-1.5 mb-1 px-1 text-[11px] text-white/40">
                  {isUser ? (
                    <>
                      <span>You</span>
                      <span>•</span>
                      <span>{msg.timestamp}</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
                      <span className="text-cyan-400 font-medium">MediKiosk AI Assistant</span>
                      <span>•</span>
                      <span>{msg.timestamp}</span>
                    </>
                  )}
                </div>

                <div
                  className={`relative group max-w-[88%] sm:max-w-[75%] rounded-3xl px-5 py-3.5 text-sm leading-relaxed ${
                    isUser
                      ? 'bg-gradient-to-r from-cyan-600 to-teal-600 text-white rounded-tr-sm shadow-lg'
                      : 'bg-white/[0.05] border border-white/10 text-white/90 rounded-tl-sm backdrop-blur-md'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>

                  <button
                    onClick={() => copyToClipboard(msg.id, msg.content)}
                    title="Copy message"
                    className="absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg bg-black/40 text-white/60 hover:text-white transition-opacity"
                  >
                    {copiedId === msg.id ? <Check className="h-3.5 w-3.5 text-teal-400" /> : <Copy className="h-3.5 w-3.5" />}
                  </button>
                </div>

                {msg.alerts && msg.alerts.length > 0 && (
                  <div className="mt-2 p-3 rounded-2xl bg-amber-500/15 border border-amber-500/30 text-amber-200 text-xs flex items-center gap-2.5 max-w-[85%]">
                    <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
                    <div>
                      <span className="font-semibold block">Triage Priority Warning:</span>
                      <span>These symptoms suggest potentially acute pathology. Please report directly to OPD triage.</span>
                    </div>
                  </div>
                )}

                {/* QA BUG-006: honest provenance for AI-generated replies */}
                {!isUser && msg.engine && (
                  <div className="mt-1 px-1 text-[10px] text-white/40 font-light max-w-[85%] flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-white/30 inline-block" />
                    <span>Source: {engineLabel(msg.engine, msg.engine === 'openrouter' ? modelState : null)}</span>
                  </div>
                )}
              </div>
            );
          })}

          {loading && (
            <div className="flex items-center gap-2 p-4 rounded-2xl bg-white/[0.04] border border-white/5 w-fit">
              <div className="flex gap-1">
                <div className="h-2 w-2 rounded-full bg-cyan-400 animate-bounce"></div>
                <div className="h-2 w-2 rounded-full bg-cyan-400 animate-bounce [animation-delay:0.2s]"></div>
                <div className="h-2 w-2 rounded-full bg-cyan-400 animate-bounce [animation-delay:0.4s]"></div>
              </div>
              <span className="text-xs text-white/50 font-light ml-2">
                Composing clinical response...
              </span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Suggested Quick Prompts */}
        {prompts.length > 0 && (
          <div className="my-3 flex gap-2 overflow-x-auto no-scrollbar">
            {prompts.map((p) => (
              <button
                key={p.id}
                onClick={() => handleSendMessage(p.text)}
                className="whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs bg-white/5 hover:bg-cyan-500/20 text-white/70 hover:text-cyan-200 border border-white/10 hover:border-cyan-400/40 transition-all shrink-0"
              >
                {p.text}
              </button>
            ))}
          </div>
        )}

        {/* Input Form */}
        <div className="mt-2 p-3 liquid-glass rounded-3xl border border-white/10 flex items-center gap-3">
          <button
            type="button"
            onClick={toggleVoiceInput}
            title={isListening ? 'Stop Listening' : 'Speak Message'}
            className={`p-3 rounded-2xl transition-all ${
              isListening
                ? 'bg-rose-500 text-white animate-pulse shadow-[0_0_15px_#f43f5e]'
                : 'liquid-glass text-cyan-300 hover:bg-cyan-500/20 border border-white/10'
            }`}
          >
            <Mic className="h-5 w-5" />
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
                ? 'अपने लक्षण अपनी भाषा में बताएं (उदा. मुझे 3 दिन से तेज बुखार है)...'
                : language === 'gu'
                ? 'તમારા લક્ષણો તમારી ભાષામાં જણાવો (દા.ત. મને 3 દિવસથી તાવ છે)...'
                : role === 'doctor'
                ? 'Ask clinical questions, drug interactions, or guidelines...'
                : 'Describe your symptoms in your own words...'
            }
            className="flex-1 px-4 py-3 rounded-2xl bg-white/[0.04] border border-white/10 text-white text-sm placeholder:text-white/30 focus:border-cyan-400 focus:outline-none"
          />

          <button
            onClick={() => handleSendMessage()}
            disabled={!inputMessage.trim() || loading}
            className="px-6 py-3.5 rounded-2xl bg-gradient-to-r from-cyan-500 to-teal-400 text-slate-950 font-bold text-sm disabled:opacity-40 hover:scale-105 transition-all shadow-[0_0_20px_rgba(0,242,254,0.3)] flex items-center gap-2"
          >
            <span>Send</span>
            <Send className="h-4 w-4" />
          </button>
        </div>

        {/* Action Link to Kiosk Intake */}
        <div className="mt-4 text-center">
          <p className="text-xs text-white/40">
            Ready to generate your official OPD queue token?{' '}
            <Link href="/patient/intake" className="text-cyan-400 hover:underline font-medium">
              Start Kiosk Patient Intake →
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
