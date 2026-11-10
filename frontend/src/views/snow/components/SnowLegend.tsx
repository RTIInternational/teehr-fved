import { Group, Paper, ScrollArea, Stack, Text } from '@mantine/core';

import GriddedColorBar from '@/features/gridded/components/GriddedColorBar';
import { useDashboard } from '@/features/gridded/DashboardContext';
import { useTilesLegend } from '@/shared/queries/gridded/tiles';

import { useOverlayLegends } from '../hooks/useOverlayLegends';

type SnowLegendProps = {
  className?: string;
};

/** Color bar for the gridded layer plus the legends of active overlays. */
export const SnowLegend = ({ className }: SnowLegendProps) => {
  const { state } = useDashboard();
  const { dataset, variable, colorRamp, colorRampMin, colorRampMax } = state.mapFilters;

  const tilesLegend = useTilesLegend(dataset, variable, colorRamp, colorRampMin, colorRampMax);
  const overlayLegends = useOverlayLegends(state.activeOverlays);

  const colorLegend = dataset && variable ? tilesLegend.data : undefined;
  if (!colorLegend && overlayLegends.length === 0) return null;

  return (
    <Paper shadow="sm" radius="md" p="xs" withBorder className={className}>
      <ScrollArea.Autosize mah="40dvh">
        <Stack gap="sm">
          {colorLegend && <GriddedColorBar legend={colorLegend} />}
          {overlayLegends.map(({ id, label, entries }) => (
            <Stack key={id} gap={2}>
              <Text size="xs" fw={600}>
                {label}
              </Text>
              {entries.map((entry) => (
                <Group key={entry.label} gap={4} wrap="nowrap">
                  <img
                    src={`data:${entry.contentType};base64,${entry.imageData}`}
                    width={entry.width}
                    height={entry.height}
                    alt=""
                  />
                  <Text size="xs">{entry.label}</Text>
                </Group>
              ))}
            </Stack>
          ))}
        </Stack>
      </ScrollArea.Autosize>
    </Paper>
  );
};
