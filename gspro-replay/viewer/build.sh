#!/bin/sh
# Rebuild the bundled viewer (only needed if you edit viewer/src)
cd "$(dirname "$0")" && npx esbuild src/main.js --bundle --minify --format=iife --target=es2020 --outfile=../gspro_replay/viewer_dist/viewer.js && cp src/style.css ../gspro_replay/viewer_dist/viewer.css
