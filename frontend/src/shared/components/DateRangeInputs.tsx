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

/** Start/end `datetime-local` inputs, side by side from the `sm` breakpoint up. */
const DateRangeInputs = ({
  start,
  end,
  onStartChange,
  onEndChange,
  startLabel = 'Start Date',
  endLabel = 'End Date',
  error,
}: DateRangeInputsProps) => (
  <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" verticalSpacing="sm">
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
