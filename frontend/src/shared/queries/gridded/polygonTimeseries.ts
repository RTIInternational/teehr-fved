import { skipToken, useQuery } from '@tanstack/react-query';

import { apiService } from '@/services/api';
import type { GriddedTimeseriesFilters } from '@/shared/types/gridded/timeseries';
import { parseUtcTime } from '@/shared/utils/dates';

// Default span without dates: 3 years before the map's date, as for point queries
const DEFAULT_SPAN_DAYS = 3 * 365;

type PolygonTimeseriesArgs = GriddedTimeseriesFilters & {
  locationId?: string;
  variable: string | null;
  // End of the default span: the map's date when the timeseries was loaded
  anchor?: string;
};

// Times are naive UTC, so shift in UTC and drop the zone again
const daysBefore = (time: string, days: number) => {
  const date = new Date(parseUtcTime(time));
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 19);
};

// Mean areal secondary timeseries of a polygon from the warehouse, one series per dataset
export const usePolygonTimeseries = ({
  locationId,
  datasets,
  variable,
  start_date,
  end_date,
  anchor,
}: PolygonTimeseriesArgs) => {
  const useDefaultSpan = !start_date && !end_date;
  const start = useDefaultSpan ? anchor && daysBefore(anchor, DEFAULT_SPAN_DAYS) : start_date;
  const end = useDefaultSpan ? anchor : end_date;

  return useQuery({
    queryKey: ['gridded', 'polygonTimeseries', locationId, datasets, variable, start, end],
    queryFn:
      locationId && variable && datasets.length > 0 && (!useDefaultSpan || anchor)
        ? () =>
            apiService.getSecondaryTimeseries(locationId, {
              configuration: datasets,
              variable,
              start_date: start ?? undefined,
              end_date: end ?? undefined,
            })
        : skipToken,
  });
};
