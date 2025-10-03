from importlib.metadata import version, PackageNotFoundError

try:
	__version__ = version("hakilens_scraper")
except PackageNotFoundError:
	__version__ = "0.1.0"

__all__ = [
	"__version__",
]


