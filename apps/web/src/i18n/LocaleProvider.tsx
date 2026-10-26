/** Typed, complete locale dictionaries; only language preference uses localStorage. */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import en from "./en.json";
import da from "./da.json";

type Locale = "en" | "da";
type Messages = typeof en;
const dictionaries: Record<Locale, Messages> = { en, da };
const LocaleContext = createContext<{
  locale: Locale;
  setLocale: (value: Locale) => void;
  t: Messages;
} | null>(null);

/** Read a validated preference; storage denial must not prevent the UI from loading. */
function initialLocale(): Locale {
  try {
    return localStorage.getItem("sii.locale") === "da" ? "da" : "en";
  } catch {
    return "en";
  }
}

/** Synchronize document language and harmless preference; never infer user permissions. */
export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(initialLocale);
  useEffect(() => {
    document.documentElement.lang = locale;
    try {
      localStorage.setItem("sii.locale", locale);
    } catch {
      /* Private storage is optional. */
    }
  }, [locale]);
  return (
    <LocaleContext.Provider
      value={{ locale, setLocale, t: dictionaries[locale] }}
    >
      {children}
    </LocaleContext.Provider>
  );
}

/** Require an explicit provider so missing localization fails during development. */
export function useLocale() {
  const context = useContext(LocaleContext);
  if (!context) throw new Error("LocaleProvider is required");
  return context;
}
