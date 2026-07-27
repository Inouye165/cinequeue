import { useState } from "react";
import { api } from "../api";
import { StarRating } from "./StarRating";

export interface PendingActionItem {
  id: string;
  tmdb_id?: number;
  media_type: "movie" | "tv";
  title: string;
  poster_path?: string;
  release_date?: string;
  rating: number;
  action_type: "rate_movie" | "add_monitoring";
  checked: boolean;
}

interface ActionConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  proposedItems: PendingActionItem[];
  onConfirm: (confirmedItems: PendingActionItem[]) => Promise<void>;
}

export function ActionConfirmationModal({
  isOpen,
  onClose,
  proposedItems,
  onConfirm,
}: ActionConfirmationModalProps) {
  const [items, setItems] = useState<PendingActionItem[]>(proposedItems);
  const [newTitle, setNewTitle] = useState("");
  const [searching, setSearching] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleToggleCheck = (id: string) => {
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, checked: !item.checked } : item))
    );
  };

  const handleRatingChange = (id: string, newRating: number) => {
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, rating: newRating } : item))
    );
  };

  const handleAddTitle = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setSearching(true);
    try {
      const searchRes = await api.search(newTitle.trim());
      if (searchRes && searchRes.length > 0) {
        const top = searchRes[0];
        const posterPath = "poster_path" in top ? (top as any).poster_path || null : null;
        const newItem: PendingActionItem = {
          id: `custom_${Date.now()}_${top.id}`,
          tmdb_id: top.id,
          media_type: top.media_type || "movie",
          title: top.title,
          poster_path: posterPath,
          release_date: top.release_date || undefined,
          rating: 5,
          action_type: "rate_movie",
          checked: true,
        };
        setItems((prev) => [...prev, newItem]);
        setNewTitle("");
      } else {
        const fallbackItem: PendingActionItem = {
          id: `custom_${Date.now()}`,
          media_type: "movie",
          title: newTitle.trim(),
          rating: 5,
          action_type: "rate_movie",
          checked: true,
        };
        setItems((prev) => [...prev, fallbackItem]);
        setNewTitle("");
      }
    } catch {
      const fallbackItem: PendingActionItem = {
        id: `custom_${Date.now()}`,
        media_type: "movie",
        title: newTitle.trim(),
        rating: 5,
        action_type: "rate_movie",
        checked: true,
      };
      setItems((prev) => [...prev, fallbackItem]);
      setNewTitle("");
    } finally {
      setSearching(false);
    }
  };

  const handleConfirmAll = async () => {
    const checkedItems = items.filter((i) => i.checked);
    if (checkedItems.length === 0) {
      onClose();
      return;
    }
    setSubmitting(true);
    try {
      await onConfirm(checkedItems);
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  const selectedCount = items.filter((i) => i.checked).length;

  return (
    <div className="modal-backdrop" onClick={onClose} style={{ zIndex: 1100 }}>
      <div
        className="modal-content confirmation-modal"
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: "600px",
          width: "90%",
          maxHeight: "85vh",
          display: "flex",
          flexDirection: "column",
          borderRadius: "16px",
          background: "linear-gradient(135deg, #181928 0%, #11121d 100%)",
          border: "1px solid rgba(255, 184, 0, 0.25)",
          boxShadow: "0 20px 50px rgba(0,0,0,0.8), 0 0 30px rgba(255, 184, 0, 0.15)",
          overflow: "hidden",
        }}
      >
        <div className="mobile-sheet-handle" aria-hidden="true" />
        <div
          style={{
            padding: "20px 24px",
            borderBottom: "1px solid rgba(255, 255, 255, 0.1)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: "1.25rem", color: "#FFB800", display: "flex", alignItems: "center", gap: "8px" }}>
              🛡️ Confirm Agent Actions ({selectedCount} Selected)
            </h2>
            <p style={{ margin: "4px 0 0", fontSize: "0.85rem", color: "#9ca3af" }}>
              Review proposed titles, uncheck unwanted items, edit ratings, or search to add more before saving.
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "#9ca3af",
              fontSize: "1.5rem",
              cursor: "pointer",
              padding: "0 8px",
            }}
          >
            &times;
          </button>
        </div>

        <div style={{ padding: "20px 24px", overflowY: "auto", flex: 1 }}>
          {/* Add Title Form */}
          <form onSubmit={handleAddTitle} style={{ display: "flex", gap: "8px", marginBottom: "20px" }}>
            <input
              type="text"
              placeholder="+ Add another title to this list..."
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              style={{
                flex: 1,
                padding: "10px 14px",
                borderRadius: "8px",
                background: "rgba(255, 255, 255, 0.06)",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                color: "#fff",
                fontSize: "0.9rem",
              }}
            />
            <button
              type="submit"
              disabled={searching || !newTitle.trim()}
              style={{
                padding: "10px 16px",
                borderRadius: "8px",
                background: "rgba(255, 184, 0, 0.2)",
                color: "#FFB800",
                border: "1px solid rgba(255, 184, 0, 0.4)",
                fontWeight: 600,
                cursor: searching || !newTitle.trim() ? "not-allowed" : "pointer",
                fontSize: "0.85rem",
              }}
            >
              {searching ? "Searching..." : "Add Title"}
            </button>
          </form>

          {/* Action List */}
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {items.map((item) => (
              <div
                key={item.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "12px",
                  padding: "12px 16px",
                  borderRadius: "10px",
                  background: item.checked ? "rgba(255, 184, 0, 0.08)" : "rgba(255, 255, 255, 0.03)",
                  border: item.checked ? "1px solid rgba(255, 184, 0, 0.3)" : "1px solid rgba(255, 255, 255, 0.08)",
                  opacity: item.checked ? 1 : 0.5,
                  transition: "all 0.2s ease",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "12px", flex: 1, minWidth: 0 }}>
                  <input
                    type="checkbox"
                    checked={item.checked}
                    onChange={() => handleToggleCheck(item.id)}
                    style={{
                      width: "18px",
                      height: "18px",
                      accentColor: "#FFB800",
                      cursor: "pointer",
                    }}
                  />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontWeight: 600, color: "#fff", fontSize: "0.95rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {item.title}
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "#9ca3af", marginTop: "2px" }}>
                      {item.action_type === "rate_movie" ? "Rating & Watched List" : "Add to Queue"}
                    </div>
                  </div>
                </div>

                {item.checked && (
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <StarRating
                      rating={item.rating}
                      onRate={(r: number) => handleRatingChange(item.id, r)}
                      size="sm"
                    />
                    <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "#FFB800", width: "24px" }}>
                      {item.rating}★
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Footer Actions */}
        <div
          style={{
            padding: "16px 24px",
            borderTop: "1px solid rgba(255, 255, 255, 0.1)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            background: "rgba(0, 0, 0, 0.2)",
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: "10px 18px",
              borderRadius: "8px",
              background: "rgba(255, 255, 255, 0.1)",
              color: "#e5e7eb",
              border: "none",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Cancel All
          </button>
          <button
            type="button"
            onClick={handleConfirmAll}
            disabled={submitting || selectedCount === 0}
            style={{
              padding: "10px 24px",
              borderRadius: "8px",
              background: "#FFB800",
              color: "#000",
              border: "none",
              fontWeight: 700,
              cursor: submitting || selectedCount === 0 ? "not-allowed" : "pointer",
              boxShadow: "0 4px 12px rgba(255, 184, 0, 0.3)",
            }}
          >
            {submitting ? "Saving..." : `Confirm & Apply (${selectedCount})`}
          </button>
        </div>
      </div>
    </div>
  );
}
