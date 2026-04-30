import os
import json

data_dir = "data"
unique_headers = set()

for filename in os.listdir(data_dir):
    if filename.endswith(".headers.json"):
        with open(os.path.join(data_dir, filename), "r", encoding="utf-8") as f:
            headers = json.load(f)
            for h in headers.keys():
                unique_headers.add(h)

print("Unique headers found:")
for h in sorted(unique_headers):
    print(h)
