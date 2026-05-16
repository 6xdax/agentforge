"""全部本地测试的快速运行器。"""

import sys
import subprocess
from pathlib import Path

def run_test(script_name):
    """运行一个测试脚本并返回成功状态。"""
    script_path = Path(__file__).parent / script_name
    print(f"\n{'='*70}")
    print(f"运行：{script_name}")
    print(f"{'='*70}\n")
    
    result = subprocess.run([sys.executable, str(script_path)], cwd=Path(__file__).parent)
    return result.returncode == 0


def main():
    """运行所有本地测试（不需要服务器）。"""
    print("\n" + "="*70)
    print("运行所有本地测试（不需要服务器）")
    print("="*70)
    
    tests = [
        "test_auth.py",
        "test_session.py",
    ]
    
    results = {}
    for test in tests:
        results[test] = run_test(test)
    
    # 汇总
    print("\n" + "="*70)
    print("测试汇总")
    print("="*70)
    for test, passed in results.items():
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{test:30} {status}")
    
    print("\n" + "="*70)
    
    all_passed = all(results.values())
    if all_passed:
        print("所有测试通过！✓")
        print("="*70)
        print("\n要运行API集成测试，需要先启动服务器：")
        print("  cd ..")
        print("  python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 9000")
        print("\n然后在另一个终端中：")
        print("  python3 test_api_integration.py")
        return 0
    else:
        print("一些测试失败！✗")
        print("="*70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
