import { useEffect, useRef, useState, type ReactNode } from 'react';

type SnowDisplayPopoverProps = {
  content: ReactNode;
};

const SnowDisplayPopover = ({ content }: SnowDisplayPopoverProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleOutsidePointerDown = (event: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleOutsidePointerDown);

    return () => {
      document.removeEventListener('mousedown', handleOutsidePointerDown);
    };
  }, [isOpen]);

  return (
    <div ref={containerRef} className="snow-display-popover">
      <button
        type="button"
        className="btn btn-sm btn-light border shadow-sm snow-display-popover__button"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
        aria-label={isOpen ? 'Collapse layers panel' : 'Expand layers panel'}
        title="Layers"
      >
        <i className="bi bi-layers" aria-hidden="true"></i>
        <span className="snow-display-popover__button-label">Layers</span>
      </button>

      {isOpen && <div className="snow-display-popover__panel">{content}</div>}
    </div>
  );
};

export default SnowDisplayPopover;
