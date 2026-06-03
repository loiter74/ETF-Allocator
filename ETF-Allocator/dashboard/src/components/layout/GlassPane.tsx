import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}

export function GlassPane({ children, className = '', onClick }: Props) {
  return (
    <motion.div
      className={`glass ${className}`}
      whileHover={{ borderColor: 'oklch(1 0 0 / 0.15)', boxShadow: '0 0 20px oklch(0.53 0.18 var(--chromatic-hue, 220) / 0.12)' }}
      transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      onClick={onClick}
    >
      {children}
    </motion.div>
  );
}
