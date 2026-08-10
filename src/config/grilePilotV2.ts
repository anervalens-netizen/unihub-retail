export interface GrilaPilotV2 {
  siteCode: string;
  locatie: string;
  firma: 'Mobicell' | 'Mobiup';
  sheetId: string;
}

export const GRILE_PILOT_V2: readonly GrilaPilotV2[] = [
  {
    siteCode: 'PROMEN',
    locatie: 'Mobicell Promenada',
    firma: 'Mobicell',
    sheetId: '1jcVCLHaujv0O2qlTPXG7b1IqGGVq8572p7pJFvEAgdg', // pragma: allowlist secret
  },
  {
    siteCode: 'MCRFBAL',
    locatie: 'Mobiup Carrefour Balotești',
    firma: 'Mobiup',
    sheetId: '1MusUrpTjkFyW2JefvJVdFOdx5ypUbKr1Hs-2SViihEo', // pragma: allowlist secret
  },
  {
    siteCode: 'CRFFEER',
    locatie: 'Mobiup Carrefour Feeria',
    firma: 'Mobiup',
    sheetId: '1bEWiDcg9tqWPeqQdw6hna_lsIIc16ozKMCutkVIAHu0', // pragma: allowlist secret
  },
  {
    siteCode: 'ORAUCHAN',
    locatie: 'Mobicell Oradea Auchan',
    firma: 'Mobicell',
    sheetId: '1ZxugdHXXhvPSFyxyOh9bipq11J2N872n7isAxRXMxuM', // pragma: allowlist secret
  },
  {
    siteCode: 'ORAUCH',
    locatie: 'Mobiup Oradea Auchan',
    firma: 'Mobiup',
    sheetId: '12ejRCcDRNdQqiz38S7BjTKNb-pSrJWW2UNclhFJUiCI', // pragma: allowlist secret
  },
] as const;
