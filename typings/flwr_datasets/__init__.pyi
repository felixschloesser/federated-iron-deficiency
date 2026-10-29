from collections.abc import Callable

from datasets import Dataset, DatasetDict
from flwr_datasets.partitioner import Partitioner

class FederatedDataset:
    partitioners: dict[str, Partitioner]
    def __init__(
        self,
        *,
        dataset: str,
        revision: str | None = None,
        data_files: str | None = None,
        columns: list[str] | None = None,
        preprocessor: Callable[[DatasetDict], DatasetDict] | None = None,
        partitioners: dict[str, Partitioner],
        shuffle: bool = True,
    ) -> None: ...
    def load_partition(
        self, partition_id: int, split: str | None = None
    ) -> Dataset: ...
