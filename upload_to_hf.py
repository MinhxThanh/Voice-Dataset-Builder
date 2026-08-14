from pathlib import Path

token = ""  # Optional: leave blank after `hf auth login`, or paste a NEW write token.
root = Path(__file__).resolve().parent / "projects" / "my_voice_dataset"
repo_id = "username/dataset-name"


def _metadata_files(dataset_root: Path) -> dict[str, str]:
    train = dataset_root / "metadata_train.jsonl"
    if not train.is_file():
        raise FileNotFoundError(f"Missing required metadata: {train}")
    files = {"train": str(train)}
    validation = dataset_root / "metadata_val.jsonl"
    if validation.is_file():
        files["validation"] = str(validation)
    return files


def main() -> None:
    from datasets import Audio, load_dataset

    dataset_root = root.resolve()
    dataset = load_dataset(
        "json",
        data_files=_metadata_files(dataset_root),
        cache_dir=str(dataset_root / ".cache"),
    )

    for split in dataset:
        columns = dataset[split].column_names
        path_column = "file_name" if "file_name" in columns else "audio_path"
        if path_column not in columns:
            raise KeyError(f"{split}: missing 'file_name' or 'audio_path'")

        paths = dataset[split][path_column]
        missing = [path for path in paths if not path or not (dataset_root / path).is_file()]
        if missing:
            raise FileNotFoundError(
                f"{split}: missing {len(missing)} audio files, first: {missing[0]}"
            )

        dataset[split] = dataset[split].map(
            lambda row, column=path_column: {
                column: str((dataset_root / row[column]).resolve())
            },
            desc=f"Resolving {split} audio paths",
        )
        dataset[split] = dataset[split].rename_column(path_column, "audio")
        dataset[split] = dataset[split].cast_column("audio", Audio())

    assert all(isinstance(dataset[split].features["audio"], Audio) for split in dataset)

    print(f"Uploading typed audio dataset to {repo_id}...")
    dataset.push_to_hub(
        repo_id,
        private=True,
        token=token or None,
        commit_message="Upload typed audio dataset",
    )
    print("Upload completed successfully.")


if __name__ == "__main__":
    main()
