import { createContext } from 'react';
import type { Theme } from '../design-system/theme';

export interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  mode: 'dark' | 'light';
  toggleMode: () => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);
