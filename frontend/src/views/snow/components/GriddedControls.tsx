import {
  Accordion,
  ActionIcon,
  Alert,
  Group,
  Input,
  Loader,
  NumberInput,
  Radio,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react';
import { useEffect, useId, useState } from 'react';

import { useDatasets } from '@/shared/queries/gridded/datasets';
import { usePolygonLayers } from '@/shared/queries/gridded/tiles';
import { useTimesteps } from '@/shared/queries/gridded/timesteps';
import { useVariableAttrs } from '@/shared/queries/gridded/variableAttrs';
import { useVariables } from '@/shared/queries/gridded/variables';
import { parseUtcTime, shortestStep } from '@/shared/utils/dates';

import { useDashboard, ActionTypes } from '../DashboardContext';
import { useCurrentTimestep } from '../hooks/useCurrentTimestep';
import { OVERLAY_LAYERS } from '../utils/overlayLayers';

import styles from './GriddedControls.module.css';

const COLOR_RAMPS = [
  { label: 'Plasma', value: 'raster/plasma' },
  { label: 'Turbo', value: 'raster/turbo' },
  { label: 'Viridis', value: 'raster/viridis' },
  { label: 'Inferno', value: 'raster/inferno' },
  { label: 'Blues', value: 'raster/Blues' },
  { label: 'RdBu', value: 'raster/RdBu' },
];

// Radio value for "no layer"; real ids come from the tiles API and OVERLAY_LAYERS.
const NO_LAYER = '__none__';

type ColorRangeInputsProps = {
  min: number;
  max: number;
  units?: string;
  onCommit: (range: { colorRampMin: number; colorRampMax: number }) => void;
};

/**
 * Min/max inputs that keep a local draft while typing, so a field can be cleared
 * or pass through an invalid range, and apply it on blur or Enter once valid.
 */
const ColorRangeInputs = ({ min, max, units, onCommit }: ColorRangeInputsProps) => {
  const [draft, setDraft] = useState<{ min: number | string; max: number | string }>({ min, max });

  // Reset the draft when the range changes elsewhere (e.g. a new variable's defaults)
  const [synced, setSynced] = useState({ min, max });
  if (synced.min !== min || synced.max !== max) {
    setSynced({ min, max });
    setDraft({ min, max });
  }

  const draftMin = typeof draft.min === 'number' ? draft.min : NaN;
  const draftMax = typeof draft.max === 'number' ? draft.max : NaN;
  const minError = Number.isFinite(draftMin) ? null : 'Enter a number';
  const maxError = !Number.isFinite(draftMax)
    ? 'Enter a number'
    : Number.isFinite(draftMin) && draftMin >= draftMax
      ? 'Max must be greater than Min'
      : null;

  const commit = () => {
    if (minError || maxError || (draftMin === min && draftMax === max)) return;
    onCommit({ colorRampMin: draftMin, colorRampMax: draftMax });
  };
  const commitOnEnter = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') commit();
  };
  const suffix = units ? ` (${units})` : '';

  return (
    <SimpleGrid cols={2} spacing="sm">
      <NumberInput
        label={`Min${suffix}`}
        value={draft.min}
        onChange={(value) => setDraft((d) => ({ ...d, min: value }))}
        onBlur={commit}
        onKeyDown={commitOnEnter}
        error={minError}
      />
      <NumberInput
        label={`Max${suffix}`}
        value={draft.max}
        onChange={(value) => setDraft((d) => ({ ...d, max: value }))}
        onBlur={commit}
        onKeyDown={commitOnEnter}
        error={maxError}
      />
    </SimpleGrid>
  );
};

