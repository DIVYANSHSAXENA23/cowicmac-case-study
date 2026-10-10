"""Domain-specific exceptions for CoWiC-MAC."""


class CoWiCError(Exception):
    """Base class for all CoWiC-MAC errors."""


class ConfigurationError(CoWiCError):
    """Raised when a configuration value is missing or out of range."""


class TraceError(CoWiCError):
    """Raised when a WiFi trace is malformed or cannot be generated."""
