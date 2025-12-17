#!/usr/bin/env python3
"""
War Thunder Audio Tool 打包脚本
使用PyInstaller将程序打包为单文件可执行程序
"""
import os
import sys
import subprocess
from pathlib import Path

def get_project_root():
    """
    获取项目根目录路径
    """
    # 当前脚本位于src目录下，向上一级即为项目根目录
    return Path(__file__).parent.parent

def main():
    """
    主函数，执行打包操作
    """
    project_root = get_project_root()
    src_dir = project_root / "src"
    ui_dir = project_root / "ui"
    
    # 确保在src目录下执行打包
    os.chdir(src_dir)
    
    # 构建PyInstaller命令
    cmd = [
        sys.executable,  # 使用当前Python解释器
        "-m", "PyInstaller",
        "--onefile",  # 单文件模式
        "--windowed",  # 无控制台窗口
        f"--icon={ui_dir}/favicon.ico",  # 设置图标
        "--name", "WarThunderAudioTool",  # 指定输出文件名
        "main.py"  # 主程序文件
    ]
    
    print(f"执行打包命令: {' '.join(cmd)}")
    
    # 执行打包命令
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    
    # 输出结果
    print(f"\n打包输出:")
    print(result.stdout)
    
    if result.stderr:
        print(f"\n错误信息:")
        print(result.stderr)
    
    if result.returncode == 0:
        print(f"\n✅ 打包成功！可执行文件位于: {src_dir}/dist/WarThunderAudioTool.exe")
    else:
        print(f"\n❌ 打包失败，返回码: {result.returncode}")
        sys.exit(result.returncode)

if __name__ == "__main__":
    main()