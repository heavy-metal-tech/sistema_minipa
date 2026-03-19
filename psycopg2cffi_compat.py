# Compatibilidade psycopg2cffi com SQLAlchemy no Python 3.14
try:
    import psycopg2
except ImportError:
    from psycopg2cffi import compat
    compat.register()
