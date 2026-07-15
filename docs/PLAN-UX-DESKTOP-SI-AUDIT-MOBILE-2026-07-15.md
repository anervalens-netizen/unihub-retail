# Plan UX desktop și audit mobil — 2026-07-15

## Obiectiv

Uniformizarea celor 18 suprafețe desktop, reducerea densității inutile și clarificarea fluxurilor operaționale, urmate de auditarea și implementarea experienței mobile.

## Etape desktop

1. Sistem comun: taburi accesibile, text funcțional de minimum 12 px pe desktop, scrollbar vizibil și un singur scroll principal acolo unde nu este necesar un tabel intern.
2. Hub: denumiri KPI comerciale, status clar pentru forecast, intervale istorice rapide și acoperire vizite.
3. Focus: separarea bonurilor promo de unitățile promo, păstrarea indicatorilor operaționali originali pentru Incentive, selector persistent de concurs și selector lunar explicit pentru Focus.
4. Agenți: navigare Echipă/Acoperire/Listă, antet sticky și stare persistentă în Grile, scorul 0–100 implicit în Analiza agenți.
5. Management: overview managerial fără duplicarea vânzărilor, Calculator Target pe pași, Salarii împărțit în Overview/Magazine/Agenți și P&L cu variații și reconciliere vizibilă.
6. Setări: confirmare înainte de înlocuirea snapshotului, export ghidat în patru pași și preferințe explicite.
7. Acceptanță: typecheck, lint, teste frontend/backend, Playwright desktop, accesibilitate, build și verificare live.

## Status implementare

- [x] Sistem comun desktop
- [x] Hub
- [x] Focus
- [x] Agenți
- [x] Management
- [x] Setări
- [x] Acceptanță și publicare
- [x] Audit complet mobil după publicarea desktop
- [x] Implementarea recomandărilor mobile P0–P2
- [x] Teste responsive permanente și reverificare desktop

## Criterii pentru auditul mobil

- navigare și acces la acțiunile principale cu o singură mână;
- lipsa overflow-ului orizontal la nivel de pagină;
- tabele transformate în carduri sau cu prioritizare de coloane;
- touch target de minimum 44 px pentru acțiunile frecvente;
- ierarhie KPI lizibilă la 390 px;
- filtre, selectoare și drawere care nu blochează conținutul;
- contrast WCAG A/AA și comportament corect cu tastatura virtuală;
- coerență între starea desktop și mobil pentru filtre, lună și secțiunea activă.
