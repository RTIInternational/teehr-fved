import Plotly from 'plotly.js-dist-min';
import { type RefObject, useEffect } from 'react';

/**
 * Resizes a Plotly plot when its container changes size. Plotly's `responsive`
 * option only tracks window resizes, which misses panels that expand or collapse.
 */
export const usePlotResize = (ref: RefObject<HTMLElement | null>, active = true) => {
  useEffect(() => {
    const element = ref.current;
    if (!active || !element || typeof ResizeObserver === 'undefined') return;

    const observer = new ResizeObserver(() => {
      // Plotly sets `data` on the element once it has drawn a plot there.
      if (!('data' in element)) return;
      void Promise.resolve(Plotly.Plots.resize(element)).catch(() => {
        // The element can be detached mid-resize; the next render redraws it.
      });
    });
    observer.observe(element);

    return () => observer.disconnect();
  }, [ref, active]);
};
