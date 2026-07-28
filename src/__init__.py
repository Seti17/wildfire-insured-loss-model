# Makes `src` importable as a package so tests can do `from src.common
# import ...`. The numbered pipeline scripts still can't be imported this
# way (leading digits aren't valid identifiers) -- see common.py's
# docstring; this only exposes common.py itself.
