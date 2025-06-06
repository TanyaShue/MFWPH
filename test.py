"""
完整的PySide6配置系统运行示例
包含所有必要的代码和测试数据
"""

import json
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QTextEdit
from PySide6.QtCore import Qt
import sys

from c import OptionsManager


# 从之前的代码中导入必要的类
# from option_parser import OptionsManager

def create_test_ui():
    """创建测试UI"""
    # 测试配置数据
    config_data = {
        "resource_name": "阴阳师",
        "resource_version": "v1.1.6-beta.2",
        "resource_tasks": [
            {
                "task_name": "自动御魂",
                "task_entry": "自动御魂",
                "options": ["soul_boost", "challenge_count", "soul_team"]
            },
            {
                "task_name": "日常任务",
                "task_entry": "日常_任务列表",
                "options": ["daily_tasks"]
            }
        ],
        "options": {
            "soul_boost": {
                "display_name": "御魂加成",
                "widget_type": "check_box",
                "default_value": False,
                "values": {
                    "true": {
                        "display": "启用",
                        "pipeline_override": {
                            "寮3026_copy1": {
                                "enabled": True
                            }
                        }
                    },
                    "false": {
                        "display": "关闭",
                        "pipeline_override": {
                            "寮3026_copy1": {
                                "enabled": False
                            }
                        }
                    }
                }
            },
            "challenge_count": {
                "display_name": "自动挑战次数",
                "widget_type": "spin_box",
                "default_value": 10,
                "min_value": 1,
                "max_value": 999,
                "pipeline_override": {
                    "自动御魂3": {
                        "custom_action_param": {
                            "expected_number": "{value}"
                        }
                    }
                }
            },
            "soul_team": {
                "display_name": "御魂队伍",
                "widget_type": "line_edit",
                "default_value": "默认队伍",
                "placeholder": "输入队伍名称",
                "pipeline_override": {
                    "自动御魂_装备": {
                        "custom_action_param": {
                            "team_name": "{value}"
                        }
                    }
                }
            },
            "daily_tasks": {
                "display_name": "日常任务选择",
                "widget_type": "check_list",
                "default_values": ["friendship", "mail"],
                "items": {
                    "friendship": {
                        "display": "送友情点",
                        "pipeline_override": {
                            "日常_任务列表": {
                                "custom_action_param": {
                                    "task_list": {
                                        "日常_送友情点": True
                                    }
                                }
                            }
                        }
                    },
                    "mail": {
                        "display": "邮件奖励",
                        "pipeline_override": {
                            "日常_任务列表": {
                                "custom_action_param": {
                                    "task_list": {
                                        "领取奖励_邮件": True
                                    }
                                }
                            }
                        }
                    },
                    "garden": {
                        "display": "庭院奖励",
                        "pipeline_override": {
                            "日常_任务列表": {
                                "custom_action_param": {
                                    "task_list": {
                                        "领取奖励_日常庭院奖励": True
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    # 创建应用
    app = QApplication(sys.argv)

    # 创建主窗口
    window = QMainWindow()
    window.setWindowTitle("阴阳师配置管理系统")
    window.resize(800, 600)

    # 创建中心部件
    central_widget = QWidget()
    window.setCentralWidget(central_widget)

    # 创建布局
    layout = QVBoxLayout(central_widget)

    # 创建选项管理器
    manager = OptionsManager(config_data)
    widgets = manager.create_widgets()

    # 添加所有控件
    for widget in widgets.values():
        layout.addWidget(widget)

    # 添加分隔线
    layout.addWidget(QWidget())  # 空白间隔

    # 创建输出区域
    output_text = QTextEdit()
    output_text.setReadOnly(True)
    output_text.setMaximumHeight(200)
    layout.addWidget(output_text)

    # 创建按钮组
    button_layout = QVBoxLayout()

    # 获取所有配置按钮
    btn_all = QPushButton("获取所有Pipeline配置")
    btn_all.clicked.connect(lambda: output_text.setPlainText(
        json.dumps(manager.get_all_pipeline_overrides(), ensure_ascii=False, indent=2)
    ))
    button_layout.addWidget(btn_all)

    # 获取御魂任务配置按钮
    btn_soul = QPushButton("获取自动御魂任务配置")
    btn_soul.clicked.connect(lambda: output_text.setPlainText(
        json.dumps(manager.get_pipeline_override_for_task("自动御魂"), ensure_ascii=False, indent=2)
    ))
    button_layout.addWidget(btn_soul)

    # 获取日常任务配置按钮
    btn_daily = QPushButton("获取日常任务配置")
    btn_daily.clicked.connect(lambda: output_text.setPlainText(
        json.dumps(manager.get_pipeline_override_for_task("日常任务"), ensure_ascii=False, indent=2)
    ))
    button_layout.addWidget(btn_daily)

    # 获取当前值按钮
    btn_values = QPushButton("获取当前所有值")
    btn_values.clicked.connect(lambda: output_text.setPlainText(
        json.dumps(manager.get_values(), ensure_ascii=False, indent=2)
    ))
    button_layout.addWidget(btn_values)

    layout.addLayout(button_layout)

    # 显示窗口
    window.show()

    # 运行应用
    sys.exit(app.exec())


def test_pipeline_generation():
    """测试pipeline生成逻辑"""
    # 模拟不同的用户设置
    test_cases = [
        {
            "name": "默认设置",
            "values": {
                "soul_boost": False,
                "challenge_count": 10,
                "soul_team": "默认队伍",
                "daily_tasks": ["friendship", "mail"]
            }
        },
        {
            "name": "开启加成",
            "values": {
                "soul_boost": True,
                "challenge_count": 50,
                "soul_team": "速刷队",
                "daily_tasks": ["friendship", "mail", "garden"]
            }
        }
    ]

    for test in test_cases:
        print(f"\n=== {test['name']} ===")
        print("设置值:", json.dumps(test['values'], ensure_ascii=False, indent=2))

        # 根据设置生成pipeline_override
        # 这里展示生成逻辑
        pipeline = {}

        # 处理soul_boost
        if test['values']['soul_boost']:
            pipeline["寮3026_copy1"] = {"enabled": True}
        else:
            pipeline["寮3026_copy1"] = {"enabled": False}

        # 处理challenge_count
        pipeline["自动御魂3"] = {
            "custom_action_param": {
                "expected_number": str(test['values']['challenge_count'])
            }
        }

        # 处理soul_team
        pipeline["自动御魂_装备"] = {
            "custom_action_param": {
                "team_name": test['values']['soul_team']
            }
        }

        # 处理daily_tasks
        task_list = {}
        if "friendship" in test['values']['daily_tasks']:
            task_list["日常_送友情点"] = True
        if "mail" in test['values']['daily_tasks']:
            task_list["领取奖励_邮件"] = True
        if "garden" in test['values']['daily_tasks']:
            task_list["领取奖励_日常庭院奖励"] = True

        if task_list:
            pipeline["日常_任务列表"] = {
                "custom_action_param": {
                    "task_list": task_list
                }
            }

        print("生成的Pipeline:", json.dumps(pipeline, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    # 如果已经导入了OptionsManager类，运行UI
    # create_test_ui()

    # 否则运行测试
    test_pipeline_generation()