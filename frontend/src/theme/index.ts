import { createTheme } from '@mantine/core';

export const FvedTheme = createTheme({
  colors: {
    usbrBlue: [
      '#d7f3fb',
      '#a9e6f9',
      '#7bd9f8',
      '#5ccef6',
      '#4ec7f6',
      '#46c4f7',
      '#39addc',
      '#2a9ac5',
      '#007396', // Official USBR light blue
      '#003E51', // Official USBR dark blue
    ],
    usbrGold: [
      '#fdf6e8',
      '#f3ebda',
      '#ddcba4', // Official USBR yellow
      '#f6dea5',
      '#f1cc74',
      '#ecbd4b',
      '#e8ae22',
      '#c69214', // Official USBR gold
      '#b7870b',
      '#9f7400',
    ],
  },
  primaryColor: 'usbrBlue',
  primaryShade: 8,
});
