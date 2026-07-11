import { useTheme } from '../../contexts/useTheme';

export function ThemeSwitcher() {
  const { mode, toggleMode } = useTheme();

  return (
    <div className="fixed top-20 right-4 z-50">
      <button
        onClick={toggleMode}
        className="w-10 h-10 bg-white/80 backdrop-blur border border-gray-200 rounded-xl flex items-center justify-center text-lg cursor-pointer hover:border-[#7C3AED] hover:shadow-md transition shadow-sm"
        title={mode === 'dark' ? '亮色模式' : '暗色模式'}
      >
        {mode === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19'}
      </button>
    </div>
  );
}
