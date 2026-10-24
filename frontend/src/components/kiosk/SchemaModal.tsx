'use client';

import React, { useState } from 'react';
import { Database, Copy, Check, X } from 'lucide-react';
import { POSTGRES_SCHEMA_SQL } from '@/lib/clinicalStore';
import { useModalDialog } from '@/lib/useModalDialog';

interface SchemaModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function SchemaModal({ isOpen, onClose }: SchemaModalProps) {
  const [copied, setCopied] = useState(false);
  // QA-12: dialog semantics, Escape-to-close, focus trap and focus restore.
  const { dialogRef, onBackdropClick } = useModalDialog(isOpen, { onClose });

  if (!isOpen) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(POSTGRES_SCHEMA_SQL);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-3 sm:p-6"
      onClick={onBackdropClick}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="mk-schema-title"
        aria-describedby="mk-schema-desc"
        tabIndex={-1}
        className="bg-white rounded-xl max-w-4xl w-full max-h-[90vh] flex flex-col shadow-2xl border border-neutral-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150 outline-none"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 bg-neutral-50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-[#F3EEFC] flex items-center justify-center text-[#6C3FC5]">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <h3 id="mk-schema-title" className="text-base sm:text-lg font-bold text-[#171717]">
                PostgreSQL / Supabase Database Schema
              </h3>
              <p id="mk-schema-desc" className="text-xs text-[#666666]">
                Schema DDL with RLS, foreign keys, and indexes for MediKiosk
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-xs font-semibold rounded-lg transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copied SQL!' : 'Copy SQL'}</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close database schema dialog"
              className="text-[#666666] hover:text-[#171717] p-1.5 rounded-md"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 sm:p-6 bg-[#0E131F] text-slate-200 font-mono text-xs leading-relaxed">
          <pre className="whitespace-pre-wrap">{POSTGRES_SCHEMA_SQL}</pre>
        </div>

        <div className="px-6 py-3 border-t border-neutral-200 bg-white flex justify-between items-center text-xs text-[#666666]">
          <span>Compatible with PostgreSQL 15+, Supabase, Neon DB, and AWS RDS</span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 border border-neutral-200 rounded-lg hover:bg-neutral-50 font-medium text-[#171717]"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
