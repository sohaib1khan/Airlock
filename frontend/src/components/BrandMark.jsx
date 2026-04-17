/**
 * App mark for header, login, and other branded surfaces.
 * Uses the same asset as favicon / PWA icons.
 */
export function BrandMark({ className, size = 32 }) {
  return (
    <img
      src="/icon.svg"
      width={size}
      height={size}
      alt=""
      className={className}
      draggable={false}
      decoding="async"
    />
  );
}
