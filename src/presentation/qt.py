"""PyQt6 기반 KTX Macro - 개선된 버전"""
import sys
import os
import html
import datetime
import random
import time
import threading
import platform
import json
from pathlib import Path
from collections import deque
from string import Template

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit,
    QCheckBox, QScrollArea, QFrame, QComboBox, QDateEdit, QTimeEdit,
    QDialog, QStackedWidget, QTabWidget, QAbstractSpinBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QDate, QTime
from PyQt6.QtGui import QIcon, QPalette, QColor, QPixmap, QPainter
from src.domain.models.entities import ReservationRequest, Passenger, TrainSchedule, ReservationResult, CreditCard, PaymentResult
from src.domain.models.enums import PassengerType, TrainType
from src.infrastructure.adapters.ktx_service import KTXService
from src.infrastructure.security.credential_storage import CredentialStorage
from src.constants.ui import (
    DEFAULT_KTX_DEPARTURE, DEFAULT_KTX_ARRIVAL,
    RETRY_DELAY_MIN, RETRY_DELAY_MAX, MAX_CONCURRENT_JOBS, MAX_SEARCH_JOBS,
)


class NoScrollWheelMixin:
    """스크롤 영역 안에 있는 콤보박스/날짜/시간 필드가 포커스 없이도 마우스 휠에 반응해
    값을 바꿔버리는 문제를 막는다. 포커스가 없으면 휠 이벤트를 무시해서 부모(스크롤
    영역)로 흘려보내고, 클릭해서 포커스를 준 뒤에만 휠로 값 조정이 가능하게 한다."""

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NoScrollComboBox(NoScrollWheelMixin, QComboBox):
    pass


class NoScrollDateEdit(NoScrollWheelMixin, QDateEdit):
    pass


class NoScrollTimeEdit(NoScrollWheelMixin, QTimeEdit):
    pass


TRAIN_TYPE_LABELS = {
    TrainType.KTX: "KTX",
    TrainType.SAEMAEUL: "새마을호",
    TrainType.MUGUNGHWA: "무궁화호",
    TrainType.TONGGEUN: "통근열차",
    TrainType.NURIRO: "누리로",
    TrainType.ITX_CHEONGCHUN: "ITX-청춘",
    TrainType.AIRPORT: "공항직통",
}

# 검색 작업 카드들의 입력값을 재실행 후에도 유지하기 위한 저장 위치.
# 저장된 파일이 없는 최초 실행에서만 DEFAULT_SEARCH_JOBS로 카드를 채운다.
SEARCH_JOBS_STATE_PATH = Path.home() / ".ktx-srt-macro" / "search_jobs.json"

DEFAULT_SEARCH_JOBS = [
    {"dep": "대전", "arr": "서울", "date": "20260927", "time": "200000", "train_type": None},
    {"dep": "서울", "arr": "대전", "date": "20260923", "time": "210000", "train_type": None},
    {"dep": "조치원", "arr": "서울", "date": "20260926", "time": "150000", "train_type": None},
]


def resource_path(relative_path):
    """PyInstaller로 패키징된 리소스 파일의 절대 경로를 반환합니다."""
    try:
        # PyInstaller가 생성한 임시 폴더
        base_path = sys._MEIPASS
    except AttributeError:
        # 개발 환경
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    return os.path.join(base_path, relative_path)


def setup_dark_palette(app):
    """다크 모드 팔레트 설정 (Windows 시스템 테마 무시)"""
    palette = QPalette()

    # 기본 배경/전경 색상 - Dark Theme
    palette.setColor(QPalette.ColorRole.Window, QColor(17, 24, 39))  # #111827
    palette.setColor(QPalette.ColorRole.WindowText, QColor(243, 244, 246))  # #f3f4f6
    palette.setColor(QPalette.ColorRole.Base, QColor(31, 41, 55))  # #1f2937
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(17, 24, 39))  # #111827
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(31, 41, 55))  # #1f2937
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(243, 244, 246))  # #f3f4f6
    palette.setColor(QPalette.ColorRole.Text, QColor(243, 244, 246))  # #f3f4f6
    palette.setColor(QPalette.ColorRole.Button, QColor(31, 41, 55))  # #1f2937
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(209, 213, 219))  # #d1d5db
    palette.setColor(QPalette.ColorRole.BrightText, QColor(239, 68, 68))  # #ef4444
    palette.setColor(QPalette.ColorRole.Link, QColor(96, 165, 250))  # #60a5fa
    palette.setColor(QPalette.ColorRole.Highlight, QColor(59, 130, 246))  # #3b82f6
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))  # #ffffff

    # Disabled 상태
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(75, 85, 99))  # #4b5563
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(75, 85, 99))  # #4b5563
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(75, 85, 99))  # #4b5563

    app.setPalette(palette)


# ---- 디자인 토큰: "기차역 전광판(출발/도착 안내판)" 컨셉 ----
# 흔한 다크모드 대시보드 느낌을 피하고, 실제 역사(驛舍)의 종이/안내판 질감을 준다.
PAPER = "#F6F7F5"          # 앱 전체 배경 (따뜻한 밝은 회백)
INK = "#1C1F26"            # 본문 텍스트
RAIL_NAVY = "#16233F"      # 헤더 / 주요 강조
RAIL_BLUE = "#2F5FA3"      # 버튼 / 인터랙티브 강조, 포커스
SIGNAL_GREEN = "#2E7D32"   # 성공 / 예약완료 상태
SIGNAL_AMBER = "#F2A900"   # 진행중 / 주의 상태
HAIRLINE = "#D8DCE2"       # 구분선 / 보더 (실패·중지 상태 표시에도 사용)
BOARD_BG = "#12140F"       # 전광판(로그 · 예약완료 패널) 배경
BOARD_AMBER = "#FFB300"    # 전광판 텍스트 (앰버)

# 위 토큰에서 파생된 보조 값 (문서화된 9개 토큰을 그대로 쓰되, 구현에 필요한 변형만 추가)
CARD_BG = "#FFFFFF"
INK_MUTED = "rgba(28, 31, 38, 0.62)"
INK_FAINT = "rgba(28, 31, 38, 0.38)"
FOCUS_TINT = "rgba(47, 95, 163, 0.10)"
NEUTRAL_GRAY = "#9AA1AC"       # 대기 상태 색바 (HAIRLINE보다 또렷하게 보이도록)
SIGNAL_RED = "#B3261E"         # 중지 버튼 전용 (철도 정지 신호 느낌)


def setup_light_palette(app):
    """STYLESHEET(라이트 "기차역 전광판" 테마)와 일치하는 QPalette을 OS 설정과 무관하게 강제한다.

    Fusion 스타일은 OS가 다크 모드일 때 기본 QPalette 자체를 어둡게 만든다(실측: macOS
    다크 모드에서 Window #1e1e1e / WindowText #ffffff). STYLESHEET가 미처 다시 칠하지
    않는 위젯(팝업 등)은 이 QPalette로 배경/글자색이 새어나오므로, OS 테마와 무관하게
    항상 PAPER/INK 계열 라이트 팔레트를 쓰도록 명시해 대비를 보장한다.
    """
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(PAPER))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(INK))
    palette.setColor(QPalette.ColorRole.Base, QColor(CARD_BG))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(PAPER))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(CARD_BG))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(INK))
    palette.setColor(QPalette.ColorRole.Text, QColor(INK))
    palette.setColor(QPalette.ColorRole.Button, QColor(CARD_BG))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(INK))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(RAIL_BLUE))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))

    # Disabled 상태
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(HAIRLINE))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(HAIRLINE))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(HAIRLINE))

    app.setPalette(palette)


