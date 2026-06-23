# Promotor Avatar — posts diaris (al núvol)

Genera cada dia 3 posts (LinkedIn, X, Instagram) en veu impersonal sobre
l'obra de Sergi Castillo Lapeira i els programa a Buffer per a les 7:00 del
matí, amb una imatge pròpia per a cada xarxa (Imagen 4).

**On s'executa:** als servidors de GitHub (GitHub Actions), no al Mac. Així
no depèn que l'ordinador estigui engegat. Vegeu `.github/workflows/posts-diaris.yml`.

- Cada dia a ~11:00 (Madrid) prepara els posts de DEMÀ i els programa a les 7:00.
- És a prova de duplicats: si Buffer ja té un post d'aquell canal i dia, no en crea cap altre.
- Per provar-ho a mà: pestanya **Actions** del repositori → *Posts diaris a Buffer* → *Run workflow*.

**Claus (a Settings → Secrets and variables → Actions):**
`GEMINI_API_KEY` i `BUFFER_ACCESS_TOKEN`.

El codi és el mateix que la versió d'escriptori; aquí només hi ha el necessari
per a la preparació automàtica diària (sense el tauler web).
