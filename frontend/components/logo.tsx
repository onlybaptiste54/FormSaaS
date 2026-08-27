export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="logo-wrap" aria-label="Sillage">
      <svg className="logo-mark" viewBox="0 0 40 40" aria-hidden="true">
        <path d="M8 13.5c7.2 0 8.7 13 16.1 13 3.4 0 5.8-2.5 7.9-6.5" />
        <path d="M8 21c5.5 0 7.3 7.5 13.4 7.5" />
        <circle cx="8" cy="13.5" r="2" />
      </svg>
      {!compact && <span className="logo-word">sillage</span>}
    </div>
  );
}

