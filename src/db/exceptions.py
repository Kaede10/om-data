class DatabaseError(Exception):
    pass


class DatabaseConnectionError(DatabaseError):
    pass


class DatabaseOperationError(DatabaseError):
    pass


class DatabaseConfigError(DatabaseError):
    pass