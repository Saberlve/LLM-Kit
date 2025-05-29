import i18next from "i18next";
import { createI18nStore } from "svelte-i18next";

import en from "./en";

i18next.init({
  lng: "en",
  resources: {
    en: { translation: en }
  },
});

export default () => createI18nStore(i18next);

const t = i18next.t;

export { t };
