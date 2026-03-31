export interface VisitFormData {
  data_raport: string | null;
  ora_trimitere: string | null;
  firma: string | null;
  regional: string | null;
  asm: string | null;
  magazin: string | null;
  site_code: string | null;
  durata_vizita_ore: number | null;
  curatenie: boolean;
  imagine: boolean;
  uniforma: boolean;
  afise: boolean;
  produse_promo: boolean;
  tpu: number | null;
  sticla: number | null;
  altele: number | null;
  avizat: boolean;
  avize: number | null;
  charisma: number | null;
  casa: number | null;
  incarcari_epay: number | null;
  incarcari_charisma: number | null;
  agent1_nume: string | null;
  agent1_perf: number | null;
  agent1_doi_pe_bon: number | null;
  agent1_focus: number | null;
  agent1_analiza: string | null;
  agent1_plan: string | null;
  agent2_nume: string | null;
  agent2_perf: number | null;
  agent2_doi_pe_bon: number | null;
  agent2_focus: number | null;
  agent2_analiza: string | null;
  agent2_plan: string | null;
  foto1: string | null;
  foto2: string | null;
  foto3: string | null;
  foto4: string | null;
  notes: string | null;
}

export const VISIT_DRAFT_KEY = 'visit_draft';
export const emptyPhotos = ['', '', '', ''];

export const complianceFields = [
  { key: 'curatenie', label: 'Curățenie' },
  { key: 'imagine', label: 'Imagine' },
  { key: 'uniforma', label: 'Uniformă' },
  { key: 'afise', label: 'Afișe' },
  { key: 'produse_promo', label: 'Produse Promo' },
] as const;

export const inventoryFields = [
  { key: 'avize', label: 'Avize' },
  { key: 'tpu', label: 'TPU' },
  { key: 'sticla', label: 'Sticlă' },
] as const;

export const cashFields = [
  { key: 'charisma', label: 'Charisma' },
  { key: 'casa', label: 'Casă' },
  { key: 'incarcari_epay', label: 'Încărcări E-Pay' },
  { key: 'incarcari_charisma', label: 'Încărcări Charisma' },
] as const;

export function defaultVisitFormData(): VisitFormData {
  return {
    data_raport: null,
    ora_trimitere: null,
    firma: null,
    regional: null,
    asm: null,
    magazin: null,
    site_code: null,
    durata_vizita_ore: null,
    curatenie: false,
    imagine: false,
    uniforma: false,
    afise: false,
    produse_promo: false,
    tpu: null,
    sticla: null,
    altele: null,
    avizat: false,
    avize: null,
    charisma: null,
    casa: null,
    incarcari_epay: null,
    incarcari_charisma: null,
    agent1_nume: null,
    agent1_perf: null,
    agent1_doi_pe_bon: null,
    agent1_focus: null,
    agent1_analiza: null,
    agent1_plan: null,
    agent2_nume: null,
    agent2_perf: null,
    agent2_doi_pe_bon: null,
    agent2_focus: null,
    agent2_analiza: null,
    agent2_plan: null,
    foto1: null,
    foto2: null,
    foto3: null,
    foto4: null,
    notes: null,
  };
}

export function formatLocalDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}
