def init_admin(app):
    """Compatibility shim for the original project layout.

    The repo does not currently include Flask-Admin, and this app only needs
    an admin object placeholder during startup. Returning None keeps the app
    bootable without introducing an extra dependency.
    """
    return None
