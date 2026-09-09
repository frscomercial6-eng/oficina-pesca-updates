import sys

# Read the spawn.py file
with open(r'C:\Users\User\AppData\Local\Programs\Python\Python311\Lib\multiprocessing\spawn.py', 'r') as f:
    content = f.read()

# Search for 'spawn' in the content (not just def spawn)
idx = content.find('spawn')
while idx != -1:
    start = max(0, idx-20)
    end = min(len(content), idx+60)
    print(f"Position {idx}: ...{content[start:end]}...")
    idx = content.find('spawn', idx+1)
    if idx > 5000:  # Only first 5000 chars
        break