STYLESHEET = Template("""
* {
    font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "맑은 고딕", "Malgun Gothic", "Segoe UI", sans-serif;
}

QMainWindow {
    background: $PAPER;
}

#centralWidget {
    background: $PAPER;
    border-radius: 0px;
}

/* 탭 스타일 */
QTabWidget::pane {
    border: none;
    background: transparent;
    border-radius: 12px;
}

QTabBar::tab {
    background: transparent;
    color: $INK_MUTED;
    padding: 16px 28px;
    margin-right: 4px;
    border: none;
    font-size: 16px;
    font-weight: 700;
    min-width: 100px;
}

QTabBar::tab:selected {
    color: $RAIL_NAVY;
    background: $FOCUS_TINT;
    border-radius: 8px;
    font-weight: 800;
}

QTabBar::tab:hover:!selected {
    color: $RAIL_BLUE;
}

/* 최상위 탭("🚄 작업" / "🔔 알림")은 카드 탭보다 작게 - 페이지 전환용이라 시각적 위계를 낮춘다 */
QTabWidget#topTabs QTabBar::tab {
    padding: 8px 16px;
    font-size: 13px;
    min-width: 72px;
}

/* 헤더 - "안내판 라벨" 위계 */
QLabel#titleLabel {
    font-size: 26px;
    font-weight: 800;
    color: $RAIL_NAVY;
    padding: 20px 24px;
    background: transparent;
    letter-spacing: 0.5px;
}

QLabel#sectionLabel {
    font-size: 14px;
    font-weight: 700;
    color: $RAIL_NAVY;
    padding: 4px 0;
    background: transparent;
    letter-spacing: 1px;
}

QLabel {
    color: $INK_MUTED;
    font-size: 14px;
    background: transparent;
    font-weight: 500;
}

/* 카드 */
QFrame#card {
    background: $CARD_BG;
    border-radius: 14px;
    border: 1px solid $HAIRLINE;
    padding: 6px;
}

/* 입력 필드 */
QLineEdit, QComboBox, QDateEdit, QTimeEdit {
    background: $CARD_BG;
    border: 1.5px solid $HAIRLINE;
    border-radius: 10px;
    padding: 10px 12px;
    color: $INK;
    font-size: 14px;
    font-weight: 500;
    selection-background-color: $RAIL_BLUE;
    selection-color: #ffffff;
}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus {
    border: 2px solid $RAIL_BLUE;
    background: $FOCUS_TINT;
}

QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled, QTimeEdit:disabled {
    background: $PAPER;
    color: $INK_FAINT;
    border-color: $HAIRLINE;
}

QLineEdit::placeholder {
    color: $INK_FAINT;
    font-weight: 400;
}

QComboBox::drop-down, QDateEdit::drop-down {
    border: none;
    width: 22px;
}

QComboBox QAbstractItemView {
    background: $CARD_BG;
    color: $INK;
    border: 1px solid $HAIRLINE;
    selection-background-color: $RAIL_BLUE;
    selection-color: #ffffff;
    outline: none;
}

/* 버튼 */
QPushButton {
    background: $RAIL_BLUE;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 12px 22px;
    font-size: 14px;
    font-weight: 700;
    min-height: 40px;
}

QPushButton:hover {
    background: #3E6FB8;
}

QPushButton:pressed {
    background: #244C82;
}

QPushButton:disabled {
    background: $HAIRLINE;
    color: $INK_FAINT;
}

/* Primary 버튼 (예약 시작 등 핵심 CTA) */
QPushButton#primaryButton {
    background: $RAIL_NAVY;
    font-weight: 800;
    padding: 14px 26px;
    font-size: 15px;
    letter-spacing: 0.3px;
}

QPushButton#primaryButton:hover {
    background: #22355C;
}

QPushButton#primaryButton:pressed {
    background: #0F1830;
}

QPushButton#primaryButton:disabled {
    background: $HAIRLINE;
    color: $INK_FAINT;
}

/* Search 버튼 (보조 액션 - 아웃라인) */
QPushButton#searchButton {
    background: transparent;
    color: $RAIL_BLUE;
    border: 1.5px solid $RAIL_BLUE;
}

QPushButton#searchButton:hover {
    background: $FOCUS_TINT;
}

QPushButton#searchButton:pressed {
    background: rgba(47, 95, 163, 0.18);
}

/* Stop 버튼 */
QPushButton#stopButton {
    background: $SIGNAL_RED;
    color: #ffffff;
}

QPushButton#stopButton:hover {
    background: #99201A;
}

QPushButton#stopButton:pressed {
    background: #7A1915;
}

/* #stopButton은 ID 셀렉터라 기본 QPushButton:disabled보다 우선순위가 높아,
   :disabled 상태를 따로 정의하지 않으면 setEnabled(False) 상태에서도 계속
   붉은색(활성처럼) 보인다 - 카드 생성 직후 중지 버튼이 눌려있는 것처럼
   보이는 버그의 원인. */
QPushButton#stopButton:disabled {
    background: $HAIRLINE;
    color: $INK_FAINT;
}

/* Clear 버튼 */
QPushButton#clearButton {
    background: transparent;
    color: $INK_MUTED;
    border: 1.5px solid $HAIRLINE;
    padding: 8px 18px;
    min-height: 36px;
    font-weight: 600;
}

QPushButton#clearButton:hover {
    background: $PAPER;
    color: $INK;
    border-color: #C3C9D1;
}

/* 탭 위젯 corner "+" 버튼 (터미널의 새 탭 버튼처럼 작은 정사각형 - clearButton의
   18px 좌우 패딩을 쓰면 좁은 고정폭 안에서 글자가 밀려나 보이지 않으므로 별도 정의) */
QPushButton#addTabButton {
    background: transparent;
    color: $RAIL_BLUE;
    border: 1.5px solid $HAIRLINE;
    border-radius: 8px;
    padding: 0px;
    min-height: 0px;
    font-size: 18px;
    font-weight: 800;
}

QPushButton#addTabButton:hover {
    background: $FOCUS_TINT;
    border-color: $RAIL_BLUE;
}

QPushButton#addTabButton:pressed {
    background: rgba(47, 95, 163, 0.18);
}

/* #addTabButton도 #stopButton과 같은 ID 셀렉터 우선순위 함정이 있다.
   :disabled 상태를 따로 정의하지 않으면 setEnabled(False)여도 계속 활성처럼 보인다. */
QPushButton#addTabButton:disabled {
    background: transparent;
    color: $INK_FAINT;
    border-color: $HAIRLINE;
}

QPushButton#clearButton:pressed {
    background: $HAIRLINE;
}

/* 체크박스 */
QCheckBox {
    color: $INK;
    spacing: 10px;
    font-size: 14px;
    font-weight: 600;
}

QCheckBox::indicator {
    width: 20px;
    height: 20px;
    border-radius: 5px;
    border: 2px solid $HAIRLINE;
    background: $CARD_BG;
}

QCheckBox::indicator:hover {
    border-color: $RAIL_BLUE;
}

QCheckBox::indicator:checked {
    background: $RAIL_BLUE;
    border-color: $RAIL_BLUE;
    image: url(none);
}

/* 전광판 (로그 / 예약완료 패널) - Split-Flap Display */
QTextEdit#logDisplay {
    background: $BOARD_BG;
    color: $BOARD_AMBER;
    border: 1.5px solid #2A2C22;
    border-radius: 12px;
    padding: 16px 18px;
    font-family: "Menlo", "SF Mono", "D2Coding", "Consolas", monospace;
    font-size: 13px;
    line-height: 1.7;
    font-weight: 500;
}

/* 스크롤바 */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    border-radius: 4px;
    margin: 4px;
}

QScrollBar::handle:vertical {
    background: #C3C9D1;
    border-radius: 4px;
    min-height: 40px;
}

QScrollBar::handle:vertical:hover {
    background: #A9B0BA;
}

QScrollBar::handle:vertical:pressed {
    background: $RAIL_BLUE;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    border-radius: 4px;
    margin: 4px;
}

QScrollBar::handle:horizontal {
    background: #C3C9D1;
    border-radius: 4px;
    min-width: 40px;
}

QScrollBar::handle:horizontal:hover {
    background: #A9B0BA;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* 열차 항목 */
QFrame#trainItem {
    background: $CARD_BG;
    border: 1.5px solid $HAIRLINE;
    border-radius: 12px;
}

QFrame#trainItem:hover {
    background: $FOCUS_TINT;
    border: 1.5px solid $RAIL_BLUE;
}

/* 티켓 스텁 요약 헤더 */
QFrame#ticketStub {
    background: $FOCUS_TINT;
    border: 1px solid $HAIRLINE;
    border-radius: 10px;
}

QFrame#statusBar {
    border-radius: 2px;
}

QLabel#ticketRoute {
    color: $RAIL_NAVY;
    font-size: 18px;
    font-weight: 800;
    background: transparent;
}

QLabel#ticketMeta {
    color: $INK_MUTED;
    font-size: 14px;
    font-weight: 500;
    background: transparent;
}

QScrollArea {
    border: none;
    background: transparent;
}

/* 토스트 알림 (우측 하단 오버레이) */
QFrame#toastItem {
    background: $CARD_BG;
    border: 1.5px solid $HAIRLINE;
    border-radius: 10px;
}

QLabel#toastText {
    color: $INK;
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}

QWidget#toastHost {
    background: transparent;
}
""").substitute(
    PAPER=PAPER, INK=INK, RAIL_NAVY=RAIL_NAVY, RAIL_BLUE=RAIL_BLUE,
    SIGNAL_GREEN=SIGNAL_GREEN, SIGNAL_AMBER=SIGNAL_AMBER, HAIRLINE=HAIRLINE,
    BOARD_BG=BOARD_BG, BOARD_AMBER=BOARD_AMBER, CARD_BG=CARD_BG,
    INK_MUTED=INK_MUTED, INK_FAINT=INK_FAINT, FOCUS_TINT=FOCUS_TINT,
    SIGNAL_RED=SIGNAL_RED,
)


# ---- 토스트 알림 / 알림 히스토리 상수 ----
TOAST_WIDTH = 320
TOAST_MARGIN = 24
TOAST_DURATION_MS = 3500        # info/success 토스트 노출 시간
TOAST_ERROR_DURATION_MS = 5500  # error 토스트는 조금 더 오래 노출
MAX_VISIBLE_TOASTS = 4
NOTIFICATION_HISTORY_MAX = 200

# BOARD_BG(전광판 배경) 위에서 SIGNAL_GREEN/SIGNAL_RED를 그대로 쓰면 대비가 부족해
# (실측 각각 3.62:1 / 2.84:1) 판독이 어렵다. 전광판 텍스트 전용 파생 색을 별도로 둔다.
BOARD_GREEN = "#5CC46A"
BOARD_RED = "#FF7A6E"

TOAST_LEVEL_STYLES = {
    "success": (SIGNAL_GREEN, "✓"),
    "error": (SIGNAL_RED, "✗"),
    "info": (RAIL_BLUE, "ℹ"),
}

TOAST_LEVEL_BOARD_COLORS = {
    "success": BOARD_GREEN,
    "error": BOARD_RED,
    "info": BOARD_AMBER,
}

# 카드(SearchJobWidget)와 앱(탭 아이콘) 양쪽이 공유하는 상태별 색.
# STYLESHEET는 Template(...).substitute()라 $NEUTRAL_GRAY처럼 substitute 인자에 없는
# 새 $토큰을 QSS 안에 쓰면 import 자체가 깨진다 - 여기서는 순수 파이썬 딕셔너리라 무관하다.
JOB_STATUS_COLORS = {
    "대기중": (NEUTRAL_GRAY, INK_MUTED),
    "검색중": (SIGNAL_AMBER, SIGNAL_AMBER),
    "실행중": (SIGNAL_AMBER, SIGNAL_AMBER),
    "예약완료": (SIGNAL_GREEN, SIGNAL_GREEN),
    "중지됨": (HAIRLINE, INK_MUTED),
}


def make_status_dot_icon(color: str, diameter: int = 10) -> QIcon:
    """지정한 색의 원형 점 아이콘을 만든다 (작업 탭 헤더의 상태 색점용)."""
    pixmap = QPixmap(diameter, diameter)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(0, 0, diameter, diameter)
    painter.end()

    return QIcon(pixmap)


def play_alert_sound_once():
    """OS에 따라 알림음 1회 재생"""
    try:
        system = platform.system()
        if system == "Darwin":  # macOS
            os.system('afplay /System/Library/Sounds/Glass.aiff')
        elif system == "Windows":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
        elif system == "Linux":
            os.system('paplay /usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga 2>/dev/null || beep 2>/dev/null')
    except Exception as e:
        print(f"알림음 재생 실패: {e}")


class LogSignals(QObject):
    """로그 시그널 (앱 레벨 - 로그인 등 공용 이벤트)"""
    log_message = pyqtSignal(str)
    show_ktx_alert_button = pyqtSignal()  # 하위 호환용 (실제 알림음 중지 버튼은 SearchJobWidget이 각자 소유)


class AppSignals(QObject):
    """앱 레벨 시그널 (여러 검색 작업 카드가 공유하는 이벤트).

    워커 스레드에서 emit해도 슬롯은 항상 GUI 스레드(이 QObject가 생성된 스레드)에서
    큐잉되어 실행되므로 별도 락 없이 안전하다.
    """
    reservation_completed = pyqtSignal(dict)
    login_finished = pyqtSignal(bool, str)
    notification = pyqtSignal(str, str)  # (level, message) - 토스트 + 알림 히스토리 공용 채널


class JobSignals(QObject):
    """검색 작업 카드(SearchJobWidget) 전용 시그널.

    워커 스레드는 위젯을 직접 만지지 않고 이 시그널들만 emit한다.
    슬롯은 전부 GUI 스레드에서 실행된다(Qt 시그널/슬롯 큐잉).
    """
    log = pyqtSignal(str)
    state_changed = pyqtSignal(str)  # 워커 → GUI 내부 전이 요청 (예: "search_idle")
    trains_found = pyqtSignal(list)
    finished = pyqtSignal(bool)
    show_alert_button = pyqtSignal()
    status_changed = pyqtSignal(str)  # _set_status()가 실제로 바뀔 때마다 emit (앱의 탭 아이콘 갱신용)


class TrainItemWidget(QWidget):
    """열차 항목 위젯"""
    def __init__(self, train_info: str, parent=None):
        super().__init__(parent)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 2, 0, 2)

        frame = QFrame()
        frame.setObjectName("trainItem")

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        self.checkbox = QCheckBox()
        self.label = QLabel(train_info)
        self.label.setStyleSheet(f"font-size: 14px; color: {INK};")

        layout.addWidget(self.checkbox)
        layout.addWidget(self.label, 1)

        self.main_layout.addWidget(frame)


class SectionCard(QFrame):
    """섹션 카드 위젯"""
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(12)
        self.main_layout.setContentsMargins(20, 20, 20, 20)

        # 타이틀
        title_label = QLabel(title)
        title_label.setObjectName("sectionLabel")
        self.main_layout.addWidget(title_label)

    def add_widget(self, widget):
        """위젯 추가"""
        self.main_layout.addWidget(widget)

    def add_layout(self, layout):
        """레이아웃 추가"""
        self.main_layout.addLayout(layout)


