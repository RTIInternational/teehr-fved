import { Button, Popover, Select, Stack } from '@mantine/core';
import { IconAdjustmentsHorizontal } from '@tabler/icons-react';
import { useState } from 'react';

import { useDistinctValues } from '@/shared/queries/distinctValues';
import { useTableProperties } from '@/shared/queries/queryables';
import type { MapFilters } from '@/shared/types/maps';
import { isMapMetric } from '@/shared/utils/mapMetrics';

type MapFilterButtonProps = {
  tables: string[];
  mapFilters: MapFilters;
  updateMapFilters: (filter: Partial<MapFilters>) => void;
};

const MapFilterButton = ({ tables, mapFilters, updateMapFilters }: MapFilterButtonProps) => {
  const [opened, setOpened] = useState(false);

  const configurations = useDistinctValues(tables[0], 'configuration_name');
  const variables = useDistinctValues(tables[0], 'variable_name');
  const tableProperties = useTableProperties(tables);

  // Unique map-colorable metrics across every table, so single- and multi-table
  // dashboards both work
  const metrics = [
    ...new Set(
      Object.values(tableProperties.data ?? {}).flatMap((tableProps) =>
        Array.isArray(tableProps?.metrics) ? tableProps.metrics : []
      )
    ),
  ].filter(isMapMetric);

  return (
    <Popover
      opened={opened}
      onChange={setOpened}
      position="bottom-end"
      // Fixed so the dropdown never extends the page while it is being positioned
      floatingStrategy="fixed"
      width={300}
      shadow="md"
      radius="md"
      // Stays open while the map is used, so changes can be watched as they apply
      closeOnClickOutside={false}
    >
      <Popover.Target>
        <Button
          variant="default"
          leftSection={<IconAdjustmentsHorizontal size={16} />}
          onClick={() => setOpened((value) => !value)}
          aria-expanded={opened}
        >
          Display
        </Button>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="sm">
          <Select
            label="Configuration"
            placeholder="Select configuration..."
            data={Array.isArray(configurations.data) ? configurations.data : []}
            value={mapFilters.configuration}
            onChange={(configuration) => configuration && updateMapFilters({ configuration })}
            allowDeselect={false}
          />
          <Select
            label="Variable"
            placeholder="Select variable..."
            data={Array.isArray(variables.data) ? variables.data : []}
            value={mapFilters.variable}
            onChange={(variable) => variable && updateMapFilters({ variable })}
            allowDeselect={false}
          />
          <Select
            label="Color By Metric"
            placeholder="Select metric..."
            data={metrics}
            value={mapFilters.metricName ?? null}
            onChange={(metricName) =>
              metricName && isMapMetric(metricName) && updateMapFilters({ metricName })
            }
            allowDeselect={false}
          />
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
};

export default MapFilterButton;
