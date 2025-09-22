import os
import sys

# 导入您原始的 main 函数
try:
    from main import main as original_main
except ImportError:
    print("错误：无法找到 'main.py'。请确保此脚本与 main.py 在同一目录下。")
    sys.exit(1)


def run_with_forced_no_git():
    """
    通过设置 GitPython 的专用环境变量来模拟无 Git 环境。
    这是最可靠的测试方法。
    """
    # 这个环境变量会覆盖任何 PATH 搜索，强制 GitPython 使用这个路径
    git_override_variable = 'GIT_PYTHON_GIT_EXECUTABLE'

    # 备份可能存在的旧值
    original_value = os.environ.get(git_override_variable)

    print("--- 准备模拟无 Git 环境 (可靠方法) ---")

    try:
        # 1. 将环境变量设置为一个无效的、不存在的路径
        #    这会强制 GitPython 在导入或使用时失败。
        invalid_path = "path_that_does_not_exist"
        os.environ[git_override_variable] = invalid_path
        print(f"已临时设置 {git_override_variable}={invalid_path}")

        print("--- 环境变量已修改，现在将启动您的主程序 ---")

        # 2. 调用您原来的 main() 函数
        original_main()

    finally:
        # 3. 无论程序是否出错，都恢复或删除该环境变量
        print("\n--- 测试结束，正在恢复原始环境变量 ---")
        if original_value is not None:
            # 如果原来有值，就恢复它
            os.environ[git_override_variable] = original_value
            print(f"已恢复 {git_override_variable}")
        else:
            # 如果原来没有这个变量，就删除它
            if git_override_variable in os.environ:
                del os.environ[git_override_variable]
                print(f"已移除临时设置的 {git_override_variable}")


if __name__ == "__main__":
    run_with_forced_no_git()