class ToastWidget(QFrame):
    """자동 소멸하는 토스트 알림 1건. 좌측 4px 색 액센트 바 + 메시지 라벨로 구성된다."""

    closed = pyqtSignal(object)  # self를 함께 보내 ToastHost가 리스트에서 제거할 수 있게 한다

    def __init__(self, level: str, message: str, parent=None):
        super().__init__(parent)
        self.setObjectName("toastItem")
        self.setFixedWidth(TOAST_WIDTH)

        # 실제 호출부의 메시지는(add_log와 동일한 기존 관례로) 전부 자기 자신의 의미있는
        # 선두 이모지(✓/✗/🚀/🔍 등)를 이미 달고 온다. 레벨 구분은 좌측 색바가 맡으므로
        # 여기서 레벨 아이콘("✓"/"✗"/"ℹ")을 문구 앞에 또 붙이면 "✗✗ 로그인 실패"처럼
        # 아이콘이 중복되어 보인다 - level_icon은 색상만 취하고 텍스트에는 쓰지 않는다.
        accent_color, _level_icon = TOAST_LEVEL_STYLES.get(level, TOAST_LEVEL_STYLES["info"])

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar = QFrame()
        bar.setFixedWidth(4)
        bar.setStyleSheet(f"background: {accent_color}; border-top-left-radius: 10px; border-bottom-left-radius: 10px;")
        outer.addWidget(bar)

        text_label = QLabel(message[:160])
        text_label.setObjectName("toastText")
        text_label.setWordWrap(True)
        text_label.setContentsMargins(12, 10, 12, 10)
        outer.addWidget(text_label, 1)

        duration = TOAST_ERROR_DURATION_MS if level == "error" else TOAST_DURATION_MS
        QTimer.singleShot(duration, self._close)

    def _close(self):
        self.closed.emit(self)
        self.setParent(None)
        self.deleteLater()


