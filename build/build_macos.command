#!/bin/bash
set -e
cd "$(dirname "$0")"
./build_macos.sh
printf '\nBuild finished. The .app is in the dist-macos folder.\n\n'
read -r -p "Press Return to close..." _
