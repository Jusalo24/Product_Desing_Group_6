import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

// Search box in the site header. Submitting opens the homepage with ?q=...,
// and MealSearchPage runs the search from that URL parameter.
export default function HeaderSearch() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const currentQuery = params.get("q") ?? "";
  const [value, setValue] = useState(currentQuery);

  useEffect(() => {
    setValue(currentQuery);
  }, [currentQuery]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const term = value.trim();
    navigate(term ? `/?q=${encodeURIComponent(term)}` : "/");
  }

  return (
    <form role="search" className="header-search" onSubmit={submit}>
      <input
        type="search"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="search recipes"
        aria-label="Search recipes"
      />
      <button type="submit" aria-label="Search">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <circle cx="10.5" cy="10.5" r="6.5" />
          <line x1="15.5" y1="15.5" x2="21" y2="21" />
        </svg>
      </button>
    </form>
  );
}
