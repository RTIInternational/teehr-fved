// Shared Map Legend Component - shows color scale for any dashboard
import { ColorSwatch, Group, Paper, Stack, Text } from '@mantine/core';

import { getMetricDisplay, getMetricLabel, metricDisplay } from '@/shared/utils/mapMetrics';

type MapLegendProps = {
  metric?: keyof typeof metricDisplay;
};

const MapLegend = ({ metric }: MapLegendProps) => {
  if (!metric) return null;

  const display = getMetricDisplay(metric);
  if (!display) return null;

  return (
    <Paper shadow="sm" radius="md" p="xs" withBorder miw={150} maw={200}>
      <Stack gap={4}>
        <Text size="xs" fw={600}>
          {getMetricLabel(metric)}
        </Text>
        {display.colors.map((color, i) => (
          <Group key={i} gap={6} wrap="nowrap">
            <ColorSwatch color={color} size={12} radius={2} />
            <Text size="xs">{display.stops[i]}</Text>
          </Group>
        ))}
      </Stack>
    </Paper>
  );
};

export default MapLegend;
