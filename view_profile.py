import pstats
from pstats import SortKey
import argparse

def main():
    parser = argparse.ArgumentParser(description="Analyze cProfile output file.")
    parser.add_argument(
        "file", 
        help="The profiling output file (default: 'profiling')", 
        nargs="?", 
        default="profiling"
    )
    args = parser.parse_args()

    try:
        print(f"Reading profiling data from: {args.file}\n")
        p = pstats.Stats(args.file)
        
        p.strip_dirs()
        
        print("="*80)
        print("--- TOP 30 FUNCTIONS BY CUMULATIVE TIME ---")
        print("(Total time spent in the function and all sub-functions it calls)")
        print("="*80)
        p.sort_stats(SortKey.CUMULATIVE).print_stats(30)
        
        print("\n" + "="*80)
        print("--- TOP 30 FUNCTIONS BY INTERNAL TIME ---")
        print("(Time spent purely within the function itself, excluding sub-functions)")
        print("="*80)
        p.sort_stats(SortKey.TIME).print_stats(30)
        
        print("\n" + "="*80)
        print("--- TOP 30 FUNCTIONS BY CALL COUNT ---")
        print("(Functions that are called the most often)")
        print("="*80)
        p.sort_stats(SortKey.CALLS).print_stats(30)
        
    except FileNotFoundError:
        print(f"Error: Could not find the file '{args.file}'. Please ensure you have run the profiler.")
    except Exception as e:
        print(f"An error occurred while reading the profile: {e}")

if __name__ == "__main__":
    main()
