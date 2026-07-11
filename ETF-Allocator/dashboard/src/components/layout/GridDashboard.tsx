import { useMemo, type ReactNode } from 'react';
import { Responsive, useContainerWidth, type ResponsiveLayouts } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import GlassCard from '../GlassCard';

interface WidgetDef {
  id: string;
  layout: { w: number; h: number; minW?: number; minH?: number };
  component: ReactNode;
}

interface Props {
  widgets: WidgetDef[];
}

const BREAKPOINTS = { lg: 1200, md: 996, sm: 768 };
const COLS = { lg: 12, md: 8, sm: 4 };
const ROW_H = 80;
const STORAGE_KEY = 'etf-dashboard-layout';
type BreakpointName = keyof typeof BREAKPOINTS;

function loadLayout(): ResponsiveLayouts<BreakpointName> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as ResponsiveLayouts<BreakpointName>;
  } catch {
    return {};
  }
  return {};
}

function saveLayout(layouts: ResponsiveLayouts<BreakpointName>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(layouts));
  } catch {
    // Dragging remains functional when layout persistence is unavailable.
  }
}

export function GridDashboard({ widgets }: Props) {
  const { width, containerRef } = useContainerWidth();
  const savedLayouts = useMemo(() => loadLayout(), []);

  if (!width) return <div ref={containerRef} className="min-h-64" />;

  return (
    <div ref={containerRef}>
      <Responsive<BreakpointName>
        layouts={savedLayouts}
        breakpoints={BREAKPOINTS}
        cols={COLS}
        rowHeight={ROW_H}
        width={width}
        margin={[16, 16] as [number, number]}
        containerPadding={[0, 0] as [number, number]}
        onLayoutChange={(_current, all) => saveLayout(all)}
        dragConfig={{ enabled: true, handle: '.drag-handle' }}
        resizeConfig={{ enabled: true }}
      >
        {widgets.map(w => (
          <div key={w.id} data-grid={w.layout}>
            <GlassCard className="h-full overflow-auto">
              <div className="drag-handle absolute top-3 left-3 flex gap-1 opacity-20 hover:opacity-60 transition cursor-grab active:cursor-grabbing z-10">
                <span className="w-1.5 h-1.5 rounded-full bg-[#7C3AED]" />
                <span className="w-1.5 h-1.5 rounded-full bg-[#7C3AED]" />
                <span className="w-1.5 h-1.5 rounded-full bg-[#7C3AED]" />
              </div>
              {w.component}
            </GlassCard>
          </div>
        ))}
      </Responsive>
    </div>
  );
}
