import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { getSavedTheme, getSavedMode, applyTheme, applyMode, type Theme, themes } from '../design-system/theme';

interface ThemeCtx {
  theme: Theme;
  setTheme: (t: Theme) => void;
  mode: 'dark' | 'light';
  toggleMode: () => void;
}

const Ctx = createContext<ThemeCtx>(null!);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(themes[0]);
  const [mode, setModeState] = useState<'dark' | 'light'>('light');

  useEffect(() => {
    const t = getSavedTheme();
    const m = getSavedMode();
    setThemeState(t);
    setModeState(m);
    applyTheme(t);
    applyMode(m);
  }, []);

  const setTheme = (t: Theme) => {
    setThemeState(t);
    applyTheme(t);
  };
  const toggleMode = () => {
    const next = mode === 'dark' ? 'light' : 'dark';
    setModeState(next);
    applyMode(next);
  };

  return <Ctx.Provider value={{ theme, setTheme, mode, toggleMode }}>{children}</Ctx.Provider>;
}

export function useTheme() {
  return useContext(Ctx);
}
