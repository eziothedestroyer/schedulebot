"""Store secrets in the operating system credential vault, never schedule.json."""
try:
    import keyring
except ImportError:
    keyring = None

SERVICE = "ScheduleBot"


def available():
    return keyring is not None


def get(name):
    if not keyring:
        return ""
    try:
        return keyring.get_password(SERVICE, name) or ""
    except Exception:
        return ""


def set_secret(name, value):
    if not keyring:
        return False
    try:
        if value:
            keyring.set_password(SERVICE, name, value)
        else:
            try: keyring.delete_password(SERVICE, name)
            except Exception: pass
        return True
    except Exception:
        return False

