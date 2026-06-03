import { useEffect, useRef } from 'react';
import katex from 'katex';

interface Props {
  tex: string;
  displayMode?: boolean;
}

/**
 * 渲染 LaTeX 公式（KaTeX 引擎）。
 * 用法：<Formula tex="1 - PE_{分位}" />
 */
export function Formula({ tex, displayMode = false }: Props) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (ref.current) {
      try {
        katex.render(tex, ref.current, {
          displayMode,
          throwOnError: false,
          trust: true,
        });
      } catch {
        ref.current.textContent = tex;
      }
    }
  }, [tex, displayMode]);

  return <span ref={ref} />;
}
