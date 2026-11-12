import { useEffect, useRef, useState } from 'react';

/** Fast loads finish before the indicator appears, so they never flash it. */
const SHOW_DELAY_MS = 300;
/** Once shown, stay long enough to read rather than blink out. */
const MIN_VISIBLE_MS = 400;

/**
 * Whether the indicator should be showing for `active`, after the show delay
 * and the minimum visible time.
 */
const useSettledVisibility = (active: boolean) => {
  const [visible, setVisible] = useState(false);
  const shownAtRef = useRef(0);

  useEffect(() => {
    if (active === visible) return;
    const wait = active
      ? SHOW_DELAY_MS
      : Math.max(0, MIN_VISIBLE_MS - (Date.now() - shownAtRef.current));
    const timer = setTimeout(() => {
      if (active) shownAtRef.current = Date.now();
      setVisible(active);
    }, wait);
    return () => clearTimeout(timer);
  }, [active, visible]);

  return visible;
};

/**
 * Debounced loading state for a map view, from a label such as
 * "Loading locations…" (null when ready): hidden for loads under
 * SHOW_DELAY_MS, then shown for at least MIN_VISIBLE_MS. Keeps the last label
 * while it lingers so the text doesn't blank out before it hides.
 */
export const useMapLoadingStatus = (label: string | null) => {
  const visible = useSettledVisibility(label !== null);
  const [lastLabel, setLastLabel] = useState(label ?? '');
  if (label !== null && label !== lastLabel) setLastLabel(label);
  return { visible, label: lastLabel };
};
