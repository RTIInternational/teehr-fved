// Fixed-size vertical color bar for the gridded layer, drawn from the tiles legend JSON so
// its size and position never depend on the value range or label widths.

import { Text } from '@mantine/core';

import type { TilesLegendResponse } from '@/shared/api/gridded/tiles';

import styles from './GriddedColorBar.module.css';

type GriddedColorBarProps = {
  legend: TilesLegendResponse;
};

// Bar and label sizes are fixed in GriddedColorBar.module.css
const TICK_COUNT = 5;
const GRADIENT_STOPS = 32;

// Exponent form keeps very small values to a fixed label width
const formatTick = (value: number): string =>
  value !== 0 && Math.abs(value) < 1e-3
    ? value.toExponential(2)
    : Number(value.toPrecision(3)).toString();

const GriddedColorBar = ({ legend }: GriddedColorBarProps) => {
  const [min, max] = legend.colorscalerange;
  const { stops } = legend;
  // Unset or 'extend' draws values above the max in the top color
  const topIsOpenEnded = legend.abovemaxcolor == null || legend.abovemaxcolor === 'extend';

  // Sample the legend's stops; plenty for a smooth CSS gradient
  const sampled = Array.from(
    { length: GRADIENT_STOPS },
    (_, i) => stops[Math.round((i / (GRADIENT_STOPS - 1)) * (stops.length - 1))]
  );
  const gradient = `linear-gradient(to top, ${sampled
    .map((s, i) => `${s.color} ${(i / (GRADIENT_STOPS - 1)) * 100}%`)
    .join(', ')})`;
  const ticks = Array.from(
    { length: TICK_COUNT },
    (_, i) => min + (i / (TICK_COUNT - 1)) * (max - min)
  );

  return (
    <div className={styles.root}>
      {legend.units && (
        <Text size="xs" fw={600} mb={6}>
          {legend.units}
        </Text>
      )}
      <div className={styles.scale}>
        <div className={styles.bar} style={{ background: gradient }} />
        <div className={styles.labels}>
          {ticks.map((value, i) => (
            <span
              key={i}
              className={styles.tick}
              style={{ bottom: `${(i / (TICK_COUNT - 1)) * 100}%` }}
            >
              {i === TICK_COUNT - 1 && topIsOpenEnded
                ? `≥ ${formatTick(value)}`
                : formatTick(value)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};

export default GriddedColorBar;
