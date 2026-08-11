"""Was diese App vom Lizenzteil aller anderen Apps unterscheidet."""

# Bestimmt zusammen mit dem Hauptschluessel den App-Schluessel. Eine Aenderung
# hier entwertet alle bereits ausgestellten Lizenzen dieser App.
PRODUKT = "Spotify Playlist Generator"

# Unterordner in %APPDATA% fuer die Lizenzdatei des Nutzers. Muss sich von dem
# jeder anderen App unterscheiden, sonst ueberschreiben sich zwei Apps
# gegenseitig die Lizenz.
ORDNER = "SpotifyPlaylistGenerator"

# Sichtbarer Anfang jedes Lizenzschluessels.
VORSILBE = "KDS"

# Aus dem Hauptschluessel abgeleitet. Leer = noch nicht eingerichtet, die App
# ist dann gesperrt und weist jeden Schluessel ab. Das ist Absicht: eine
# versehentlich ohne App-Schluessel gebaute EXE soll unbrauchbar sein und nicht
# unbewacht.
APP_SCHLUESSEL = ""
