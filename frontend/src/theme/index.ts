import { createTheme } from '@mantine/core';

export const FvedTheme = createTheme({
  colors: {
    usbrBlue: [
      '#defaff',
      '#b3edff',
      '#86e0fd',
      '#5ad4fc',
      '#3bc8fa',
      '#2eafe1',
      '#2088b0',
      '#007396', // Official USBR light blue
      '#003E51', // Official USBR dark blue
      '#00151d',
    ],
    usbrGold: [
      '#fff7dd',
      '#fbf4e4',
      '#ddcba4', // Official USBR yellow
      '#ceb57e',
      '#efc45b',
      '#c69214', // Official USBR gold
      '#a2780d',
      '#745507',
      '#463300',
      '#1b1000',
    ],
  },
  primaryColor: 'usbrBlue',
});
