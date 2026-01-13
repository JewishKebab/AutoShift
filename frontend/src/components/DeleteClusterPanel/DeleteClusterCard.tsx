import { useEffect, useRef, useState } from 'react';
import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';

type Props = {
  cluster: any;
  onDelete: () => void | Promise<void>;
  isBusy: boolean;
  isThisBusy: boolean;
};

const HOLD_SECONDS = 5;
const HOLD_MS = HOLD_SECONDS * 1000;

export function ClusterCard({ cluster, onDelete, isBusy, isThisBusy }: Props) {
  const [holding, setHolding] = useState(false);
  const [progressMs, setProgressMs] = useState(0);

  const rafRef = useRef<number | null>(null);
  const startRef = useRef<number | null>(null);
  const firedRef = useRef(false);

  const disabled = isBusy && !isThisBusy;

  const reset = () => {
    setHolding(false);
    setProgressMs(0);
    startRef.current = null;
    firedRef.current = false;
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
  };

  const tick = (now: number) => {
    if (!startRef.current) startRef.current = now;
    const elapsed = now - startRef.current;
    const clamped = Math.min(elapsed, HOLD_MS);
    setProgressMs(clamped);

    if (clamped >= HOLD_MS && !firedRef.current) {
      firedRef.current = true;
      Promise.resolve(onDelete()).finally(reset);
      return;
    }

    rafRef.current = requestAnimationFrame(tick);
  };

  const startHold = () => {
    if (disabled || isThisBusy) return;
    setHolding(true);
    setProgressMs(0);
    startRef.current = null;
    firedRef.current = false;
    rafRef.current = requestAnimationFrame(tick);
  };

  const cancelHold = () => {
    if (!holding) return;
    reset();
  };

  useEffect(() => {
    if (isThisBusy) reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isThisBusy]);

  const pct = Math.min(100, Math.round((progressMs / HOLD_MS) * 100));
  const secondsLeft = Math.max(0, Math.ceil((HOLD_MS - progressMs) / 1000));

  return (
    <Card className="relative">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="font-display text-lg font-semibold">
              {cluster.name ?? cluster.id}
            </div>
            <div className="text-sm text-muted-foreground">
              Status: <span className="font-medium">{cluster.status}</span>
            </div>
          </div>

          <div className="w-48 space-y-2">
            {/* Button with fill overlay */}
            <Button
              variant="destructive"
              disabled={disabled || isThisBusy}
              className="relative overflow-hidden select-none"
              onMouseDown={startHold}
              onMouseUp={cancelHold}
              onMouseLeave={cancelHold}
              onTouchStart={(e) => {
                e.preventDefault();
                startHold();
              }}
              onTouchEnd={(e) => {
                e.preventDefault();
                cancelHold();
              }}
              onTouchCancel={cancelHold}
            >
              {/* Progress fill (LEFT → RIGHT) */}
              <span
                className="absolute inset-y-0 left-0 bg-destructive/40"
                style={{
                  width: `${pct}%`,
                  transition: holding ? 'none' : 'width 150ms ease-out',
                }}
              />

              <span className="relative z-10 flex items-center gap-2">
                <Trash2 className="h-4 w-4" />
                {holding ? `Hold… ${secondsLeft}s` : 'Hold to delete'}
              </span>
            </Button>

            {/* Progress bar */}
            <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-destructive"
                style={{
                  width: `${pct}%`,
                  transition: holding ? 'none' : 'width 150ms ease-out',
                }}
              />
            </div>

            <div className="text-xs text-muted-foreground">
              {holding ? 'Release to cancel' : `Hold for ${HOLD_SECONDS}s`}
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-2">
        <div className="text-sm text-muted-foreground">
          ID: <span className="font-mono">{cluster.id}</span>
        </div>
      </CardContent>
    </Card>
  );
}
