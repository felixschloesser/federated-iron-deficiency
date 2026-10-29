from numpy.typing import ArrayLike

def train_test_split[T](
    array: T,
    /,
    *,
    test_size: float,
    stratify: ArrayLike | None = None,
    random_state: int | None = None,
) -> list[T]: ...
