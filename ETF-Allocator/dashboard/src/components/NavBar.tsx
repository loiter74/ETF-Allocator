import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'

const NAV_ITEMS: { path: string; label: string }[] = [
  { path: '/', label: '本月概览' },
  { path: '/trends', label: '历史趋势' },
  { path: '/investments', label: '资金记录' },
];

export default function NavBar() {
  const [menuOpen, setMenuOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const today = new Date()
  const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`

  return (
    <nav className="glass-card relative z-50 px-4 sm:px-8 py-3 sm:py-4 mb-4 sm:mb-6 flex items-center justify-between rounded-none sm:rounded-2xl mx-0 sm:mx-6 mt-0 sm:mt-6">
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-lg bg-gradient-to-br from-[#7C3AED] to-[#EC4899] flex items-center justify-center">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg>
        </div>
        <span className="font-semibold text-[#1F2937] text-base sm:text-lg tracking-tight">
          ETF Allocator
        </span>
      </div>

      <div className="hidden sm:flex items-center gap-1.5">
        {NAV_ITEMS.map((item) => (
          <button
            type="button"
            key={item.path}
            onClick={() => navigate(item.path)}
            className={`px-3 sm:px-4 py-2 rounded-xl text-sm font-medium transition-all cursor-pointer ${
              location.pathname === item.path
                ? 'bg-[#7C3AED] text-white shadow-sm'
                : 'text-[#6B7280] hover:bg-white/60'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="hidden sm:block nums text-xs text-[#6B7280] bg-white/50 px-3 py-1.5 rounded-lg">
        {dateStr}
      </div>

      {/* Mobile hamburger */}
      <button
        type="button"
        className="sm:hidden p-2 rounded-lg hover:bg-white/50 transition-colors"
        onClick={() => setMenuOpen(!menuOpen)}
        aria-label={menuOpen ? '关闭导航菜单' : '打开导航菜单'}
        aria-expanded={menuOpen}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#1F2937" strokeWidth="2" strokeLinecap="round">
          {menuOpen
            ? <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>
            : <><line x1="4" y1="6" x2="20" y2="6" /><line x1="4" y1="12" x2="20" y2="12" /><line x1="4" y1="18" x2="20" y2="18" /></>
          }
        </svg>
      </button>

      {/* Mobile dropdown */}
      {menuOpen && (
        <div className="absolute top-full left-0 right-0 mt-2 mx-4 sm:hidden z-50">
          <div className="glass-card mobile-nav-menu rounded-2xl p-3 shadow-lg space-y-1">
            {NAV_ITEMS.map((item) => (
              <button
                type="button"
                key={item.path}
                onClick={() => { navigate(item.path); setMenuOpen(false) }}
                className={`block w-full text-left px-4 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                  location.pathname === item.path
                    ? 'bg-[#7C3AED] text-white'
                    : 'text-[#6B7280] hover:bg-white/60'
                }`}
              >
                {item.label}
              </button>
            ))}
            <div className="nums text-xs text-[#6B7280] px-4 pt-2 border-t border-gray-100 mt-1">
              {dateStr}
            </div>
          </div>
        </div>
      )}
    </nav>
  )
}
