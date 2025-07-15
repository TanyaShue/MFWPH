# optimized_node_editor.py
"""
优化后的节点编辑器
- 清晰的模块结构
- 完整的连接功能
- 正确的拖拽连线
- 命令模式支持撤销/重做
"""

import json
import time
import os
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

from PySide6.QtCore import (
    Qt, QPointF, QRectF, Signal, QObject, QTimer,
    QLineF, QPropertyAnimation, QEasingCurve
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QWheelEvent, QMouseEvent,
    QKeyEvent, QBrush, QFont, QPainterPath, QPixmap,
    QLinearGradient, QRadialGradient
)
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QWidget, QVBoxLayout,
    QLabel, QMenu, QGraphicsItem, QGraphicsPathItem,
    QGraphicsDropShadowEffect, QApplication
)


# ============= 数据结构定义 =============

@dataclass
class PortConfig:
    """端口配置"""
    name: str
    port_type: str  # 'input' or 'output'
    data_type: str = 'any'
    position: str = 'auto'  # 'top', 'bottom', 'left', 'right'
    max_connections: int = -1  # -1表示无限制
    color: Optional[str] = None


@dataclass
class NodeMetadata:
    """节点元数据"""
    type_id: str
    display_name: str
    category: str
    description: str = ""
    icon: Optional[str] = None
    color_scheme: Dict[str, str] = field(default_factory=dict)
    default_size: Tuple[float, float] = (240, 160)
    resizable: bool = True
    ports: List[PortConfig] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


# ============= 端口系统 =============

class Port(QGraphicsItem):
    """端口基类"""

    def __init__(self, node: 'BaseNode', config: PortConfig, parent=None):
        super().__init__(parent)
        self.node = node
        self.config = config
        self.connections: Set['Connection'] = set()

        # 视觉属性
        self.radius = 6
        self.hover_radius = 8
        self._hovered = False

        # 设置标志
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CrossCursor)

    def boundingRect(self) -> QRectF:
        """获取边界矩形"""
        r = self.hover_radius if self._hovered else self.radius
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, painter: QPainter, option, widget):
        """绘制端口"""
        painter.setRenderHint(QPainter.Antialiasing)

        # 确定颜色
        if self.config.color:
            color = QColor(self.config.color)
        else:
            color = QColor(100, 150, 200) if self.config.port_type == 'input' else QColor(200, 150, 100)

        # 绘制外圈
        r = self.hover_radius if self._hovered else self.radius
        painter.setPen(QPen(color.darker(150), 2))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(0, 0), r, r)

        # 如果有连接，绘制内圈
        if self.connections:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color.darker(150)))
            painter.drawEllipse(QPointF(0, 0), r * 0.5, r * 0.5)

    def hoverEnterEvent(self, event):
        """鼠标进入事件"""
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """鼠标离开事件"""
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def can_connect_to(self, other: 'Port') -> bool:
        """判断是否可以连接到另一个端口"""
        # 不能连接到自己
        if other == self:
            return False

        # 不能连接到同一个节点
        if other.node == self.node:
            return False

        # 输入只能连接到输出，输出只能连接到输入
        if self.config.port_type == other.config.port_type:
            return False

        # 检查连接数限制
        if self.config.max_connections != -1 and len(self.connections) >= self.config.max_connections:
            return False

        if other.config.max_connections != -1 and len(other.connections) >= other.config.max_connections:
            return False

        # 检查是否已经连接
        for conn in self.connections:
            if conn.get_other_port(self) == other:
                return False

        return True

    def add_connection(self, connection: 'Connection'):
        """添加连接"""
        self.connections.add(connection)
        self.update()

    def remove_connection(self, connection: 'Connection'):
        """移除连接"""
        self.connections.discard(connection)
        self.update()

    def get_connections(self) -> List['Connection']:
        """获取所有连接"""
        return list(self.connections)


