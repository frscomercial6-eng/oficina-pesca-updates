import sys, os
print(f"Python: {sys.executable}")
print(f"Version: {sys.version}")
print(f"Version info: {sys.version_info}")

# Check what multiprocessing.spawn.spawn should be
# In Python 3.8+, it's the main entry point for spawn context
import multiprocessing.spawn as mp
print(f"spawn module: {mp}")
print(f"spawn module file: {mp.__file__}")

# Check if there's a 'spawn' function
print(f"has spawn: {hasattr(mp, 'spawn')}")

# In Python 3.8+, spawn context uses 'spawn_main'
# Let's see what multiprocessing.get_start_method returns
import multiprocessing
print(f"\nstart_method: {multiprocessing.get_start_method(allow_none=True)}")

# Check if spawn context is supported
try:
    ctx = multiprocessing.get_context('spawn')
    print(f"spawn context: {ctx}")
    print(f"spawn context Process: {ctx.Process}")
except ValueError as e:
    print(f"spawn context NOT SUPPORTED: {e}")

# Check the multiprocessing source
import inspect
spawn_file = inspect.getfile(mp)
print(f"\nspawn module file: {spawn_file}")
with open(spawn_file, 'r') as f:
    content = f.read()
print(f"File size: {len(content)} bytes")
print(f"Has 'def spawn': {'def spawn' in content}")
print(f"Has 'spawn_main': {'spawn_main' in content}")
