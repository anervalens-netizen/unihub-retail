import type { Dispatch, MutableRefObject, SetStateAction } from 'react';

import type { SeasonalityMode } from '../../../components/SeasonalityControl';
import type { TargetCalculatorContext, TargetScenario } from '../api';

export type TargetScenarioActionDeps = {
  context: TargetCalculatorContext | null;
  scenario: TargetScenario | null;
  regionalFilter: string;
  targetMonth: string;
  totalTarget: string;
  minFloor: string;
  seasonalityMode: SeasonalityMode;
  dirty: boolean;
  dirtyRows: Set<string>;
  savingRows: Set<string>;
  scenarioRef: MutableRefObject<TargetScenario | null>;
  dirtyRowsRef: MutableRefObject<Set<string>>;
  editVersionsRef: MutableRefObject<Map<string, number>>;
  replaceScenario: (next: TargetScenario | null) => void;
  clearLocalEdits: () => void;
  setRegionalFilter: Dispatch<SetStateAction<string>>;
  setSelectedLocationCodes: Dispatch<SetStateAction<string[]>>;
  setBusy: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string | null>>;
  setConflictRetryAvailable: Dispatch<SetStateAction<boolean>>;
  setDirtyRows: Dispatch<SetStateAction<Set<string>>>;
  setSavingRows: Dispatch<SetStateAction<Set<string>>>;
};

export type PersistDraft = () => Promise<TargetScenario | null>;