class Connection(QGraphicsPathItem):
    """连接线"""

    def __init__(self, start_port: Port, end_port: Port):
        super().__init__()
        self.start_port = start_port
        self.end_port = end_port

        # 视觉属性
        self.setZValue(-1)  # 放在节点下面
        self._selected = False

        # 设置画笔
        self._update_pen()

        # 添加到端口
        self.start_port.add_connection(self)
        self.end_port.add_connection(self)

        # 设置标志
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        # 更新路径
        self.update_path()

    def _update_pen(self):
        """更新画笔"""
        color = QColor(100, 100, 100)
        width = 3 if self._selected else 2

        pen = QPen(color, width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)

        self.setPen(pen)

    def update_path(self):
        """更新连接路径"""
        # 获取端口的场景坐标
        start_pos = self.start_port.scenePos()
        end_pos = self.end_port.scenePos()

        # 创建贝塞尔曲线路径
        path = QPainterPath()
        path.moveTo(start_pos)

        # 计算控制点
        dx = end_pos.x() - start_pos.x()
        dy = end_pos.y() - start_pos.y()

        ctrl1 = QPointF(start_pos.x() + dx * 0.5, start_pos.y())
        ctrl2 = QPointF(end_pos.x() - dx * 0.5, end_pos.y())

        # 如果是垂直连接，调整控制点
        if abs(dx) < 50:
            offset = 50
            ctrl1 = QPointF(start_pos.x(), start_pos.y() + offset)
            ctrl2 = QPointF(end_pos.x(), end_pos.y() - offset)

        path.cubicTo(ctrl1, ctrl2, end_pos)
        self.setPath(path)

    def itemChange(self, change, value):
        """处理项目变化"""
        if change == QGraphicsItem.ItemSelectedChange:
            self._selected = value
            self._update_pen()

        return super().itemChange(change, value)

    def get_other_port(self, port: Port) -> Optional[Port]:
        """获取另一端的端口"""
        if port == self.start_port:
            return self.end_port
        elif port == self.end_port:
            return self.start_port
        return None

    def delete(self):
        """删除连接"""
        self.start_port.remove_connection(self)
        self.end_port.remove_connection(self)

        scene = self.scene()
        if scene:
            scene.removeItem(self)


# ============= 节点基类 =============

