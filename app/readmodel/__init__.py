"""Read-model builders — run inside the collector, never in the web tier.

Each function turns collected state (simulated today, real telemetry later) into a
plain dict that one page and its JSON API twin render. The collector publishes
these dicts to Redis on a schedule; the web process only reads them back.
"""
