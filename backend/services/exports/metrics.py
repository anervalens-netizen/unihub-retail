"""Prometheus instrumentation owned by the export boundary."""
from prometheus_client import Counter, Gauge, Histogram

EXPORT_PEAK_RSS_BYTES = Gauge("export_peak_rss_bytes", "Peak resident set size observed while building the latest export.")
EXPORT_BUILD_SECONDS = Histogram("export_build_seconds", "Time spent serializing an XLSX artifact.", buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120))
EXPORT_LAST_BUILD_SECONDS = Gauge("export_last_build_seconds", "Build time of the latest durable complex export observed by the web process.")
EXPORT_OUTPUT_BYTES = Gauge("export_output_bytes", "Size of the latest XLSX artifact.")
EXPORT_CELLS = Gauge("export_cells", "Cell count passed to the XLSX writer.")
EXPORT_REJECTED_TOTAL = Counter("export_rejected_total", "Exports rejected by a finite resource or validation cap.", ("reason",))
