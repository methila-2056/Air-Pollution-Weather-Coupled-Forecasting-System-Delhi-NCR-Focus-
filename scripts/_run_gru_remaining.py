import pathlib

from ml.training.train_gru import DEFAULT_GRU_PARAMS, run_training

run_training(
    csv_path=pathlib.Path("data", "ml", "training_dataset.csv"),
    model_dir=pathlib.Path("models", "pm25"),
    horizons=[72],
    seq_len=48,
    gap_threshold=2.0,
    gru_params={**DEFAULT_GRU_PARAMS, "batch_size": 512, "lr": 0.001},
)
