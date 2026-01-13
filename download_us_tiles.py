#!/usr/bin/env python3
"""
Download OpenStreetMap tiles for offline use in GNOME Maps.
Tiles are saved to the libshumate cache directory.
"""

import os
import sys
import math
import time
import urllib.request
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# US bounding box (Continental US + Alaska + Hawaii approximate)
US_BOUNDS = {
    'continental': {'min_lat': 24.5, 'max_lat': 49.5, 'min_lon': -125.0, 'max_lon': -66.5},
    'alaska': {'min_lat': 51.0, 'max_lat': 71.5, 'min_lon': -180.0, 'max_lon': -129.0},
    'hawaii': {'min_lat': 18.5, 'max_lat': 22.5, 'min_lon': -160.5, 'max_lon': -154.5},
}

# OSM tile server - use a fair-use compliant server
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = "CyberboyOfflineCache/1.0 (personal offline use)"

# GNOME Maps (libshumate) cache location
CACHE_DIR = Path.home() / ".cache" / "shumate" / "osm-mapnik"


def lat_lon_to_tile(lat, lon, zoom):
    """Convert lat/lon to tile coordinates."""
    lat_rad = math.radians(lat)
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def get_tiles_for_bounds(bounds, zoom):
    """Get all tile coordinates within bounds for a zoom level."""
    min_x, max_y = lat_lon_to_tile(bounds['min_lat'], bounds['min_lon'], zoom)
    max_x, min_y = lat_lon_to_tile(bounds['max_lat'], bounds['max_lon'], zoom)

    tiles = []
    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            tiles.append((zoom, x, y))
    return tiles


def get_all_us_tiles(max_zoom=11):
    """Get all tiles for the US up to max_zoom."""
    all_tiles = []

    for zoom in range(max_zoom + 1):
        for region, bounds in US_BOUNDS.items():
            tiles = get_tiles_for_bounds(bounds, zoom)
            all_tiles.extend(tiles)

    # Remove duplicates
    return list(set(all_tiles))


def download_tile(tile):
    """Download a single tile and save to cache."""
    zoom, x, y = tile
    url = TILE_URL.format(z=zoom, x=x, y=y)

    # Shumate cache path format: zoom/x/y.png
    cache_path = CACHE_DIR / str(zoom) / str(x) / f"{y}.png"

    if cache_path.exists():
        return (tile, "exists")

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()

        with open(cache_path, 'wb') as f:
            f.write(data)

        return (tile, "downloaded")

    except Exception as e:
        return (tile, f"error: {e}")


def estimate_size(tiles):
    """Estimate download size (avg ~15KB per tile)."""
    return len(tiles) * 15 / 1024  # MB


def main():
    print("=" * 60)
    print("US Offline Map Tile Downloader")
    print("=" * 60)

    # Parse arguments
    max_zoom = 10  # Default - good balance of detail vs size
    if len(sys.argv) > 1:
        try:
            max_zoom = int(sys.argv[1])
            if max_zoom > 14:
                print("Warning: Zoom > 14 will download many GB of tiles!")
        except ValueError:
            pass

    print(f"\nTarget zoom levels: 0-{max_zoom}")
    print(f"Cache directory: {CACHE_DIR}")

    # Calculate tiles needed
    print("\nCalculating tiles needed...")
    tiles = get_all_us_tiles(max_zoom)
    total_tiles = len(tiles)

    est_size = estimate_size(tiles)
    print(f"Total tiles to check: {total_tiles:,}")
    print(f"Estimated max size: ~{est_size:.1f} MB")

    # Check existing tiles
    existing = sum(1 for t in tiles if (CACHE_DIR / str(t[0]) / str(t[1]) / f"{t[2]}.png").exists())
    to_download = total_tiles - existing

    print(f"Already cached: {existing:,}")
    print(f"To download: {to_download:,}")

    if to_download == 0:
        print("\nAll tiles already cached!")
        return

    print(f"\nDownloading {to_download:,} tiles...")
    print("(This may take a while. Press Ctrl+C to stop.)\n")

    # Download with thread pool
    downloaded = 0
    errors = 0
    start_time = time.time()

    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(download_tile, tile): tile for tile in tiles}

            for future in as_completed(futures):
                tile, status = future.result()

                if status == "downloaded":
                    downloaded += 1
                elif status.startswith("error"):
                    errors += 1

                # Progress update every 100 tiles
                if (downloaded + errors) % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = downloaded / elapsed if elapsed > 0 else 0
                    remaining = (to_download - downloaded - errors) / rate if rate > 0 else 0
                    print(f"\rProgress: {downloaded + errors + existing:,}/{total_tiles:,} "
                          f"({rate:.1f} tiles/s, ~{remaining/60:.1f}m remaining)", end="")

                    # Rate limit to be nice to tile servers
                    time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n\nDownload interrupted by user.")

    elapsed = time.time() - start_time
    print(f"\n\nDownload complete!")
    print(f"Downloaded: {downloaded:,} tiles")
    print(f"Errors: {errors:,}")
    print(f"Time: {elapsed/60:.1f} minutes")

    # Calculate actual cache size
    cache_size = sum(f.stat().st_size for f in CACHE_DIR.rglob("*.png")) / (1024 * 1024)
    print(f"Cache size: {cache_size:.1f} MB")


if __name__ == "__main__":
    main()
