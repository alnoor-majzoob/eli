import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import ar from "../locales/ar/common.json";
import en from "../locales/en/common.json";

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { common: en },
      ar: { common: ar },
    },
    fallbackLng: "en",
    supportedLngs: ["en", "ar"],
    defaultNS: "common",
    interpolation: { escapeValue: false },
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
      lookupLocalStorage: "eil.language",
    },
  });

export function applyDocumentDirection(language: string | undefined): void {
  const resolved = language?.startsWith("ar") ? "ar" : "en";
  document.documentElement.lang = resolved;
  document.documentElement.dir = resolved === "ar" ? "rtl" : "ltr";
}

i18n.on("languageChanged", applyDocumentDirection);
applyDocumentDirection(i18n.resolvedLanguage ?? "en");

export default i18n;
