import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SearchFiltersPanel } from "../SearchFiltersPanel";
import type { SearchFilterState } from "../../types";

describe("SearchFiltersPanel", () => {
  const initialFilters: SearchFilterState = {
    query: "",
    actors: [],
    director: "",
    yearType: "any",
    mediaType: "all",
  };

  it("does not render when isOpen is false", () => {
    const { container } = render(
      <SearchFiltersPanel
        isOpen={false}
        onClose={() => {}}
        filters={initialFilters}
        onUpdateFilters={() => {}}
        onApplyAndSearch={() => {}}
        onResetFilters={() => {}}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it("adds multiple actors and removes an actor chip", () => {
    const handleUpdateFilters = vi.fn();
    render(
      <SearchFiltersPanel
        isOpen={true}
        onClose={() => {}}
        filters={{ ...initialFilters, actors: ["Tom Hanks"] }}
        onUpdateFilters={handleUpdateFilters}
        onApplyAndSearch={() => {}}
        onResetFilters={() => {}}
      />
    );

    expect(screen.getByText("Tom Hanks")).not.toBeNull();

    // Type a new actor and click Add
    const actorInput = screen.getByLabelText("Actor name");
    fireEvent.change(actorInput, { target: { value: "Meg Ryan" } });

    const addBtn = screen.getByRole("button", { name: "Add actor" });
    fireEvent.click(addBtn);

    expect(handleUpdateFilters).toHaveBeenCalledWith(
      expect.objectContaining({
        actors: ["Tom Hanks", "Meg Ryan"],
      })
    );

    // Remove actor chip
    const removeBtn = screen.getByRole("button", { name: "Remove actor Tom Hanks" });
    fireEvent.click(removeBtn);
    expect(handleUpdateFilters).toHaveBeenCalledWith(
      expect.objectContaining({
        actors: [],
      })
    );
  });

  it("handles director input and clearing", () => {
    const handleUpdateFilters = vi.fn();
    render(
      <SearchFiltersPanel
        isOpen={true}
        onClose={() => {}}
        filters={{ ...initialFilters, director: "Christopher Nolan" }}
        onUpdateFilters={handleUpdateFilters}
        onApplyAndSearch={() => {}}
        onResetFilters={() => {}}
      />
    );

    const clearBtn = screen.getByRole("button", { name: "Clear director" });
    fireEvent.click(clearBtn);
    expect(handleUpdateFilters).toHaveBeenCalledWith(
      expect.objectContaining({
        director: "",
      })
    );
  });

  it("switches year filter types and allows entering year values", () => {
    const handleUpdateFilters = vi.fn();
    const { rerender } = render(
      <SearchFiltersPanel
        isOpen={true}
        onClose={() => {}}
        filters={initialFilters}
        onUpdateFilters={handleUpdateFilters}
        onApplyAndSearch={() => {}}
        onResetFilters={() => {}}
      />
    );

    // Click "Exact Year" pill
    const exactPill = screen.getByRole("radio", { name: "Exact Year" });
    fireEvent.click(exactPill);
    expect(handleUpdateFilters).toHaveBeenCalledWith(
      expect.objectContaining({
        yearType: "exact",
      })
    );

    // Rerender with yearType="exact"
    rerender(
      <SearchFiltersPanel
        isOpen={true}
        onClose={() => {}}
        filters={{ ...initialFilters, yearType: "exact" }}
        onUpdateFilters={handleUpdateFilters}
        onApplyAndSearch={() => {}}
        onResetFilters={() => {}}
      />
    );

    const exactInput = screen.getByLabelText("Exact release year");
    fireEvent.change(exactInput, { target: { value: "1999" } });
    expect(handleUpdateFilters).toHaveBeenCalledWith(
      expect.objectContaining({
        year: 1999,
      })
    );

    // Rerender with yearType="before"
    rerender(
      <SearchFiltersPanel
        isOpen={true}
        onClose={() => {}}
        filters={{ ...initialFilters, yearType: "before" }}
        onUpdateFilters={handleUpdateFilters}
        onApplyAndSearch={() => {}}
        onResetFilters={() => {}}
      />
    );
    const beforeInput = screen.getByLabelText("Released before year");
    fireEvent.change(beforeInput, { target: { value: "2000" } });
    expect(handleUpdateFilters).toHaveBeenCalledWith(
      expect.objectContaining({
        yearBefore: 2000,
      })
    );

    // Rerender with yearType="after"
    rerender(
      <SearchFiltersPanel
        isOpen={true}
        onClose={() => {}}
        filters={{ ...initialFilters, yearType: "after" }}
        onUpdateFilters={handleUpdateFilters}
        onApplyAndSearch={() => {}}
        onResetFilters={() => {}}
      />
    );
    const afterInput = screen.getByLabelText("Released after year");
    fireEvent.change(afterInput, { target: { value: "2015" } });
    expect(handleUpdateFilters).toHaveBeenCalledWith(
      expect.objectContaining({
        yearAfter: 2015,
      })
    );

    // Rerender with yearType="range"
    rerender(
      <SearchFiltersPanel
        isOpen={true}
        onClose={() => {}}
        filters={{ ...initialFilters, yearType: "range" }}
        onUpdateFilters={handleUpdateFilters}
        onApplyAndSearch={() => {}}
        onResetFilters={() => {}}
      />
    );
    const fromInput = screen.getByLabelText("From year");
    fireEvent.change(fromInput, { target: { value: "1990" } });
    expect(handleUpdateFilters).toHaveBeenCalledWith(
      expect.objectContaining({
        yearFrom: 1990,
      })
    );
    const toInput = screen.getByLabelText("To year");
    fireEvent.change(toInput, { target: { value: "2005" } });
    expect(handleUpdateFilters).toHaveBeenCalledWith(
      expect.objectContaining({
        yearTo: 2005,
      })
    );
  });

  it("calls onApplyAndSearch when Apply button is clicked", () => {
    const handleApply = vi.fn();
    const handleClose = vi.fn();
    render(
      <SearchFiltersPanel
        isOpen={true}
        onClose={handleClose}
        filters={initialFilters}
        onUpdateFilters={() => {}}
        onApplyAndSearch={handleApply}
        onResetFilters={() => {}}
      />
    );

    const applyBtn = screen.getByRole("button", { name: "Apply & Search" });
    fireEvent.click(applyBtn);
    expect(handleApply).toHaveBeenCalled();
    expect(handleClose).toHaveBeenCalled();
  });
});
