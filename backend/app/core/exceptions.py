"""Domain errors. Services raise these; app.main turns them into HTTP responses."""


class NotFoundError(Exception):
    """The requested resource does not exist in the catalogue."""

    def __init__(self, resource: str, key: str) -> None:
        super().__init__(f"{resource} '{key}' was not found")
        self.resource = resource
        self.key = key


class GraphUnavailableError(Exception):
    """The graph database could not be reached or refused the query. Details are logged, never returned to clients."""
