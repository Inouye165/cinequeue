import { useState } from "react";

interface StarRatingProps {
  rating?: number | null;
  onRate?: (rating: number) => void;
  readOnly?: boolean;
  size?: "sm" | "md" | "lg";
}

export function StarRating({ rating = 0, onRate, readOnly = false, size = "md" }: StarRatingProps) {
  const [hoverRating, setHoverRating] = useState<number | null>(null);

  const currentRating = hoverRating !== null ? hoverRating : rating || 0;

  const sizePx = size === "sm" ? 16 : size === "lg" ? 28 : 22;

  const handleClick = (star: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (readOnly || !onRate) return;
    // If clicking the current rating, allow clearing it back to 0 or setting it
    onRate(rating === star ? 0 : star);
  };

  return (
    <div
      className={`star-rating-container ${readOnly ? "read-only" : "interactive"}`}
      style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}
      onMouseLeave={() => setHoverRating(null)}
    >
      {[1, 2, 3, 4, 5].map((star) => {
        const isFilled = star <= currentRating;
        return (
          <button
            key={star}
            type="button"
            className={`star-button ${isFilled ? "filled" : "empty"}`}
            onClick={(e) => handleClick(star, e)}
            onMouseEnter={() => !readOnly && setHoverRating(star)}
            disabled={readOnly}
            title={readOnly ? `${rating || 0} / 5 Stars` : `Rate ${star} star${star > 1 ? "s" : ""}`}
            style={{
              background: "none",
              border: "none",
              padding: "2px",
              cursor: readOnly ? "default" : "pointer",
              lineHeight: 1,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              transition: "transform 0.15s ease",
            }}
          >
            <svg
              width={sizePx}
              height={sizePx}
              viewBox="0 0 24 24"
              fill={isFilled ? "#FFB800" : "rgba(255, 255, 255, 0.15)"}
              stroke={isFilled ? "#FFB800" : "rgba(255, 255, 255, 0.3)"}
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{
                filter: isFilled ? "drop-shadow(0 0 4px rgba(255, 184, 0, 0.4))" : "none",
              }}
            >
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          </button>
        );
      })}
      {rating && rating > 0 ? (
        <span
          style={{
            fontSize: size === "sm" ? "0.75rem" : "0.85rem",
            fontWeight: 600,
            color: "#FFB800",
            marginLeft: "4px",
          }}
        >
          {rating}/5
        </span>
      ) : null}
    </div>
  );
}
