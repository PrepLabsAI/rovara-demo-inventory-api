"""Domain failures are mapped to HTTP only at the boundary."""


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass
