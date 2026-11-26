# unifi-release-archiv

Dauerhaftes Archiv der UniFi-Firmware- und Software-Releases von Ubiquiti.

Die RSS-Feeds der Ubiquiti-Community enthalten pro Produktkategorie nur die
letzten 10–20 Releases; ältere fallen heraus. Ein GitHub-Actions-Workflow ruft
die Feeds deshalb täglich ab und speichert jedes Release dauerhaft als JSON.
Neue oder nachträglich geänderte Releases (z. B. eine später eingetragene
Stable-Freigabe) erscheinen als Commit, die Git-Historie zeigt also jede Änderung.

## Kategorien

| Datei | Inhalt |
| --- | --- |
| `archiv/access-point.json` | Access Points, AirWire, UDB-Switch, UDB-IoT … |
| `archiv/switch.json` | UniFi Switches |
| `archiv/unifi-os-dream-machines.json` | UniFi OS für UDM, UDR, UCG … |
| `archiv/unifi-os-server.json` | UniFi OS Server |
| `archiv/network-application.json` | UniFi Network Application |
| `archiv/protect-application.json` | UniFi Protect Application |
| `archiv/access-hub.json` | UniFi Access Hub |
| `archiv/security-advisories.json` | Security Advisory Bulletins |
| `archiv/index.json` | Liste der Kategorien für die Weboberfläche (wird automatisch erzeugt) |

Weitere Kategorie hinzufügen: die Feed-UUID (aus
`https://community.ui.com/rss/releases/<Name>/<UUID>`) im Dictionary `FEEDS`
in `unifi_archiv.py` ergänzen.

## Weboberfläche

`index.html` zeigt das Archiv im Browser: Suche nach Modell oder Text (z. B.
`UDB-Switch`, trifft auch „UDB Switch“), Filter nach Kategorie und Kanal,
aufklappbare Release Notes und „Stable für <Modell> seit …“. Filter stehen in
der URL, Links lassen sich also teilen (z. B. `#q=UDB-Switch&kanal=stable`).

Die Seite lädt `archiv/index.json` und die Kategorie-Dateien per `fetch` und
braucht deshalb einen Webserver:

- **GitHub Pages**: *Settings → Pages → Deploy from a branch → `main` / root*.
  Die Seite zeigt nach jedem Workflow-Lauf automatisch den neuen Stand.
- **Lokal**: `python3 -m http.server` im Repo-Verzeichnis, dann
  http://localhost:8000 öffnen.

## Aufbau eines Eintrags

```json
{
  "id": "10247e29-044d-48b2-9e83-e7c5fb17305a",
  "kategorie": "access-point",
  "version": "8.8.14",
  "titel": "UniFi Access Point & Wireless Bridge 8.8.14",
  "link": "https://community.ui.com/releases/…",
  "veroeffentlicht": "2026-11-03T16:43:39+00:00",
  "kanal": "stable",
  "stable_freigaben": [
    { "modelle": ["U7-Lite", "UDB-Switch", "AirWire", "…"], "stable_seit": "2026-11-12" }
  ],
  "abschnitte": { "Overview": ["…"], "Improvements": ["…"], "Bugfixes": ["…"] },
  "html": "<h2>Overview</h2>…",
  "zuerst_gesehen": "2026-11-26T04:38:00+00:00",
  "zuletzt_geaendert": "2026-11-26T04:38:00+00:00"
}
```

- `kanal`: `stable`, `release-candidate` oder `unbekannt`. Die Feeds nennen den
  Kanal nur im Fließtext und nicht in allen Kategorien (vor allem bei Access Point
  und Switch); sonst steht hier `unbekannt`.
- `stable_freigaben`: aus Zeilen wie „U7-Lite, UDB-Switch – November 12, 2026“ gelesen.
- `html`: die Original-Release-Notes, damit sich die Daten später neu auswerten lassen.

## Lokal benutzen

Nur Python 3 (Standardbibliothek) nötig.

```bash
python3 unifi_archiv.py                      # alle Feeds abrufen und archivieren
python3 unifi_archiv.py --nur switch         # nur eine Kategorie
python3 unifi_archiv.py --suche UDB-Switch   # alle Releases, die ein Modell betreffen
```

## Größe

Rund 6 KB pro Release, insgesamt etwa 1–1,5 MB pro Jahr über alle Kategorien.

## Quelle

Release Notes: [Ubiquiti Community – Releases](https://community.ui.com/releases).
Die Inhalte gehören Ubiquiti; dieses Repo archiviert nur die öffentlichen RSS-Feeds.
