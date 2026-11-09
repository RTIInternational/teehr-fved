import { type ReactNode, useEffect, useMemo } from 'react';

import type { ViewDefinition } from './ViewDefinition';

type ViewHostProps = {
  viewId: string | undefined;
  views: ViewDefinition[];
  onResolvedView?: (view: ViewDefinition) => void;
  children: (activeView: ViewDefinition, isFallback: boolean) => ReactNode;
};

/** Resolves the active view and lets callers render it without router coupling. */
export const ViewHost = ({ viewId, views, onResolvedView, children }: ViewHostProps) => {
  const { activeView, isFallback } = useMemo(() => {
    if (views.length === 0) {
      return { activeView: null, isFallback: true };
    }

    const direct = views.find((view) => view.id === viewId);
    if (direct) return { activeView: direct, isFallback: false };

    const fallback = views[0];
    return { activeView: fallback, isFallback: true };
  }, [viewId, views]);

  useEffect(() => {
    if (!activeView) return;
    onResolvedView?.(activeView);
  }, [activeView, onResolvedView]);

  if (!activeView) return null;

  return children(activeView, isFallback);
};
