import {
  Button,
  Checkbox,
  Combobox,
  Group,
  Input,
  InputBase,
  ScrollArea,
  useCombobox,
  type InputBaseProps,
} from '@mantine/core';

import classes from './MultiSelectDropdown.module.css';

type MultiSelectDropdownProps = Omit<InputBaseProps, 'value' | 'onChange'> & {
  data?: string[];
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
};

/**
 * Checkbox multi-select that summarizes the selection ("3 of 10 selected")
 * instead of rendering each value as a pill. Remaining props go to InputBase
 * (label, size, loading, disabled, ...).
 */
const MultiSelectDropdown = ({
  data = [],
  value,
  onChange,
  placeholder,
  ...inputProps
}: MultiSelectDropdownProps) => {
  const combobox = useCombobox({
    onDropdownClose: () => combobox.resetSelectedOption(),
  });

  const toggle = (item: string) =>
    onChange(value.includes(item) ? value.filter((v) => v !== item) : [...value, item]);

  const summary =
    value.length === 0
      ? null
      : value.length === data.length
        ? 'All selected'
        : `${value.length} of ${data.length} selected`;

  // Keep focus on the target so keyboard navigation still works after clicking a header button.
  const keepFocus = (event: React.MouseEvent) => event.preventDefault();

  return (
    <Combobox store={combobox} onOptionSubmit={toggle}>
      <Combobox.Target targetType="button">
        <InputBase
          component="button"
          type="button"
          pointer
          rightSection={
            value.length > 0 ? (
              <Combobox.ClearButton onClear={() => onChange([])} />
            ) : (
              <Combobox.Chevron />
            )
          }
          rightSectionPointerEvents={value.length > 0 ? 'all' : 'none'}
          onClick={() => combobox.toggleDropdown()}
          {...inputProps}
        >
          {summary ?? <Input.Placeholder>{placeholder}</Input.Placeholder>}
        </InputBase>
      </Combobox.Target>

      <Combobox.Dropdown>
        {data.length > 0 && (
          <Combobox.Header>
            <Group gap="xs">
              <Button
                variant="subtle"
                size="compact-xs"
                onMouseDown={keepFocus}
                onClick={() => onChange([...data])}
              >
                Select All
              </Button>
              <Button
                variant="subtle"
                color="red"
                size="compact-xs"
                onMouseDown={keepFocus}
                onClick={() => onChange([])}
              >
                Clear All
              </Button>
            </Group>
          </Combobox.Header>
        )}

        <Combobox.Options>
          <ScrollArea.Autosize mah={250} type="scroll">
            {data.length === 0 && <Combobox.Empty>No options available</Combobox.Empty>}
            {data.map((item) => (
              <Combobox.Option value={item} key={item} active={value.includes(item)}>
                <Group gap="sm" wrap="nowrap">
                  <Checkbox
                    checked={value.includes(item)}
                    readOnly
                    tabIndex={-1}
                    aria-hidden
                    size="xs"
                    className={classes.checkbox}
                  />
                  <span>{item}</span>
                </Group>
              </Combobox.Option>
            ))}
          </ScrollArea.Autosize>
        </Combobox.Options>
      </Combobox.Dropdown>
    </Combobox>
  );
};

export default MultiSelectDropdown;
