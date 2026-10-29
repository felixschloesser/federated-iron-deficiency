from os import PathLike

import pandas as pd

class Dataset:
    @classmethod
    def from_pandas(
        cls, df: pd.DataFrame, preserve_index: bool | None = None
    ) -> Dataset: ...
    def to_pandas(self) -> pd.DataFrame: ...
    def save_to_disk(self, dataset_path: str | PathLike[str]) -> None: ...

class DatasetDict(dict[str, Dataset]): ...

def load_dataset(
    path: str,
    *,
    revision: str | None = None,
    data_files: str | None = None,
    columns: list[str] | None = None,
    split: str,
) -> Dataset: ...
def load_from_disk(dataset_path: str) -> Dataset: ...
