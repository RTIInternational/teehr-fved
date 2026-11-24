import { SimpleGrid, TextInput } from '@mantine/core';

type DateRangeInputsProps = {
  start: string | null;
  end: string | null;
  onStartChange: (value: string | null) => void;
  onEndChange: (value: string | null) => void;
  startLabel?: string;
  endLabel?: string;
  /** Validation message shown on the end input (e.g. when start is after end). */
  error?: string | null;
};

/**
 * Start/end `datetime-local` inputs, side by side once their container is wide
 * enough for both (it sizes to its container, not the viewport, so it also fits
 * narrow sidebars).
 */
const DateRangeInputs = ({
  start,
  end,
  onStartChange,
  onEndChange,
  startLabel = 'Start Date',
  endLabel = 'End Date',
  error,
}: DateRangeInputsProps) => (
  <SimpleGrid type="container" cols={{ base: 1, '448px': 2 }} spacing="sm" verticalSpacing="sm">
    <TextInput
      type="datetime-local"
      label={startLabel}
      value={start || ''}
      onChange={(e) => onStartChange(e.target.value || null)}
    />
    <TextInput
      type="datetime-local"
      label={endLabel}
      value={end || ''}
      error={error}
      onChange={(e) => onEndChange(e.target.value || null)}
    />
  </SimpleGrid>
);

export default DateRangeInputs;
