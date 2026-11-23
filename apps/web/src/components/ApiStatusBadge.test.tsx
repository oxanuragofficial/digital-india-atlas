import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ApiStatusBadge from "./ApiStatusBadge";

vi.mock("@/lib/api", () => ({ fetchApiStatus: vi.fn() }));
import { fetchApiStatus } from "@/lib/api";

const mockedFetch = vi.mocked(fetchApiStatus);

beforeEach(() => mockedFetch.mockReset());

describe("ApiStatusBadge", () => {
  it("shows a checking state first, then online", async () => {
    mockedFetch.mockResolvedValue({ state: "online", detail: "API is reachable" });
    render(<ApiStatusBadge />);
    expect(screen.getByRole("status")).toHaveTextContent("Checking API…");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("API online"));
    expect(screen.getByRole("status")).toHaveAttribute("data-state", "online");
  });

  it("shows offline when the API is unreachable", async () => {
    mockedFetch.mockResolvedValue({ state: "offline", detail: "API is not reachable" });
    render(<ApiStatusBadge />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("API offline"));
  });
});
