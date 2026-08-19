import React, { useState, useEffect } from 'react';
import { Form, Row, Col, Button, InputGroup } from 'react-bootstrap';
import { useDatasets } from '@/shared/queries/gridded/datasets';
import { useTimesteps } from '@/shared/queries/gridded/timesteps';
import { useVariables } from '@/shared/queries/gridded/variables';
import { useGriddedDashboard, ActionTypes } from '../DashboardContext';
import { OVERLAY_LAYERS } from '../utils/overlayLayers';

const COLOR_RAMPS = [
  { label: 'Plasma', value: 'raster/plasma' },
  { label: 'Turbo', value: 'raster/turbo' },
  { label: 'Viridis', value: 'raster/viridis' },
  { label: 'Inferno', value: 'raster/inferno' },
  { label: 'Blues', value: 'raster/Blues' },
  { label: 'RdBu', value: 'raster/RdBu' },
];

const GriddedControls = () => {
  const [overlaysExpanded, setOverlaysExpanded] = useState(false);
  const [mapControlsExpanded, setMapControlsExpanded] = useState(false);
  const { state, dispatch } = useGriddedDashboard();
  const { mapFilters, activeOverlays, variableAttrs } = state;
  const { dataset, variable, timestepIndex, colorRamp, colorRampMin, colorRampMax } = mapFilters;

  const datasets = useDatasets();
  const variables = useVariables(dataset);
  const timesteps = useTimesteps(dataset);

  const units = variable ? variableAttrs[variable]?.units : undefined;

  const currentTimestep = timesteps.data[timestepIndex] ?? '';
  const canStepBack = timestepIndex > 0;
  const canStepForward = timestepIndex < timesteps.data.length - 1;

  const [timestepInput, setTimestepInput] = useState(currentTimestep);
  const [timestepEditing, setTimestepEditing] = useState(false);
  const [timestepInputError, setTimestepInputError] = useState(false);

  // Keep display in sync when stepping with buttons
  useEffect(() => {
    if (!timestepEditing) {
      setTimestepInput(currentTimestep);
      setTimestepInputError(false);
    }
  }, [currentTimestep, timestepEditing]);

  const commitTimestepInput = () => {
    setTimestepEditing(false);
    if (!timestepInput || timesteps.data.length === 0) return;
    const entered = new Date(timestepInput);
    if (isNaN(entered.getTime())) {
      setTimestepInputError(true);
      return;
    }
    let closestIdx = 0;
    let closestDiff = Infinity;
    timesteps.data.forEach((ts, i) => {
      const diff = Math.abs(new Date(ts).getTime() - entered.getTime());
      if (diff < closestDiff) {
        closestDiff = diff;
        closestIdx = i;
      }
    });
    setTimestepInputError(false);
    dispatch({ type: ActionTypes.UPDATE_MAP_FILTERS, payload: { timestepIndex: closestIdx } });
  };

  const handleTimestepKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') commitTimestepInput();
    if (e.key === 'Escape') {
      setTimestepEditing(false);
      setTimestepInput(currentTimestep);
      setTimestepInputError(false);
    }
  };

  const handleDatasetChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const selected = e.target.value || null;
    dispatch({
      type: ActionTypes.UPDATE_MAP_FILTERS,
      payload: { dataset: selected, timestepIndex: 0 },
    });
  };

  const handleVariableChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const selected = e.target.value || null;
    dispatch({
      type: ActionTypes.UPDATE_MAP_FILTERS,
      payload: { variable: selected, timestepIndex: 0 },
    });
  };

  const handlePrevTimestep = () => {
    if (canStepBack) {
      dispatch({
        type: ActionTypes.UPDATE_MAP_FILTERS,
        payload: { timestepIndex: timestepIndex - 1 },
      });
    }
  };

  const handleNextTimestep = () => {
    if (canStepForward) {
      dispatch({
        type: ActionTypes.UPDATE_MAP_FILTERS,
        payload: { timestepIndex: timestepIndex + 1 },
      });
    }
  };

  const handleColorRampChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    dispatch({ type: ActionTypes.UPDATE_MAP_FILTERS, payload: { colorRamp: e.target.value } });
  };

  const handleRangeChange = (field: string, value: string) => {
    const num = parseFloat(value);
    if (Number.isNaN(num)) return;
    if (field === 'colorRampMin' && num >= colorRampMax) return;
    if (field === 'colorRampMax' && num <= colorRampMin) return;
    dispatch({ type: ActionTypes.UPDATE_MAP_FILTERS, payload: { [field]: num } });
  };

  return (
    <div className="h-100 d-flex flex-column overflow-auto p-1">
      <Form>
        <Row className="g-2">
          {/* Dataset selector */}
          <Col md={12}>
            <Form.Group>
              <Form.Label className="small fw-bold">Dataset</Form.Label>
              <Form.Select
                size="sm"
                value={dataset ?? ''}
                onChange={handleDatasetChange}
                disabled={datasets.data.length === 0}
              >
                <option value="">Select dataset…</option>
                {datasets.data.map((ds) => (
                  <option key={ds} value={ds}>
                    {ds}
                  </option>
                ))}
              </Form.Select>
            </Form.Group>
          </Col>

          {/* Variable selector */}
          <Col md={12}>
            <Form.Group>
              <Form.Label className="small fw-bold">Variable</Form.Label>
              <Form.Select
                size="sm"
                value={variable ?? ''}
                onChange={handleVariableChange}
                disabled={!dataset || variables.data.length === 0}
              >
                <option value="">Select variable…</option>
                {variables.data.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </Form.Select>
            </Form.Group>
          </Col>

          {/* Timestep pager */}
          <Col md={12}>
            <Form.Label className="small fw-bold d-block">Time Step</Form.Label>
            <InputGroup size="sm">
              <Button
                variant="outline-secondary"
                onClick={handlePrevTimestep}
                disabled={!canStepBack}
                title="Previous time step"
              >
                &#9664;
              </Button>
              <Form.Control
                value={timestepInput}
                placeholder={variable ? 'No timesteps' : '—'}
                onChange={(e) => {
                  setTimestepEditing(true);
                  setTimestepInput(e.target.value);
                  setTimestepInputError(false);
                }}
                onBlur={commitTimestepInput}
                onKeyDown={handleTimestepKeyDown}
                disabled={timesteps.data.length === 0}
                isInvalid={timestepInputError}
                className="text-center"
                style={{ fontSize: '0.8rem' }}
                title="Enter a datetime string or use arrows to step"
              />
              <Button
                variant="outline-secondary"
                onClick={handleNextTimestep}
                disabled={!canStepForward}
                title="Next time step"
              >
                &#9654;
              </Button>
            </InputGroup>
            {timestepInputError && (
              <div style={{ fontSize: '0.7rem', color: '#dc3545', marginTop: '2px' }}>
                Invalid datetime — try e.g. 2024-01-15T12:00:00
              </div>
            )}
            {!timestepInputError && timesteps.data.length > 0 && (
              <div className="text-muted" style={{ fontSize: '0.75rem', marginTop: '2px' }}>
                {timestepIndex + 1} / {timesteps.data.length}
              </div>
            )}
          </Col>

          {/* Overlay layer toggles */}
          <Col md={12}>
            <button
              type="button"
              className="small btn btn-link p-0 text-decoration-none d-flex align-items-center gap-1"
              style={{ color: '#555658', fontWeight: 700 }}
              onClick={() => setOverlaysExpanded((v) => !v)}
              aria-expanded={overlaysExpanded}
            >
              <span style={{ fontSize: '0.65rem' }}>{overlaysExpanded ? '▼' : '▶'}</span>
              <span>Overlay Layers</span>
            </button>
            {overlaysExpanded && (
              <div className="mt-1">
                {OVERLAY_LAYERS.map((overlay) => (
                  <Form.Check
                    key={overlay.id}
                    type="checkbox"
                    id={`overlay-${overlay.id}`}
                    label={<span style={{ fontSize: '0.8rem' }}>{overlay.label}</span>}
                    checked={activeOverlays.includes(overlay.id)}
                    onChange={() =>
                      dispatch({ type: ActionTypes.TOGGLE_OVERLAY, payload: overlay.id })
                    }
                    className="mb-1"
                  />
                ))}
              </div>
            )}
          </Col>

          {/* Map controls (color ramp + range) */}
          <Col md={12}>
            <button
              type="button"
              className="small btn btn-link p-0 text-decoration-none d-flex align-items-center gap-1"
              style={{ color: '#555658', fontWeight: 700 }}
              onClick={() => setMapControlsExpanded((v) => !v)}
              aria-expanded={mapControlsExpanded}
            >
              <span style={{ fontSize: '0.65rem' }}>{mapControlsExpanded ? '▼' : '▶'}</span>
              <span>Map Controls</span>
            </button>
            {mapControlsExpanded && (
              <Row className="g-2 mt-0">
                <Col md={12}>
                  <Form.Group>
                    <Form.Label className="small fw-bold">Color Scale</Form.Label>
                    <Form.Select size="sm" value={colorRamp} onChange={handleColorRampChange}>
                      {COLOR_RAMPS.map((cr) => (
                        <option key={cr.value} value={cr.value}>
                          {cr.label}
                        </option>
                      ))}
                    </Form.Select>
                  </Form.Group>
                </Col>
                <Col md={6}>
                  <Form.Group>
                    <Form.Label className="small fw-bold">
                      Min{units ? ` (${units})` : ''}
                    </Form.Label>
                    <Form.Control
                      size="sm"
                      type="number"
                      value={colorRampMin}
                      onChange={(e) => handleRangeChange('colorRampMin', e.target.value)}
                    />
                  </Form.Group>
                </Col>
                <Col md={6}>
                  <Form.Group>
                    <Form.Label className="small fw-bold">
                      Max{units ? ` (${units})` : ''}
                    </Form.Label>
                    <Form.Control
                      size="sm"
                      type="number"
                      value={colorRampMax}
                      onChange={(e) => handleRangeChange('colorRampMax', e.target.value)}
                    />
                  </Form.Group>
                </Col>
              </Row>
            )}
          </Col>
        </Row>
      </Form>
    </div>
  );
};

export default GriddedControls;
