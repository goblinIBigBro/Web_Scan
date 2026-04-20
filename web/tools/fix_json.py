import os

filepath = 'web/config/algorithm_adapters.json'
with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

with open(filepath, 'w', encoding='utf-8') as f:
    for line in lines:
        if '"notes":' in line:
            indent = line.split('"notes":')[0]
            f.write(indent + '"notes": ""\n')
        else:
            f.write(line)
