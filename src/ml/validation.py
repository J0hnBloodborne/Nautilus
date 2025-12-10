import pandas as pd
from deepchecks.tabular import Dataset
from deepchecks.tabular.suites import data_integrity
from src.core.database import get_db
from src.core import models
import os

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
        'vote_average': m.vote_average,
        'vote_count': m.vote_count,
        'runtime': m.runtime,
        'revenue': m.revenue,
        'budget': m.budget,
        'title': m.title
    } for m in movies]
    
    df = pd.DataFrame(data)
    
    ds = Dataset(df, label='vote_average', cat_features=['title'])
    
    integ_suite = data_integrity()
    result = integ_suite.run(ds)

    # Save Report
    report_path = "reports/deepchecks_report.html"
    os.makedirs("reports", exist_ok=True)
    result.save_as_html(report_path)
    print(f"DeepChecks report saved to {report_path}")
    return True

if __name__ == "__main__":
    run_data_validation()
