# Mathiász 2026 km — élő tábla + képernyőkép-dátum ellenőrzés

## Működés
- `index.html` a publikus tábla (GitHub Pagesről megy, mindenkinek élőben).
- A tábla a `data.json`-ból olvas: **csak az igazolt km számít** bele az összegbe.
- `.github/workflows/validate.yml` 10 percenként fut: lehúzza a Forms-válasz Sheetet,
  letölti a képernyőképeket Drive-ról, és megnézi, hogy a kép **aznap készült-e**,
  amikor feltöltötték (EXIF-dátum, ha van; különben Meta Llama vision olvassa ki
  a dátumot a képről). Eredmény → `data.json` + `validator/validation.json`.

## Beüzemelés (egyszeri)
1. Google Drive: a Form feltöltési mappáját oszd meg olvasásra ezzel a címmel:
   `mathiasz-validator@summit-14b74.iam.gserviceaccount.com` (Megtekintő).
2. GitHub repo Secrets (`Settings → Secrets → Actions`):
   - `GOOGLE_SA_KEY`: a service account JSON-kulcsa.
   - `LLAMA_API_KEY`: Meta Llama API-kulcs (e nélkül csak az EXIF-es JPEG-ek
     igazolódnak automatikusan; a PNG-képernyőképek „ellenőrzés alatt" maradnak).
3. `Actions → validate-screenshots → Run workflow` az első futtatáshoz.

Költség: GitHub Actions ingyenes keretben elfér, Firebase nem kell.
