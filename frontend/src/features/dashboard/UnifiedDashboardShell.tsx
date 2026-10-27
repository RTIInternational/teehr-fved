import type { ReactNode } from 'react';

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
};

const renderOverlayCard = (overlay?: OverlayCardProps) => {
  if (!overlay) return null;

  return (
    <div className={`unified-dashboard-shell__card ${overlay.className ?? ''}`.trim()}>
      {overlay.content}
    </div>
  );
};

const UnifiedDashboardShell = ({
  mapContent,
  desktopTopLeftCard,
  desktopTopRightCard,
  desktopBottomCard,
  mobileBottomSheet,
}: UnifiedDashboardShellProps) => {
  return (
    <div className="unified-dashboard-shell">
      <div className="unified-dashboard-shell__map">{mapContent}</div>

      {desktopTopLeftCard && (
        <div className="unified-dashboard-shell__overlay unified-dashboard-shell__overlay--top-left d-none d-md-block">
          {renderOverlayCard(desktopTopLeftCard)}
        </div>
      )}

      {desktopTopRightCard && (
        <div className="unified-dashboard-shell__overlay unified-dashboard-shell__overlay--top-right d-none d-md-block">
          {renderOverlayCard(desktopTopRightCard)}
        </div>
      )}

      {desktopBottomCard && (
        <div className="unified-dashboard-shell__overlay unified-dashboard-shell__overlay--bottom d-none d-md-block">
          {renderOverlayCard(desktopBottomCard)}
        </div>
      )}

      {mobileBottomSheet && (
        <div className="unified-dashboard-shell__mobile-sheet d-md-none">
          {renderOverlayCard(mobileBottomSheet)}
        </div>
      )}
    </div>
  );
};

export default UnifiedDashboardShell;
