import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ThemeToggle } from "@/components/theme-toggle";
import { ThemeProvider } from "@/lib/theme";

describe("theme toggle", () => {
  it("switches between light and dark", async () => {
    window.localStorage.setItem("eil.theme", "light");
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );

    expect(document.documentElement.classList.contains("dark")).toBe(false);
    await user.click(screen.getByTestId("theme-toggle"));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(window.localStorage.getItem("eil.theme")).toBe("dark");
  });
});
