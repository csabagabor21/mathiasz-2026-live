# Mathiász 2026 km — élő tábla + aznapi kép-ellenőrzés (AI nélkül)

## Működés
- `index.html` a publikus tábla (GitHub Pagesről megy, mindenkinek élőben).
- A táblán **csak az igazolt km** számít bele az összegbe.
- `.github/workflows/validate.yml` ellenőrzi a beküldéseket:
  1. **Azonnal**: a Form `apps-script/Code.gs` webhookja minden beküldéskor
     indítja (`repository_dispatch`), ~1–3 perc alatt fenn az eredmény.
  2. **Biztonsági háló**: 10 percenként időzített futás is van.
- Az ellenőrzés azt nézi, hogy a kép **aznap készült-e**, amikor feltöltötték —
  semmi AI, semmi kulcs:
  1. EXIF-felvétel dátuma (JPEG-eknél, ha van),
  2. különben Tesseract OCR kiolvassa a dátumot a képről
     (a Strava / Google Fit / Apple Health kiírja az edzés napját),
  3. ha egyik sem megy: „ellenőrzés alatt" (szervezői döntésre vár).

## Beüzemelés (egyszeri)
1. Google Drive: a Form feltöltési mappáját oszd meg olvasásra ezzel a címmel:
   `mathiasz-validator@summit-14b74.iam.gserviceaccount.com` (Megtekintő).
   Enélkül a validátor nem éri el a képeket, minden „ellenőrzés alatt" marad.
2. GitHub repo Secrets (`Settings → Secrets → Actions`): `GOOGLE_SA_KEY`
   (service account JSON-kulcs) — már beállítva.
3. Realtime webhook: `apps-script/Code.gs` telepítése a leírása szerint
   (kell hozzá egy GitHub classic PAT `repo` joggal).

Költség: minden ingyenes keretben elfér (Actions + Pages), Firebase nem kell.