class ToastHost(QWidget):
    """QMainWindow의 레이아웃 비관리 자식으로 떠서 우측 하단에 토스트를 쌓아 보여준다.

    별도 top-level 창이 아니라 QMainWindow의 자식이라 QStackedWidget의 어느 페이지
    (로그인/메인)에 있든 항상 같은 위치에 보이고, window.grab() 스크린샷에도 잡힌다.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toastHost")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

        self._toasts = []
        self.hide()

    def add(self, level: str, message: str):
        """토스트 1건을 추가한다. 최상단(가장 오래된)이 상한을 넘기면 즉시 닫는다."""
        if len(self._toasts) >= MAX_VISIBLE_TOASTS:
            oldest = self._toasts[0]
            oldest._close()

        toast = ToastWidget(level, message, self)
        toast.closed.connect(self._on_toast_closed)
        self._toasts.append(toast)
        self._layout.addWidget(toast)  # 최신 토스트가 아래로 쌓인다
        toast.show()

        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()

    def _on_toast_closed(self, toast):
        if toast in self._toasts:
            self._toasts.remove(toast)
        self.adjustSize()
        self.reposition()
        if not self._toasts:
            self.hide()

    def reposition(self):
        """부모(QMainWindow) 우측 하단에 맞춰 위치를 갱신한다."""
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        x = parent.width() - self.width() - TOAST_MARGIN
        y = parent.height() - self.height() - TOAST_MARGIN
        self.move(max(0, x), max(0, y))


class SearchJobWidget(QWidget):
    """검색조건 ~ 열차선택 ~ 시작/중지 ~ 작업 로그를 소유하는 검색 작업 카드.

    "+ 검색 작업 추가"로 여러 개(최대 MAX_CONCURRENT_JOBS개 동시 실행) 만들 수 있다.
    로그인된 공유 ktx_service를 생성자로 주입받으며, 결제 검증/처리·동시 실행 슬롯·
    네트워크 임계구역·알림음 중복 방지·자동결제 직렬화·예약완료 통지는 전부
    앱 레벨(TrainReservationApp) 콜백으로 위임한다. 워커 스레드는 위젯을 직접
    만지지 않고 self.signals(JobSignals)로만 GUI 스레드에 통지한다.
    """

    config_changed = pyqtSignal()  # 검색 조건 입력값이 바뀔 때마다 발신 (앱 레벨 저장 트리거용)

    def __init__(
        self,
        ktx_service: KTXService,
        validate_payment,
        process_payment,
        network_call,
        acquire_slot,
        acquire_payment_lock,
        release_payment_lock,
        acquire_alert_guard,
        release_alert_guard,
        notify_reservation_completed,
        notify,
        on_delete,
        parent=None,
    ):
        super().__init__(parent)
        self.ktx_service = ktx_service
        self._validate_payment = validate_payment
        self._process_payment = process_payment
        self._network_call = network_call  # 검색/예약 HTTP 호출을 앱 레벨 전역 Lock으로 직렬화
        self._acquire_slot = acquire_slot  # 동시 실행 5개 제한 (GUI 스레드에서만 호출)
        self._acquire_payment_lock = acquire_payment_lock  # 자동 결제는 한 번에 한 건씩 순서대로(직렬화)
        self._release_payment_lock = release_payment_lock
        self._acquire_alert_guard = acquire_alert_guard  # 알림음 동시 재생 방지
        self._release_alert_guard = release_alert_guard
        self._notify_reservation_completed = notify_reservation_completed  # 공용 예약완료 패널 통지
        self._notify = notify  # 토스트 + 알림 히스토리 공용 채널 (app_signals.notification.emit)
        self._on_delete = on_delete  # 카드 삭제 요청을 앱에 위임

        # 이 카드가 소유하는 상태
        self.trains = []
        self.train_widgets = []
        self.is_running = False
        self.is_alert_playing = False
        self.alert_thread = None

        self.signals = JobSignals()
        self.signals.log.connect(self._append_log)
        self.signals.state_changed.connect(self._on_state_changed)
        self.signals.trains_found.connect(self._on_trains_found)
        self.signals.finished.connect(self._on_finished)
        self.signals.show_alert_button.connect(self._show_alert_stop_button)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # ---- 티켓 스텁 요약 헤더: 출발→도착 · 날짜/시간 · 열차종류 · 상태를 한 줄로 압축 ----
        ticket_stub = QFrame()
        ticket_stub.setObjectName("ticketStub")
        ticket_stub_layout = QHBoxLayout(ticket_stub)
        ticket_stub_layout.setContentsMargins(10, 10, 14, 10)
        ticket_stub_layout.setSpacing(14)

        # 상태별 좌측 색바 (대기=회색 / 검색·실행중=amber / 예약완료=green / 중지=hairline)
        self.status_bar_frame = QFrame()
        self.status_bar_frame.setObjectName("statusBar")
        self.status_bar_frame.setFixedWidth(4)
        ticket_stub_layout.addWidget(self.status_bar_frame)

        ticket_info_layout = QVBoxLayout()
        ticket_info_layout.setContentsMargins(4, 10, 4, 10)
        ticket_info_layout.setSpacing(2)

        self.ticket_route_label = QLabel("")
        self.ticket_route_label.setObjectName("ticketRoute")
        self.ticket_meta_label = QLabel("")
        self.ticket_meta_label.setObjectName("ticketMeta")
        ticket_info_layout.addWidget(self.ticket_route_label)
        ticket_info_layout.addWidget(self.ticket_meta_label)

        ticket_stub_layout.addLayout(ticket_info_layout, 1)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        ticket_stub_layout.addWidget(self.status_label)

        self.delete_btn = QPushButton("🗑 삭제")
        self.delete_btn.setObjectName("clearButton")
        self.delete_btn.clicked.connect(self._request_delete)
        ticket_stub_layout.addWidget(self.delete_btn)

        layout.addWidget(ticket_stub)

        # 검색 조건
        search_card = SectionCard("🔍 검색 조건")

        grid = QGridLayout()
        grid.setSpacing(10)

        station_names = [station.name for station in self.ktx_service.get_stations()]

        self.dep_input = NoScrollComboBox()
        self.dep_input.setEditable(True)
        self.dep_input.addItems(station_names)
        self.dep_input.setCurrentText(DEFAULT_KTX_DEPARTURE)

        self.arr_input = NoScrollComboBox()
        self.arr_input.setEditable(True)
        self.arr_input.addItems(station_names)
        self.arr_input.setCurrentText(DEFAULT_KTX_ARRIVAL)

        grid.addWidget(QLabel("출발역"), 0, 0)
        grid.addWidget(self.dep_input, 0, 1)
        grid.addWidget(QLabel("도착역"), 0, 2)
        grid.addWidget(self.arr_input, 0, 3)

        self.date_input = NoScrollDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
        self.date_input.setMinimumDate(QDate.currentDate())
        self.date_input.setDisplayFormat("yyyy-MM-dd")

        self.time_input = NoScrollTimeEdit(QTime.currentTime())
        self.time_input.setDisplayFormat("HH:mm")
        self.time_input.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

        grid.addWidget(QLabel("출발일"), 1, 0)
        grid.addWidget(self.date_input, 1, 1)
        grid.addWidget(QLabel("출발시간"), 1, 2)
        grid.addWidget(self.time_input, 1, 3)

        self.train_type_input = NoScrollComboBox()
        self.train_type_input.addItem("전체", None)
        for train_type, label in TRAIN_TYPE_LABELS.items():
            self.train_type_input.addItem(label, train_type)

        grid.addWidget(QLabel("열차종류"), 2, 0)
        grid.addWidget(self.train_type_input, 2, 1)

        # 승객 수 - 같은 grid의 한 행에 압축 배치.
        # 각 필드 왼쪽에 항상 보이는 고정 라벨을 붙인다(플레이스홀더만으로는 값을 입력하는
        # 순간 라벨이 사라져 어떤 필드인지 알 수 없었다 - 값 입력 여부와 무관하게 항상 표시).
        self.adult_input = QLineEdit("1")
        self.child_input = QLineEdit("0")
        self.senior_input = QLineEdit("0")

        passenger_row = QHBoxLayout()
        passenger_row.setSpacing(8)
        for label_text, field in (
            ("어른", self.adult_input),
            ("어린이", self.child_input),
            ("경로", self.senior_input),
        ):
            field_pair = QHBoxLayout()
            field_pair.setSpacing(4)
            field_label = QLabel(label_text)
            field_pair.addWidget(field_label)
            field_pair.addWidget(field)
            passenger_row.addLayout(field_pair)

        grid.addWidget(QLabel("인원"), 2, 2)
        grid.addLayout(passenger_row, 2, 3)

        search_card.add_layout(grid)

        self.search_btn = QPushButton("🔍 열차 검색")
        self.search_btn.setObjectName("searchButton")
        self.search_btn.clicked.connect(self.search)
        search_card.add_widget(self.search_btn)

        layout.addWidget(search_card)

        # 열차 선택
        self.trains_card = SectionCard("🚄 열차 선택")
        self.trains_layout = QVBoxLayout()
        self.trains_card.add_layout(self.trains_layout)
        self.trains_card.setVisible(False)
        layout.addWidget(self.trains_card)

        # 시작/중지/알림음 중지 버튼
        self.action_widget = QWidget()
        action_layout = QHBoxLayout(self.action_widget)
        action_layout.setSpacing(12)
        action_layout.setContentsMargins(0, 0, 0, 0)

        self.start_btn = QPushButton("🚀 예약 시작")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start)

        self.stop_btn = QPushButton("⏹ 예약 중지")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)

        self.alert_stop_btn = QPushButton("🔇 알림음 중지")
        self.alert_stop_btn.setObjectName("stopButton")
        self.alert_stop_btn.setVisible(False)
        self.alert_stop_btn.clicked.connect(self.stop_alert)

        action_layout.addWidget(self.start_btn)
        action_layout.addWidget(self.stop_btn)
        action_layout.addWidget(self.alert_stop_btn)

        self.action_widget.setVisible(False)
        layout.addWidget(self.action_widget)

        # 이 카드 전용 로그 (Phase 5에서 더 다듬을 예정 - 지금은 최소 기능)
        log_card = SectionCard("📋 작업 로그")
        self.log_display = QTextEdit()
        self.log_display.setObjectName("logDisplay")
        self.log_display.setReadOnly(True)
        self.log_display.setMinimumHeight(120)
        self.log_display.setMaximumHeight(160)
        log_card.add_widget(self.log_display)
        layout.addWidget(log_card)

        # 티켓 스텁 요약(표시 전용) - 값이 바뀔 때마다 갱신, 초기값도 즉시 표시
        self.dep_input.currentTextChanged.connect(self._update_ticket_summary)
        self.arr_input.currentTextChanged.connect(self._update_ticket_summary)
        self.date_input.dateChanged.connect(self._update_ticket_summary)
        self.time_input.timeChanged.connect(self._update_ticket_summary)
        self.train_type_input.currentIndexChanged.connect(self._update_ticket_summary)
        self._update_ticket_summary()
        self._set_status("대기중")

        # 검색 조건이 바뀔 때마다 앱 레벨에 저장을 요청한다(재실행 시 복원용)
        self.dep_input.currentTextChanged.connect(self.config_changed)
        self.arr_input.currentTextChanged.connect(self.config_changed)
        self.date_input.dateChanged.connect(self.config_changed)
        self.time_input.timeChanged.connect(self.config_changed)
        self.train_type_input.currentIndexChanged.connect(self.config_changed)
        self.adult_input.textChanged.connect(self.config_changed)
        self.child_input.textChanged.connect(self.config_changed)
        self.senior_input.textChanged.connect(self.config_changed)

    def get_search_config(self) -> dict:
        """현재 검색 조건 입력값을 저장 가능한 dict로 반환한다."""
        train_type = self.train_type_input.currentData()
        return {
            "dep": self.dep_input.currentText(),
            "arr": self.arr_input.currentText(),
            "date": self.date_input.date().toString("yyyyMMdd"),
            "time": self.time_input.time().toString("HHmmss"),
            "train_type": train_type.name if train_type is not None else None,
            "adult": self.adult_input.text(),
            "child": self.child_input.text(),
            "senior": self.senior_input.text(),
        }

    def apply_search_config(self, config: dict) -> None:
        """저장된(또는 기본) 검색 조건을 입력 필드에 반영한다. 알 수 없는 키는 무시한다."""
        if config.get("dep"):
            self.dep_input.setCurrentText(config["dep"])
        if config.get("arr"):
            self.arr_input.setCurrentText(config["arr"])
        if config.get("date"):
            date = QDate.fromString(config["date"], "yyyyMMdd")
            if date.isValid():
                self.date_input.setDate(date)
        if config.get("time"):
            time = QTime.fromString(config["time"], "HHmmss")
            if time.isValid():
                self.time_input.setTime(time)
        train_type_name = config.get("train_type")
        for i in range(self.train_type_input.count()):
            data = self.train_type_input.itemData(i)
            if data is None and train_type_name is None:
                self.train_type_input.setCurrentIndex(i)
                break
            if data is not None and data.name == train_type_name:
                self.train_type_input.setCurrentIndex(i)
                break
        if "adult" in config:
            self.adult_input.setText(str(config["adult"]))
        if "child" in config:
            self.child_input.setText(str(config["child"]))
        if "senior" in config:
            self.senior_input.setText(str(config["senior"]))

    # ---- 티켓 스텁 요약 / 상태 표시 (표시 전용 - 예약 로직에는 관여하지 않음) ----
    def _update_ticket_summary(self, *_args):
        """출발역/도착역/날짜/시간/열차종류 요약을 티켓 스텁 헤더에 반영한다."""
        dep = self.dep_input.currentText() or "?"
        arr = self.arr_input.currentText() or "?"
        date_str = self.date_input.date().toString("MM/dd")
        time_str = self.time_input.time().toString("HH:mm")
        train_type_label = self.train_type_input.currentText() or "전체"
        self.ticket_route_label.setText(f"{dep} → {arr}")
        self.ticket_meta_label.setText(f"{date_str} {time_str} · {train_type_label}")

    def _set_status(self, status: str):
        """카드 좌측 색바 + 상태 라벨을 갱신한다."""
        bar_color, text_color = JOB_STATUS_COLORS.get(status, (NEUTRAL_GRAY, INK_MUTED))
        self.status_bar_frame.setStyleSheet(f"background: {bar_color}; border-radius: 2px;")
        self.status_label.setText(f"● {status}")
        self.status_label.setStyleSheet(
            f"color: {text_color}; font-size: 14px; font-weight: 700; background: transparent;"
        )
        self.current_status = status
        self.signals.status_changed.emit(status)

    def _notify_job(self, level: str, message: str):
        """이 카드발 토스트/알림 히스토리 발행. 메시지 앞에 [출발→도착] 구간을 붙여 구분한다."""
        route = self.ticket_route_label.text() or "?"
        self._notify(level, f"[{route}] {message}")

    # ---- 로그 ----
    def add_log(self, message: str):
        """로그 추가. 워커 스레드에서도 emit만 하면 GUI 스레드 슬롯에서 큐잉 실행된다."""
        self.signals.log.emit(message)

    def _append_log(self, message: str):
        """로그 표시 (GUI 스레드에서 실행)"""
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        self.log_display.append(f"[{timestamp}] {message}")
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_state_changed(self, state: str):
        """워커 스레드가 emit한 상태 변화를 GUI 스레드에서 위젯에 반영."""
        if state == "search_idle":
            self.search_btn.setEnabled(True)
            if not self.is_running:
                self._set_status("대기중")

    # ---- 삭제 ----
    def _request_delete(self):
        """삭제 버튼 클릭 (GUI 스레드). 실행 중이면 거부하고, 아니면 앱에 삭제를 위임한다."""
        if self.is_running:
            self.add_log("✗ 실행 중인 작업은 삭제할 수 없습니다. 먼저 '예약 중지'를 눌러주세요.")
            return
        self._on_delete(self)

    # ---- 검색 ----
    def search(self):
        """열차 검색 (로그인 카드에서 로그인이 완료된 상태에서만 동작). 버튼 클릭 = GUI 스레드."""
        if not self.ktx_service.is_logged_in():
            self.add_log("✗ 먼저 로그인하세요")
            return
        self.search_btn.setEnabled(False)  # 버튼 클릭 핸들러(GUI 스레드)이므로 직접 호출 가능
        self._set_status("검색중")
        threading.Thread(target=self._search_thread, daemon=True).start()

    def _search_thread(self):
        """검색 스레드. 위젯을 직접 만지지 않고 시그널로만 GUI 스레드에 통지한다."""
        self.add_log("🔍 열차 검색 중...")

        try:
            departure_date = datetime.datetime.strptime(self.date_input.date().toString("yyyyMMdd"), "%Y%m%d").date()
            departure_time = self.time_input.time().toString("HHmmss")

            # 승객 정보 수집
            passengers = []
            adult_count = int(self.adult_input.text() or "0")
            child_count = int(self.child_input.text() or "0")
            senior_count = int(self.senior_input.text() or "0")

            if adult_count > 0:
                passengers.append(Passenger(PassengerType.ADULT, adult_count))
            if child_count > 0:
                passengers.append(Passenger(PassengerType.CHILD, child_count))
            if senior_count > 0:
                passengers.append(Passenger(PassengerType.SENIOR, senior_count))

            if not passengers:
                self.add_log("✗ 최소 1명 이상의 승객이 필요합니다")
                return

            request = ReservationRequest(
                departure_station=self.dep_input.currentText(),
                arrival_station=self.arr_input.currentText(),
                departure_date=departure_date,
                departure_time=departure_time,
                passengers=passengers,
                train_type=self.train_type_input.currentData()
            )

            # 네트워크 임계구역: 앱 레벨 전역 Lock으로 직렬화 + 최소 요청 간격 강제
            trains = self._network_call(self.ktx_service.search_trains, request)
            self.trains = trains

            if trains:
                self.add_log(f"✓ {len(trains)}개의 열차를 찾았습니다")
                self.signals.trains_found.emit(trains)
                self._notify_job("success", f"🔍 열차 {len(trains)}개를 찾았습니다")
            else:
                self.add_log("✗ 열차를 찾을 수 없습니다")
                self._notify_job("error", "✗ 조건에 맞는 열차가 없습니다")

        except Exception as e:
            self.add_log(f"✗ 검색 중 오류가 발생했습니다: {str(e)}")
            self._notify_job("error", f"✗ 검색 중 오류가 발생했습니다: {str(e)}")

        finally:
            self.signals.state_changed.emit("search_idle")

    def _on_trains_found(self, trains):
        """검색된 열차 목록 표시 (GUI 스레드, trains_found 시그널 슬롯)"""
        # 기존 위젯 제거
        while self.trains_layout.count():
            item = self.trains_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.train_widgets = []

        for train in trains:
            train_type_label = TRAIN_TYPE_LABELS.get(train.train_type, "?")
            train_info = f"[{train_type_label}] {train.train_number} | 🚉 {train.departure_time.strftime('%H:%M')} → {train.arrival_time.strftime('%H:%M')}"
            widget = TrainItemWidget(train_info)
            widget.checkbox.stateChanged.connect(self._update_start_button)
            self.train_widgets.append(widget)
            self.trains_layout.addWidget(widget)

        self.trains_card.setVisible(True)
        self.action_widget.setVisible(True)
        self._update_start_button()

    def _update_start_button(self):
        """시작 버튼 활성화 상태 업데이트 (체크박스 이벤트 = GUI 스레드에서만 호출됨)"""
        has_selection = any(w.checkbox.isChecked() for w in self.train_widgets)
        self.start_btn.setEnabled(has_selection)

    # ---- 예약 ----
    def start(self):
        """예약 시작 (버튼 클릭 = GUI 스레드). 동시 실행 슬롯(최대 MAX_CONCURRENT_JOBS개)을 여기서 획득한다."""
        selected_indices = [i for i, w in enumerate(self.train_widgets) if w.checkbox.isChecked()]

        if not selected_indices:
            self.add_log("✗ 열차를 선택해주세요")
            return

        if not self._acquire_slot():
            self.add_log(f"✗ 동시 실행 가능한 작업은 최대 {MAX_CONCURRENT_JOBS}개입니다. 다른 작업을 중지하거나 완료를 기다려주세요.")
            self._notify_job("error", f"✗ 동시 실행은 최대 {MAX_CONCURRENT_JOBS}개까지 가능합니다")
            return

        self.is_running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.delete_btn.setEnabled(False)
        self._set_status("실행중")

        self.add_log("🚀 예약을 시작합니다")
        self._notify_job("info", "🚀 예약 시작")

        threading.Thread(
            target=self._reservation_loop,
            args=(selected_indices,),
            daemon=True
        ).start()

    def _reservation_loop(self, selected_indices):
        """예약 재시도 루프 (워커 스레드).

        어떤 경로로 끝나든(성공/중지/예외) finally에서 반드시 finished를 emit해
        앱 레벨 동시 실행 슬롯을 반납하고, 카드 버튼 상태를 GUI 스레드에서 정리한다.
        """
        success = False
        try:
            selected_trains = [self.trains[i] for i in selected_indices]
            attempt = 0

            # 승객 정보 수집
            passengers = []
            adult_count = int(self.adult_input.text() or "0")
            child_count = int(self.child_input.text() or "0")
            senior_count = int(self.senior_input.text() or "0")

            if adult_count > 0:
                passengers.append(Passenger(PassengerType.ADULT, adult_count))
            if child_count > 0:
                passengers.append(Passenger(PassengerType.CHILD, child_count))
            if senior_count > 0:
                passengers.append(Passenger(PassengerType.SENIOR, senior_count))

            while self.is_running:
                attempt += 1
                self.add_log(f"🔄 예약 시도 #{attempt}")

                for idx, train in enumerate(selected_trains):
                    if not self.is_running:
                        break

                    try:
                        self.add_log(f"  → {train.train_number} 예약 시도 중...")

                        request = ReservationRequest(
                            departure_station=train.departure_station,
                            arrival_station=train.arrival_station,
                            departure_date=train.departure_time.date(),
                            departure_time=train.departure_time.strftime("%H%M%S"),
                            passengers=passengers,
                            train_type=train.train_type
                        )
                        # 네트워크 임계구역: 앱 레벨 전역 Lock으로 직렬화 + 최소 요청 간격 강제
                        reservation = self._network_call(self.ktx_service.reserve_train, train, request)
                        if reservation.success:
                            self.add_log(f"  ✓ {train.train_number} 예약 성공!")
                            self.add_log(f"  예약번호: {reservation.reservation_number}")
                            success = True
                            self.is_running = False  # 이 카드만 중지 (다른 카드는 계속 실행)

                            train_type_label = TRAIN_TYPE_LABELS.get(train.train_type, "?")
                            reservation_info = {
                                "route": f"{train.departure_station} → {train.arrival_station}",
                                "datetime": f"{train.departure_time.strftime('%Y-%m-%d %H:%M')} → {train.arrival_time.strftime('%H:%M')}",
                                "train_type": train_type_label,
                                "train_number": train.train_number,
                                "reservation_number": reservation.reservation_number,
                            }

                            payment_status = self._settle_payment(reservation)
                            reservation_info["payment_status"] = payment_status
                            self._notify_reservation_completed(reservation_info)

                            if payment_status != "자동결제완료":
                                self.add_log("    알림음 중지 버튼을 눌러 알림음을 중지하고")
                                self.add_log("    앱에 들어가 10분 내에 결제해주세요.")
                                if self._acquire_alert_guard():
                                    self.alert_thread = threading.Thread(target=self._play_alert_sound_loop, daemon=True)
                                    self.alert_thread.start()
                                else:
                                    self.add_log("  (다른 작업이 이미 알림음을 재생 중이라 이 작업은 알림음을 재생하지 않습니다)")
                                # 시그널로 알림음 중지 버튼 표시
                                self.signals.show_alert_button.emit()

                            return  # 다른 열차는 시도하지 않고 종료
                        else:
                            self.add_log(f"  ✗ {train.train_number} 예약 실패: {reservation.message}")
                            delay = random.uniform(RETRY_DELAY_MIN, RETRY_DELAY_MAX)
                            if idx == len(selected_trains) - 1:
                                self.add_log(f"⏳ {delay:.1f}초 후 재시도...")
                            else:
                                self.add_log(f"⏳ {delay:.1f}초 후 다음 열차 시도...")
                            time.sleep(delay)

                    except Exception as e:
                        self.add_log(f"  ✗ 오류: {str(e)}")
        finally:
            self.signals.finished.emit(success)

    def _settle_payment(self, reservation) -> str:
        """예약 성공 건의 결제를 시도하고 결제 상태 문자열("자동결제완료"/"수동결제필요")을 반환한다.

        결제 폼(카드 정보 입력)이 앱에 하나뿐이라 동시에 두 건을 함께 결제할 수는
        없지만, 성공한 모든 건이 자동 결제 대상이다. payment_lock을 블로킹으로
        acquire해 "한 번에 한 건씩, 순서대로" 처리되게 직렬화한다.
        """
        if not self._validate_payment():
            self.add_log("  ✗ 예약은 완료되었으나 결제 정보가 입력되지 않았습니다.")
            self.add_log(f"    예약번호: {reservation.reservation_number}")
            return "수동결제필요"

        self._acquire_payment_lock()
        try:
            payment = self._process_payment(reservation)
        finally:
            self._release_payment_lock()

        if payment.success:
            self.add_log("  ✓ 결제 완료!")
            return "자동결제완료"
        else:
            self.add_log(f"  ✗ 예약은 완료되었으나 결제에 실패했습니다: {payment.message}")
            self.add_log(f"    예약번호: {reservation.reservation_number}")
            return "수동결제필요"

    def stop(self):
        """예약 중지 (버튼 클릭 = GUI 스레드)"""
        self.is_running = False
        self.add_log("⏹ 예약을 중지했습니다")
        self._notify_job("info", "⏹ 예약 중지")
        self.stop_btn.setEnabled(False)
        self._set_status("중지됨")
        # start_btn/delete_btn 재활성화는 워커 스레드가 finished를 emit하면 _on_finished가 처리한다.

    def _play_alert_sound_loop(self):
        """알림음을 반복 재생 (정지 버튼을 누를 때까지). 위젯을 만지지 않는 순수 스레드."""
        self.is_alert_playing = True
        while self.is_alert_playing:
            play_alert_sound_once()
            time.sleep(1)  # 소리 간격 (1초)
        self._release_alert_guard()  # 앱 레벨 "동시 1개만 재생" 가드 반납

    def stop_alert(self):
        """알림음 중지 (버튼 클릭 = GUI 스레드)"""
        self.is_alert_playing = False
        self.is_running = False  # 예약도 중지
        self.add_log("🔇 알림음을 중지했습니다")
        self.add_log("⏹ 예약을 중지했습니다")
        self.alert_stop_btn.setVisible(False)
        self.start_btn.setVisible(True)
        self.start_btn.setEnabled(True)
        self.stop_btn.setVisible(True)
        self.stop_btn.setEnabled(False)
        self.delete_btn.setEnabled(True)

    def _show_alert_stop_button(self):
        """알림음 중지 버튼 표시 (GUI 스레드에서 실행, show_alert_button 시그널 슬롯)"""
        self.action_widget.setVisible(True)
        self.start_btn.setVisible(False)
        self.stop_btn.setVisible(False)
        self.alert_stop_btn.setVisible(True)

    def _on_finished(self, success: bool):
        """작업 루프 종료 처리 (GUI 스레드, finished 시그널 슬롯).

        버튼 활성 상태만 정리한다(가시성은 알림음 경로/stop_alert가 이미 관리하므로 건드리지 않음).
        동시 실행 슬롯 반납은 앱이 같은 finished 시그널에 별도로 연결해 처리한다.
        """
        self.is_running = False
        self.stop_btn.setEnabled(False)
        self.start_btn.setEnabled(any(w.checkbox.isChecked() for w in self.train_widgets))
        self.delete_btn.setEnabled(True)
        self._set_status("예약완료" if success else "중지됨")
        if success:
            self._notify_job("success", "🎫 예약 성공")


class TrainReservationApp(QMainWindow):
    """기차표 예약 메인 윈도우"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🚄 Korail Macro")
        self.setMinimumSize(1000, 900)

        # 토스트 오버레이는 init_ui()에서 centralWidget 설정 직후 생성된다.
        # 그 전에 add_notification/resizeEvent가 호출될 수 있으므로 None으로 먼저 선언해둔다.
        self.toast_host = None
        self.notification_history = deque(maxlen=NOTIFICATION_HISTORY_MAX)

        # 아이콘 설정
        icon_path = resource_path('assets/favicon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 서비스 초기화 (여러 검색 작업 카드가 공유하는 단일 인스턴스)
        self.ktx_service = KTXService()

        # 중복 로그인 요청 차단용 락
        self._login_lock = threading.Lock()

        # 상태 변수
        self.is_log_visible = False

        # ---- Phase 5: 병렬 검색 작업 카드 관리 ----
        self.search_jobs = []  # 현재 배치된 SearchJobWidget 카드들

        # 동시 실행 카운터. GUI 스레드에서만 증감한다(시작 클릭 = GUI 스레드,
        # 종료 통지는 카드의 finished 시그널로 GUI 스레드에 마샬링) → 락 없이 레이스 없음.
        self.running_job_count = 0

        # 검색/예약 네트워크 임계구역: 공유 self.ktx_service 세션을 여러 카드가
        # 동시에 두드리지 않도록 전역 Lock으로 직렬화하고, 마지막 호출 이후
        # 최소 RETRY_DELAY_MIN 간격을 강제해 실효 요청률을 억제한다.
        self.network_lock = threading.Lock()
        self._last_network_call_at = 0.0

        # 결제는 첫 예약 성공 건에만 자동 적용한다(acquire(blocking=False)로 선점).
        self.payment_lock = threading.Lock()

        # 알림음은 앱 전체에서 동시에 하나만 재생되게 가드한다.
        self._alert_lock = threading.Lock()
        self.is_alert_playing = False

        # 로그 시그널 (앱 레벨 - 로그인 등 공용 이벤트)
        self.log_signals = LogSignals()
        self.log_signals.log_message.connect(self.append_log)

        # 앱 레벨 시그널 (공용 "예약 완료" 패널 갱신 등 - 카드 → 앱 통지)
        self.app_signals = AppSignals()
        self.app_signals.reservation_completed.connect(self._on_reservation_completed)
        self.app_signals.login_finished.connect(self._on_login_finished)
        self.app_signals.notification.connect(self._on_notification)

        # UI 초기화
        self.init_ui()

        # 스타일시트 적용
        self.setStyleSheet(STYLESHEET)

        # 저장된 자격 증명 로드. 로그인 정보가 있으면 로그인 화면에 필드만 채우는 것을
        # 넘어, 버튼을 누른 것처럼 1회만 자동 로그인을 시도한다(재시도/반복 없음).
        # 실패하면 로그인 화면에 그대로 머무르고 에러 메시지만 보여준다.
        if self.load_saved_credentials():
            self.login_ktx()

    def init_ui(self):
        """UI 초기화

        중앙 위젯을 QStackedWidget으로 구성해 페이지 0(로그인 화면) / 페이지 1(메인
        화면)을 오간다. 앱 시작 시에는 항상 로그인 화면(0)이 먼저 보이고, 로그인이
        성공해야 메인 화면(1)으로 전환된다.
        """
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setObjectName("centralWidget")
        self.setCentralWidget(self.stacked_widget)

        # 토스트 오버레이는 QMainWindow의 레이아웃 비관리 자식으로 만들어야
        # QStackedWidget의 어느 페이지에서도 같은 위치(우측 하단)에 보인다.
        self.toast_host = ToastHost(self)

        # 알림 히스토리 탭(create_main_page()가 top_tab_widget에 부착)은
        # login/main 페이지보다 먼저 준비해둔다.
        self.notification_page = self.create_notification_page()

        self.login_page = self.create_login_page()
        self.main_page = self.create_main_page()

        self.stacked_widget.addWidget(self.login_page)  # index 0: 로그인 화면
        self.stacked_widget.addWidget(self.main_page)   # index 1: 메인 화면
        self.stacked_widget.setCurrentIndex(0)

    def create_login_page(self):
        """앱 첫 진입 화면. 아이디/비밀번호/저장 체크박스/로그인 버튼만 담는다.

        로그인 성공 시 _on_login_finished()가 stacked_widget을 메인 화면(1)으로 전환한다.
        """
        page = QWidget()

        outer_layout = QVBoxLayout(page)
        outer_layout.addStretch()

        center_row = QHBoxLayout()
        center_row.addStretch()

        login_card = SectionCard("🚄 Korail Macro 로그인")
        login_card.setFixedWidth(420)

        self.ktx_id_input = QLineEdit()
        self.ktx_id_input.setPlaceholderText("아이디를 입력하세요")

        # 비밀번호 입력란 (보기/숨기기 버튼 포함)
        ktx_pw_layout = QHBoxLayout()
        ktx_pw_layout.setSpacing(8)
        self.ktx_pw_input = QLineEdit()
        self.ktx_pw_input.setPlaceholderText("비밀번호를 입력하세요")
        self.ktx_pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.ktx_pw_input.setInputMethodHints(Qt.InputMethodHint.ImhLatinOnly)

        self.ktx_pw_toggle_btn = QPushButton("Show")
        self.ktx_pw_toggle_btn.setFixedWidth(80)
        self.ktx_pw_toggle_btn.setObjectName("clearButton")
        self.ktx_pw_toggle_btn.clicked.connect(lambda: self.toggle_password_visibility(self.ktx_pw_input, self.ktx_pw_toggle_btn))

        ktx_pw_layout.addWidget(self.ktx_pw_input)
        ktx_pw_layout.addWidget(self.ktx_pw_toggle_btn)

        login_card.add_widget(self.ktx_id_input)
        login_card.add_layout(ktx_pw_layout)

        # 로그인 정보 저장 체크박스
        self.ktx_save_login_check = QCheckBox("로그인 정보 저장 (안전하게 암호화됨)")
        self.ktx_save_login_check.setChecked(True)
        login_card.add_widget(self.ktx_save_login_check)

        # 로그인 실패 시 화면에서 바로 보이는 에러 메시지 (로그 패널은 메인 화면에만 있음)
        self.ktx_login_error_label = QLabel("")
        self.ktx_login_error_label.setWordWrap(True)
        self.ktx_login_error_label.setStyleSheet(f"color: {SIGNAL_RED}; font-size: 12px; font-weight: 600;")
        self.ktx_login_error_label.setVisible(False)
        login_card.add_widget(self.ktx_login_error_label)

        self.ktx_login_btn = QPushButton("🔐 로그인")
        self.ktx_login_btn.setObjectName("primaryButton")
        self.ktx_login_btn.clicked.connect(self.login_ktx)
        login_card.add_widget(self.ktx_login_btn)

        center_row.addWidget(login_card)
        center_row.addStretch()

        outer_layout.addLayout(center_row)
        outer_layout.addStretch()

        return page

    def create_notification_page(self):
        """"🔔 알림" 탭 페이지. 토스트로 스쳐 지나간 알림을 시간 역순 히스토리로 보여준다."""
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)

        board = SectionCard("🔔 알림 히스토리")

        self.notification_board = QTextEdit()
        self.notification_board.setObjectName("logDisplay")
        self.notification_board.setReadOnly(True)
        self.notification_board.setPlaceholderText("아직 알림이 없습니다.")
        self.notification_board.setMinimumHeight(320)
        board.add_widget(self.notification_board)

        clear_btn = QPushButton("🗑️ 지우기")
        clear_btn.setObjectName("clearButton")
        clear_btn.clicked.connect(self.clear_notifications)
        board.add_widget(clear_btn)

        main_layout.addWidget(board)
        return page

    def add_notification(self, level: str, message: str):
        """공용 알림 채널로 발행한다. 어디서 호출하든(워커 스레드 포함) 안전하다."""
        self.app_signals.notification.emit(level, message)

    def _on_notification(self, level: str, message: str):
        """알림 발행 처리 (GUI 스레드, app_signals.notification 시그널 슬롯).

        토스트를 띄우고, 히스토리(최신이 맨 위)에 추가한 뒤 알림 탭을 다시 그린다.
        """
        if self.toast_host is not None:
            self.toast_host.add(level, message)

        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        self.notification_history.appendleft((timestamp, level, message))
        self._render_notification_history()

    def _render_notification_history(self):
        """notification_history를 시간 역순 HTML로 렌더링한다."""
        lines = []
        for timestamp, level, message in self.notification_history:
            color = TOAST_LEVEL_BOARD_COLORS.get(level, BOARD_AMBER)
            safe_message = html.escape(message)
            lines.append(
                f'<div style="color:{color};">[{timestamp}] {safe_message}</div>'
            )
        self.notification_board.setHtml("".join(lines))

    def clear_notifications(self):
        """"🗑️ 지우기" 버튼: 알림 히스토리를 전부 비운다."""
        self.notification_history.clear()
        self.notification_board.clear()

    def resizeEvent(self, event):
        """창 크기 변화에 맞춰 토스트 오버레이 위치를 다시 계산한다."""
        super().resizeEvent(event)
        if self.toast_host is not None:
            self.toast_host.reposition()

    def create_main_page(self):
        """로그인 성공 후 보여줄 메인 화면 (헤더 + 검색 작업 탭 + 실행 로그)."""
        page = QWidget()

        main_layout = QVBoxLayout(page)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 30, 30, 30)

        # 헤더 (타이틀 + 로그인 상태 라벨 + 설정 버튼)
        header_layout = QHBoxLayout()
        header = QLabel("🚄 Korail Macro")
        header.setObjectName("titleLabel")
        header_layout.addWidget(header)
        header_layout.addStretch()

        # 로그인 상태 표시 (다이얼로그가 닫혀 있어도 현재 로그인 상태를 헤더에서 바로 확인)
        self.ktx_login_status_label = QLabel("로그인 필요")
        header_layout.addWidget(self.ktx_login_status_label)

        self.settings_btn = QPushButton("⚙ 설정")
        self.settings_btn.setObjectName("clearButton")
        self.settings_btn.clicked.connect(self.open_settings_dialog)
        header_layout.addWidget(self.settings_btn)

        main_layout.addLayout(header_layout)

        # 로그 섹션을 먼저 만들어 self.log_display를 준비해둔다.
        # create_ktx_tab()이 카드를 배치하며 self.add_log(...)를 호출하는데(예: 최초
        # 검색 작업 카드 추가 로그), 이 시그널의 슬롯(append_log)이 GUI 스레드에서
        # 곧바로(direct connection) 실행되므로 log_display가 미리 존재해야 한다.
        self.log_toggle_btn = QPushButton("▼ 실행 로그 보기")
        self.log_toggle_btn.setObjectName("clearButton")
        self.log_toggle_btn.clicked.connect(self.toggle_log_section)

        self.log_section = self.create_log_section()
        self.log_section.setVisible(False)

        # 결제 정보 / 계정 정보는 별도 "설정" 다이얼로그로 분리한다 (메인 화면에는 노출하지 않음).
        # 위젯 자체는 다이얼로그가 닫혀 있어도 계속 존재하므로 값(결제 정보)은 유지된다.
        self.settings_dialog = self.create_settings_dialog()

        # 최상위 탭 2개: "🚄 작업"(기존 메인 화면 전체) / "🔔 알림"(시간 역순 히스토리).
        # create_ktx_tab() 내부는 무수정 - 위치만 최상위 탭 안으로 옮긴다.
        self.top_tab_widget = QTabWidget()
        self.top_tab_widget.setObjectName("topTabs")
        self.top_tab_widget.addTab(self.create_ktx_tab(), "🚄 작업")
        self.top_tab_widget.addTab(self.notification_page, "🔔 알림")
        main_layout.addWidget(self.top_tab_widget)

        main_layout.addWidget(self.log_toggle_btn)
        main_layout.addWidget(self.log_section)

        return page

    def create_settings_dialog(self):
        """계정 정보(읽기 전용) / 결제 정보를 담는 설정 다이얼로그 생성.

        로그인 폼은 로그인 화면(create_login_page)으로 옮겨졌으므로, 이 다이얼로그의
        로그인 폼 자리에는 현재 로그인된 계정 정보만 읽기 전용으로 보여준다.
        결제 카드는 그대로 유지하며 시그널 연결과 검증/처리 로직(_validate_ktx_payment_info
        등)도 변경 없이 재사용한다.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("⚙ 설정")
        dialog.setMinimumWidth(420)

        dialog_layout = QVBoxLayout(dialog)
        dialog_layout.setSpacing(16)
        dialog_layout.setContentsMargins(20, 20, 20, 20)

        # 계정 정보 (읽기 전용) - Korail.login() 성공 후 파싱되는 membership_number/name/email
        account_card = SectionCard("👤 계정 정보")

        self.account_id_label = QLabel("정보 없음")
        self.account_name_label = QLabel("정보 없음")
        self.account_membership_label = QLabel("정보 없음")
        self.account_email_label = QLabel("정보 없음")

        for field_text, value_label in (
            ("아이디", self.account_id_label),
            ("이름", self.account_name_label),
            ("회원번호", self.account_membership_label),
            ("이메일", self.account_email_label),
        ):
            row = QHBoxLayout()
            row.setSpacing(8)
            field_label = QLabel(field_text)
            field_label.setFixedWidth(60)
            field_label.setStyleSheet(f"color: {INK}; font-weight: 700;")
            row.addWidget(field_label)
            row.addWidget(value_label, 1)
            account_card.add_layout(row)

        self.logout_btn = QPushButton("🚪 로그아웃")
        self.logout_btn.setObjectName("stopButton")
        self.logout_btn.clicked.connect(self.logout_ktx)
        account_card.add_widget(self.logout_btn)

        dialog_layout.addWidget(account_card)

        # 결제 정보 (다이얼로그에 하나만 유지 - 검색 작업 카드들이 공유)
        self.ktx_payment_card = SectionCard("💳 결제 정보 (공용)")

        self.ktx_payment_card_num_input = QLineEdit()
        self.ktx_payment_card_num_input.setPlaceholderText("카드번호 (16자리)")
        self.ktx_payment_card_pw_input = QLineEdit()
        self.ktx_payment_card_pw_input.setPlaceholderText("카드 비밀번호 앞 2자리")
        self.ktx_payment_card_pw_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.ktx_payment_card.add_widget(self.ktx_payment_card_num_input)
        self.ktx_payment_card.add_widget(self.ktx_payment_card_pw_input)

        self.ktx_payment_corporate_check = QCheckBox("법인카드 사용")
        self.ktx_payment_card.add_widget(self.ktx_payment_corporate_check)

        self.ktx_payment_birth_input = QLineEdit()
        self.ktx_payment_birth_input.setPlaceholderText("생년월일 (YYMMDD)")
        self.ktx_payment_business_num_input = QLineEdit()
        self.ktx_payment_business_num_input.setPlaceholderText("사업자번호 (10자리)")
        self.ktx_payment_business_num_input.setVisible(False)
        self.ktx_payment_expire_input = QLineEdit()
        self.ktx_payment_expire_input.setPlaceholderText("유효기간 (YYMM)")

        def toggle_ktx_corporate():
            if self.ktx_payment_corporate_check.isChecked():
                self.ktx_payment_birth_input.setVisible(False)
                self.ktx_payment_business_num_input.setVisible(True)
            else:
                self.ktx_payment_birth_input.setVisible(True)
                self.ktx_payment_business_num_input.setVisible(False)

        self.ktx_payment_corporate_check.stateChanged.connect(toggle_ktx_corporate)

        self.ktx_payment_card.add_widget(self.ktx_payment_birth_input)
        self.ktx_payment_card.add_widget(self.ktx_payment_business_num_input)
        self.ktx_payment_card.add_widget(self.ktx_payment_expire_input)

        # 결제 정보 저장 체크박스
        self.ktx_save_payment_check = QCheckBox("결제 정보 저장 (안전하게 암호화됨)")
        self.ktx_save_payment_check.setChecked(True)
        self.ktx_payment_card.add_widget(self.ktx_save_payment_check)

        dialog_layout.addWidget(self.ktx_payment_card)

        close_btn = QPushButton("닫기")
        close_btn.setObjectName("clearButton")
        close_btn.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_btn)

        return dialog

    def open_settings_dialog(self):
        """헤더의 "⚙ 설정" 버튼 클릭 시 계정/결제 정보 다이얼로그를 모달로 띄운다."""
        self._refresh_account_info_labels()
        self.settings_dialog.exec()

    def _refresh_account_info_labels(self):
        """설정 다이얼로그의 계정 정보 라벨을 ktx_service의 최신 값으로 갱신한다."""
        info = self.ktx_service.get_account_info()
        self.account_id_label.setText(info.get("id") or "정보 없음")
        self.account_name_label.setText(info.get("name") or "정보 없음")
        self.account_membership_label.setText(info.get("membership_number") or "정보 없음")
        self.account_email_label.setText(info.get("email") or "정보 없음")

    def logout_ktx(self):
        """설정 다이얼로그의 "🚪 로그아웃" 버튼: 로그아웃 후 로그인 화면(페이지 0)으로 되돌린다."""
        self.ktx_service.logout()
        self.ktx_login_status_label.setText("로그인 필요")
        self.ktx_pw_input.clear()
        self.ktx_login_btn.setEnabled(True)
        self._refresh_account_info_labels()
        self.settings_dialog.accept()
        self.stacked_widget.setCurrentIndex(0)

    def create_ktx_tab(self):
        """KTX 탭 생성

        검색 작업 카드들은 터미널 앱(iTerm/Terminal)처럼 QTabWidget 탭으로 배치한다.
        탭 하나 = SearchJobWidget 카드 하나, corner widget의 "+" 버튼이 새 탭 추가,
        각 탭의 닫기(x)가 카드 삭제에 대응한다.
        """
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(10, 10, 10, 10)

        # ✅ 예약 완료 패널 (공용 - 어떤 카드든 예약이 성사되면 여기 한 줄 추가)
        self.reservation_panel = SectionCard("✅ 예약 완료")
        self.reservation_panel_display = QTextEdit()
        self.reservation_panel_display.setObjectName("logDisplay")
        self.reservation_panel_display.setReadOnly(True)
        self.reservation_panel_display.setMinimumHeight(100)
        self.reservation_panel_display.setMaximumHeight(160)
        self.reservation_panel_display.setPlaceholderText("아직 성사된 예약이 없습니다.")
        self.reservation_panel.add_widget(self.reservation_panel_display)
        layout.addWidget(self.reservation_panel)

        jobs_header_label = QLabel(f"🧵 검색 작업 (동시 실행 최대 {MAX_CONCURRENT_JOBS}개)")
        jobs_header_label.setObjectName("sectionLabel")
        layout.addWidget(jobs_header_label)

        # 검색 작업 카드들을 터미널 탭처럼 배치
        self.jobs_tab_widget = QTabWidget()
        self.jobs_tab_widget.setTabsClosable(True)
        self.jobs_tab_widget.tabCloseRequested.connect(self._on_job_tab_close_requested)

        # 터미널의 "새 탭" 버튼처럼 corner widget에 "+" 버튼을 둔다
        self.add_job_btn = QPushButton("+")
        self.add_job_btn.setObjectName("addTabButton")
        self.add_job_btn.setFixedSize(32, 32)
        self.add_job_btn.setToolTip("검색 작업 추가")
        self.add_job_btn.clicked.connect(self._add_search_job)

        # Fusion 스타일에서 QTabWidget의 corner widget 배치 계산이 위젯 폭과 무관하게
        # 일정 폭만큼 오른쪽 경계 밖으로 밀어내 버튼이 "+" 글자 없이 작은 점만 보이는
        # 버그가 있다. corner widget을 버튼보다 넓은 컨테이너로 감싸 버튼을 좌측에
        # 붙이고 남는 여백이 바깥으로 밀려나가게 해 실제 버튼은 항상 보이는 영역
        # 안에 들어오도록 한다.
        corner_container = QWidget()
        corner_layout = QHBoxLayout(corner_container)
        corner_layout.setContentsMargins(0, 0, 24, 0)
        corner_layout.setSpacing(0)
        corner_layout.addWidget(self.add_job_btn)
        self.jobs_tab_widget.setCornerWidget(corner_container, Qt.Corner.TopRightCorner)

        layout.addWidget(self.jobs_tab_widget)

        # 저장된 검색 조건이 있으면 복원하고, 없으면(최초 실행) 기본 카드 3개를 배치한다.
        saved_configs = self._load_search_jobs_state()
        for config in (saved_configs or DEFAULT_SEARCH_JOBS):
            self._add_search_job(config)

        layout.addStretch()
        scroll.setWidget(container)

        main_layout = QVBoxLayout(widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

        return widget

    # ---- Phase 5: 검색 작업 카드 추가/삭제 (탭 컨테이너) ----
    def _add_search_job(self, config: dict = None):
        """"+" corner 버튼(또는 최초 배치)에서 새 SearchJobWidget 카드를 새 탭으로 추가한다.

        config가 주어지면(저장된 상태 복원 또는 기본값 시딩) 생성 직후 입력값에 반영한다.
        """
        if len(self.search_jobs) >= MAX_SEARCH_JOBS:
            self.add_notification("info", f"검색 작업은 최대 {MAX_SEARCH_JOBS}개까지 만들 수 있습니다")
            return

        job = SearchJobWidget(
            self.ktx_service,
            validate_payment=self._validate_ktx_payment_info,
            process_payment=self._process_ktx_payment,
            network_call=self.run_network_call,
            acquire_slot=self.try_start_job,
            acquire_payment_lock=self.acquire_auto_payment,
            release_payment_lock=self.release_auto_payment,
            acquire_alert_guard=self.try_acquire_alert,
            release_alert_guard=self.release_alert,
            notify_reservation_completed=self.app_signals.reservation_completed.emit,
            notify=self.app_signals.notification.emit,
            on_delete=self._remove_search_job,
        )
        if config:
            job.apply_search_config(config)

        # 카드 종료 시 앱 레벨 동시 실행 슬롯 반납 (카드 자신의 _on_finished와는 별개로 연결)
        job.signals.finished.connect(self._on_job_finished)
        # 검색 조건이 바뀔 때마다 상태 파일에 저장(재실행 시 복원용)
        job.config_changed.connect(self._save_search_jobs_state)

        tab_label = f"작업 {len(self.search_jobs) + 1}"
        index = self.jobs_tab_widget.addTab(job, tab_label)
        self.jobs_tab_widget.setCurrentIndex(index)

        # 티켓 스텁 요약(출발→도착)이 바뀌면 탭 제목도 함께 갱신한다.
        def _sync_tab_title(*_args, job=job):
            idx = self.jobs_tab_widget.indexOf(job)
            if idx != -1:
                self.jobs_tab_widget.setTabText(idx, job.ticket_route_label.text())

        job.dep_input.currentTextChanged.connect(_sync_tab_title)
        job.arr_input.currentTextChanged.connect(_sync_tab_title)
        _sync_tab_title()

        # 탭 헤더 상태 색점: 카드의 상태가 바뀔 때마다 탭 아이콘을 갱신한다.
        job.signals.status_changed.connect(lambda status, job=job: self._refresh_job_tab_icon(job, status))
        self._refresh_job_tab_icon(job, job.current_status)

        self.search_jobs.append(job)
        self.add_log(f"➕ 검색 작업 카드를 추가했습니다 (현재 {len(self.search_jobs)}개)")
        self._update_add_job_button_state()
        self._save_search_jobs_state()

    def _load_search_jobs_state(self):
        """저장된 검색 작업 카드 설정을 읽는다. 없거나 손상됐으면 None을 반환한다."""
        try:
            with open(SEARCH_JOBS_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        return None

    def _save_search_jobs_state(self):
        """현재 배치된 모든 검색 작업 카드의 입력값을 파일에 저장한다(다음 실행 시 복원용)."""
        try:
            SEARCH_JOBS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            configs = [job.get_search_config() for job in self.search_jobs]
            with open(SEARCH_JOBS_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(configs, f, ensure_ascii=False, indent=2)
        except OSError as e:
            self.add_log(f"⚠ 검색 조건 저장 실패: {e}")

    def _on_job_tab_close_requested(self, index):
        """탭의 닫기(x) 버튼 클릭 시 호출됨. 실제 삭제 가능 여부는 _remove_search_job이 판단한다."""
        job = self.jobs_tab_widget.widget(index)
        if job is not None:
            self._remove_search_job(job)

    def _remove_search_job(self, job):
        """카드의 삭제 버튼 또는 탭 닫기(x)에서 호출됨(카드가 이미 실행 중이 아님을 확인한 뒤)."""
        if job.is_running:
            # 이중 방어: 카드 쪽에서 이미 막지만, 콜백 계약을 명확히 하기 위해 여기서도 확인한다.
            # 탭을 제거하지 않고 그대로 둔다 - 실행 중인 작업의 탭은 닫히지 않는다.
            self.add_log("✗ 실행 중인 작업은 삭제할 수 없습니다.")
            self.add_notification("error", "✗ 실행 중인 작업은 삭제할 수 없습니다")
            return

        index = self.jobs_tab_widget.indexOf(job)
        if index != -1:
            self.jobs_tab_widget.removeTab(index)
        job.setParent(None)
        job.deleteLater()

        if job in self.search_jobs:
            self.search_jobs.remove(job)

        self.add_log(f"➖ 검색 작업 카드를 삭제했습니다 (현재 {len(self.search_jobs)}개)")
        self._update_add_job_button_state()
        self._save_search_jobs_state()

    def _update_add_job_button_state(self):
        """카드(탭) 총 개수 상한에 맞춰 "+" 버튼 활성/비활성을 갱신한다."""
        at_limit = len(self.search_jobs) >= MAX_SEARCH_JOBS
        self.add_job_btn.setEnabled(not at_limit)
        if at_limit:
            self.add_job_btn.setToolTip(f"검색 작업은 최대 {MAX_SEARCH_JOBS}개까지 만들 수 있습니다")
        else:
            self.add_job_btn.setToolTip("검색 작업 추가")

    def _refresh_job_tab_icon(self, job, status: str):
        """카드의 상태 변화에 맞춰 jobs_tab_widget의 탭 헤더 상태 색점을 갱신한다."""
        index = self.jobs_tab_widget.indexOf(job)
        if index == -1:
            return
        dot_color, _text_color = JOB_STATUS_COLORS.get(status, (NEUTRAL_GRAY, INK_MUTED))
        self.jobs_tab_widget.setTabIcon(index, make_status_dot_icon(dot_color))

    # ---- Phase 5: 동시 실행 5개 제한 (GUI 스레드에서만 증감 - 락 불필요) ----
    def try_start_job(self) -> bool:
        """카드의 '시작' 버튼 클릭(GUI 스레드)에서 직접 호출된다.

        실행 중인 작업이 MAX_CONCURRENT_JOBS 미만이면 카운터를 증가시키고 True를 반환한다.
        """
        if self.running_job_count >= MAX_CONCURRENT_JOBS:
            return False
        self.running_job_count += 1
        return True

    def _on_job_finished(self, success: bool):
        """카드의 finished 시그널 슬롯(= 항상 GUI 스레드에서 실행됨).

        워커 스레드는 이 카운터를 직접 건드리지 않고 시그널만 emit하므로 레이스가 없다.
        """
        if self.running_job_count > 0:
            self.running_job_count -= 1

    # ---- Phase 5: 네트워크 임계구역 전역 직렬화 ----
    def run_network_call(self, fn, *args, **kwargs):
        """검색/예약 등 실제 HTTP 호출을 전역 Lock으로 감싸 직렬화한다.

        여러 카드가 공유하는 self.ktx_service(하나의 로그인 세션)를 동시에
        두드리면 쿠키 갱신 경쟁·서버측 세션 간섭·안티봇 탐지 위험이 커진다.
        마지막 호출 이후 최소 RETRY_DELAY_MIN 간격도 함께 강제한다.
        """
        with self.network_lock:
            elapsed = time.monotonic() - self._last_network_call_at
            remaining = RETRY_DELAY_MIN - elapsed
            if remaining > 0:
                time.sleep(remaining)
            try:
                return fn(*args, **kwargs)
            finally:
                self._last_network_call_at = time.monotonic()

    # ---- Phase 5: 알림음 동시 재생 방지 ----
    def try_acquire_alert(self) -> bool:
        """다른 카드가 이미 알림음을 재생 중이 아니면 True를 반환하고 가드를 선점한다."""
        with self._alert_lock:
            if self.is_alert_playing:
                return False
            self.is_alert_playing = True
            return True

    def release_alert(self):
        """알림음 재생을 마친 카드가 가드를 반납한다."""
        with self._alert_lock:
            self.is_alert_playing = False

    # ---- Phase 5: 자동 결제는 한 번에 한 건씩 순서대로 ----
    def acquire_auto_payment(self) -> None:
        """결제 폼(카드 정보 입력)이 앱에 하나뿐이라, 이 락으로 결제 시도를 직렬화한다.

        여러 카드가 동시에 예약에 성공해도 스킵하지 않고, 이 락을 잡은 순서대로
        한 건씩 자동 결제를 진행한다(블로킹 acquire).
        """
        self.payment_lock.acquire()

    def release_auto_payment(self) -> None:
        """결제를 마친 카드가 다음 대기 중인 카드에게 락을 넘긴다."""
        self.payment_lock.release()

    # ---- Phase 5: 공용 "예약 완료" 패널 ----
    def _on_reservation_completed(self, data: dict):
        """카드로부터 예약 성사 통지를 받아 공용 패널에 한 줄 추가한다.

        (GUI 스레드, app_signals.reservation_completed 시그널 슬롯)
        """
        # 전광판처럼 "구간 / 날짜시간 / 열차종류 / 예약번호 / 결제상태" 순으로, 모노스페이스
        # 폰트에서 열이 맞춰지도록 각 칸의 폭을 고정해 정렬한다(표시 전용 포맷팅).
        route = str(data.get('route', '?')).ljust(20)
        dt = str(data.get('datetime', '?')).ljust(24)
        train_type = str(data.get('train_type', '?')).ljust(8)
        reservation_number = str(data.get('reservation_number', '?')).ljust(12)
        payment_status = str(data.get('payment_status', '?'))
        line = f"{route} {dt} {train_type} {reservation_number} {payment_status}"
        self.reservation_panel_display.append(line)

    def create_log_section(self):
        """로그 섹션 생성"""
        # 카드 프레임
        card = QFrame()
        card.setObjectName("card")

        main_layout = QVBoxLayout(card)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 헤더 (제목 + 지우기 버튼)
        header_layout = QHBoxLayout()
        title_label = QLabel("📋 실행 로그")
        title_label.setObjectName("sectionLabel")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        clear_btn = QPushButton("🗑️ 지우기")
        clear_btn.setObjectName("clearButton")
        clear_btn.clicked.connect(self.clear_log)
        header_layout.addWidget(clear_btn)

        main_layout.addLayout(header_layout)

        # 로그 디스플레이
        self.log_display = QTextEdit()
        self.log_display.setObjectName("logDisplay")
        self.log_display.setReadOnly(True)
        self.log_display.setMinimumHeight(200)
        self.log_display.setMaximumHeight(250)
        main_layout.addWidget(self.log_display)

        return card

    def add_log(self, message: str):
        """로그 추가 (스레드 안전)"""
        self.log_signals.log_message.emit(message)

    def append_log(self, message: str):
        """로그 표시"""
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        self.log_display.append(f"[{timestamp}] {message}")
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_log(self):
        """로그 지우기"""
        self.log_display.clear()

    def load_saved_credentials(self) -> bool:
        """저장된 자격 증명 로드. 로그인 정보(아이디/비밀번호)가 있었으면 True를 반환한다

        (호출부는 이 반환값으로 1회 자동 로그인 시도 여부를 결정한다).
        """
        # KTX 로그인 정보 로드
        ktx_login_loaded = False
        ktx_login = CredentialStorage.load_ktx_login()
        if ktx_login:
            self.ktx_id_input.setText(ktx_login.username)
            self.ktx_pw_input.setText(ktx_login.password)
            self.ktx_save_login_check.setChecked(True)
            ktx_login_loaded = True

        # KTX 결제 정보 로드
        ktx_payment = CredentialStorage.load_ktx_payment()
        if ktx_payment:
            self.ktx_payment_card_num_input.setText(ktx_payment.card_number)
            self.ktx_payment_card_pw_input.setText(ktx_payment.card_password)
            self.ktx_payment_expire_input.setText(ktx_payment.expire)
            self.ktx_payment_corporate_check.setChecked(ktx_payment.is_corporate)
            if ktx_payment.is_corporate:
                self.ktx_payment_business_num_input.setText(ktx_payment.validation_number)
            else:
                self.ktx_payment_birth_input.setText(ktx_payment.validation_number)
            self.ktx_save_payment_check.setChecked(True)

        return ktx_login_loaded

    def toggle_password_visibility(self, password_input: QLineEdit, toggle_btn: QPushButton):
        """비밀번호 보기/숨기기 토글"""
        if password_input.echoMode() == QLineEdit.EchoMode.Password:
            password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            toggle_btn.setText("Hide")
        else:
            password_input.setEchoMode(QLineEdit.EchoMode.Password)
            toggle_btn.setText("Show")

    def toggle_log_section(self):
        """로그 섹션 보기/숨기기 토글"""
        self.is_log_visible = not self.is_log_visible
        self.log_section.setVisible(self.is_log_visible)
        if self.is_log_visible:
            self.log_toggle_btn.setText("▲ 실행 로그 숨기기")
        else:
            self.log_toggle_btn.setText("▼ 실행 로그 보기")

    # ---- 로그인 (검색 버튼에서 분리) ----
    def login_ktx(self):
        """KTX 로그인 시도 (로그인 화면의 버튼 클릭 또는 저장된 자격증명이 있을 때 앱 시작 시 1회)"""
        if not self.ktx_id_input.text().strip() or not self.ktx_pw_input.text().strip():
            self.ktx_login_error_label.setText("✗ 아이디와 비밀번호를 입력해주세요")
            self.ktx_login_error_label.setVisible(True)
            self.add_log("✗ 입력 오류: 아이디와 비밀번호를 입력해주세요")
            self.add_notification("error", "✗ 아이디와 비밀번호를 입력해주세요")
            return

        self.ktx_login_btn.setEnabled(False)
        self.ktx_login_error_label.setVisible(False)
        self.add_log("🔐 Korail 로그인 중...")

        threading.Thread(target=self._login_ktx_thread, daemon=True).start()

    def _login_ktx_thread(self):
        """로그인 스레드. 중복 로그인 요청은 락으로 직렬화한다."""
        username = self.ktx_id_input.text()
        password = self.ktx_pw_input.text()
        error_detail = None

        with self._login_lock:
            try:
                success = self.ktx_service.login(username, password)
                if not success:
                    error_detail = getattr(self.ktx_service, "last_login_error", None) \
                        or "아이디 또는 비밀번호가 올바르지 않습니다"
            except Exception as e:
                success = False
                error_detail = str(e)

        if success:
            # 로그인 정보 저장 (체크박스 확인)
            if self.ktx_save_login_check.isChecked():
                CredentialStorage.save_ktx_login(username, password)
            else:
                CredentialStorage.delete_ktx_login()

        # UI 갱신은 GUI 스레드로 마샬링.
        # 주의: QTimer.singleShot()은 그걸 호출하는 스레드에 이벤트루프가 있어야
        # 콜백이 실행된다. 여기는 평범한 threading.Thread(이벤트루프 없음)라
        # singleShot이 영원히 발화하지 않아 로그인이 성공해도 버튼/화면이
        # 멈춰있는 버그가 있었다. pyqtSignal.emit()은 어느 스레드에서 호출해도
        # 항상 수신 QObject가 속한 스레드(GUI 스레드)의 큐에 안전하게 전달된다.
        self.app_signals.login_finished.emit(success, error_detail or "")

    def _on_login_finished(self, success: bool, error_detail: str = ""):
        """로그인 결과를 UI에 반영 (GUI 스레드에서 실행)

        성공하면 계정 정보를 갱신하고 메인 화면(페이지 1)으로 전환한다.
        실패하면 로그인 화면(페이지 0)에 그대로 머무르며 에러 메시지를 보여준다.
        """
        if success:
            self.add_log("✓ 로그인 성공")
            self.ktx_login_status_label.setText("✓ 로그인됨")
            self.ktx_login_error_label.setVisible(False)
            self._refresh_account_info_labels()
            self.stacked_widget.setCurrentIndex(1)
            self.add_notification("success", "✓ 로그인 성공")
        else:
            self.add_log(f"✗ 로그인 실패: {error_detail}")
            self.ktx_login_error_label.setText(f"✗ 로그인 실패: {error_detail}")
            self.ktx_login_error_label.setVisible(True)
            self.ktx_login_btn.setEnabled(True)
            self.add_notification("error", f"✗ 로그인 실패: {error_detail}")

    def _validate_ktx_payment_info(self) -> bool:
        """KTX 결제 정보 검증"""
        card_num = self.ktx_payment_card_num_input.text().strip()
        card_pw = self.ktx_payment_card_pw_input.text().strip()
        expire = self.ktx_payment_expire_input.text().strip()

        # 기본 정보 체크
        if not card_num or not card_pw or not expire:
            return False

        # 법인카드 체크
        if self.ktx_payment_corporate_check.isChecked():
            business_num = self.ktx_payment_business_num_input.text().strip()
            if not business_num:
                return False
        else:
            birth = self.ktx_payment_birth_input.text().strip()
            if not birth:
                return False

        return True

    def _process_ktx_payment(self, reservation: ReservationResult) -> PaymentResult:
        """KTX 결제 처리"""
        try:
            self.add_log("💳 결제 진행 중...")

            card_number = self.ktx_payment_card_num_input.text()
            card_pw = self.ktx_payment_card_pw_input.text()
            is_corporate = self.ktx_payment_corporate_check.isChecked()
            validation_number = (
                self.ktx_payment_birth_input.text()
                if not is_corporate
                else self.ktx_payment_business_num_input.text()
            )
            expire = self.ktx_payment_expire_input.text()

            # 결제 정보 저장 (체크박스 확인)
            if self.ktx_save_payment_check.isChecked():
                CredentialStorage.save_ktx_payment(
                    card_number=card_number,
                    card_password=card_pw,
                    expire=expire,
                    validation_number=validation_number,
                    is_corporate=is_corporate
                )
            else:
                CredentialStorage.delete_ktx_payment()

            # 결제 API 호출
            credit_card = CreditCard(
                number=card_number,
                password=card_pw,
                validation_number=validation_number,
                expire=expire,
                is_corporate=is_corporate
            )
            # 네트워크 임계구역: 결제도 공유 세션을 통해 나가는 HTTP 호출이므로 직렬화한다
            payment_result = self.run_network_call(
                self.ktx_service.payment_reservation,
                reservation,
                credit_card,
            )

            return payment_result
        except Exception as e:
            self.add_log(f"💳 결제 오류: {str(e)}")
            return PaymentResult(success=False, message=f"Payment error: {str(e)}")


def main():
    """메인 함수"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 모던한 스타일 적용
    # 주의: setup_dark_palette(app)는 여기서 호출하지 않는다.
    # STYLESHEET가 "기차역 전광판" 라이트 테마(PAPER/INK 배경)로 완전히 통일되어 있는데,
    # 다크 QPalette(어두운 배경 + 거의 흰색 텍스트)를 앱 전체에 적용하면 QSS가 명시적으로
    # 다시 칠하지 않는 위젯(팝업/기본 패널 등)에서 팔레트가 새어나와 밝은 배경 위에 거의 흰색
    # 글자가 겹쳐 텍스트가 안 보이는 문제가 생긴다. 함수 자체는 기존 테스트가 검증하므로
    # 그대로 두고, 실제 QApplication에 적용하는 이 호출부만 제거했다.
    # 대신 setup_light_palette(app)로 STYLESHEET와 일치하는 라이트 팔레트를 명시한다 -
    # OS가 다크 모드여도 Fusion 스타일의 기본 팔레트가 어두워지는 것을 막아야 하기 때문이다.
    setup_light_palette(app)
    window = TrainReservationApp()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
