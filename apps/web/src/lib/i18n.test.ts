import { afterEach, describe, expect, it } from "vitest";

import i18n, { applyDocumentDirection } from "@/lib/i18n";

afterEach(async () => {
  await i18n.changeLanguage("en");
});

describe("i18n and RTL", () => {
  it("applies the Arabic locale and RTL direction", async () => {
    await i18n.changeLanguage("ar");
    expect(i18n.t("nav.overview")).toBe("نظرة عامة");
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
  });

  it("returns to LTR for English", () => {
    applyDocumentDirection("en");
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
  });
});
