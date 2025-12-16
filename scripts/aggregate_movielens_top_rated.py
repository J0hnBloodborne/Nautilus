"""Aggregate MovieLens ratings to produce a cached top-rated JSON.

This script streams ratings.csv and computes avg rating and vote count per movieId.
It then attempts to map MovieLens movieId -> tmdbId using data/raw/*/links.csv (if present).
Writes output to data/processed/top_rated_movies.json with configurable top_n.

Usage:
    python scripts/aggregate_movielens_top_rated.py --top 500

Notes:
- Designed to be memory-friendly: aggregates using dicts but streams the CSV line-by-line.
- If no ratings files are found, will exit cleanly with message and return code 2.
"""

import argparse
import csv
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime


def find_ratings_and_links(root='data/raw'):
    # Look for ratings.csv and links.csv under any subfolder of data/raw
    ratings_paths = glob.glob(os.path.join(root, '**', 'ratings.csv'), recursive=True)
    links_paths = glob.glob(os.path.join(root, '**', 'links.csv'), recursive=True)
    return ratings_paths, links_paths


def stream_aggregate_ratings(ratings_path):
    """Return dict movieId -> (sum, count) by streaming CSV."""
    sums = defaultdict(float)
    counts = defaultdict(int)
    print(f"Streaming ratings from: {ratings_path}")
    with open(ratings_path, 'r', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader, start=1):
            try:
                mid = row.get('movieId') or row.get('movieId')
                rating = row.get('rating')
                if mid is None or rating is None:
                    continue
                mid = mid.strip()
                r = float(rating)
                sums[mid] += r
                counts[mid] += 1
            except Exception:
                # skip malformed lines
                continue
            if i % 1_000_000 == 0:
                print(f"  processed {i} rows...")
    return sums, counts


def load_links(links_paths):
    """Return mapping movieId -> tmdbId and movieId -> title (if available)."""
    movie_to_tmdb = {}
    movie_titles = {}
    for p in links_paths:
        print(f"Reading links: {p}")
        with open(p, 'r', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                mid = row.get('movieId')
                tmdb = row.get('tmdbId') or row.get('tmdbId')
                title = row.get('title') or row.get('title')
                if mid and tmdb:
                    movie_to_tmdb[mid.strip()] = tmdb.strip()
                if mid and title:
                    movie_titles[mid.strip()] = title.strip()
    return movie_to_tmdb, movie_titles


def write_output(out_path, records):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    meta = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'count': len(records),
    }
    payload = {'meta': meta, 'items': records}
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print(f"Wrote cache: {out_path} (items={len(records)})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='data/raw', help='MovieLens raw data root')
    parser.add_argument('--out', default='data/processed/top_rated_movies.json', help='Output JSON path')
    parser.add_argument('--top', type=int, default=500, help='How many top items to keep')
    parser.add_argument('--min_votes', type=int, default=100, help='Minimum votes to include')
    args = parser.parse_args()

    ratings_paths, links_paths = find_ratings_and_links(args.root)
    if not ratings_paths:
        print('No ratings.csv found under', args.root)
        sys.exit(2)

    # Use the first ratings file we find (typical MovieLens has one)
    sums, counts = stream_aggregate_ratings(ratings_paths[0])
    movie_to_tmdb, movie_titles = load_links(links_paths) if links_paths else ({}, {})

    records = []
    for mid, total in sums.items():
        cnt = counts.get(mid, 0)
        if cnt < args.min_votes:
            continue
        avg = total / cnt if cnt else 0.0
        rec = {
            'movieId': mid,
            'tmdb_id': movie_to_tmdb.get(mid),
            'title': movie_titles.get(mid),
            'avg_rating': round(avg, 3),
            'vote_count': cnt,
        }
        records.append(rec)

    # sort by avg_rating desc then vote_count desc
    records.sort(key=lambda r: (r['avg_rating'], r['vote_count']), reverse=True)
    topn = records[: args.top]

    write_output(args.out, topn)


if __name__ == '__main__':
    main()
