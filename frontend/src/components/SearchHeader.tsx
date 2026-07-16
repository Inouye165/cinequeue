

interface SearchHeaderProps {
  query: string;
  setQuery: (q: string) => void;
  onSubmit: (e: React.FormEvent) => void;
}

export function SearchHeader({ query, setQuery, onSubmit }: SearchHeaderProps) {
  return (
    <header className="hero">
      <div>
        <h1>Cinequeue</h1>
        <p>
          Track what you want to watch, see days until release, where to stream or buy,
          and skim reviews and headlines in one place.
        </p>
      </div>
      <form className="search-bar" onSubmit={onSubmit}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search movies and TV…"
        />
        <button type="submit">Search</button>
      </form>
    </header>
  );
}
