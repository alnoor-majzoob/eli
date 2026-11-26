import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReplayBadge, SimBadge, SyntheticBadge } from "@/components/badges";

describe("honest-labelling badges", () => {
  it("renders the SIM badge", () => {
    render(<SimBadge />);
    expect(screen.getByTestId("sim-badge")).toHaveTextContent(/SIM/i);
  });

  it("renders the REPLAY badge", () => {
    render(<ReplayBadge />);
    expect(screen.getByTestId("replay-badge")).toHaveTextContent(/REPLAY/i);
  });

  it("renders the SYNTHETIC badge", () => {
    render(<SyntheticBadge />);
    expect(screen.getByTestId("synthetic-badge")).toHaveTextContent(/SYNTHETIC/i);
  });
});
