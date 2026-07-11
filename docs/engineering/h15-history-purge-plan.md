# H-15 — Plan separat pentru history purge

Cele 22 path-uri `reports/**` eliminate din HEAD rămân în istoric. Ele pot
conține artefacte comerciale sau forecast, deci purge-ul necesită aprobare
separată și nu se execută în PR #30. Cele 8 PNG din backupul public nu necesită
purge în lipsa datelor sensibile.

Într-o fereastră de mentenanță: oprire temporară a pushurilor, backup al tuturor
refs, rulare `git filter-repo` pe o clonă controlată, verificare cu `git rev-list`
și `git log`, ștergerea branch-urilor vechi care rețin bloburi, apoi force-push
coordonat pentru main și tag-urile relevante. Colaboratorii trebuie să recloneze.
Nu executa această operație în PR #30.
