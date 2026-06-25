import ko from '../locales/ko.json';

type TranslationKey = string;

function resolvePath(obj: any, path: string) {
  return path.split('.').reduce((prev, curr) => {
    return prev ? prev[curr] : null;
  }, obj);
}

export function useTranslation() {
  const t = (key: TranslationKey): string => {
    // In a real app, you'd check a global state for the current locale.
    // We default to Korean in v1.
    const translation = resolvePath(ko, key);
    return translation || key;
  };

  return { t };
}
