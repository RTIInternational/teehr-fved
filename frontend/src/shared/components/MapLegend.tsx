// Shared Map Legend Component - shows color scale for any dashboard
import { getMetricDisplay, getMetricLabel, metricDisplay } from '@/shared/utils/mapMetrics';

type MapLegendProps = {
  metric?: keyof typeof metricDisplay;
  floating?: boolean;
};

const MapLegend = ({ metric, floating = true }: MapLegendProps) => {
  if (!metric) return null;

  const display = getMetricDisplay(metric);
  if (!display) return null;

  const metricLabel = getMetricLabel(metric);

  return (
    <div
      className={
        floating ? 'card position-absolute bottom-0 start-0 m-3 shadow-sm' : 'card shadow-sm'
      }
      style={{
        minWidth: '150px',
        maxWidth: '220px',
        zIndex: floating ? 1000 : undefined,
        fontSize: '0.85rem',
      }}
    >
      <div className="card-header py-2">
        <h6 className="card-title mb-0 small">Legend</h6>
      </div>
      <div className="card-body py-2">
        <div className="small">
          <strong>{metricLabel}</strong>
        </div>
        {display.colors.map((color, i) => (
          <div key={i} className="d-flex align-items-center mt-1">
            <div
              style={{
                width: '12px',
                height: '12px',
                backgroundColor: color,
                border: '1px solid var(--color-border-default)',
                marginRight: '6px',
              }}
            ></div>
            <small>{display.stops[i]}</small>
          </div>
        ))}
      </div>
    </div>
  );
};

export default MapLegend;
