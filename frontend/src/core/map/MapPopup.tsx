import { Text } from '@mantine/core';
import maplibregl, { type LngLatLike } from 'maplibre-gl';
import {
  useEffect,
  useEffectEvent,
  useImperativeHandle,
  useRef,
  useState,
  type ReactNode,
  type Ref,
} from 'react';
import { createPortal } from 'react-dom';

import { useMap } from './MapContext';

export type MapPopupHandle = {
  /** Moves the popup without a render, e.g. to follow the cursor on mousemove. */
  setLngLat: (lngLat: LngLatLike) => void;
};

type MapPopupProps = {
  /** Where the popup points. Applied on mount and whenever the value changes identity. */
  lngLat: LngLatLike;
  children: ReactNode;
  /** Shows a close button in the corner; `onClose` runs when it is used. */
  closeButton?: boolean;
  onClose?: () => void;
  maxWidth?: string;
  ref?: Ref<MapPopupHandle>;
};

/**
 * A MapLibre popup on the shared map whose content is React, rendered through a
 * portal so it keeps this tree's context (theme, queries, dashboard state). It is
 * shown while mounted: render it conditionally to open and close it.
 */
export const MapPopup = ({
  lngLat,
  children,
  closeButton = false,
  onClose,
  maxWidth = '300px',
  ref,
}: MapPopupProps) => {
  const map = useMap();
  const [container] = useState(() => document.createElement('div'));
  const popupRef = useRef<maplibregl.Popup>(null);
  // Read as an event so a new lngLat value doesn't recreate the popup.
  const currentLngLat = useEffectEvent(() => lngLat);
  const handleClose = useEffectEvent(() => onClose?.());

  useImperativeHandle(ref, () => ({ setLngLat: (next) => popupRef.current?.setLngLat(next) }), []);

  useEffect(() => {
    if (!map) return;
    const popup = new maplibregl.Popup({ closeButton, closeOnClick: false, maxWidth })
      .setDOMContent(container)
      .setLngLat(currentLngLat())
      .addTo(map);
    const onPopupClose = () => handleClose();
    popup.on('close', onPopupClose);
    popupRef.current = popup;

    return () => {
      // remove() fires 'close' too; only the close button should report it.
      popup.off('close', onPopupClose);
      popup.remove();
      popupRef.current = null;
    };
  }, [map, container, closeButton, maxWidth]);

  useEffect(() => {
    popupRef.current?.setLngLat(lngLat);
  }, [lngLat]);

  return createPortal(children, container);
};

/** The popup's heading. */
export const MapPopupTitle = ({ children }: { children: ReactNode }) => (
  <Text size="sm" fw={600} lh={1.3} mb={4}>
    {children}
  </Text>
);

/** A labelled value, e.g. "Lat: 39.7392". */
export const MapPopupField = ({ label, children }: { label: ReactNode; children: ReactNode }) => (
  <Text size="xs">
    <Text span inherit fw={600}>
      {label}:
    </Text>{' '}
    {children}
  </Text>
);

/** Secondary text below the values, such as what a click will do. */
export const MapPopupNote = ({ children }: { children: ReactNode }) => (
  <Text size="xs" c="dimmed" mt={6}>
    {children}
  </Text>
);
