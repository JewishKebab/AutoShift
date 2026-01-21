import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

type Props = {
  holdMs?: number;
  onConfirm: () => void | Promise<void>;
  disabled?: boolean;
  className?: string;
  variant?: 'default' | 'destructive' | 'secondary' | 'outline' | 'ghost' | 'link';
  children: React.ReactNode;
};

export function HoldToConfirmButton({
  holdMs = 5000,
  onConfirm,
  disabled,
  className,
  variant = 'destructive',
  children,
}: Props) {
  const [holding, setHolding] = useState(false);
  const [progress, setProgress] = useState(0);

  const rafRef = useRef<number | null>(null);
  const startRef = useRef<number>(0);
  const firedRef = useRef(false);

  const stop = () => {
    setHolding(false);
    setProgress(0);
    firedRef.current = false;
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
  };

  const tick = (ts: number) => {
    if (!holding) return;
    if (!startRef.current) startRef.current = ts;

    const elapsed = ts - startRef.current;
    const p = Math.min(1, elapsed / holdMs);
    setProgress(p);

    if (p >= 1 && !firedRef.current) {
      firedRef.current = true;
      Promise.resolve(onConfirm()).finally(() => stop());
      return;
    }

    rafRef.current = requestAnimationFrame(tick);
  };

  const start = () => {
    if (disabled) return;
    setHolding(true);
    setProgress(0);
    startRef.current = 0;
    firedRef.current = false;
    rafRef.current = requestAnimationFrame(tick);
  };

  useEffect(() => () => stop(), []);

  return (
    <Button
      type="button"
      variant={variant}
      disabled={disabled}
      className={cn('relative overflow-hidden select-none', className)}
      onMouseDown={start}
      onMouseUp={stop}
      onMouseLeave={stop}
      onTouchStart={start}
      onTouchEnd={stop}
    >
      {/* progress overlay */}
      <span
        className="absolute inset-0 opacity-30"
        style={{
          transformOrigin: 'left',
          transform: `scaleX(${progress})`,
        }}
      />
      <span className="relative z-10">{children}</span>
    </Button>
  );
}
