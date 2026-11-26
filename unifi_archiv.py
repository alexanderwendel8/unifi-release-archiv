#!/usr/bin/env python3
"""Archiviert UniFi-Firmware- und Software-Releases aus den Ubiquiti-RSS-Feeds.

Jeder Feed (eine Produktkategorie) enthaelt nur die letzten 10-20 Releases.
Dieses Skript ruft alle konfigurierten Feeds ab und fuehrt sie pro Kategorie in
eine JSON-Datei zusammen (archiv/<kategorie>.json). Alte Eintraege bleiben
erhalten, auch wenn sie aus dem Feed fallen; spaeter geaenderte Eintraege
(z. B. nachgetragene Stable-Freigabe) werden aktualisiert.

Nur Python-Standardbibliothek. Aufruf:
    python3 unifi_archiv.py [--ziel archiv] [--nur access-point,switch]
    python3 unifi_archiv.py --suche UDB-Switch      # Archiv nach Modell durchsuchen
"""

import argparse
import email.utils
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser

RSS = "https://community.ui.com/rss/releases/x/"  # der Pfadteil vor der UUID wird ignoriert

# Kategorie -> Feed-UUID. Alle am 26.11.2026 geprueft. Weitere Kategorien einfach ergaenzen.
FEEDS = {
    "access-point":        "9fc3b2fa-9e73-449a-924f-470e79884470",  # APs, AirWire, UDB-*
    "switch":              "f5882c6b-e77f-45c1-b019-68fd20000c31",
    "unifi-os-dream-machines": "b0f0a740-021e-4027-a778-ceba983be74b",  # UDM, UDR, UCG ...
    "unifi-os-server":     "76650b06-fc47-4892-9c12-25c64c39f842",
    "network-application": "e6712595-81bb-4829-8e42-9e2630fabcfe",
    "protect-application": "aada5f38-35d4-4525-9235-b14bd320e4d0",
    "access-hub":          "e047d85b-e99f-4ae8-9cf9-849b6ce28f44",
    "security-advisories": "f3f45fa2-1784-4594-b48d-28baf317b208",
}

VERSION = re.compile(r"\b(\d+(?:\.\d+){1,3})\s*$")
MONATE = ("january february march april may june july august september "
          "october november december").split()
# "U7-Lite, UDB-Switch, AirWire - November 12, 2026"
FREIGABE = re.compile(r"(.+?)\s+[-–]\s+([A-Za-z]+)\.?\s+(\d{1,2}),?\s*(\d{4})")
RC_HINWEIS = re.compile(r"Release Channel.{0,80}Release Candidate", re.I | re.S)


class Abschnitte(HTMLParser):
    """Zerlegt Release-HTML in Abschnitte (h2/h3) mit Textzeilen (p/li)."""

    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "div", "tr"}

    def __init__(self):
        super().__init__()
        self.abschnitte = {}
        self.aktuell = "Overview"
        self.puffer = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK or tag == "br":
            self._flush()

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4"):
            titel = self._text()
            self.puffer = []
            if titel:
                self.aktuell = titel.rstrip(":")
        elif tag in self.BLOCK:
            self._flush()

    def handle_data(self, data):
        self.puffer.append(data)

    def _text(self):
        return re.sub(r"\s+", " ", "".join(self.puffer).replace("\xa0", " ")).strip()

    def _flush(self):
        text = self._text()
        self.puffer = []
        if text:
            self.abschnitte.setdefault(self.aktuell, []).append(text)

    def ergebnis(self):
        self._flush()
        return self.abschnitte


def datum_iso(monat, tag, jahr):
    try:
        return f"{int(jahr):04d}-{MONATE.index(monat.lower()) + 1:02d}-{int(tag):02d}"
    except ValueError:
        return None


def auswerten(item, kategorie):
    titel = (item.findtext("title") or "").strip()
    html = item.findtext("description") or ""
    p = Abschnitte()
    p.feed(html)
    abschnitte = p.ergebnis()
    volltext = " ".join(z for zeilen in abschnitte.values() for z in zeilen)

    # Stable-Freigaben: Zeilen "Modell, Modell - Monat Tag, Jahr" (meist im Overview)
    freigaben = []
    for zeile in abschnitte.get("Overview", []):
        m = FREIGABE.fullmatch(zeile)
        datum = m and datum_iso(m.group(2), m.group(3), m.group(4))
        if datum:
            modelle = [x.strip() for x in re.split(r",|\band\b", m.group(1)) if x.strip()]
            freigaben.append({"modelle": modelle, "stable_seit": datum})

    if freigaben or re.search(r"promoted to (Official|Stable)", volltext, re.I):
        kanal = "stable"
    elif RC_HINWEIS.search(volltext):
        kanal = "release-candidate"
    else:
        kanal = "unbekannt"  # z. B. Erstrelease oder anderer Wortlaut

    pub = item.findtext("pubDate")
    m = VERSION.search(titel)
    return {
        "id": (item.findtext("guid") or "").strip(),
        "kategorie": kategorie,
        "version": m.group(1) if m else None,
        "titel": titel,
        "link": (item.findtext("link") or "").strip(),
        "veroeffentlicht": (email.utils.parsedate_to_datetime(pub)
                            .astimezone(timezone.utc).isoformat() if pub else None),
        "kanal": kanal,
        "stable_freigaben": freigaben,
        "abschnitte": abschnitte,
        "html": html,  # Original, falls der Parser spaeter verbessert wird
    }


