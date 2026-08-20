import { useEffect } from 'react';
import DashboardPanel from '../../shared/components/DashboardPanel';
import GriddedControls from './components/GriddedControls';
import GriddedMapComponent from './components/GriddedMapComponent';
import GriddedTimeseriesPanel from './components/GriddedTimeseriesPanel';
import { useGriddedDashboard, ActionTypes } from './DashboardContext';
import { useGriddedDataFetching } from './hooks/useGriddedDataFetching';
import { useGriddedVariableStyles } from './hooks/useGriddedVariableStyles';

const Dashboard = () => {
  const { state, dispatch } = useGriddedDashboard();
  const { runTimeseriesQuery } = useGriddedDataFetching();
  const { resetStyles, applyVariableStyleIfNew } = useGriddedVariableStyles();

  // Run timeseries query when the user clicks a point on the map
  useEffect(() => {
    if (state.clickedPoint) {
      runTimeseriesQuery(state.clickedPoint.lon, state.clickedPoint.lat);
    }
  }, [state.clickedPoint, runTimeseriesQuery]);

  // Reset style-tracking when dataset changes
  useEffect(() => {
    if (state.mapFilters.dataset) {
      resetStyles();
    }
  }, [state.mapFilters.dataset, resetStyles]);

  // Auto-apply variable-specific default styles on first selection of each variable
  useEffect(() => {
    applyVariableStyleIfNew(state.mapFilters.variable);
  }, [state.mapFilters.variable, applyVariableStyleIfNew]);

  return (
    <div className="d-flex flex-column" style={{ height: 'calc(100dvh - 56px)', minHeight: 0 }}>
      <div className="container-fluid flex-grow-1 p-0" style={{ minHeight: 0, overflow: 'hidden' }}>
        <div
          className="dashboard-grid h-100"
          style={{
            display: 'grid',
            gridTemplateColumns: '13fr 7fr',
            gridTemplateRows: 'auto minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.8fr)',
            gap: '12px',
            padding: '12px',
            height: '100%',
            minHeight: 0,
            overflow: 'hidden',
          }}
        >
          {/* Error banner */}
          {state.error && (
            <div
              className="alert alert-danger alert-dismissible"
              role="alert"
              style={{ gridColumn: '1 / -1', gridRow: '1 / 2', zIndex: 1000, margin: 0 }}
            >
              <i className="bi bi-exclamation-triangle-fill me-2"></i>
              <strong>Error:</strong> {state.error}
              <button
                type="button"
                className="btn-close"
                onClick={() => dispatch({ type: ActionTypes.CLEAR_ERROR })}
                aria-label="Close"
              ></button>
            </div>
          )}

          {/* Map panel — upper left */}
          <div
            className="map-panel"
            style={{
              gridColumn: '1 / 2',
              gridRow: state.error ? '2 / 4' : '1 / 4',
              border: '1px solid #e0e0e0',
              borderRadius: '8px',
              overflow: 'hidden',
              position: 'relative',
              minHeight: 0,
            }}
          >
            <GriddedMapComponent />
          </div>

          {/* Controls panel — upper right */}
          <div
            style={{
              gridColumn: '2 / 3',
              gridRow: state.error ? '2 / 3' : '1 / 2',
              minHeight: 0,
              height: '680px',
            }}
          >
            <DashboardPanel>
              <GriddedControls />
            </DashboardPanel>
          </div>

          {/* Bottom full-width panel — timeseries plot */}
          <div
            style={{
              gridColumn: '1 / -1',
              gridRow: '4 / 5',
              minHeight: 0,
            }}
          >
            <GriddedTimeseriesPanel />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
