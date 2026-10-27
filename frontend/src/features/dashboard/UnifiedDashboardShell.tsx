import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

type OverlayCardProps = {
  content: ReactNode;
  className?: string;
};

type UnifiedDashboardShellProps = {
  mapContent: ReactNode;
  desktopTopLeftCard?: OverlayCardProps;
  desktopTopRightCard?: OverlayCardProps;
  desktopBottomCard?: OverlayCardProps;
  mobileBottomSheet?: OverlayCardProps;
  transitionKey?: string;
};

type OverlaySet = {
  desktopTopLeftCard?: OverlayCardProps;
  desktopTopRightCard?: OverlayCardProps;
  desktopBottomCard?: OverlayCardProps;
  mobileBottomSheet?: OverlayCardProps;
};

const OVERLAY_OUT_DURATION_MS = 360;
const OVERLAY_IN_DURATION_MS = 320;

type OverlayPhase = 'idle' | 'out' | 'in';

const renderOverlayCard = (overlay?: OverlayCardProps, phaseClassName?: string) => {
  if (!overlay) return null;

  return (
    <div
      className={`unified-dashboard-shell__card ${overlay.className ?? ''} ${phaseClassName ?? ''}`.trim()}
    >
      {overlay.content}
    </div>
  );
};

const renderOverlaySet = (overlaySet: OverlaySet | null, phaseClassName?: string) => {
  if (!overlaySet) return null;

  return (
    <>
      {overlaySet.desktopTopLeftCard && (
        <div
          className={`unified-dashboard-shell__overlay unified-dashboard-shell__overlay--top-left d-none d-md-block ${phaseClassName ?? ''}`.trim()}
        >
          {renderOverlayCard(overlaySet.desktopTopLeftCard, phaseClassName)}
        </div>
      )}

      {overlaySet.desktopTopRightCard && (
        <div
          className={`unified-dashboard-shell__overlay unified-dashboard-shell__overlay--top-right d-none d-md-block ${phaseClassName ?? ''}`.trim()}
        >
          {renderOverlayCard(overlaySet.desktopTopRightCard, phaseClassName)}
        </div>
      )}

      {overlaySet.desktopBottomCard && (
        <div
          className={`unified-dashboard-shell__overlay unified-dashboard-shell__overlay--bottom d-none d-md-block ${phaseClassName ?? ''}`.trim()}
        >
          {renderOverlayCard(overlaySet.desktopBottomCard, phaseClassName)}
        </div>
      )}

      {overlaySet.mobileBottomSheet && (
        <div
          className={`unified-dashboard-shell__mobile-sheet d-md-none ${phaseClassName ?? ''}`.trim()}
        >
          {renderOverlayCard(overlaySet.mobileBottomSheet, phaseClassName)}
        </div>
      )}
    </>
  );
};

const UnifiedDashboardShell = ({
  mapContent,
  desktopTopLeftCard,
  desktopTopRightCard,
  desktopBottomCard,
  mobileBottomSheet,
  transitionKey,
}: UnifiedDashboardShellProps) => {
  const activeOverlaySet = useMemo(
    () => ({
      desktopTopLeftCard,
      desktopTopRightCard,
      desktopBottomCard,
      mobileBottomSheet,
    }),
    [desktopTopLeftCard, desktopTopRightCard, desktopBottomCard, mobileBottomSheet]
  );
  const previousOverlaySetRef = useRef<OverlaySet>(activeOverlaySet);
  const previousTransitionKeyRef = useRef(transitionKey);
  const outTimeoutRef = useRef<number | null>(null);
  const inTimeoutRef = useRef<number | null>(null);
  const [overlayPhase, setOverlayPhase] = useState<OverlayPhase>('idle');
  const [outgoingOverlaySet, setOutgoingOverlaySet] = useState<OverlaySet | null>(null);
  const [incomingOverlaySet, setIncomingOverlaySet] = useState<OverlaySet | null>(null);

  const clearTransitionTimers = () => {
    if (outTimeoutRef.current !== null) {
      window.clearTimeout(outTimeoutRef.current);
      outTimeoutRef.current = null;
    }
    if (inTimeoutRef.current !== null) {
      window.clearTimeout(inTimeoutRef.current);
      inTimeoutRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      clearTransitionTimers();
    };
  }, []);

  useEffect(() => {
    if (!transitionKey || previousTransitionKeyRef.current === transitionKey) {
      previousTransitionKeyRef.current = transitionKey;
      return;
    }

    clearTransitionTimers();

    setOutgoingOverlaySet(previousOverlaySetRef.current);
    setIncomingOverlaySet(activeOverlaySet);
    setOverlayPhase('out');
    previousTransitionKeyRef.current = transitionKey;

    outTimeoutRef.current = window.setTimeout(() => {
      setOutgoingOverlaySet(null);
      setOverlayPhase('in');

      inTimeoutRef.current = window.setTimeout(() => {
        setOverlayPhase('idle');
        setIncomingOverlaySet(null);
      }, OVERLAY_IN_DURATION_MS);
    }, OVERLAY_OUT_DURATION_MS);
  }, [transitionKey, activeOverlaySet]);

  useEffect(() => {
    previousOverlaySetRef.current = activeOverlaySet;
  }, [activeOverlaySet]);

  const renderedOverlaySet = overlayPhase === 'in' ? incomingOverlaySet : activeOverlaySet;

  return (
    <div className="unified-dashboard-shell">
      <div className="unified-dashboard-shell__map">{mapContent}</div>

      {overlayPhase === 'out' &&
        outgoingOverlaySet &&
        renderOverlaySet(outgoingOverlaySet, 'unified-dashboard-shell__overlay-phase--outgoing')}

      {overlayPhase !== 'out' &&
        renderOverlaySet(
          renderedOverlaySet,
          overlayPhase === 'in' ? 'unified-dashboard-shell__overlay-phase--incoming' : undefined
        )}
    </div>
  );
};

export default UnifiedDashboardShell;
