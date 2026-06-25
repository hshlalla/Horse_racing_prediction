#!/usr/bin/env bash
set -e

# Build the web app
echo "Building web app..."
cd web
npm run build

# Ensure static directory exists
echo "Copying build to backend..."
mkdir -p ../backend/app/static

# Copy dist files
cp -r dist/* ../backend/app/static/

echo "Done! The web app has been copied to backend/app/static."
