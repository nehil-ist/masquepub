#!/bin/sh
# Makes assets/app.min.js and assets/style.min.css. Needs Node.js. Run it again after every change to app.js or style.css.
set -e
cd "$(dirname "$0")"
npx --yes esbuild assets/app.js --minify --outfile=assets/app.min.js
npx --yes esbuild assets/style.css --minify --outfile=assets/style.min.css
ls -l assets/app.js assets/app.min.js assets/style.css assets/style.min.css