const GriddedControls = () => {
  const timestepInputId = useId();
  const { state, dispatch } = useDashboard();
  const { mapFilters, activeOverlays, activePolygonLayer } = state;
  const { dataset, variable, timestepIndex, colorRamp, colorRampMin, colorRampMax } = mapFilters;

  const datasets = useDatasets();
  const variables = useVariables(dataset);
  const timesteps = useTimesteps(dataset);
  const variableAttrs = useVariableAttrs(dataset);

  const units = variable ? variableAttrs.data?.[variable]?.units : undefined;

  const currentTimestep = useCurrentTimestep() ?? '';
  const canStepBack = timestepIndex > 0;
  const canStepForward = timestepIndex < timesteps.data.length - 1;

  const polygonLayers = usePolygonLayers();

  // Auto-select variable when dataset is selected
  useEffect(() => {
    if (!dataset) return;
    if (variables.data.length === 0) return;

    const currentIsValid = !!variable && variables.data.includes(variable);
    if (currentIsValid) return;

    dispatch({
      type: ActionTypes.UPDATE_MAP_FILTERS,
      payload: { variable: variables.data[0], timestepIndex: 0 },
    });
  }, [dataset, variable, variables.data, dispatch]);

  // Daily or coarser data picks a date only; sub-daily data picks the hour too
  const isDaily = shortestStep(timesteps.data.map(parseUtcTime)) >= 24 * 60 * 60 * 1000;
  const pickerLength = isDaily ? 10 : 16;

  // Jump to the timestep nearest the picked date; times are naive UTC
  const selectTimestep = (value: string) => {
    if (!value || timesteps.data.length === 0) return;
    // A picked date takes the data's time of day, so steps at e.g. 23:00 match the same day
    const picked = parseUtcTime(isDaily ? value + currentTimestep.slice(10) : value);
    let closestIdx = 0;
    let closestDiff = Infinity;
    timesteps.data.forEach((ts, i) => {
      const diff = Math.abs(parseUtcTime(ts) - picked);
      if (diff < closestDiff) {
        closestDiff = diff;
        closestIdx = i;
      }
    });
    dispatch({ type: ActionTypes.UPDATE_MAP_FILTERS, payload: { timestepIndex: closestIdx } });
  };

  const updateMapFilters = (payload: Partial<typeof mapFilters>) =>
    dispatch({ type: ActionTypes.UPDATE_MAP_FILTERS, payload });

  return (
    <Stack gap="sm" p={4}>
      <Select
        label="Dataset"
        placeholder="Select dataset…"
        data={datasets.data}
        value={dataset}
        onChange={(selected) => updateMapFilters({ dataset: selected, timestepIndex: 0 })}
        allowDeselect={false}
        disabled={datasets.data.length === 0}
      />

      <Select
        label="Variable"
        placeholder="Select variable…"
        data={variables.data}
        value={variable}
        onChange={(selected) => updateMapFilters({ variable: selected, timestepIndex: 0 })}
        allowDeselect={false}
        disabled={!dataset || variables.data.length === 0}
      />

      <Input.Wrapper label="Time Step (UTC)" labelProps={{ htmlFor: timestepInputId }}>
        <Group gap={4} wrap="nowrap">
          <ActionIcon
            variant="default"
            size="input-sm"
            onClick={() => updateMapFilters({ timestepIndex: timestepIndex - 1 })}
            disabled={!canStepBack}
            aria-label="Previous time step"
          >
            <IconChevronLeft size={16} />
          </ActionIcon>
          <TextInput
            id={timestepInputId}
            type={isDaily ? 'date' : 'datetime-local'}
            value={currentTimestep.slice(0, pickerLength)}
            min={timesteps.data[0]?.slice(0, pickerLength)}
            max={timesteps.data[timesteps.data.length - 1]?.slice(0, pickerLength)}
            onChange={(e) => selectTimestep(e.target.value)}
            disabled={timesteps.data.length === 0}
            title="Pick a date or use the arrows to step"
            className={styles.timestepInput}
            classNames={{ input: styles.timestepInputField }}
          />
          <ActionIcon
            variant="default"
            size="input-sm"
            onClick={() => updateMapFilters({ timestepIndex: timestepIndex + 1 })}
            disabled={!canStepForward}
            aria-label="Next time step"
          >
            <IconChevronRight size={16} />
          </ActionIcon>
        </Group>
        {timesteps.data.length > 0 && (
          <Text size="xs" c="dimmed" mt={2}>
            {timestepIndex + 1} / {timesteps.data.length}
          </Text>
        )}
      </Input.Wrapper>

      <Accordion
        multiple
        chevronPosition="left"
        classNames={{ control: styles.sectionControl, item: styles.sectionItem }}
      >
        <Accordion.Item value="polygon-layers">
          <Accordion.Control>Polygon Layers</Accordion.Control>
          <Accordion.Panel>
            {polygonLayers.isLoading && (
              <Group gap="xs">
                <Loader size="xs" />
                <Text size="xs">Loading layers…</Text>
              </Group>
            )}
            {polygonLayers.isError && (
              <Alert color="yellow" p="xs" fz="xs">
                {polygonLayers.error.message}
              </Alert>
            )}
            {!polygonLayers.isLoading &&
              polygonLayers.data?.length === 0 &&
              !polygonLayers.isError && (
                <Text size="xs" c="dimmed">
                  No polygon layers available
                </Text>
              )}
            {!polygonLayers.isLoading && !!polygonLayers.data?.length && (
              <Radio.Group
                aria-label="Polygon layer"
                value={activePolygonLayer ?? NO_LAYER}
                onChange={(value) =>
                  dispatch({
                    type: ActionTypes.SET_ACTIVE_POLYGON_LAYER,
                    payload: value === NO_LAYER ? null : value,
                  })
                }
              >
                <Stack gap="xs">
                  <Radio size="xs" value={NO_LAYER} label="None" />
                  {polygonLayers.data.map((layer) => (
                    <Radio key={layer.id} size="xs" value={layer.id} label={layer.id} />
                  ))}
                </Stack>
              </Radio.Group>
            )}
          </Accordion.Panel>
        </Accordion.Item>

        <Accordion.Item value="overlay-layers">
          <Accordion.Control>Overlay Layers</Accordion.Control>
          <Accordion.Panel>
            {/* One overlay at a time: TOGGLE_OVERLAY replaces the active overlay */}
            <Radio.Group
              aria-label="Overlay layer"
              value={activeOverlays[0] ?? NO_LAYER}
              onChange={(value) => {
                const toggled = value === NO_LAYER ? activeOverlays[0] : value;
                if (toggled) dispatch({ type: ActionTypes.TOGGLE_OVERLAY, payload: toggled });
              }}
            >
              <Stack gap="xs">
                <Radio size="xs" value={NO_LAYER} label="None" />
                {OVERLAY_LAYERS.map((overlay) => (
                  <Radio key={overlay.id} size="xs" value={overlay.id} label={overlay.label} />
                ))}
              </Stack>
            </Radio.Group>
          </Accordion.Panel>
        </Accordion.Item>

        <Accordion.Item value="display-controls">
          <Accordion.Control>Display Controls</Accordion.Control>
          <Accordion.Panel>
            <Stack gap="sm">
              <Select
                label="Color Scale"
                data={COLOR_RAMPS}
                value={colorRamp}
                onChange={(value) => value && updateMapFilters({ colorRamp: value })}
                allowDeselect={false}
              />
              <ColorRangeInputs
                min={colorRampMin}
                max={colorRampMax}
                units={units}
                onCommit={updateMapFilters}
              />
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
};

export default GriddedControls;
