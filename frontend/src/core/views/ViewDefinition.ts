import type { ReactNode } from 'react';

export type ViewDefinition = {
  id: string;
  label: string;
  leftSection?: ReactNode;
  description?: string;
};
