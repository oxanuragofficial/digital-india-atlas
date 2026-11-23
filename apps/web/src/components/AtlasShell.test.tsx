import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AtlasShell from "./AtlasShell";

// The real map needs WebGL, which jsdom does not provide.
vi.mock("./map/MapLoader", () => ({ default: () => <div data-testid="map-stub" /> }));
vi.mock("./ApiStatusBadge", () => ({ default: () => <span>api-badge-stub</span> }));

describe("AtlasShell", () => {
  it("renders the title, the map area and the information panel", () => {
    render(<AtlasShell />);
    expect(screen.getByRole("heading", { level: 1, name: "Digital India Atlas" })).toBeVisible();
    expect(screen.getByTestId("map-stub")).toBeInTheDocument();
    expect(screen.getByLabelText("Atlas information")).toBeInTheDocument();
  });

  it("states honestly that no datasets are loaded", () => {
    render(<AtlasShell />);
    expect(screen.getByText("No datasets loaded")).toBeInTheDocument();
  });

  it("shows basemap attribution links to OpenFreeMap and OpenStreetMap", () => {
    render(<AtlasShell />);
    expect(screen.getByRole("link", { name: "OpenFreeMap" })).toHaveAttribute(
      "href",
      "https://openfreemap.org",
    );
    expect(screen.getByRole("link", { name: /OpenStreetMap contributors/ })).toHaveAttribute(
      "href",
      "https://www.openstreetmap.org/copyright",
    );
  });

  it("toggles the mobile info panel and keeps aria-expanded in sync", () => {
    render(<AtlasShell />);
    const toggle = screen.getByRole("button", { name: "Info" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Hide info" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});
