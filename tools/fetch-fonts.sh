#!/bin/sh
# Downloads the web fonts Masque uses ONCE (at build time) and saves them in assets/fonts/, so visitors'
# browsers load fonts from your own site and never contact Google (Google would see their IP address).
# Needs curl and perl (both are in the Docker image). Run it again if you change the font list below.
# Nothing is written to assets/fonts/fonts.css until every file downloaded and checked out; if this fails,
# the site keeps using Google Fonts exactly as before.
set -e
cd "$(dirname "$0")/.."
OUT=assets/fonts
URL='https://fonts.googleapis.com/css2?family=Pirata+One&family=Figtree:wght@400;600;700&family=Space+Mono:wght@400;700&family=Lora:wght@400;700&family=Playfair+Display:wght@400;700&family=Nunito:wght@400;700&family=Caveat:wght@400;700&display=swap'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$OUT/google"
# a modern browser user agent makes Google answer with woff2 files
curl -fsSL --retry 3 -A "$UA" "$URL" -o "$TMP/g.css"
# keep the latin and latin-ext pieces (other alphabets fall back to the device font), point each file at google/<name>
perl -0777 -e '
  local $/; open(F, "<", $ARGV[0]) or die; my $c = <F>; close F;
  open(CSS, ">", $ARGV[1]) or die; open(LST, ">", $ARGV[2]) or die;
  my %seen;
  while ($c =~ m{/\*\s*([\w-]+)\s*\*/\s*(\@font-face\s*\{.*?\})}gs) {
    my ($sub, $blk) = ($1, $2);
    next unless $sub eq "latin" or $sub eq "latin-ext";
    next unless $blk =~ m{url\((https://[^)]+?([^/)]+\.woff2))\)};
    my ($u, $name) = ($1, $2);
    $blk =~ s{url\(\Q$u\E\)}{url(google/$name)};
    print CSS "/* $sub */\n$blk\n";
    print LST "$u\n" unless $seen{$u}++;
  }
  close CSS; close LST;
' "$TMP/g.css" "$TMP/fonts.css" "$TMP/list"
[ -s "$TMP/list" ] || { echo "fetch-fonts: no font files found in Google's answer" >&2; exit 1; }
while read -r u; do
  f="$OUT/google/$(basename "$u")"
  curl -fsSL --retry 3 -o "$f" "$u"
  [ "$(head -c 4 "$f")" = "wOF2" ] || { echo "fetch-fonts: $f is not a woff2 file" >&2; rm -f "$f"; exit 1; }
done < "$TMP/list"
for fam in "Pirata One" "Figtree" "Space Mono" "Lora" "Playfair Display" "Nunito" "Caveat"; do
  grep -q "font-family: '$fam'" "$TMP/fonts.css" || { echo "fetch-fonts: $fam is missing" >&2; exit 1; }
done
mv "$TMP/fonts.css" "$OUT/fonts.css"
echo "fetch-fonts: saved $(wc -l < "$TMP/list" 2>/dev/null || echo some) font files to $OUT/google/"
