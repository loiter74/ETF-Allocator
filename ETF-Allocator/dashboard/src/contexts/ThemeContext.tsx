import { useState, type ReactNode } from 'react';
import { getSavedTheme, applyTheme, applyMode, type Theme } from '../design-system/theme';
import { ThemeContext } from './theme-context';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getSavedTheme);
  const [mode, setModeState] = useState<'dark' | 'light'>('light');

  const setTheme = (t: Theme) => {
    setThemeState(t);
    applyTheme(t);
  };
  const toggleMode = () => {
    const next = mode === 'dark' ? 'light' : 'dark';
    setModeState(next);
    applyMode(next);
  };

  return <ThemeContext.Provider value={{ theme, setTheme, mode, toggleMode }}>{children}</ThemeContext.Provider>;
}
