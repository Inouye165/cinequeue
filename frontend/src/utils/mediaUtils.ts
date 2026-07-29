/**
 * Formats TMDB poster paths or URLs into full, valid image URLs.
 * Handles full URLs, leading slashes (/path.jpg), relative paths, and missing values.
 */
export function formatPosterUrl(
  pathOrUrl?: string | null,
  size: "w185" | "w342" | "w500" | "original" = "w500"
): string | null {
  if (!pathOrUrl) return null;
  const trimmed = pathOrUrl.trim();
  if (!trimmed) return null;

  // Already a full HTTP(S) URL
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    return trimmed;
  }

  // TMDB relative path
  const cleanPath = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  return `https://image.tmdb.org/t/p/${size}${cleanPath}`;
}
