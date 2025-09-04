def parse_metrics_text(text):
    """
    Parse Prometheus metrics text and return a list of dicts with method, path, sum, count.
    """
    import re
    sum_pattern = re.compile(r'http_request_duration_seconds_sum\{method="([^"]+)",path="([^"]+)"\} ([\d\.eE+-]+)')
    count_pattern = re.compile(r'http_request_duration_seconds_count\{method="([^"]+)",path="([^"]+)"\} ([\d\.eE+-]+)')
    sum_map = {}
    count_map = {}
    for m in sum_pattern.finditer(text):
        method, path, value = m.groups()
        sum_map[(method, path)] = float(value)
    for m in count_pattern.finditer(text):
        method, path, value = m.groups()
        count_map[(method, path)] = float(value)
    metrics = []
    for key in sum_map:
        metrics.append({
            "method": key[0],
            "path": key[1],
            "sum": sum_map[key],
            "count": count_map.get(key, 0.0)
        })
    for key in count_map:
        if key not in sum_map:
            metrics.append({
                "method": key[0],
                "path": key[1],
                "sum": 0.0,
                "count": count_map[key]
            })
    metrics.sort(key=lambda x: (x["path"], x["method"]))
    return metrics
