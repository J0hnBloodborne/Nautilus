import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
import matplotlib.pyplot as plt
import os
import sys
import joblib
from src.database import DATABASE_URL
from src.models import MLModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

plt.switch_backend('Agg')

# Path setup
sys.path.append(os.getcwd())

RAW_DATA_PATH = "data/raw/ml-25m/ratings.csv"
OUTPUT_DIR = "reports/figures"
MODEL_PATH = "src/models/traffic_forecaster.pkl"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs("src/models", exist_ok=True)

def run_analysis():
    print("Loading MovieLens timestamps...")
    if not os.path.exists(RAW_DATA_PATH):
        print(f"Error: {RAW_DATA_PATH} not found.")
        return

    try:
        df = pd.read_csv(RAW_DATA_PATH, usecols=['timestamp'])
        df['date'] = pd.to_datetime(df['timestamp'], unit='s')
        
        # Resample to Monthly
        monthly_data = df.set_index('date').resample('ME').size().reset_index(name='count')
        
        # Feature Engineering (Ordinal Date)
        monthly_data['date_ordinal'] = monthly_data['date'].apply(lambda x: x.toordinal())
        
        X = monthly_data[['date_ordinal']]
        y = monthly_data['count']
        
        # Split for validation (Train on first 80%, Test on last 20%)
        train_size = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:train_size], X.iloc[train_size:]
        y_train, y_test = y.iloc[:train_size], y.iloc[train_size:]
        
        # Train
        model = LinearRegression()
        model.fit(X_train, y_train)
        
        # Evaluate
        preds = model.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        
        # Re-train on full data for future forecast
        model.fit(X, y)
        
        # Forecast next 12 months
        last_date = monthly_data['date'].iloc[-1]
        future_dates = [last_date + pd.DateOffset(months=i) for i in range(1, 13)]
        future_ordinals = np.array([d.toordinal() for d in future_dates]).reshape(-1, 1)
        future_counts = model.predict(future_ordinals)
        
        # Metrics
        metrics = {"mae": float(mae), "forecast_months": 12}
        print(f"Metrics: {metrics}")
        
        # Plotting
        plt.figure(figsize=(12, 6))
        plt.plot(monthly_data['date'], monthly_data['count'], label='Historical Data')
        plt.plot(future_dates, future_counts, label='Forecast (Next Year)', linestyle='--', color='red')
        plt.title(f"Traffic Forecast (MAE: {mae:.0f})")
        plt.xlabel("Date")
        plt.ylabel("Interactions")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(os.path.join(OUTPUT_DIR, "time_series_forecast.png"))
        print("Graph saved.")
        
        # Save Model
        joblib.dump(model, MODEL_PATH)
        
        # Register to DB
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            session.query(MLModel).filter(MLModel.model_type == "time_series").update({MLModel.is_active: False})
            entry = MLModel(
                name="Traffic_LinReg_v1",
                version="1.0.0",
                model_type="time_series",
                file_path=MODEL_PATH,
                metrics=metrics,
                is_active=True
            )
            session.add(entry)
            session.commit()
            print("Model registered to Database.")
        except Exception as e:
            session.rollback()
            print(f"DB Error: {e}")
        finally:
            session.close()
            
    except Exception as e:
        print(f"Time Series Failed: {e}")

if __name__ == "__main__":
    run_analysis()