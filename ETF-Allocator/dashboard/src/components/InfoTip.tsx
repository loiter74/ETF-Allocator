import { useState } from 'react';
import { Formula } from './Formula';

interface Props {
  text: string;
  formula?: string;
}

export function InfoTip({ text, formula }: Props) {
  const [show, setShow] = useState(false);

  return (
    <span
      className="relative inline-flex items-center ml-1"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <button
        onClick={() => setShow(!show)}
        className="w-4 h-4 rounded-full bg-gray-200 hover:bg-gray-300 text-[10px] text-gray-500 font-bold flex items-center justify-center cursor-help transition-colors"
      >
        ?
      </button>
      {show && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-4 rounded-xl bg-gray-800 text-white text-xs leading-relaxed shadow-xl pointer-events-none">
          <div className="whitespace-pre-line">{text}</div>
          {formula && (
            <div className="mt-2 pt-2 border-t border-gray-600 flex justify-center">
              <Formula tex={formula} />
            </div>
          )}
          <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-800" />
        </div>
      )}
    </span>
  );
}
