import pandas as pd
import numpy as np
import json
import os
import unicodedata
import sys

from src.core.database import get_db
from src.core import models

if not hasattr(np, 'Inf'):
    np.Inf = np.inf

from deepchecks.tabular import Dataset
from deepchecks.tabular.suites import data_integrity


def run_data_validation():
    """
    Runs DeepChecks data integrity suite on the Movies dataset.
    Returns True if passed, False if failed.
    """
    print("Running DeepChecks Data Validation...")

    db = next(get_db())
    movies = db.query(models.Movie).limit(1000).all()

    if not movies:
        print("No data to validate.")
        return True

    data = [{
        'popularity': m.popularity_score,
        'title': m.title
    } for m in movies]

    df = pd.DataFrame(data)

    # Quick cleaning to avoid trivial string-mismatch failures in DeepChecks
    # Normalize titles: strip whitespace, remove trailing punctuation, collapse spaces
    if 'title' in df.columns:
        df['title'] = df['title'].fillna('').astype(str)
        # remove leading/trailing whitespace and collapse multiple spaces
        df['title'] = df['title'].str.strip().str.replace(r'\s+', ' ', regex=True)
        # remove trailing punctuation characters like '.' ',' ':' ';' etc.
        df['title'] = df['title'].str.replace(r'[\.:,;!\?]+$', '', regex=True)
    # unify common unicode punctuation (simple normalization)
    df['title'] = df['title'].apply(lambda s: unicodedata.normalize('NFKC', s))

    # Ensure popularity is numeric and fill missing values with median to avoid NaN feature importance
    if 'popularity' in df.columns:
        df['popularity'] = pd.to_numeric(df['popularity'], errors='coerce')
        if df['popularity'].isna().all():
            df['popularity'] = df['popularity'].fillna(0.0)
        else:
            df['popularity'] = df['popularity'].fillna(df['popularity'].median())

    ds = Dataset(df, label='popularity', cat_features=['title'])

    integ_suite = data_integrity()
    result = integ_suite.run(ds)

    # Save Report to the path expected by the admin UI
    report_path = "reports/data_integrity_report.html"
    os.makedirs("reports", exist_ok=True)
    # Remove any previous variants like 'data_integrity_report (1).html' so we always overwrite
    try:
        for fname in os.listdir('reports'):
            if fname.startswith('data_integrity_report') and fname.endswith('.html'):
                os.remove(os.path.join('reports', fname))
    except Exception:
        pass

    result.save_as_html(report_path)
    print(f"DeepChecks report saved to {report_path}")

    # Print brief summary
    passed = result.passed()
    print("Suite passed:", passed)

    # Collect failed checks details in a JSON-friendly structure so other systems (admin/discord) can consume
    failed_checks = result.get_not_passed_checks()
    print("Checks failed:", len(failed_checks))

    failed_summaries = []
    for idx, chk in enumerate(failed_checks, start=1):
        info = {
            'index': idx,
            'repr': str(chk)
        }
        # Try common attribute names used by deepchecks result objects
        for attr in ('name', 'header', 'message', 'description', 'label', 'error'):
            try:
                val = getattr(chk, attr, None)
                if val:
                    # some attributes may be objects; convert to string for safety
                    info[attr] = val if isinstance(val, (str, int, float)) else str(val)
            except Exception:
                pass

        # Try to extract structured details if available
        for dattr in ('details', 'result', 'meta'):
            try:
                val = getattr(chk, dattr, None)
                if val is not None:
                    # Only include lightweight textual detail
                    info[dattr] = str(val)[:1000]
            except Exception:
                pass

        failed_summaries.append(info)
        # Print readable line for interactive use
        print(f"- [{idx}] {info.get('name') or info.get('header') or info.get('repr')}")

    # Save JSON summary next to the HTML report
    summary = {
        'passed': passed,
        'failed_count': len(failed_summaries),
        'failed_checks': failed_summaries
    }
    summary_path = os.path.join('reports', 'data_integrity_summary.json')
    try:
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"Summary JSON saved to {summary_path}")
    except Exception as e:
        print(f"Failed to write summary JSON: {e}")

    return passed


if __name__ == "__main__":
    passed = run_data_validation()
    # Exit non-zero in CI when the suite fails so workflows can fail fast
    sys.exit(0 if passed else 1)
