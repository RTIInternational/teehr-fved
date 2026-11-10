import { Button, Popover, ScrollArea } from '@mantine/core';
import { IconStack2 } from '@tabler/icons-react';
import { useState } from 'react';

import GriddedControls from '@/features/gridded/components/GriddedControls';

import styles from './SnowLayersPopover.module.css';

/** Dataset, overlay and polygon layer controls behind a "Layers" button. */
export const SnowLayersPopover = () => {
  const [opened, setOpened] = useState(false);

  return (
    <Popover
      opened={opened}
      onChange={setOpened}
      position="bottom-end"
      // While kept mounted and hidden, the dropdown's position is computed at zero
      // size, so it first appears overhanging the viewport. With absolute
      // positioning that briefly adds a scrollbar, which resizes (and redraws)
      // the map; fixed elements never extend the page.
      floatingStrategy="fixed"
      // Must be a number: Mantine applies it inline via rem(), which corrupts CSS
      // math. The narrow-screen cap is max-width in the CSS module.
      width={380}
      shadow="md"
      radius="md"
      // GriddedControls must keep running its effects (e.g. picking a valid
      // variable) while closed; Activity, the default mode, would suspend them.
      keepMounted
      keepMountedMode="display-none"
      // Stays open while the map is used, so changes can be watched as they apply.
      closeOnClickOutside={false}
    >
      <Popover.Target>
        <Button
          variant="default"
          leftSection={<IconStack2 size={16} />}
          onClick={() => setOpened((value) => !value)}
          aria-expanded={opened}
        >
          Layers
        </Button>
      </Popover.Target>
      <Popover.Dropdown className={styles.dropdown}>
        <ScrollArea.Autosize mah="calc(100dvh - 8rem)">
          <GriddedControls />
        </ScrollArea.Autosize>
      </Popover.Dropdown>
    </Popover>
  );
};
