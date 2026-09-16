/**
 * Mathiász 2026 km — azonnali validátor-indítás Form-beküldéskor.
 *
 * Telepítés (egyszeri, ~3 perc):
 *  1. Nyisd meg a Google Formot szerkesztésre.
 *  2. Jobb fent ⋮ (Továbbiak) → "Parancsfájl" (Script editor) → töröld ki ami
 *     benne van, másold be EZT a fájlt, mentsd el.
 *  3. Bal oldalt fogaskerék (Project Settings) → alul "Script Properties" →
 *     "Add script property" kétszer:
 *       GITHUB_REPO  = csabagabor21/mathiasz-2026-live
 *       GITHUB_TOKEN = <GitHub classic PAT "repo" jogosultsággal>
 *     (PAT: github.com → Settings → Developer settings → Personal access
 *     tokens → Tokens (classic) → Generate new token (classic), csak "repo"
 *     pipát kér. A tokent CSAK itt, a Script Propertiesben tárold!)
 *  4. Bal oldalt óra ikon (Triggers) → "Add Trigger" → függvénynek válaszd az
 *     onFormSubmit-et, event source: "From form", event type: "On form submit"
 *     → Save (elsőre engedélyt kér: saját fiókoddal OK-zd le).
 *
 * Ezután minden beküldéskor azonnal indul a GitHub Actions ellenőrzés
 * (~1-3 perc alatt fenn az eredmény a táblán). Ha a webhook elmaradna,
 * a 10 perces időzített futás pótolja.
 */
function onFormSubmit(e) {
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty('GITHUB_TOKEN');
  var repo = props.getProperty('GITHUB_REPO');
  if (!token || !repo) {
    throw new Error('Hiányzik a GITHUB_TOKEN vagy GITHUB_REPO script property.');
  }
  var payload = {
    event_type: 'form-submit',
    client_payload: { at: new Date().toISOString() }
  };
  var res = UrlFetchApp.fetch('https://api.github.com/repos/' + repo + '/dispatches', {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'Authorization': 'Bearer ' + token,
      'Accept': 'application/vnd.github+json'
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
  Logger.log('dispatch HTTP ' + res.getResponseCode());
}
