from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


APP_STYLESHEET = """
QWidget {
    background-color: #0f151b;
    color: #e9f0f3;
    font-size: 13px;
}
QLabel, QCheckBox, QRadioButton { background: transparent; }
QMainWindow, QDialog { background-color: #0f151b; }
QMenuBar {
    background: #121a21;
    border-bottom: 1px solid #27333c;
    padding: 4px 8px;
}
QMenuBar::item { padding: 7px 12px; border-radius: 6px; }
QMenuBar::item:selected { background: #223039; }
QMenu {
    background: #182129;
    border: 1px solid #31404a;
    padding: 6px;
}
QMenu::item { padding: 8px 28px 8px 12px; border-radius: 5px; }
QMenu::item:selected { background: #263640; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #3a4852; min-height: 30px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QFrame#SummaryTile, QFrame#JobCard, QFrame#EmptyState {
    background: #182129;
    border: 1px solid #293741;
    border-radius: 12px;
}
QFrame#JobCard[active="true"] { border: 1px solid #35c7b2; }
QFrame#JobCard[disabled="true"] { background: #141b21; }
QFrame#QueueNotice {
    background: #13242a;
    border: 1px solid #24525a;
    border-radius: 10px;
}
QLabel#ActionCallout {
    background: #13242a;
    border: 1px solid #24525a;
    border-radius: 9px;
    padding: 11px;
}
QGroupBox {
    background: #151e25;
    border: 1px solid #2d3a44;
    border-radius: 10px;
    margin-top: 12px;
    padding: 14px 10px 10px 10px;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #aebdc5;
}
QLabel#Eyebrow { color: #35c7b2; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#PageTitle { color: #f3f7f9; font-size: 26px; font-weight: 700; }
QLabel#PageSubtitle, QLabel#Muted { color: #8fa0ac; }
QLabel#SummaryValue { color: #f3f7f9; font-size: 22px; font-weight: 700; }
QLabel#SummaryLabel { color: #8fa0ac; font-size: 12px; }
QLabel#CardTitle { color: #f3f7f9; font-size: 17px; font-weight: 700; }
QLabel#CardSubtitle { color: #94a4ae; }
QLabel#MetricLabel { color: #71828e; font-size: 11px; font-weight: 600; }
QLabel#MetricValue { color: #dce6ea; font-size: 13px; font-weight: 600; }
QLabel#StatusPill {
    background: #233139;
    border: 1px solid #344650;
    border-radius: 10px;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#StatusPill[state="running"] { color: #63dfcc; border-color: #287b70; background: #16302f; }
QLabel#StatusPill[state="success"] { color: #6bd696; border-color: #2e6d49; background: #182d23; }
QLabel#StatusPill[state="failed"] { color: #ff9098; border-color: #84434a; background: #351f24; }
QLabel#StatusPill[state="warning"] { color: #f4c97a; border-color: #80652f; background: #332b1b; }
QLabel#StatusPill[state="queued"] { color: #e8c673; border-color: #766235; background: #302a1b; }
QPushButton {
    background: #202b33;
    border: 1px solid #34434d;
    border-radius: 8px;
    min-height: 34px;
    padding: 0 13px;
    font-weight: 600;
}
QPushButton:hover { background: #283640; border-color: #4a5d68; }
QPushButton:pressed { background: #182129; }
QPushButton:focus { border: 2px solid #63dfcc; }
QPushButton:disabled { color: #596974; background: #171f25; border-color: #26323a; }
QPushButton[role="primary"] { color: #071513; background: #35c7b2; border-color: #35c7b2; }
QPushButton[role="primary"]:hover { background: #54d6c3; border-color: #54d6c3; }
QPushButton[role="danger"] { color: #ff9ca3; background: #2b1d21; border-color: #63373d; }
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QTimeEdit, QComboBox, QTableWidget {
    background: #111920;
    border: 1px solid #33414b;
    border-radius: 7px;
    padding: 7px 9px;
    selection-background-color: #287b70;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QTimeEdit:focus, QComboBox:focus, QTableWidget:focus { border-color: #35c7b2; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox QAbstractItemView { background: #182129; border: 1px solid #33414b; selection-background-color: #287b70; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border-radius: 4px; border: 1px solid #52636e; background: #111920; }
QCheckBox::indicator:checked { background: #35c7b2; border-color: #35c7b2; }
QTabWidget::pane { border: 1px solid #33414b; border-radius: 8px; top: -1px; }
QTabBar::tab { background: #151e25; border: 1px solid #2c3942; padding: 8px 18px; }
QTabBar::tab:selected { color: #55d8c4; background: #1b292f; border-bottom-color: #1b292f; }
QHeaderView::section { background: #1c272f; color: #aebdc5; border: none; border-bottom: 1px solid #33414b; padding: 8px; }
QTableWidget { gridline-color: #28353e; }
QTableWidget::item { padding: 6px; }
QTableWidget::item:selected { background: #1d4e4a; }
QToolTip { color: #eef5f7; background: #223039; border: 1px solid #40515c; padding: 6px; }
"""


def apply_theme(application: QApplication) -> None:
    application.setStyle("Fusion")
    application.setFont(QFont("Microsoft YaHei UI", 10))
    application.setStyleSheet(APP_STYLESHEET)


__all__ = ["APP_STYLESHEET", "apply_theme"]
