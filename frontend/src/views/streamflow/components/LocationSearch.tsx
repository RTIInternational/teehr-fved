import { Autocomplete, Stack, Text, type ComboboxItem } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import type { Feature, FeatureCollection, Point } from 'geojson';
import { useMemo, useState } from 'react';

import type { MapLocation } from '@/shared/types/locations';

import { toMapLocation } from '../utils/locationFeatures';

const MAX_RESULTS = 15;

type SearchOption = ComboboxItem & { location: MapLocation };

const featureKey = (feature: Feature<Point>) =>
  `${String(feature.properties?.primary_location_id ?? '')}|${String(
    feature.properties?.secondary_location_id ?? ''
  )}`;

const matchesTerm = (feature: Feature<Point>, term: string) => {
  const properties = feature.properties ?? {};
  return [properties.primary_location_id, properties.secondary_location_id, properties.name].some(
    (value) =>
      String(value ?? '')
        .toLowerCase()
        .includes(term)
  );
};

type LocationSearchProps = {
  locations: FeatureCollection<Point> | undefined;
  onSelect: (location: MapLocation) => void;
};

/** Finds a location by primary ID, secondary ID or name. */
export const LocationSearch = ({ locations, onSelect }: LocationSearchProps) => {
  const [search, setSearch] = useState('');

  const options = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term || !locations?.features) return [];

    const results: SearchOption[] = [];
    for (const feature of locations.features) {
      if (results.length >= MAX_RESULTS) break;
      if (!matchesTerm(feature, term)) continue;
      const location = toMapLocation(feature);
      if (!location) continue;
      results.push({ value: featureKey(feature), label: location.name, location });
    }
    return results;
  }, [search, locations]);

  const optionsByValue = useMemo(
    () => new Map(options.map((option) => [option.value, option])),
    [options]
  );

  return (
    <Autocomplete
      aria-label="Search map locations"
      placeholder="Search by primary ID, secondary ID, or name"
      leftSection={<IconSearch size={16} />}
      clearable
      value={search}
      onChange={setSearch}
      data={options}
      // Options are already filtered and limited above.
      filter={({ options: unfiltered }) => unfiltered}
      onOptionSubmit={(value) => {
        const option = optionsByValue.get(value);
        if (option) onSelect(option.location);
      }}
      renderOption={({ option }) => {
        const { location } = optionsByValue.get(option.value) ?? {};
        return (
          <Stack gap={0}>
            <Text size="sm" fw={600}>
              {location?.name}
            </Text>
            <Text size="xs" c="dimmed">
              Primary: {location?.primary_location_id || 'N/A'}
            </Text>
            <Text size="xs" c="dimmed">
              Secondary: {location?.secondary_location_id || 'N/A'}
            </Text>
          </Stack>
        );
      }}
      maxDropdownHeight={260}
    />
  );
};
