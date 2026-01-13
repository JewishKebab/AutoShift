// src/components/clusters/CreateClusterForm/useInstallerLogs.ts
import { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';

type Options = {
  apiBase?: string; // default ''
  flushIntervalMs?: number; // default 200
  initialMaxLines?: number; // default 8000
  storageKeyPrefix?: string; // default 'autoshift'
};

export function useInstallerLogs(opts: Options = {}) {
  const {
    apiBase = '',
    flushIntervalMs = 200,
    initialMaxLines = 8000,
    storageKeyPrefix = 'autoshift',
  } = opts;

  const JOB_KEY = `${storageKeyPrefix}:lastJobId`;
  const SEQ_KEY = `${storageKeyPrefix}:lastSeq`;

  const [installJobId, setInstallJobId] = useState<string | null>(null);
  const [installLogs, setInstallLogs] = useState<string[]>([]);
  const [isInstalling, setIsInstalling] = useState(false);

  const [logsExpanded, setLogsExpanded] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [maxLines, setMaxLines] = useState(initialMaxLines);

  const logBoxRef = useRef<HTMLDivElement | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const logBufferRef = useRef<string[]>([]);
  const flushTimerRef = useRef<number | null>(null);

  const isUserAtBottom = () => {
    const el = logBoxRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  };

  const scrollToBottom = () => {
    const el = logBoxRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  };

  const flushBufferToState = () => {
    if (logBufferRef.current.length === 0) return;

    setInstallLogs((prev) => {
      const next = [...prev, ...logBufferRef.current];
      logBufferRef.current = [];
      if (next.length > maxLines) return next.slice(next.length - maxLines);
      return next;
    });

    if (autoScroll && isUserAtBottom()) {
      requestAnimationFrame(scrollToBottom);
    }
  };

  const stopLogStream = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (flushTimerRef.current) {
      window.clearInterval(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    setIsInstalling(false);
  };

  const startLogStream = async (jobId: string) => {
    stopLogStream();

    // persist job id so refresh/leave page can recover
    localStorage.setItem(JOB_KEY, jobId);

    setInstallLogs([]);
    logBufferRef.current = [];
    setIsInstalling(true);
    setInstallJobId(jobId);

    // 1) hydrate existing logs (if any) from backend snapshot
    try {
      const fromSeq = Number(localStorage.getItem(SEQ_KEY) ?? '0');
      const snapRes = await fetch(`${apiBase}/api/installer/logs/${jobId}?from=0`, {
        method: 'GET',
        credentials: 'include',
        headers: { Accept: 'application/json' },
      });

      if (snapRes.ok) {
        const snap = await snapRes.json();
        const lines = Array.isArray(snap?.lines) ? (snap.lines as [number, string][]) : [];
        const lastSeq = typeof snap?.lastSeq === 'number' ? snap.lastSeq : fromSeq;

        // save latest seq we know about
        localStorage.setItem(SEQ_KEY, String(lastSeq));

        // push snapshot into buffer -> state
        for (const [, line] of lines) logBufferRef.current.push(String(line));
        flushBufferToState();

        // if job already finished, stop here (still show logs)
        if (snap?.done) {
          setIsInstalling(false);
          return;
        }
      }
    } catch {
      // snapshot failure shouldn't block streaming
    }

    // 2) connect stream starting from last known sequence
    const fromSeq = Number(localStorage.getItem(SEQ_KEY) ?? '0');
    const url = `${apiBase}/api/installer/stream/${jobId}?from=${fromSeq}`;

    const es = new EventSource(url);
    eventSourceRef.current = es;

    flushTimerRef.current = window.setInterval(flushBufferToState, flushIntervalMs);

    es.onmessage = (ev) => {
      if (ev.data == null) return;

      // server sends: id: <seq>
      if (ev.lastEventId) {
        localStorage.setItem(SEQ_KEY, ev.lastEventId);
      }

      const line = String(ev.data);

      // ignore heartbeats (":" comments come through differently, but keep safe)
      if (line === '') return;

      logBufferRef.current.push(line);

      if (line === '[done]' || line.includes('[done]') || line.includes('[error]')) {
        setIsInstalling(false);
        flushBufferToState();
        stopLogStream();
      }
    };

    es.onerror = () => {
      // IMPORTANT: don't clear jobId/seq. user can come back and resume.
      setIsInstalling(false);
      flushBufferToState();
      stopLogStream();
      toast.error('Log stream disconnected', {
        description: 'You can refresh/reopen the page to reattach to the running job.',
      });
    };
  };

  // NEW: restore stream on mount if jobId exists
  useEffect(() => {
    const savedJobId = localStorage.getItem(JOB_KEY);
    if (savedJobId) {
      // best effort: reattach automatically
      startLogStream(savedJobId);
    }
    return () => stopLogStream();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const actions = useMemo(
    () => ({
      startLogStream,
      stopLogStream,
      setInstallLogs,
      setLogsExpanded,
      setAutoScroll,
      setMaxLines,
      clearPersistedJob: () => {
        localStorage.removeItem(JOB_KEY);
        localStorage.removeItem(SEQ_KEY);
      },
      setPersistedCursor: (seq: number) => {
        localStorage.setItem(SEQ_KEY, String(seq));
      },
    }),
    [maxLines, autoScroll]
  );

  const ui = {
    logBoxRef,
    isUserAtBottom,
    scrollToBottom,
  };

  const state = {
    installJobId,
    installLogs,
    isInstalling,
    logsExpanded,
    autoScroll,
    maxLines,
  };

  return { state, actions, ui };
}
