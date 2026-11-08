"""Small single-process leases for paid batch execution, independent of file locks."""
from collections import OrderedDict
from contextlib import contextmanager
from threading import Lock

_GUARD = Lock()
_LEASES = OrderedDict()


@contextmanager
def batch_lease(workspace_id, batch_id):
    key = (workspace_id, batch_id)
    with _GUARD:
        lock = _LEASES.setdefault(key, Lock())
        _LEASES.move_to_end(key)
        if not lock.acquire(blocking=False):
            raise RuntimeError('这份作业正在另一窗口批改，请稍后刷新查看结果。')
        for old in list(_LEASES):
            if len(_LEASES) <= 256:
                break
            if not _LEASES[old].locked():
                del _LEASES[old]
    try:
        yield
    finally:
        with _GUARD:
            lock.release()
