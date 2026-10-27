export type SemanticState = 'default' | 'hover' | 'focus' | 'disabled';

export type SemanticStateColors = Record<SemanticState, string>;

export interface ThemeColorContract {
  surfaces: {
    appBackground: string;
    panelBackground: string;
    subtleBackground: string;
    interactiveBackground: string;
  };
  text: {
    primary: string;
    secondary: string;
    onDark: string;
    link: string;
  };
  borders: {
    default: string;
    strong: string;
    focus: string;
  };
  actions: {
    primary: SemanticStateColors;
    secondary: SemanticStateColors;
    ghost: SemanticStateColors;
  };
  status: {
    info: SemanticStateColors;
    success: SemanticStateColors;
    warning: SemanticStateColors;
    danger: SemanticStateColors;
  };
  dataViz: {
    useThemeTokens: false;
    note: string;
  };
}

export const BRAND_PRIMARY_PALETTE = {
  darkBlue3035: '#003E51',
  lightBlue633: '#007396',
  mustard1245: '#C69214',
  tan468: '#DDCBA4',
} as const;

export const BRAND_SECONDARY_PALETTE = {
  orange165: '#FF671F',
  green357: '#215732',
  purple2091: '#4C12A1',
  red484: '#9A3324',
} as const;

export const BRAND_METALLIC_ACCENTS = {
  gold: '#C5A65A',
  silver: '#B2B7BD',
  copper: '#B87333',
} as const;

export const THEME_COLOR_CONTRACT: ThemeColorContract = {
  surfaces: {
    appBackground: '#F6F2E8',
    panelBackground: '#FFFFFF',
    subtleBackground: BRAND_PRIMARY_PALETTE.tan468,
    interactiveBackground: '#F2EBDD',
  },
  text: {
    primary: BRAND_PRIMARY_PALETTE.darkBlue3035,
    secondary: '#2B6478',
    onDark: '#FFFFFF',
    link: BRAND_PRIMARY_PALETTE.lightBlue633,
  },
  borders: {
    default: '#C8B892',
    strong: BRAND_PRIMARY_PALETTE.darkBlue3035,
    focus: BRAND_PRIMARY_PALETTE.lightBlue633,
  },
  actions: {
    primary: {
      default: BRAND_PRIMARY_PALETTE.darkBlue3035,
      hover: '#00506A',
      focus: BRAND_PRIMARY_PALETTE.lightBlue633,
      disabled: '#7A98A4',
    },
    secondary: {
      default: BRAND_PRIMARY_PALETTE.mustard1245,
      hover: '#A97610',
      focus: BRAND_PRIMARY_PALETTE.lightBlue633,
      disabled: '#D6B56A',
    },
    ghost: {
      default: 'transparent',
      hover: BRAND_PRIMARY_PALETTE.tan468,
      focus: BRAND_PRIMARY_PALETTE.lightBlue633,
      disabled: 'transparent',
    },
  },
  status: {
    info: {
      default: BRAND_PRIMARY_PALETTE.lightBlue633,
      hover: '#005F7D',
      focus: BRAND_PRIMARY_PALETTE.lightBlue633,
      disabled: '#73AFC6',
    },
    success: {
      default: BRAND_SECONDARY_PALETTE.green357,
      hover: '#1A4729',
      focus: BRAND_PRIMARY_PALETTE.lightBlue633,
      disabled: '#7FA08A',
    },
    warning: {
      default: BRAND_PRIMARY_PALETTE.mustard1245,
      hover: '#A97610',
      focus: BRAND_PRIMARY_PALETTE.lightBlue633,
      disabled: '#D6B56A',
    },
    danger: {
      default: BRAND_SECONDARY_PALETTE.red484,
      hover: '#7F2A1D',
      focus: BRAND_PRIMARY_PALETTE.lightBlue633,
      disabled: '#BE8A80',
    },
  },
  dataViz: {
    useThemeTokens: false,
    note: 'Map metric ramps, chart trace palettes, and gridded scientific ramps remain unchanged by the UI theme token layer.',
  },
} as const;
