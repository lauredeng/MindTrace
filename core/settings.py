"""Small server-only settings reader; never enumerate or print secrets."""
import os


def secret_value(name):
    try:
        import streamlit as st
        return st.secrets.get(name)
    except (FileNotFoundError, KeyError):
        return None
    except Exception:
        raise RuntimeError('服务端配置暂不可用，请联系演示提供者。') from None


def setting(name, default=''):
    injected = os.getenv(name)
    if injected is not None and injected.strip():
        return injected.strip()
    value = secret_value(name)
    return str(value).strip() if value is not None else str(default)


def development_mode():
    return setting('MINDTRACE_ENV', 'production') == 'development'


def developer_enabled():
    return setting('MINDTRACE_ENABLE_DEVELOPER_MODE', '0') == '1'


def integer_setting(name, default):
    try:
        value = int(setting(name, default))
        if value < 0:
            raise ValueError()
        return value
    except (TypeError, ValueError):
        raise RuntimeError('服务端额度配置无效，请联系演示提供者。') from None

