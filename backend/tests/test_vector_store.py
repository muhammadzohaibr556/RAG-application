"""Real FAISS tests cover cosine search, IDs, persistence, and startup crash recovery."""

import numpy as np
import pytest

from app.errors import StorageError
from app.vector_store import FaissStore


def test_insert_search_reload_delete(tmp_path):
    store = FaissStore(tmp_path, 2, "test")
    store.add([101, 202], np.array([[10, 0], [0, 3]]))
    assert store.search(np.array([[2, 0]]), 1, {101, 202}) == [(101, 1.0)]
    store.close()
    reloaded = FaissStore(tmp_path, 2, "test")
    assert reloaded.ids() == {101, 202}
    assert reloaded.search(np.array([[2, 0]]), 1, {202}) == [(202, 0.0)]
    reloaded.remove([101])
    assert reloaded.ids() == {202}
    reloaded.close()


def test_reconcile_and_model_guard(tmp_path):
    store = FaissStore(tmp_path, 2, "test")
    store.add([1, 2], np.eye(2))
    store.reconcile({2})
    assert store.ids() == {2}
    with pytest.raises(StorageError, match="missing"):
        store.reconcile({2, 3})
    with pytest.raises(StorageError, match="one API worker"):
        FaissStore(tmp_path, 2, "test")
    store.close()
    with pytest.raises(StorageError, match="settings changed"):
        FaissStore(tmp_path, 2, "other-model")


def test_failed_persist_keeps_previous_index(tmp_path, monkeypatch):
    store = FaissStore(tmp_path, 2, "test")
    store.add([1], np.array([[1, 0]]))

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("app.vector_store.os.replace", fail)
    with pytest.raises(StorageError):
        store.add([2], np.array([[0, 1]]))
    assert store.ids() == {1}
    store.close()
