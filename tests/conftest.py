"""
Configure Pytest and provide convenience fixtures.
"""

from typing import Iterator

import pytest
import sqlalchemy

from tracker import datastore


@pytest.fixture
def db_engine() -> sqlalchemy.Engine:
    return datastore.get_sqlite_engine()


@pytest.fixture
def session(db_engine: sqlalchemy.Engine) -> Iterator[datastore.DataSession]:
    with datastore.DataStore(db_engine).session() as session:
        yield session


@pytest.fixture
def transaction(session: datastore.DataSession) -> Iterator[datastore.DataTransaction]:
    with session.transaction() as transaction:
        yield transaction