class BaseNode(QGraphicsItem):
    """所有节点的基类"""

    class Signals(QObject):
        property_changed = Signal(str, object)
        port_connected = Signal(str, object)
        port_disconnected = Signal(str, object)
        position_changed = Signal(QPointF)
        selected_changed = Signal(bool)

    def __init__(self, node_id: str, metadata: NodeMetadata, **kwargs):
        super().__init__()
        self.node_id = node_id
        self.metadata = metadata
        self.signals = self.Signals()

        # 关联的业务对象
        self.task_node = kwargs.get('task_node')

        # 节点状态
        self._properties: Dict[str, Any] = metadata.properties.copy()
        self._size = QPointF(*metadata.default_size)
        self._selected = False
        self._hovered = False

        # 端口管理
        self._input_ports: Dict[str, Port] = {}
        self._output_ports: Dict[str, Port] = {}

        # 视觉状态
        self._bounds = QRectF(0, 0, self._size.x(), self._size.y())

        # 设置标志
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        # 添加阴影效果
        self._setup_effects()

        # 初始化
        self._initialize_ports()
        self.initialize()

    def _setup_effects(self):
        """设置视觉效果"""
        # 这里可以添加阴影等效果
        pass

    def _initialize_ports(self):
        """根据元数据初始化端口"""
        for port_config in self.metadata.ports:
            port = Port(self, port_config, self)

            if port_config.port_type == 'input':
                self._input_ports[port_config.name] = port
            else:
                self._output_ports[port_config.name] = port

            # 设置端口位置
            self._update_port_position(port)

    def _update_port_position(self, port: Port):
        """更新端口位置"""
        config = port.config

        if config.position == 'top':
            port.setPos(self._bounds.width() / 2, 0)
        elif config.position == 'bottom':
            port.setPos(self._bounds.width() / 2, self._bounds.height())
        elif config.position == 'left':
            port.setPos(0, self._bounds.height() / 2)
        elif config.position == 'right':
            port.setPos(self._bounds.width(), self._bounds.height() / 2)
        else:  # auto
            if config.port_type == 'input':
                port.setPos(self._bounds.width() / 2, 0)
            else:
                port.setPos(self._bounds.width() / 2, self._bounds.height())

    def initialize(self):
        """初始化节点（子类应该重写）"""
        pass

    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """处理节点逻辑（子类应该重写）"""
        return {}

    # 属性管理
    def get_property(self, name: str) -> Any:
        """获取属性值"""
        return self._properties.get(name)

    def set_property(self, name: str, value: Any):
        """设置属性值"""
        old_value = self._properties.get(name)
        self._properties[name] = value
        self.signals.property_changed.emit(name, value)
        self.on_property_changed(name, old_value, value)
        self.update()

    def on_property_changed(self, name: str, old_value: Any, new_value: Any):
        """属性变化回调（子类可重写）"""
        if self.task_node and hasattr(self.task_node, name):
            setattr(self.task_node, name, new_value)

    # 端口管理
    def get_input_port(self, name: str) -> Optional[Port]:
        """获取输入端口"""
        return self._input_ports.get(name)

    def get_output_port(self, name: str) -> Optional[Port]:
        """获取输出端口"""
        return self._output_ports.get(name)

    def get_all_connections(self) -> List[Connection]:
        """获取所有连接"""
        connections = []
        for port in self._input_ports.values():
            connections.extend(port.get_connections())
        for port in self._output_ports.values():
            connections.extend(port.get_connections())
        return list(set(connections))  # 去重

    # 绘制相关
    def boundingRect(self) -> QRectF:
        """获取边界矩形"""
        return self._bounds.adjusted(-2, -2, 2, 2)

    def paint(self, painter: QPainter, option, widget):
        """绘制节点"""
        painter.setRenderHint(QPainter.Antialiasing)

        # 获取颜色方案
        colors = self._get_color_scheme()

        # 绘制阴影
        if not self._selected:
            shadow_color = QColor(0, 0, 0, 30)
            shadow_rect = self._bounds.adjusted(2, 2, 2, 2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(shadow_color))
            painter.drawRoundedRect(shadow_rect, 8, 8)

        # 绘制主体
        if self._selected:
            # 选中状态的光晕效果
            glow_color = QColor(255, 200, 0, 50)
            for i in range(3):
                glow_rect = self._bounds.adjusted(-i * 2, -i * 2, i * 2, i * 2)
                painter.setPen(QPen(glow_color, 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(glow_rect, 8 + i, 8 + i)

        # 绘制背景
        painter.setPen(QPen(colors['border'], 2 if self._selected else 1))
        painter.setBrush(QBrush(colors['background']))
        painter.drawRoundedRect(self._bounds, 8, 8)

        # 绘制内容
        self._paint_content(painter, colors)

    def _get_color_scheme(self) -> Dict[str, QColor]:
        """获取颜色方案"""
        default_colors = {
            'background': QColor(250, 250, 250),
            'border': QColor(180, 180, 180),
            'header': QColor(60, 120, 180),
            'header_text': QColor(255, 255, 255),
            'content_text': QColor(50, 50, 50)
        }

        # 应用自定义颜色
        for key, value in self.metadata.color_scheme.items():
            if isinstance(value, str):
                default_colors[key] = QColor(value)

        # 选中状态
        if self._selected:
            default_colors['border'] = QColor(255, 165, 0)
        elif self._hovered:
            default_colors['border'] = QColor(100, 150, 200)

        return default_colors

    def _paint_content(self, painter: QPainter, colors: Dict[str, QColor]):
        """绘制内容（子类应该实现）"""
        # 绘制标题
        title_rect = QRectF(10, 10, self._bounds.width() - 20, 30)
        painter.setPen(colors['content_text'])
        painter.setFont(QFont("Arial", 10, QFont.Bold))

        title = self.get_property('display_name') or self.metadata.display_name
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, title)

    # 交互处理
    def hoverEnterEvent(self, event):
        """鼠标进入事件"""
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """鼠标离开事件"""
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        """处理项目变化"""
        if change == QGraphicsItem.ItemPositionHasChanged:
            # 更新所有连接
            for conn in self.get_all_connections():
                conn.update_path()
            self.signals.position_changed.emit(value)
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            self._selected = value
            self.signals.selected_changed.emit(value)

        return super().itemChange(change, value)


# ============= 具体节点类型 =============

class GenericNode(BaseNode):
    """通用节点"""

    def _paint_content(self, painter: QPainter, colors: Dict[str, QColor]):
        """绘制内容"""
        # 绘制标题栏
        header_height = 35
        header_rect = QRectF(0, 0, self._bounds.width(), header_height)

        # 渐变背景
        gradient = QLinearGradient(0, 0, 0, header_height)
        gradient.setColorAt(0, colors['header'])
        gradient.setColorAt(1, colors['header'].darker(110))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(header_rect, 8, 8)

        # 绘制标题
        painter.setPen(colors['header_text'])
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        title = self.get_property('display_name') or self.metadata.display_name
        painter.drawText(
            header_rect.adjusted(10, 0, -10, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            title
        )

        # 绘制属性
        content_rect = QRectF(
            10,
            header_height + 10,
            self._bounds.width() - 20,
            self._bounds.height() - header_height - 20
        )

        painter.setPen(colors['content_text'])
        painter.setFont(QFont("Arial", 9))

        y_offset = 0
        properties_to_show = ['recognition', 'action', 'enabled']

        for prop in properties_to_show:
            if y_offset + 20 > content_rect.height():
                break

            value = self.get_property(prop)
            if value is not None:
                text = f"{prop}: {value}"
                text_rect = QRectF(
                    content_rect.x(),
                    content_rect.y() + y_offset,
                    content_rect.width(),
                    20
                )
                painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)
                y_offset += 20


class RecognitionNode(BaseNode):
    """识别节点"""

    def __init__(self, node_id: str, metadata: NodeMetadata, **kwargs):
        super().__init__(node_id, metadata, **kwargs)
        self._images: List[QPixmap] = []

    def initialize(self):
        """初始化节点"""
        self._load_images()

    def _load_images(self):
        """加载识别图像"""
        if not self.task_node or not hasattr(self.task_node, 'template'):
            return

        template = self.task_node.template
        if isinstance(template, str):
            template = [template]
        elif not isinstance(template, list):
            return

        # 这里简化处理，实际需要根据配置加载图像
        self._images = []

    def _paint_content(self, painter: QPainter, colors: Dict[str, QColor]):
        """绘制内容"""
        # 绘制标题栏
        header_height = 35
        header_rect = QRectF(0, 0, self._bounds.width(), header_height)

        # 使用绿色系配色
        gradient = QLinearGradient(0, 0, 0, header_height)
        gradient.setColorAt(0, QColor(46, 204, 113))
        gradient.setColorAt(1, QColor(39, 174, 96))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(header_rect, 8, 8)

        # 绘制标题
        painter.setPen(colors['header_text'])
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        title = self.get_property('display_name') or self.metadata.display_name
        painter.drawText(
            header_rect.adjusted(10, 0, -10, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            title
        )

        # 绘制内容区域
        content_rect = QRectF(
            10,
            header_height + 10,
            self._bounds.width() - 20,
            self._bounds.height() - header_height - 20
        )

        if not self._images:
            painter.setPen(colors['content_text'])
            painter.setFont(QFont("Arial", 9))
            painter.drawText(content_rect, Qt.AlignCenter, "No Template Images")
        else:
            # 绘制图像预览
            pass


# ============= 命令系统 =============

class Command(ABC):
    """命令基类"""

    @abstractmethod
    def execute(self):
        pass

    @abstractmethod
    def undo(self):
        pass


class AddNodeCommand(Command):
    """添加节点命令"""

    def __init__(self, canvas: 'NodeCanvas', node: BaseNode):
        self.canvas = canvas
        self.node = node

    def execute(self):
        self.canvas.scene.addItem(self.node)
        self.canvas.nodes[self.node.node_id] = self.node

    def undo(self):
        self.canvas.scene.removeItem(self.node)
        del self.canvas.nodes[self.node.node_id]


class DeleteNodesCommand(Command):
    """删除节点命令"""

    def __init__(self, canvas: 'NodeCanvas', nodes: List[BaseNode]):
        self.canvas = canvas
        self.nodes = nodes
        self.connections = []

        # 保存连接信息
        for node in nodes:
            for conn in node.get_all_connections():
                if conn not in self.connections:
                    self.connections.append(conn)

    def execute(self):
        # 先删除连接
        for conn in self.connections:
            conn.delete()

        # 再删除节点
        for node in self.nodes:
            self.canvas.scene.removeItem(node)
            del self.canvas.nodes[node.node_id]

    def undo(self):
        # 恢复节点
        for node in self.nodes:
            self.canvas.scene.addItem(node)
            self.canvas.nodes[node.node_id] = node

        # 恢复连接
        for conn in self.connections:
            self.canvas.scene.addItem(conn)
            conn.start_port.add_connection(conn)
            conn.end_port.add_connection(conn)


class CreateConnectionCommand(Command):
    """创建连接命令"""

    def __init__(self, canvas: 'NodeCanvas', start_port: Port, end_port: Port):
        self.canvas = canvas
        self.start_port = start_port
        self.end_port = end_port
        self.connection = None

    def execute(self):
        self.connection = Connection(self.start_port, self.end_port)
        self.canvas.scene.addItem(self.connection)

    def undo(self):
        if self.connection:
            self.connection.delete()


class CommandManager:
    """命令管理器"""

    def __init__(self):
        self.undo_stack: List[Command] = []
        self.redo_stack: List[Command] = []

    def execute(self, command: Command):
        """执行命令"""
        command.execute()
        self.undo_stack.append(command)
        self.redo_stack.clear()

    def undo(self):
        """撤销"""
        if self.undo_stack:
            command = self.undo_stack.pop()
            command.undo()
            self.redo_stack.append(command)

    def redo(self):
        """重做"""
        if self.redo_stack:
            command = self.redo_stack.pop()
            command.execute()
            self.undo_stack.append(command)

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0


# ============= 节点画布 =============

class NodeCanvas(QWidget):
    """节点编辑器画布"""

    # 信号
    node_selected = Signal(object)
    node_added = Signal(object)
    node_removed = Signal(object)
    connection_created = Signal(object)
    connection_removed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        # 初始化组件
        self.scene = QGraphicsScene()
        self.scene.setSceneRect(-5000, -5000, 10000, 10000)

        # 节点管理
        self.nodes: Dict[str, BaseNode] = {}
        self.node_registry = self._create_node_registry()

        # 命令管理
        self.command_manager = CommandManager()

        # 剪贴板
        self.clipboard = None

        # 初始化UI
        self._init_ui()

        # 连接信号
        self._connect_signals()

    def _create_node_registry(self) -> Dict[str, NodeMetadata]:
        """创建节点注册表"""
        return {
            'generic_node': NodeMetadata(
                type_id='generic_node',
                display_name='Generic Node',
                category='General',
                color_scheme={
                    'header': '#3498db',
                    'background': '#ecf5ff',
                    'border': '#2980b9',
                    'header_text': '#ffffff',
                    'content_text': '#2c3e50'
                },
                ports=[
                    PortConfig('input', 'input', 'any', 'top'),
                    PortConfig('output', 'output', 'any', 'bottom'),
                    PortConfig('error', 'output', 'any', 'right')
                ],
                properties={
                    'recognition': 'DirectHit',
                    'action': 'Click',
                    'enabled': True
                }
            ),
            'recognition_node': NodeMetadata(
                type_id='recognition_node',
                display_name='Recognition Node',
                category='Recognition',
                color_scheme={
                    'header': '#27ae60',
                    'background': '#e8f8f5',
                    'border': '#229954',
                    'header_text': '#ffffff',
                    'content_text': '#1e5631'
                },
                ports=[
                    PortConfig('input', 'input', 'any', 'top'),
                    PortConfig('output', 'output', 'any', 'bottom'),
                    PortConfig('error', 'output', 'any', 'right')
                ],
                properties={
                    'recognition': 'TemplateMatch',
                    'threshold': 0.8,
                    'template': []
                }
            )
        }

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建视图
        self.view = NodeGraphicsView(self.scene, self)
        layout.addWidget(self.view)

        # 信息栏
        self.info_label = QLabel("Ready")
        self.info_label.setStyleSheet("""
            QLabel {
                background-color: #34495e;
                color: #ecf0f1;
                padding: 5px;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.info_label)

        # 绘制网格背景
        self._draw_grid()

    def _draw_grid(self):
        """绘制网格背景"""
        grid_size = 20
        grid_pen = QPen(QColor(200, 200, 200, 50), 0.5)

        for x in range(-5000, 5001, grid_size):
            self.scene.addLine(x, -5000, x, 5000, grid_pen)

        for y in range(-5000, 5001, grid_size):
            self.scene.addLine(-5000, y, 5000, y, grid_pen)

        # 主要网格线
        main_grid_pen = QPen(QColor(150, 150, 150, 80), 1)
        for x in range(-5000, 5001, grid_size * 5):
            self.scene.addLine(x, -5000, x, 5000, main_grid_pen)

        for y in range(-5000, 5001, grid_size * 5):
            self.scene.addLine(-5000, y, 5000, y, main_grid_pen)

    def _connect_signals(self):
        """连接信号"""
        self.scene.selectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self):
        """处理选择变化"""
        selected_items = self.scene.selectedItems()
        selected_nodes = [item for item in selected_items if isinstance(item, BaseNode)]

        if len(selected_nodes) == 1:
            self.node_selected.emit(selected_nodes[0])
            self.info_label.setText(f"Selected: {selected_nodes[0].metadata.display_name}")
        elif len(selected_nodes) > 1:
            self.info_label.setText(f"Selected {len(selected_nodes)} nodes")
        else:
            self.info_label.setText("Ready")

    def add_node(self, node_type: str, position: QPointF = None, task_node=None) -> Optional[BaseNode]:
        """添加节点"""
        if node_type not in self.node_registry:
            return None

        # 生成唯一ID
        node_id = f"{node_type}_{int(time.time() * 1000)}"

        # 获取元数据
        metadata = self.node_registry[node_type]

        # 创建节点
        if node_type == 'generic_node':
            node = GenericNode(node_id, metadata, task_node=task_node)
        elif node_type == 'recognition_node':
            node = RecognitionNode(node_id, metadata, task_node=task_node)
        else:
            node = BaseNode(node_id, metadata, task_node=task_node)

        # 设置位置
        if position:
            node.setPos(position)
        else:
            center = self.view.mapToScene(self.view.viewport().rect().center())
            node.setPos(center)

        # 添加到场景
        command = AddNodeCommand(self, node)
        self.command_manager.execute(command)

        self.node_added.emit(node)
        return node

    def delete_selected_nodes(self):
        """删除选中的节点"""
        selected_items = self.scene.selectedItems()
        selected_nodes = [item for item in selected_items if isinstance(item, BaseNode)]

        if selected_nodes:
            command = DeleteNodesCommand(self, selected_nodes)
            self.command_manager.execute(command)

            for node in selected_nodes:
                self.node_removed.emit(node)

    def copy_selected_nodes(self):
        """复制选中的节点"""
        selected_items = self.scene.selectedItems()
        selected_nodes = [item for item in selected_items if isinstance(item, BaseNode)]

        if selected_nodes:
            self.clipboard = []
            for node in selected_nodes:
                node_data = {
                    'type': node.metadata.type_id,
                    'properties': node._properties.copy(),
                    'position': node.pos(),
                    'task_node': node.task_node
                }
                self.clipboard.append(node_data)

            self.info_label.setText(f"Copied {len(selected_nodes)} nodes")

    def paste_nodes(self, position: QPointF = None):
        """粘贴节点"""
        if not self.clipboard:
            return

        if not position:
            position = self.view.mapToScene(self.view.viewport().rect().center())

        # 计算偏移量
        if self.clipboard:
            first_pos = self.clipboard[0]['position']
            offset = position - first_pos

        # 创建新节点
        new_nodes = []
        for node_data in self.clipboard:
            new_pos = node_data['position'] + offset

            # 创建节点副本
            import copy
            task_node_copy = copy.deepcopy(node_data['task_node']) if node_data['task_node'] else None

            node = self.add_node(
                node_data['type'],
                new_pos,
                task_node_copy
            )

            if node:
                # 设置属性
                for key, value in node_data['properties'].items():
                    node.set_property(key, value)

                new_nodes.append(node)

        # 选中新节点
        self.scene.clearSelection()
        for node in new_nodes:
            node.setSelected(True)

        self.info_label.setText(f"Pasted {len(new_nodes)} nodes")

    def clear(self):
        """清空画布"""
        # 删除所有节点
        all_nodes = list(self.nodes.values())
        if all_nodes:
            command = DeleteNodesCommand(self, all_nodes)
            self.command_manager.execute(command)

        # 清空选择
        self.scene.clearSelection()

        # 重置视图
        self.view.resetTransform()
        self.view.centerOn(0, 0)

    def keyPressEvent(self, event: QKeyEvent):
        """处理键盘事件"""
        # Delete键删除选中节点
        if event.key() == Qt.Key_Delete:
            self.delete_selected_nodes()

        # Ctrl+C 复制
        elif event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
            self.copy_selected_nodes()

        # Ctrl+V 粘贴
        elif event.key() == Qt.Key_V and event.modifiers() & Qt.ControlModifier:
            self.paste_nodes()

        # Ctrl+Z 撤销
        elif event.key() == Qt.Key_Z and event.modifiers() & Qt.ControlModifier:
            self.command_manager.undo()
            self.info_label.setText("Undo")

        # Ctrl+Y 重做
        elif event.key() == Qt.Key_Y and event.modifiers() & Qt.ControlModifier:
            self.command_manager.redo()
            self.info_label.setText("Redo")

        # Ctrl+A 全选
        elif event.key() == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
            for node in self.nodes.values():
                node.setSelected(True)

        super().keyPressEvent(event)


class NodeGraphicsView(QGraphicsView):
    """节点视图"""

    def __init__(self, scene: QGraphicsScene, canvas: NodeCanvas):
        super().__init__(scene)
        self.canvas = canvas

        # 视图设置
        self.setRenderHint(QPainter.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setDragMode(QGraphicsView.RubberBandDrag)

        # 连接状态
        self.connecting_port: Optional[Port] = None
        self.temp_connection: Optional[QGraphicsPathItem] = None

        # 拖动状态
        self.is_panning = False
        self.last_mouse_pos = None

    def mousePressEvent(self, event: QMouseEvent):
        """处理鼠标按下"""
        scene_pos = self.mapToScene(event.pos())
        item = self.scene().itemAt(scene_pos, self.transform())

        if event.button() == Qt.LeftButton:
            # 检查是否点击了端口
            if isinstance(item, Port):
                # 开始连接
                self.connecting_port = item
                self.setDragMode(QGraphicsView.NoDrag)

                # 创建临时连接线
                self.temp_connection = QGraphicsPathItem()
                self.temp_connection.setPen(QPen(QColor(100, 100, 100), 2, Qt.DashLine))
                self.scene().addItem(self.temp_connection)

                self._update_temp_connection(scene_pos)
                event.accept()
                return

        elif event.button() == Qt.MiddleButton:
            # 开始拖动画布
            self.is_panning = True
            self.last_mouse_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        elif event.button() == Qt.RightButton:
            # 显示右键菜单
            self._show_context_menu(scene_pos, event.globalPos())
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """处理鼠标移动"""
        scene_pos = self.mapToScene(event.pos())

        # 更新临时连接线
        if self.connecting_port and self.temp_connection:
            self._update_temp_connection(scene_pos)

            # 高亮可连接的端口
            item = self.scene().itemAt(scene_pos, self.transform())
            if isinstance(item, Port) and self.connecting_port.can_connect_to(item):
                self.setCursor(Qt.CrossCursor)
            else:
                self.setCursor(Qt.ForbiddenCursor)

            event.accept()
            return

        # 拖动画布
        if self.is_panning and self.last_mouse_pos:
            delta = event.pos() - self.last_mouse_pos
            self.last_mouse_pos = event.pos()

            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - delta.x())
            v_bar.setValue(v_bar.value() - delta.y())

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """处理鼠标释放"""
        scene_pos = self.mapToScene(event.pos())

        if event.button() == Qt.LeftButton and self.connecting_port:
            # 完成连接
            item = self.scene().itemAt(scene_pos, self.transform())

            if isinstance(item, Port) and self.connecting_port.can_connect_to(item):
                # 创建连接
                command = CreateConnectionCommand(
                    self.canvas,
                    self.connecting_port,
                    item
                )
                self.canvas.command_manager.execute(command)
                self.canvas.info_label.setText("Connection created")

            # 清理临时连接线
            if self.temp_connection:
                self.scene().removeItem(self.temp_connection)
                self.temp_connection = None

            self.connecting_port = None
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        elif event.button() == Qt.MiddleButton:
            self.is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _update_temp_connection(self, end_pos: QPointF):
        """更新临时连接线"""
        if not self.connecting_port or not self.temp_connection:
            return

        start_pos = self.connecting_port.scenePos()

        # 创建贝塞尔曲线路径
        path = QPainterPath()
        path.moveTo(start_pos)

        dx = end_pos.x() - start_pos.x()
        dy = end_pos.y() - start_pos.y()

        ctrl1 = QPointF(start_pos.x() + dx * 0.5, start_pos.y())
        ctrl2 = QPointF(end_pos.x() - dx * 0.5, end_pos.y())

        if abs(dx) < 50:
            offset = 50
            ctrl1 = QPointF(start_pos.x(), start_pos.y() + offset)
            ctrl2 = QPointF(end_pos.x(), end_pos.y() - offset)

        path.cubicTo(ctrl1, ctrl2, end_pos)
        self.temp_connection.setPath(path)

    def _show_context_menu(self, scene_pos: QPointF, global_pos: QPointF):
        """显示右键菜单"""
        menu = QMenu()

        # 检查是否点击了节点
        item = self.scene().itemAt(scene_pos, self.transform())

        if isinstance(item, BaseNode):
            # 节点菜单
            copy_action = menu.addAction("复制节点")
            copy_action.triggered.connect(self.canvas.copy_selected_nodes)

            delete_action = menu.addAction("删除节点")
            delete_action.triggered.connect(self.canvas.delete_selected_nodes)

        elif isinstance(item, Connection):
            # 连接菜单
            delete_action = menu.addAction("删除连接")
            delete_action.triggered.connect(lambda: item.delete())

        else:
            # 画布菜单
            # 添加节点子菜单
            add_menu = menu.addMenu("添加节点")

            for node_type, metadata in self.canvas.node_registry.items():
                action = add_menu.addAction(metadata.display_name)
                action.triggered.connect(
                    lambda checked, nt=node_type, pos=scene_pos:
                    self.canvas.add_node(nt, pos)
                )

            menu.addSeparator()

            # 粘贴
            if self.canvas.clipboard:
                paste_action = menu.addAction("粘贴节点")
                paste_action.triggered.connect(
                    lambda: self.canvas.paste_nodes(scene_pos)
                )

        menu.exec(global_pos)

    def wheelEvent(self, event: QWheelEvent):
        """处理滚轮缩放"""
        # 设置缩放锚点
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        # 缩放因子
        scale_factor = 1.15

        if event.angleDelta().y() > 0:
            # 放大
            self.scale(scale_factor, scale_factor)
        else:
            # 缩小
            self.scale(1 / scale_factor, 1 / scale_factor)

        event.accept()


# ============= 使用示例 =============

if __name__ == '__main__':
    import sys

    app = QApplication(sys.argv)

    # 创建主窗口
    window = QWidget()
    window.setWindowTitle("Node Editor")
    window.setGeometry(100, 100, 1200, 800)

    layout = QVBoxLayout(window)

    # 创建节点画布
    canvas = NodeCanvas()
    layout.addWidget(canvas)

    # 添加一些示例节点
    node1 = canvas.add_node('generic_node', QPointF(100, 100))
    node2 = canvas.add_node('recognition_node', QPointF(400, 100))
    node3 = canvas.add_node('generic_node', QPointF(250, 300))

    window.show()

    sys.exit(app.exec())