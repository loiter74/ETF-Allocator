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

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage may be unavailable in private browsing or restricted webviews.
  }
}

export function getSavedTheme(): Theme {
  const saved = readStorage('etf-theme');
  if (saved) {
    const found = themes.find(t => t.name === saved);
    if (found) return found;
  }
  return themes[0];
}

export function saveTheme(name: string) {
  writeStorage('etf-theme', name);
}

export function getSavedMode(): 'dark' | 'light' {
  const saved = readStorage('etf-mode');
  if (saved === 'light' || saved === 'dark') return saved;
  return 'light';
}

export function saveMode(mode: 'dark' | 'light') {
  writeStorage('etf-mode', mode);
}

export function applyTheme(t: Theme) {
  document.documentElement.style.setProperty('--chromatic-hue', String(t.hue));
  document.documentElement.dataset.theme = t.name;
  saveTheme(t.name);
}

export function applyMode(mode: 'dark' | 'light') {
  document.documentElement.classList.toggle('dark', mode === 'dark');
  saveMode(mode);
}
