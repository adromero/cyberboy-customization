#!/bin/bash
# Intercept SIGINT Platform Launcher
cd /home/alfonso/intercept
source venv/bin/activate

# Launch browser after server starts (in background)
(sleep 3 && chromium http://localhost:5050) &

# Run server (keeps terminal open)
sudo python3 intercept.py
