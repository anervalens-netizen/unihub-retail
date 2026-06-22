# Simulare grila salariala 2026

Scriptul `backend/scripts/generate_salary_grid_simulation.py` aplica grila din
`/opt/Mobiup/docs/grila 2026.docx` pe lunile inchise
`2025-12` - `2026-05`.

## Rulare

```bash
cd /opt/Mobiup/unihub-retail
backend/venv/bin/python backend/scripts/generate_salary_grid_simulation.py
```

Output-uri:

- `/opt/Mobiup/docs/simulare_grila_noua_2025-12_2026-05.xlsx`
- `/opt/Mobiup/docs/comparatie_salarii_istorice_vs_grila_noua_2025-12_2026-05.xlsx`

## Reguli de comparatie

- Comparatia principala din workbook este cu salariile HR efectiv platite,
  nu cu formula grilei vechi. Payroll-ul poate contine incentive, prime si
  reglari care nu apar in formula standard.
- Comisionul de accesorii este calculat in paralel in trei scenarii:
  `2,5%`, `2,7%` si `3,0%`, toate cu prag de acces la minimum 80% target.
- Target agent: `target magazin / zile vanzare magazin * zile vanzare agent`.
- Bonusurile de target sunt cumulative: 200 / 300 / 400 lei la
  100% / 110% / 120%.
- Medie zilnica vs coleg nu are banda de 2 puncte.
- Orice criteriu calitativ cu 0 puncte elimina bonusul calitativ.
- ePay este 0 in simulare si se adauga manual.
- Salariul istoric comparabil este `TOTAL SALARIU - ore suplimentare`, fara
  bonuri de masa.
- Pragul de luna intreaga este 2.400 lei dupa agregarea randurilor mapate la
  acelasi agent.
- Asocierile HR-agent cu incredere sub 0,65 nu intra in comparatia financiara
  si raman in foaia `Mapari de verificat`.
- Foile `Total scenarii` si `Sumar lunar` compara bugetul total, salariul
  mediu per agent si diferenta fata de istoricul ajustat pentru fiecare procent.

## Control grila veche

Workbook-ul de comparatie incepe cu foaia `Citeste intai` si include:

- `Control grila veche Mai`: sumar exact grila veche versus grila noua 3%;
- `Detaliu grila veche Mai`: reconciliere pe agent si componente.

Controlul exact este limitat la mai 2026, singura luna pentru care exista local
arhiva completa `grile-salarii/outputs/archive/Mai 2026/Grile - Mai 2026.zip`.
Din ambele grile se scad bonurile de masa si plata orelor suplimentare. Grila
veche foloseste targetul manual salvat in fiecare sheet, iar grila noua foloseste
formula din `Agenti > Analiza agenti > Evaluare noua`.
