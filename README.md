# Promotor Avatar — posts diaris (al núvol)

Genera cada dia 3 posts (LinkedIn, X, Instagram) en veu impersonal sobre
l'obra de Sergi Castillo Lapeira i els programa a Buffer per a les 7:00 del
matí, amb una imatge pròpia i relacionada amb el contingut per a cada xarxa.
Primer prova Gemini; si la quota d'imatges no està disponible, fa servir una
fotografia CC0/domini públic d'Openverse i, com a última reserva, una
il·lustració simbòlica local sense text. No publica targetes tipogràfiques.
Els posts d'El Bon Diari fan servir la imatge real de la notícia, adaptada al
format de cada xarxa, amb la mateixa reserva contextual si la font falla.

La línia editorial promocional rota segons l'historial real: **llibres → Arrel
→ Sutsumu → GeniKids → El Bon Diari**. Això evita publicar dues vegades seguides
el mateix projecte encara que un dia no s'executi l'automatització. Cada text
continua passant també pel control de semblança amb els posts recents.

**On s'executa:** als servidors de GitHub (GitHub Actions), no al Mac. Així
no depèn que l'ordinador estigui engegat. Vegeu `.github/workflows/posts-diaris.yml`.

- Cada dia a ~11:00 (Madrid) prepara els posts de DEMÀ i els programa a les 7:00.
- És a prova de duplicats: si Buffer ja té un post d'aquell canal i dia, no en crea cap altre.
- Per provar-ho a mà: pestanya **Actions** del repositori → *Posts diaris a Buffer* → *Run workflow*.

**Claus (a Settings → Secrets and variables → Actions):**
`GEMINI_API_KEY` i `BUFFER_ACCESS_TOKEN`.

El codi és el mateix que la versió d'escriptori; aquí només hi ha el necessari
per a la preparació automàtica diària (sense el tauler web).
