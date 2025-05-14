import os
import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import Qt

from app.models.config.global_config import global_config
from app.pages import HomePage


def main():
    app = QApplication(sys.argv)

    devices_config_path = "assets/debug/app_config.json"
    # 如果文件不存在，先创建该文件并写入 "{}"
    if not os.path.exists(devices_config_path):
        # 确保父目录存在
        os.makedirs(os.path.dirname(devices_config_path), exist_ok=True)
        with open(devices_config_path, "w", encoding="utf-8") as f:
            f.write("{}")

    global_config.load_devices_config(devices_config_path)

    resource_dir = "assets/resource/"
    # 如果目录不存在，则创建
    if not os.path.exists(resource_dir):
        os.makedirs(resource_dir)

    global_config.load_all_resources_from_directory(resource_dir)

        # task_manager.setup_all_device_scheduled_tasks()

    # 创建主窗口，并将 HomePage 作为中央部件加载
    main_window = QMainWindow()
    main_window.setWindowTitle("设备管理系统")
    main_window.setAttribute(Qt.WA_StyledBackground, True)  # 确保使用样式表自定义背景绘制

    # 创建 HomePage 实例
    home_page = HomePage()

    # 设置 HomePage 为主窗口的中央窗口
    main_window.setCentralWidget(home_page)

    # 可选择设置主窗口尺寸
    main_window.resize(1024, 768)
    main_window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
