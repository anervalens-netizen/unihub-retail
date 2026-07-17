# ADR-004 — Multiplicitatea rândurilor din importul de vânzări

**Status:** Accepted
**Date:** 2026-07-17
**Audit finding:** M-13, reclasificat
**Decision owner:** Retail Business și Backend/Data

## Context

Exportul cumulativ POS folosit de Retail conține coloanele de vânzare vizibile,
dar nu furnizează un identificator unic și stabil pentru linia sursă, un serial
de produs sau o poziție de bon. Același produs poate fi vândut de mai multe ori
pe același bon și poate apărea în rânduri separate cu valori identice în toate
coloanele disponibile.

Prin urmare, egalitatea tuplei formate din coloanele Excel nu demonstrează că
două rânduri reprezintă aceeași vânzare înregistrată de două ori. Folosirea
acestei tuple drept cheie de unicitate ar confunda egalitatea atributelor cu
identitatea faptului de vânzare.

Reconcilierea din 2026-07-17 a comparat multiseturile tranzacțiilor pentru
1–15 iulie din două snapshoturi cumulative consecutive. Cele 22.282 de rânduri
importabile, inclusiv multiplicitățile identice, au coincis exact. Acest lucru a
confirmat că repetarea valorilor este o proprietate stabilă a contractului
sursă, nu o dovadă suficientă de corupere a unui export.

## Decizie

Fiecare rând valid și importabil din workbook este un fapt de vânzare separat.
Multiplicitatea rândurilor se păstrează integral la parsare, persistență și
agregare.

Concret:

- importatorul nu respinge și nu elimină rânduri numai pentru că toate
  coloanele lor vizibile sunt identice;
- `Cantitate` este cantitatea aferentă fiecărui rând, iar raportarea însumează
  toate rândurile păstrate;
- pe calea vânzărilor sunt interzise `drop_duplicates`, o constrângere `UNIQUE`
  sau un hash de rând construit exclusiv din coloanele actuale;
- antetele duplicate rămân invalide, deoarece fac schema workbookului ambiguă;
- metadatele contradictorii pentru același `SiteCode` rămân invalide;
- retry-urile aceluiași fișier sunt deduplicate prin hashul conținutului în
  coadă, iar reimportul aceleiași luni înlocuiește atomic snapshotul lunar;
  acestea sunt controalele de idempotency și nu modifică multiplicitatea din
  interiorul fișierului.

Exemplu: două rânduri cu același bon, produs, preț și `Cantitate = 1`
reprezintă două unități, nu un singur rând care trebuie deduplicat.

## Controale și verificare

- `test_load_sales_dataframe_preserves_identical_sales_rows` fixează contractul
  de parsare;
- `test_identical_rows_are_preserved_as_separate_sales_facts` verifică în
  PostgreSQL numărul de rânduri, cantitatea și valoarea persistată;
- testele pentru antete duplicate, identificatori lipsă și metadate
  contradictorii rămân obligatorii;
- orice viitoare detecție de duplicate la nivel de rând trebuie să pornească de
  la un identificator unic furnizat de sursă și să supersedeze explicit acest
  ADR, după reconciliere business și migrare controlată.

## Consecințe

Aplicația evită pierderea sau subraportarea vânzărilor legitime. În același
timp, contractul sursă actual nu permite distingerea automată a unei repetări
legitime de o dublare accidentală internă a exportului. Această limitare este
acceptată explicit; controlul sigur rămâne reconcilierea totalurilor sursă și
idempotency la nivel de fișier și snapshot.

## Rollback

Reintroducerea respingerii sau deduplicării după coloanele actuale nu este un
rollback sigur, deoarece poate elimina vânzări reale. Regula poate fi schimbată
numai după introducerea unei identități unice de linie în sursă, reconcilierea
istorică a impactului și aprobarea unei decizii care supersedează acest ADR.
