import re
import sys

def parse_output(filepath):
    try:
        with open(filepath, 'r', encoding='utf-16le') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"File {filepath} not found.")
        return
        
    print(f"\n======================================")
    print(f"Analyzing {filepath}")
    print(f"======================================")

    # Find the RESPONSE PARSED structured section
    if 'RESPONSE PARSED:' not in content:
        print("Could not find RESPONSE PARSED:")
        return
        
    parsed_section = content.split('RESPONSE PARSED:')[1].split('RESPONSE USAGE_METADATA')[0]
    
    # Extract tags lists using regex. They look like: tags=[<JobTag.IT: 'IT'>, <JobTag.FIZYCZNA: 'praca fizyczna'>]
    # For Langchain they look the same.
    job_patterns = re.finditer(r"JobAnalysis\(index=(\d+),.*?tags=\[([^\]]+)\]\)", parsed_section, flags=re.DOTALL)
    
    multiple_tags = []
    transport_tags = []
    
    for match in job_patterns:
        index = match.group(1)
        tags_raw = match.group(2)
        
        # Regex to pull out just the string values like 'IT' from <JobTag.IT: 'IT'>
        tags_list = re.findall(r"'([^']+)'", tags_raw)
        
        if len(tags_list) > 1:
            multiple_tags.append((index, tags_list))
            
        if "transport" in tags_list:
            transport_tags.append((index, tags_list))
            
    print(f"Found {len(multiple_tags)} people with MULTIPLE tags:")
    for idx, tags in multiple_tags:
        print(f"  Person Index {idx}: {tags}")
        
    print(f"\nFound {len(transport_tags)} people with the 'transport' tag:")
    for idx, tags in transport_tags:
        print(f"  Person Index {idx}: {tags}")

parse_output("output_sdk.txt")
parse_output("output_langchain.txt")
