import tracemalloc
import runpy
import argparse
import sys
import os

def main():
    parser = argparse.ArgumentParser(description="Profile memory usage of a Python script using tracemalloc.")
    parser.add_argument("script", help="The Python script to run (e.g., main.py)")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments to pass to the script")
    args = parser.parse_args()

    if not os.path.exists(args.script):
        print(f"Error: Script '{args.script}' not found.")
        sys.exit(1)

    # Start tracing memory allocations
    tracemalloc.start()

    # Override sys.argv so the target script gets its expected arguments
    sys.argv = [args.script] + args.args

    print(f"Running '{args.script}' with memory tracking enabled...")
    try:
        runpy.run_path(args.script, run_name="__main__")
    except SystemExit as e:
        # Expected if script calls sys.exit()
        pass
    except Exception as e:
        print(f"\nScript execution interrupted or ended with error: {e}")

    # Take a snapshot of memory usage
    snapshot = tracemalloc.take_snapshot()
    
    # We can filter out memory allocations made by tracemalloc itself or this wrapper
    # But usually looking at the top is enough
    top_stats = snapshot.statistics('lineno')

    print("\n" + "="*80)
    print("--- TOP 20 MEMORY ALLOCATIONS BY LINE OF CODE ---")
    print("="*80)
    for stat in top_stats[:20]:
        print(stat)
        
    print("\n" + "="*80)
    print("--- TOTAL MEMORY PROFILED ---")
    print("="*80)
    # Calculate total size
    total = sum(stat.size for stat in top_stats)
    print(f"Total allocated memory tracked: {total / 1024 / 1024:.1f} MiB")

if __name__ == "__main__":
    main()
