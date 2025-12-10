import pytest
from src.ml.classification_multilabel_ffnn import run_classification_multilabel_ffnn

def test_ml_training_trigger():
    """
    Smoke test for the ML training pipeline.
    Runs the training function with smoke_test=True to ensure it executes without error.
    Does NOT save the model.
    """
    try:
        run_classification_multilabel_ffnn(smoke_test=True)
    except Exception as e:
        pytest.fail(f"ML Training Smoke Test failed: {e}")
