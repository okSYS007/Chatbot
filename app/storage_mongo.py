from __future__ import annotations


class MongoStorage:
    """Future storage adapter for MongoDB Atlas or another MongoDB provider."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("MongoDB storage will be added after the JSON MVP is stable.")
