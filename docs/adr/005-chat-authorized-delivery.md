# ADR-005 — Livrare autorizată prin conversația operațională

**Status:** Accepted
**Date:** 2026-07-17
**Decision owner:** Retail Business și Operations

## Context

Fluxul de release `v2.0.1` a introdus o cale formală completă: PR, CI pe PR,
merge, CI pe `main`, artefact imutabil, aprobare locală one-time, backup,
migrare, deploy și verificare. Calea rămâne utilă pentru release-uri formale și
schimbări cu risc mare, dar folosirea ei ca unic mecanism pentru orice corecție
mică produce timp de așteptare și confirmări care nu adaugă valoare proporțională.

Operatorul aplicației lucrează cu agentul de execuție în aceeași conversație și
pe același host administrativ. Cererea explicită din conversație este o
autorizație operațională verificabilă pentru scopul descris; nu este necesar ca
operatorul să repete aceeași aprobare în terminal sau după fiecare etapă
tehnică.

## Decizie

Retail folosește două căi de livrare.

### Calea rapidă, implicită

Pentru corecții și funcționalități obișnuite, cererea explicită din conversația
activă autorizează agentul să ducă schimbarea cap-coadă:

1. inspectează sursa de adevăr și păstrează schimbările locale fără legătură;
2. implementează și inspectează diff-ul;
3. rulează verificările proporționale cu suprafața modificată;
4. înregistrează exact starea verificată într-un commit direct pe `main`;
5. face push în `origin/main`, fără a aștepta CI ca precondiție de deploy dacă
   verificările locale sunt suficiente;
6. construiește `dist/` pentru frontend și repornește numai serviciile afectate;
7. verifică health-ul local și calea de utilizator modificată;
8. urmărește și remediază orice eșec CI produs de sincronizare.

Un PR nu este obligatoriu și nu există pas de merge când schimbarea este comisă
direct pe `main`. Producția rulează cod comis local; dacă GitHub este
indisponibil, deployul poate continua după verificările locale, iar push-ul se
face ulterior.

### Calea controlată, la nevoie

PR-ul și/sau artefactul imutabil se folosesc când reduc un risc real: schimbări
de schemă, autentificare sau autorizare, secrete, proxy/rețea, infrastructura de
deploy, operații distructive, release-uri etichetate ori modificări ample cu
consumatori multipli. Pot fi folosite și la cererea explicită a operatorului.

Dacă agentul deschide un PR pentru o schimbare deja autorizată, autorizația
acoperă în mod continuu remedierea CI, marcarea ready, merge-ul, deployul și
verificarea live. Agentul nu cere o nouă confirmare pentru fiecare etapă și nu
cere operatorului să ruleze comenzi în terminal. Gate-ul one-time al căii cu
artefact poate fi executat de agent în sesiunea administrativă pe baza
autorizației din conversație.

## Verificări obligatorii

Rapid nu înseamnă neverificat. Pentru orice cale:

- testele relevante pentru codul schimbat sunt obligatorii;
- suita completă se rulează pentru schimbări transversale, release-uri sau când
  testele țintite nu acoperă suficient riscul;
- frontendul nu este live fără build, iar backendul/workerul nu este live fără
  restartul serviciului afectat;
- health-ul și comportamentul schimbat se verifică după deploy;
- înaintea migrărilor sau a scrierilor materiale se verifică backupul și
  rollbackul/roll-forward-ul;
- operațiile distructive trebuie să fie incluse explicit în scopul cererii.

Agentul se oprește numai dacă apare o extindere materială de scop, lipsesc
credențiale sau informații pe care nu le poate obține, ori este necesară o
decizie de business care nu rezultă din cerere. O etapă tehnică normală, un PR
deja deschis sau trecerea din merge în deploy nu constituie motiv de oprire.

## Trasabilitate și audit

Dovada minimă este formată din cererea din conversație, commitul Git, comenzile
de verificare raportate, starea serviciilor și verificarea live. Pentru calea cu
artefact se păstrează suplimentar runul CI, hashul artefactului, backupul și
înregistrarea deployului. GitHub rămâne istoric, copie externă și control
suplimentar; nu este autoritatea care înlocuiește cererea operatorului.

## Consecințe

Modificările uzuale nu mai așteaptă două cicluri CI și o aprobare repetată.
Mecanismele de release `v2.0.1` nu sunt șterse și pot fi activate proporțional
cu riscul. Orice document care cere PR, artefact și aprobare one-time pentru
toate modificările este supersedat de această decizie; regulile de siguranță
specifice datelor sau domeniului rămân valabile.
