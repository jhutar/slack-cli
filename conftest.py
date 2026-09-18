def pytest_ignore_collect(collection_path, config):
    """Ignore directory entries pytest itself cannot stat.

    Guards against unreadable files (e.g. browser captures with a
    SELinux label that blocks this container) breaking collection.
    """
    try:
        collection_path.stat()
    except OSError:
        return True
