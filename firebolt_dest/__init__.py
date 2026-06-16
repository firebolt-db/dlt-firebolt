"""dlt destination for Firebolt (staged Parquet + COPY INTO)."""

from firebolt_dest.factory import firebolt

__version__ = "0.1.3"

try:
    import dlt.destinations as _destinations

    if not hasattr(_destinations, "firebolt"):
        setattr(_destinations, "firebolt", firebolt)
except ImportError:
    pass

__all__ = ["firebolt", "__version__"]
