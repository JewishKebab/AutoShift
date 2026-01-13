// src/components/clusters/CreateClusterForm/InstallerLogsCard.tsx
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';

type Props = {
  installJobId: string;
  installLogs: string[];
  isInstalling: boolean;

  logsExpanded: boolean;
  setLogsExpanded: (v: boolean) => void;

  autoScroll: boolean;
  setAutoScroll: (v: boolean) => void;

  maxLines: number;
  setMaxLines: (v: number) => void;

  onClear: () => void;

  logBoxRef: React.RefObject<HTMLDivElement>;
  isUserAtBottom: () => boolean;
  scrollToBottom: () => void;
};

export function InstallerLogsCard(props: Props) {
  const {
    installJobId,
    installLogs,
    isInstalling,
    logsExpanded,
    setLogsExpanded,
    autoScroll,
    setAutoScroll,
    maxLines,
    setMaxLines,
    onClear,
    logBoxRef,
    isUserAtBottom,
    scrollToBottom,
  } = props;

  return (
    <Card className="mt-4">
      <CardHeader className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">Installer Logs</CardTitle>
            <CardDescription>
              Job: {installJobId} {isInstalling ? '(running)' : '(finished)'} · Showing last{' '}
              {Math.min(installLogs.length, maxLines)} lines
            </CardDescription>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={() => setLogsExpanded(!logsExpanded)}>
              {logsExpanded ? 'Collapse' : 'Expand'}
            </Button>

            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => {
                navigator.clipboard.writeText(installLogs.join('\n'));
                toast.success('Copied logs');
              }}
            >
              Copy
            </Button>

            <Button type="button" variant="secondary" size="sm" onClick={onClear}>
              Clear
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} />
            Auto-scroll
          </label>

          <label className="flex items-center gap-2 text-sm">
            Max lines
            <Select value={String(maxLines)} onValueChange={(v) => setMaxLines(parseInt(v, 10))}>
              <SelectTrigger className="h-8 w-[120px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="2000">2,000</SelectItem>
                <SelectItem value="8000">8,000</SelectItem>
                <SelectItem value="20000">20,000</SelectItem>
              </SelectContent>
            </Select>
          </label>
        </div>
      </CardHeader>

      <CardContent>
        <div
          ref={logBoxRef}
          onScroll={() => {
            if (!isUserAtBottom()) setAutoScroll(false);
          }}
          className={[
            'overflow-auto rounded-md bg-black text-white p-3 font-mono text-xs whitespace-pre',
            logsExpanded ? 'h-[70vh]' : 'h-64',
          ].join(' ')}
        >
          {installLogs.length === 0 ? 'Waiting for output...\n' : installLogs.join('\n')}
        </div>

        {!autoScroll && (
          <div className="mt-2 flex justify-end">
            <Button
              type="button"
              size="sm"
              onClick={() => {
                setAutoScroll(true);
                requestAnimationFrame(scrollToBottom);
              }}
            >
              Jump to bottom
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
