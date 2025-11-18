#!/usr/bin/env python3
"""
Performance benchmark: Go vs Python scanner
"""
import json
import subprocess
import time
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from models.extractor import UnifiedCodeExtractor


def benchmark_python(directory: str) -> tuple:
    """Benchmark Python scanner"""
    extractor = UnifiedCodeExtractor()
    results = []
    
    start = time.perf_counter()
    
    for path in Path(directory).rglob("*"):
        if path.is_file():
            code = extractor.extract_code(str(path))
            if code:
                results.append({"path": str(path), "code": code})
    
    elapsed = time.perf_counter() - start
    return results, elapsed


def benchmark_go(directory: str) -> tuple:
    """Benchmark Go scanner"""
    scanner_exe = Path(__file__).parent.parent.parent / "classifier.exe"
    
    if not scanner_exe.exists():
        raise FileNotFoundError(f"Go scanner not found: {scanner_exe}")
    
    start = time.perf_counter()
    
    result = subprocess.run(
        [str(scanner_exe), "-dir", directory, "-workers", "20"],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )
    
    elapsed = time.perf_counter() - start
    
    if result.returncode != 0:
        raise RuntimeError(f"Scanner failed: {result.stderr}")
    
    results = json.loads(result.stdout)
    return results, elapsed


def create_test_files(directory: str, count: int) -> Path:
    """Create test files for benchmarking"""
    test_dir = Path(directory)
    test_dir.mkdir(parents=True, exist_ok=True)
    
    patterns = [
        "STARS-{}.mp4", "SSIS-{}.mkv", "IPX-{}.avi",
        "MIDV-{}.mp4", "CAWD-{}.mkv", "JUL-{}.mp4",
        "PRED-{}.avi", "FSDSS-{}.mp4", "EBOD-{}.mkv", "ABW-{}.mp4",
    ]
    
    print(f"Creating {count} test files...")
    for i in range(count):
        pattern = patterns[i % len(patterns)]
        filename = pattern.format(100 + i)
        (test_dir / filename).touch()
    
    return test_dir


def main():
    test_sizes = [10, 100, 1000]
    
    print("=" * 60)
    print("Performance Benchmark: Go vs Python Scanner")
    print("=" * 60)
    
    results_summary = []
    
    for size in test_sizes:
        test_dir = Path(f"C:/Users/cy540/Downloads/benchmark_test_{size}")
        
        create_test_files(str(test_dir), size)
        
        print(f"\n{chr(9472) * 60}")
        print(f"Testing with {size} files")
        print(f"{chr(9472) * 60}")
        
        try:
            # Python
            print("Running Python scanner...")
            py_results, py_time = benchmark_python(str(test_dir))
            print(f"  OK Found {len(py_results)} videos in {py_time:.3f}s")
            
            # Go
            print("Running Go scanner...")
            go_results, go_time = benchmark_go(str(test_dir))
            print(f"  OK Found {len(go_results)} videos in {go_time:.3f}s")
            
            # Compare
            speedup = py_time / go_time if go_time > 0 else float("inf")
            print(f"\n  Results:")
            print(f"     Python: {py_time:.3f}s")
            print(f"     Go:     {go_time:.3f}s")
            print(f"     Speedup: {speedup:.2f}x")
            
            # Verify
            py_codes = sorted([r["code"] for r in py_results])
            go_codes = sorted([r["code"] for r in go_results])
            
            if py_codes == go_codes:
                print(f"     OK Results match perfectly")
            else:
                print(f"     WARNING Results differ:")
                print(f"        Python: {len(py_codes)} codes")
                print(f"        Go:     {len(go_codes)} codes")
            
            results_summary.append({
                "size": size,
                "python": py_time,
                "go": go_time,
                "speedup": speedup
            })
            
        finally:
            # Cleanup
            import shutil
            if test_dir.exists():
                shutil.rmtree(test_dir)
    
    print("\n" + "=" * 60)
    print("Benchmark Summary")
    print("=" * 60)
    for r in results_summary:
        print(f"{r['size']:4d} files: Python {r['python']:.3f}s | Go {r['go']:.3f}s | Speedup {r['speedup']:.2f}x")
    
    avg_speedup = sum(r["speedup"] for r in results_summary) / len(results_summary)
    print(f"\nAverage speedup: {avg_speedup:.2f}x")
    
    print("\nRecommendation:")
    if avg_speedup >= 5:
        print("  >> Integrate Go into GUI (5x+ faster)")
    elif avg_speedup >= 2:
        print("  >> Use Go for large scans only (2-5x faster)")
    else:
        print("  >> Stick with Python (< 2x improvement not worth complexity)")


if __name__ == "__main__":
    main()
