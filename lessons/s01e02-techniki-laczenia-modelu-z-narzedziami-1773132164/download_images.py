import os
import re
import urllib.request
from urllib.parse import urlparse

base_dir = r"c:\Users\admin\git\arturroo\af-aidevs\lessons\s01e02-techniki-laczenia-modelu-z-narzedziami-1773132164"
images_dir = os.path.join(base_dir, "images")
markdown_path = os.path.join(base_dir, "s01e02-techniki-laczenia-modelu-z-narzedziami-1773132164.md")

if not os.path.exists(images_dir):
    os.makedirs(images_dir)

with open(markdown_path, 'r', encoding='utf-8') as f:
    original_content = f.read()

# Find all image URLs in ![alt](url) format
links = re.findall(r'!\[.*?\]\((https?://.*?)\)', original_content)
# Also find cover_image
cover_match = re.search(r"cover_image: '(https?://.*?)'", original_content)
if cover_match:
    links.append(cover_match.group(1))

unique_links = sorted(list(set(links)))

def download_file(url):
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path.lstrip('/')
    if not path:
        path = "index.html"
    
    target_path = os.path.join(images_dir, host, path)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    
    print(f"Downloading {url}...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(target_path, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
        print(f"Saved to: {target_path}")
    except Exception as e:
        print(f"Failed to download {url}: {e}")

for link in unique_links:
    download_file(link)

# Create local version
local_content = original_content
for link in unique_links:
    parsed = urlparse(link)
    host = parsed.netloc
    path = parsed.path.lstrip('/')
    if not path:
        path = "index.html"
    local_path = f"images/{host}/{path}"
    # Replace the link in the markdown
    local_content = local_content.replace(link, local_path)

local_md_path = os.path.join(base_dir, "s01e02-techniki-laczenia-modelu-z-narzedziami-1773132164-local.md")
with open(local_md_path, 'w', encoding='utf-8') as f:
    f.write(local_content)

print(f"Finished. Local markdown: {local_md_path}")
