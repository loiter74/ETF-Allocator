export interface Theme {
  name: string;
  hue: number;
  label: string;
  colorClass: string;
}

export const themes: Theme[] = [
  { name: 'nebula', hue: 220, label: 'Nebula', colorClass: 'bg-chromatic-500' },
  { name: 'amber',  hue: 45,  label: 'Amber',  colorClass: 'bg-amber-500' },
  { name: 'mint',   hue: 160, label: 'Mint',   colorClass: 'bg-emerald-400' },
];

export function getSavedTheme(): Theme {
  try {
    const saved = localStorage.getItem('etf-theme');
    if (saved) {
      const found = themes.find(t => t.name === saved);
      if (found) return found;
    }
  } catch {}
  return themes[0];
}

export function saveTheme(name: string) {
  try { localStorage.setItem('etf-theme', name); } catch {}
}

export function getSavedMode(): 'dark' | 'light' {
  try {
    const saved = localStorage.getItem('etf-mode');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {}
  return 'dark';
}

export function saveMode(mode: 'dark' | 'light') {
  try { localStorage.setItem('etf-mode', mode); } catch {}
}

export function applyTheme(t: Theme) {
  document.documentElement.style.setProperty('--chromatic-hue', String(t.hue));
  document.documentElement.dataset.theme = t.name;
  saveTheme(t.name);
}

export function applyMode(mode: 'dark' | 'light') {
  if (mode === 'light') {
    document.documentElement.classList.add('light');
  } else {
    document.documentElement.classList.remove('light');
  }
  saveMode(mode);
}
