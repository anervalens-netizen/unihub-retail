import { ThemeSwitcher } from "../../../components/ThemeSwitcher";

export function PreferencesView({
  theme,
  setTheme,
  showRestrictedNotice,
}: {
  theme: string;
  setTheme: (theme: string) => void;
  showRestrictedNotice: boolean;
}) {
  return (
    <div className="glass rounded-3xl p-4">
      <h3 className="mb-1 text-sm font-bold">Aspect aplicație</h3>
      <p className="mb-3 text-xs text-slate-500">
        Preferința se păstrează pe acest dispozitiv. Pe desktop, tema poate fi
        schimbată și din bara laterală.
      </p>
      <ThemeSwitcher theme={theme} setTheme={setTheme} />
      {showRestrictedNotice && (
        <p className="mt-3 text-xs text-slate-500">
          Importurile si exporturile server-side sunt disponibile doar rolurilor
          manageriale.
        </p>
      )}
    </div>
  );
}
