import sys
import requests
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QListWidget, QSlider, 
                             QLabel, QListWidgetItem, QMessageBox)
from PyQt5.QtCore import QTimer, Qt, QUrl
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtGui import QFont
from urllib3.exceptions import NewConnectionError
import socket


class MusicPlayerClient(QMainWindow):
    def __init__(self, server_url="http://127.0.0.1:8000"):  # Изменено на 127.0.0.1
        super().__init__()
        self.server_url = server_url
        self.player = QMediaPlayer()
        self.tracks = []
        self.current_track_name = ""
        self.is_playing = False
        self.connection_attempts = 0
        
        self.init_ui()
        self.setup_timer()
        self.check_server_connection()
        
    def init_ui(self):
        self.setWindowTitle("Музыкальный плеер - Клиент")
        self.setGeometry(100, 100, 600, 500)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Заголовок
        title = QLabel("🎵 Музыкальный плеер")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Информация о подключении
        self.connection_label = QLabel("Проверка подключения к серверу...")
        self.connection_label.setAlignment(Qt.AlignCenter)
        self.connection_label.setStyleSheet("padding: 5px; background-color: #ffffcc; border-radius: 3px;")
        layout.addWidget(self.connection_label)
        
        # Информация о текущем треке
        self.track_label = QLabel("Нет трека")
        self.track_label.setFont(QFont("Arial", 12))
        self.track_label.setAlignment(Qt.AlignCenter)
        self.track_label.setStyleSheet("padding: 10px; background-color: #f0f0f0; border-radius: 5px;")
        layout.addWidget(self.track_label)
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self.play)
        self.play_btn.setEnabled(False)
        
        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setEnabled(False)
        
        self.prev_btn = QPushButton("⏮ Prev")
        self.prev_btn.clicked.connect(self.prev_track)
        self.prev_btn.setEnabled(False)
        
        self.next_btn = QPushButton("⏭ Next")
        self.next_btn.clicked.connect(self.next_track)
        self.next_btn.setEnabled(False)
        
        buttons_layout.addWidget(self.prev_btn)
        buttons_layout.addWidget(self.play_btn)
        buttons_layout.addWidget(self.stop_btn)
        buttons_layout.addWidget(self.next_btn)
        
        layout.addLayout(buttons_layout)
        
        # Громкость
        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("Громкость:"))
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.valueChanged.connect(self.change_volume)
        volume_layout.addWidget(self.volume_slider)
        
        self.volume_label = QLabel("50%")
        volume_layout.addWidget(self.volume_label)
        
        layout.addLayout(volume_layout)
        
        # Список треков
        layout.addWidget(QLabel("Список треков:"))
        
        self.track_list = QListWidget()
        self.track_list.itemDoubleClicked.connect(self.play_selected_track)
        layout.addWidget(self.track_list)
        
        # Кнопка обновления списка
        refresh_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Обновить список")
        self.refresh_btn.clicked.connect(self.load_tracks)
        self.refresh_btn.setEnabled(False)
        refresh_layout.addWidget(self.refresh_btn)
        
        self.retry_btn = QPushButton("🔄 Повторить подключение")
        self.retry_btn.clicked.connect(self.check_server_connection)
        refresh_layout.addWidget(self.retry_btn)
        
        layout.addLayout(refresh_layout)
        
        # Статус бар
        self.status_label = QLabel("Статус: Ожидание подключения...")
        self.status_label.setStyleSheet("color: orange;")
        layout.addWidget(self.status_label)
        
    def check_server_connection(self):
        """Проверка подключения к серверу"""
        try:
            # Пробуем подключиться к серверу
            response = requests.get(f"{self.server_url}/state", timeout=2)
            if response.status_code == 200:
                self.connection_label.setText("✅ Подключено к серверу")
                self.connection_label.setStyleSheet("padding: 5px; background-color: #98FB98; border-radius: 3px;")
                self.connection_attempts = 0
                
                # Включаем кнопки
                self.prev_btn.setEnabled(True)
                self.next_btn.setEnabled(True)
                self.refresh_btn.setEnabled(True)
                
                # Загружаем треки
                self.load_tracks()
                self.update_state()
                
                # Запускаем таймер обновления
                self.timer.start(1000)
                
        except (requests.exceptions.ConnectionError, 
                requests.exceptions.Timeout,
                NewConnectionError,
                socket.error) as e:
            
            self.connection_attempts += 1
            self.connection_label.setText(f"❌ Нет подключения к серверу (попытка {self.connection_attempts})")
            self.connection_label.setStyleSheet("padding: 5px; background-color: #F08080; border-radius: 3px;")
            self.status_label.setText(f"Ошибка: {str(e)[:50]}...")
            self.status_label.setStyleSheet("color: red;")
            
            # Отключаем кнопки
            self.play_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            
            # Пробуем снова через 3 секунды
            QTimer.singleShot(3000, self.check_server_connection)
        
    def setup_timer(self):
        """Таймер для обновления состояния с сервера"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_state)
        # Таймер запускается только после успешного подключения
        
    def load_tracks(self):
        """Загрузка списка треков с сервера"""
        try:
            response = requests.get(f"{self.server_url}/tracks", timeout=10)
            if response.status_code == 200:
                self.tracks = response.json()
                self.track_list.clear()
                
                for track in self.tracks:
                    item = QListWidgetItem(f"{track['id'] + 1}. {track['name']}")
                    item.setData(Qt.UserRole, track)
                    self.track_list.addItem(item)
                
                self.status_label.setText(f"Статус: Загружено {len(self.tracks)} треков")
                self.status_label.setStyleSheet("color: green;")
                
                if self.tracks:
                    self.play_btn.setEnabled(True)
                    
        except requests.exceptions.RequestException as e:
            self.status_label.setText(f"Ошибка загрузки треков: {str(e)}")
            self.status_label.setStyleSheet("color: red;")
            
    def update_state(self):
        """Обновление состояния с сервера"""
        try:
            response = requests.get(f"{self.server_url}/state", timeout=1)
            if response.status_code == 200:
                state = response.json()
                
                if state['power'] and state['track']:
                    self.current_track_name = state['track']
                    self.track_label.setText(f"Сейчас играет: {state['track']}")
                    self.track_label.setStyleSheet("color: #EE82EE;")
                    self.is_playing = True
                    
                    # Если плеер не играет текущий трек, начинаем воспроизведение
                    if self.player.state() != QMediaPlayer.PlayingState:
                        self.play_current_track()
                        
                elif not state['power']:
                    self.track_label.setText("Плеер остановлен")
                    self.is_playing = False
                    self.player.stop()
                    
                # Обновление кнопок
                self.play_btn.setText("⏸ Pause" if self.is_playing else "▶ Play")
                self.stop_btn.setEnabled(self.is_playing)
                
        except requests.exceptions.RequestException:
            # Если потеряли соединение, проверяем его заново
            self.check_server_connection()
            
    def play(self):
        """Воспроизведение/пауза"""
        try:
            if self.is_playing:
                self.player.pause()
                self.is_playing = False
                self.play_btn.setText("▶ Play")
            else:
                response = requests.get(f"{self.server_url}/play", timeout=1)
                if response.status_code == 200:
                    self.is_playing = True
                    self.play_btn.setText("⏸ Pause")
                    
        except requests.exceptions.RequestException as e:
            self.status_label.setText(f"Ошибка: {str(e)}")
            self.status_label.setStyleSheet("color: red;")
            
    def stop(self):
        """Остановка воспроизведения"""
        try:
            response = requests.get(f"{self.server_url}/stop", timeout=1)
            if response.status_code == 200:
                self.player.stop()
                self.is_playing = False
                self.play_btn.setText("▶ Play")
                self.track_label.setText("Плеер остановлен")
                
        except requests.exceptions.RequestException as e:
            self.status_label.setText(f"Ошибка: {str(e)}")
            
    def next_track(self):
        """Следующий трек"""
        try:
            response = requests.get(f"{self.server_url}/next", timeout=1)
            if response.status_code == 200:
                self.update_state()
                
        except requests.exceptions.RequestException as e:
            self.status_label.setText(f"Ошибка: {str(e)}")
            
    def prev_track(self):
        """Предыдущий трек"""
        try:
            response = requests.get(f"{self.server_url}/prev", timeout=1)
            if response.status_code == 200:
                self.update_state()
                
        except requests.exceptions.RequestException as e:
            self.status_label.setText(f"Ошибка: {str(e)}")
            
    def play_selected_track(self, item):
        """Воспроизведение выбранного трека из списка"""
        track_data = item.data(Qt.UserRole)
        try:
            response = requests.get(f"{self.server_url}/play/{track_data['id']}", timeout=1)
            if response.status_code == 200:
                self.update_state()
                
        except requests.exceptions.RequestException as e:
            self.status_label.setText(f"Ошибка: {str(e)}")
            
    def play_current_track(self):
        """Воспроизведение текущего трека на клиенте"""
        if self.current_track_name:
            url = f"{self.server_url}/music/{self.current_track_name}"
            self.player.setMedia(QMediaContent(QUrl(url)))
            self.player.play()
            
    def change_volume(self, value):
        """Изменение громкости"""
        self.player.setVolume(value)
        self.volume_label.setText(f"{value}%")
        
    def closeEvent(self, event):
        """При закрытии приложения"""
        self.timer.stop()
        self.player.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    # Показываем диалог выбора адреса сервера
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    msg = QMessageBox()
    msg.setWindowTitle("Настройка подключения")
    msg.setText(f"Введите адрес сервера:\n\n"
                f"• Локальный: http://127.0.0.1:8000\n"
                f"• Этот компьютер: http://{local_ip}:8000\n"
                f"• Другой компьютер: http://<IP-АДРЕС>:8000\n\n"
                f"Будет использован: http://127.0.0.1:8000")
    msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    
    client = MusicPlayerClient("http://127.0.0.1:8000")
    client.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()