"""
This module declares errors used in the package.
"""


class TrackerError(Exception):
    """Base Error class for errors in this package."""

class OperationError(TrackerError):
    """Errors encounter while attempting a specific operation."""
    
    def __init__(self, operation: str, reason: str):
        self.operation = operation
        super().__init__(f"unable to complete {operation} because {reason}")


class NoResultError(OperationError):
    """Raised if no item with the given name and kind exists."""

    def __init__(self, kind: str, name: str, operation: str):
        self.kind = kind
        self.name = name
        super().__init__(operation, f"no item matches {kind=} and {name=}")


class PairedError(OperationError):
    """Raised if an operation cannot complete because an item is already paired."""

    def __init__(self, kind: str, name: str, pair_kind: str, pair_name: str, operation: str):
        self.kind = kind
        self.name = name
        self.pair_kind = pair_kind
        self.pair_name = pair_name
        super().__init__(operation, f"{kind} '{name}' is paired with {pair_kind} '{pair_name}'")

class UnpairedError(OperationError):
    """Raised if an operation cannot complete because the item isn't paired."""

    def __init__(self, kind: str, name: str, pair_kind: str, operation: str):
        self.kind = kind
        self.name = name
        self.pair_kind = pair_kind
        super().__init__(operation, f"{kind} '{name}' is not paired with a {pair_kind}")


class HasDependenciesError(OperationError):
    """Raised if an operation cannot complete because an item has dependencies."""

    def __init__(self, kind: str, name: str, operation: str):
        self.kind = kind
        self.name = name
        super().__init__(operation, f"{kind} '{name}' has dependencies")


class InvalidPinError(OperationError):
    """Raised if there's an attempt to unlock a door using an invalid pin."""

    def __init__(self, operation: str="unlock door"):
        super().__init__(operation, "the pin is invalid")


class OutOfRangeError(OperationError):
    """Raised if the target value is out of range."""

    def __init__(
        self, 
        kind: str, name: str,
        target_value: int, min_value: int, max_value: int,
        operation: str
    ):
        self.kind = kind
        self.name = name
        self.target_value = target_value
        self.min_value = min_value
        self.max_value = max_value
        super().__init__(
                operation,
                f"{target_value=} is not in range [{min_value}, {max_value}] "
                f"for {kind} '{name}'"
                )

