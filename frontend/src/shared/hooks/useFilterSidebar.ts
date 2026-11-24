import { useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useState } from 'react';

/**
 * Open state for a `FilterSidebarLayout`. Below the `sm` breakpoint the sidebar
 * covers the content, so it starts closed there and `closeIfOverlay` hides it
 * once the user is done with it (e.g. after loading data).
 */
export const useFilterSidebar = () => {
  const theme = useMantineTheme();
  const overlay =
    useMediaQuery(`(max-width: ${theme.breakpoints.sm})`, undefined, {
      getInitialValueInEffect: false,
    }) ?? false;
  const [opened, setOpened] = useState(!overlay);

  return {
    opened,
    setOpened,
    closeIfOverlay: () => {
      if (overlay) setOpened(false);
    },
  };
};
