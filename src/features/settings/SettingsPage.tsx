import { useEffect, useState } from "react";

import { useAuth } from "../../auth/AuthContext";
import { canAdministerImports, canExportReports } from "../../auth/permissions";
import { PageHeader } from "../../components/common/DesktopLayout";
import { SegmentedTabs } from "../../components/common/SegmentedTabs";
import { ExportsView } from "./ExportsView";
import { ImportsView } from "./ImportsView";
import { PreferencesView } from "./preferences/PreferencesView";
import { useSettingsExports } from "./hooks/useSettingsExports";
import { useSettingsImports } from "./hooks/useSettingsImports";
import type { SettingsSection } from "./types";

export interface SettingsPageProps {
  theme: string;
  setTheme: (theme: string) => void;
  onImportCompleted: (month: string) => void;
}

export function SettingsPage({
  theme,
  setTheme,
  onImportCompleted,
}: SettingsPageProps) {
  const { user } = useAuth();
  const identityKey = user?.profile.sub ?? "anonymous";
  const canImportSales = canAdministerImports(user?.profile);
  const canUseExports = canExportReports(user?.profile);
  const [section, setSection] = useState<SettingsSection>(
    canImportSales ? "imports" : canUseExports ? "exports" : "preferences",
  );
  const imports = useSettingsImports(
    Boolean(user) && canImportSales && section === "imports",
    onImportCompleted,
    identityKey,
    canImportSales,
  );
  const exports = useSettingsExports(
    Boolean(user) && section === "exports" && canUseExports,
    identityKey,
    canUseExports,
  );

  useEffect(() => {
    if (!canImportSales && section === "imports")
      setSection(canUseExports ? "exports" : "preferences");
    if (!canUseExports && section === "exports")
      setSection(canImportSales ? "imports" : "preferences");
  }, [canImportSales, canUseExports, section]);

  return (
    <div className="mx-auto max-w-6xl space-y-3 p-3 pb-24 pt-2 lg:max-w-none lg:space-y-4 lg:px-6 lg:py-3">
      <PageHeader
        className="lg:hidden"
        title="Setări"
        description="Administrare aplicație"
      />
      <SegmentedTabs<SettingsSection>
        ariaLabel="Secțiuni Setări"
        className="glass"
        options={[
          ...(canImportSales
            ? [{ value: "imports" as const, label: "Importuri" }]
            : []),
          ...(canUseExports
            ? [{ value: "exports" as const, label: "Exporturi" }]
            : []),
          { value: "preferences" as const, label: "Preferințe" },
        ]}
        value={section}
        onChange={setSection}
      />
      {section === "imports" && <ImportsView model={imports} />}
      {section === "exports" && <ExportsView model={exports} />}
      {section === "preferences" && (
        <PreferencesView
          theme={theme}
          setTheme={setTheme}
          showRestrictedNotice={!canImportSales && !canUseExports}
        />
      )}
    </div>
  );
}

export { SettingsPage as Settings };
export default SettingsPage;
