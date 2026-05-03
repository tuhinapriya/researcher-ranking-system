import json
import sys
from urllib import request


payload = {
    "query": "robotics",
    "use_mock_data": True,
    "pareto_enabled": False,
}

if len(sys.argv) > 1:
    payload["query"] = sys.argv[1]

http_request = request.Request(
    "http://127.0.0.1:8000/api/rank",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

with request.urlopen(http_request) as response:
    print(response.read().decode("utf-8"))
