# Songio

## Möbius izdanje (lokalna beta)

`mobius.json`, `index.jsx`, `service.py` i `job.py` su web izdanje koje koristi
isti kod za Spotify/YouTube analizu i MP3 obradu kao Windows aplikacija. Linkovi
se stavljaju u red, a preuzimanja se obrađuju kao pozadinski poslovi. Završenu
datoteku vlasnik sprema preko Möbiusove potvrde izvoza; aplikacija može zatražiti
izvoz samo svojih datoteka, pojedinačno do 100 MB.

Ovo izdanje **još nije spremno za App Store**: YouTube može tražiti
prijavu/provjeru bota koju web izdanje još ne podržava. Također zahtijeva Möbius
izdanje sa sigurnim izvozom datoteka. Originalna Windows aplikacija ispod ostaje
nepromijenjena.


Desktop aplikacija za Windows: zalijepiš YouTube ili Spotify link (pjesma, album ili playlista),
Songio skine zvuk, konvertuje ga u MP3 s omotom albuma i tagovima (naslov, izvođač, album, godina,
redni broj) i spremi u folder koji odabereš.

Spotify ne dopušta direktno skidanje zvuka, pa Songio s njega uzima samo podatke o pjesmi
(naslov, izvođač, album, omot), a zvuk nađe na YouTube Music-u i skine odatle.

## Brzi start

1. Instaliraj [Python 3.12](https://www.python.org/downloads/) (označi "Add python.exe to PATH").
2. Dvoklik na `Songio.bat`. Prvo pokretanje napravi `.venv` i instalira pakete (nekoliko minuta).
3. Pri prvom pokretanju aplikacija ponudi da sama preuzme dva alata (jednokratno, oko 100 MB):
   - **FFmpeg** – konverzija u MP3 (obavezno),
   - **Deno** – JavaScript runtime koji YouTube traži (bez njega neki linkovi ne rade).
   Alati se spremaju u `%LOCALAPPDATA%\Songio\bin`, ništa se ne instalira u sistem.
   Ako već imaš `ffmpeg`, `deno` ili `node` na PATH-u, koriste se oni.
4. Zalijepi link, pritisni **Dodaj** (ili Enter). Preuzimanje kreće automatski.

## Šta radi

- **YouTube**: video (`watch?v=`, `youtu.be`, `shorts`, YouTube Music) i playliste (`playlist?list=`).
  Ako link sadrži i video i playlistu, aplikacija pita šta želiš.
- **Spotify**: pjesma, album, playlista, izvođač, kratki `spotify.link` linkovi.
- Više linkova odjednom: zalijepi ih razdvojene razmakom ili novim redom.
- Link iz clipboarda se sam ubaci u polje kad se vratiš u prozor; možeš i prevući link u prozor.
- Svaka pjesma ima svoj red s omotom, napretkom, brzinom i dugmadima (otkaži, ponovi, prikaži u folderu).
- Playlista/album ide u zaseban podfolder s imenom playliste (može se isključiti).
- Pjesme koje već postoje u folderu se preskaču.
- Kvalitet MP3-a: 128, 192 ili 320 kbps.

## Postavke (zupčanik gore desno)

- broj istovremenih preuzimanja (1–6),
- ime fajla: `Izvođač - Naslov`, `Naslov - Izvođač` ili samo `Naslov`, uz opcionalni redni broj `01 - …`,
- kolačići iz browsera (Firefox, Chrome, Edge…) – pomaže kad YouTube traži prijavu ("provjera bota"),
- vlastiti Spotify API ključevi (opcionalno; bez njih se koristi besplatni pristup),
- ručne putanje do `ffmpeg.exe` i `deno.exe`/`node.exe`.

Postavke i log: `%LOCALAPPDATA%\Songio\settings.json` i `%LOCALAPPDATA%\Songio\songio.log`.

## Kad nešto ne radi

- **"YouTube traži prijavu (provjera bota)"** – u postavkama uključi kolačiće iz browsera u kojem si
  prijavljen na YouTube (Firefox radi najpouzdanije).
- **Preuzimanja odjednom prestanu raditi** – YouTube ili Spotify su nešto promijenili. Pokreni
  `update.bat` (ažurira `yt-dlp` i `spotdl`) i ponovo pokreni aplikaciju.
- **Spotify linkovi ne rade** – napravi aplikaciju na <https://developer.spotify.com/dashboard>
  i u postavkama unesi Client ID i Client Secret.
- **Pogrešna pjesma za Spotify link** – pretraga na YouTube Music-u ponekad promaši kod rijetkih
  pjesama; zalijepi direktan YouTube link te pjesme.

## Samostalni .exe

`build.bat` napravi `dist\Songio\Songio.exe` (PyInstaller). Folder `dist\Songio` možeš kopirati
na drugi računar bez Pythona; ffmpeg i Deno se i tamo preuzmu pri prvom pokretanju.

## Struktura koda

```
run.py                 pokretanje
songio/app.py          QApplication, logovanje
songio/engine.py       red čekanja, paralelna preuzimanja, Qt signali prema UI-ju
songio/sources.py      prepoznavanje linkova, analiza YouTube (yt-dlp) i Spotify (spotdl) linkova
songio/downloader.py   preuzimanje jedne pjesme: pretraga, yt-dlp, ffmpeg -> mp3, tagovi
songio/tagging.py      ID3 tagovi i omot (mutagen, Pillow)
songio/tools.py        pronalaženje i preuzimanje ffmpeg-a i Dena
songio/ui/             PySide6 prozor, widgeti, dijalozi, tema
```

Koristi samo za sadržaj za koji imaš pravo preuzimanja.
