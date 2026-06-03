export function RippleBackground() {
  return (
    <div
      className="fixed inset-0 -z-10 ripple-grid pointer-events-none"
      style={{ opacity: 0.6 }}
    />
  );
}
