import { useLayoutEffect, useState } from "react";

/** Share actual fixed-control height with the page's reserved bottom space. */
export function useFixedHeight<T extends HTMLElement>(property: string) {
  const [element, setElement] = useState<T | null>(null);
  useLayoutEffect(() => {
    if (!element) return;
    const measure = () => {
      document.documentElement.style.setProperty(
        property,
        `${element.getBoundingClientRect().height}px`,
      );
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => {
      observer.disconnect();
      document.documentElement.style.removeProperty(property);
    };
  }, [element, property]);
  return setElement;
}
