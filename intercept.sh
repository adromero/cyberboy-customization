#!/bin/bash
# Intercept SIGINT Platform Launcher
cd $HOME/intercept
source venv/bin/activate

# Launch browser in portrait mode after server starts
(
  sleep 3
  wlr-randr --output DSI-1 --transform 270
  chromium --start-fullscreen http://localhost:5050
  wlr-randr --output DSI-1 --transform normal
) &

# Run server (keeps terminal open)
sudo venv/bin/python intercept.py
