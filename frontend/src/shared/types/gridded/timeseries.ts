// Empty datasets means the map's active dataset; null dates mean each dataset's latest year
export type GriddedTimeseriesFilters = {
  datasets: string[];
  start_date: string | null;
  end_date: string | null;
};