def holen(url, versuche=3):
    req = urllib.request.Request(url, headers={"User-Agent": "unifi-archiv/1.0"})
    for n in range(versuche):
        try:
            with urllib.request.urlopen(req, timeout=30) as antwort:
                return antwort.read()
        except (urllib.error.URLError, TimeoutError) as fehler:
            if n == versuche - 1:
                raise
            print(f"  Fehler ({fehler}), neuer Versuch ...", file=sys.stderr)
            time.sleep(2 ** (n + 1))


def laden(pfad):
    if not os.path.exists(pfad):
        return {}
    with open(pfad, encoding="utf-8") as f:
        return {r["id"]: r for r in json.load(f).get("releases", [])}


def speichern(pfad, kategorie, releases, jetzt):
    liste = sorted(releases.values(), key=lambda r: r.get("veroeffentlicht") or "",
                   reverse=True)
    daten = {"kategorie": kategorie, "feed": RSS + FEEDS[kategorie],
             "zuletzt_abgerufen": jetzt, "releases": liste}
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(pfad)),
                               prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o644)  # mkstemp legt 0600 an
    os.replace(tmp, pfad)  # atomar


def archivieren(kategorie, ziel, jetzt):
    root = ET.fromstring(holen(RSS + FEEDS[kategorie]))
    items = root.findall("./channel/item")
    if not items:
        raise ValueError("Feed ohne Eintraege - Format geaendert?")
    pfad = os.path.join(ziel, f"{kategorie}.json")
    releases = laden(pfad)
    neu = geaendert = 0
    for item in items:
        e = auswerten(item, kategorie)
        if not e["id"]:
            continue
        alt = releases.get(e["id"])
        if alt is None:
            e["zuerst_gesehen"] = e["zuletzt_geaendert"] = jetzt
            neu += 1
            print(f"  neu:       {e['titel']}  [{e['kanal']}]")
        elif {k: v for k, v in alt.items()
              if k not in ("zuerst_gesehen", "zuletzt_geaendert")} != e:
            e["zuerst_gesehen"] = alt.get("zuerst_gesehen", jetzt)
            e["zuletzt_geaendert"] = jetzt
            geaendert += 1
            print(f"  geaendert: {e['titel']}  [{e['kanal']}]")
        else:
            continue
        releases[e["id"]] = e
    speichern(pfad, kategorie, releases, jetzt)
    return neu, geaendert, len(releases)


def suchen(ziel, begriff):
    muster = re.compile(r"\b" + re.escape(begriff).replace(r"\-", "[- ]") + r"\b", re.I)
    treffer = []
    for datei in sorted(os.listdir(ziel)):
        if not datei.endswith(".json"):
            continue
        with open(os.path.join(ziel, datei), encoding="utf-8") as f:
            for r in json.load(f)["releases"]:
                text = " ".join(z for zz in r["abschnitte"].values() for z in zz)
                if muster.search(r["titel"]) or muster.search(text):
                    stable = [fr["stable_seit"] for fr in r["stable_freigaben"]
                              if any(muster.search(m) for m in fr["modelle"])]
                    treffer.append((r["veroeffentlicht"][:10], r["version"], r["kanal"],
                                    stable[0] if stable else "-", r["titel"]))
    for t in sorted(treffer, reverse=True):
        print("{}  {:<10} {:<18} stable fuer Modell: {:<10}  {}".format(*t))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ziel", default="archiv", help="Verzeichnis fuer die JSON-Dateien")
    ap.add_argument("--nur", help="Kommagetrennte Kategorien, Standard: alle")
    ap.add_argument("--suche", metavar="MODELL", help="Archiv nach Modell/Begriff durchsuchen")
    args = ap.parse_args()
    os.makedirs(args.ziel, exist_ok=True)

    if args.suche:
        return suchen(args.ziel, args.suche)

    kategorien = args.nur.split(",") if args.nur else list(FEEDS)
    jetzt = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    fehler = 0
    for k in kategorien:
        print(f"{k}:")
        try:
            neu, geaendert, gesamt = archivieren(k, args.ziel, jetzt)
            print(f"  {neu} neu, {geaendert} geaendert, {gesamt} im Archiv")
        except Exception as e:  # eine kaputte Kategorie soll die anderen nicht stoppen
            fehler += 1
            print(f"  FEHLER: {e} - Archiv dieser Kategorie unveraendert", file=sys.stderr)
    sys.exit(1 if fehler else 0)


if __name__ == "__main__":
    main()
