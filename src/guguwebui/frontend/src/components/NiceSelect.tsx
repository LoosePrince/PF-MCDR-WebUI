import React, { useState } from 'react';
import { ChevronRight } from 'lucide-react';

export interface NiceSelectOption {
  value: string;
  label: string;
}

interface NiceSelectProps {
  value: string;
  onChange: (v: string) => void;
  options: NiceSelectOption[];
}

export const NiceSelect: React.FC<NiceSelectProps> = ({ value, onChange, options }) => {
  const [open, setOpen] = useState(false);
  const selected = options.find(o => o.value === value) || options[0];

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-sm text-slate-900 dark:text-white hover:border-blue-400 hover:bg-blue-50/60 dark:hover:bg-slate-800 transition-all"
      >
        <span className="truncate">{selected?.label}</span>
        <ChevronRight
          size={16}
          className={`text-slate-400 transition-transform ${open ? 'rotate-90' : ''}`}
        />
      </button>
      {open && (
        <div className="absolute z-20 mt-2 w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 shadow-lg max-h-60 overflow-y-auto">
          {options.map(opt => (
            <button
              key={opt.value}
              type="button"
              onClick={() => {
                onChange(opt.value);
                setOpen(false);
              }}
              className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                opt.value === value
                  ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 font-semibold'
                  : 'text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
