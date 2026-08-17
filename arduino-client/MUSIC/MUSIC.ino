#include <WiFi.h>
#include <ESPmDNS.h>
#include <HTTPClient.h>

#include "AudioTools.h"
#include "AudioTools/AudioCodecs/CodecMP3Helix.h"
#include "AudioTools/Communication/AudioHttp.h"

#include "BluetoothA2DPSource.h"


// ============================================================
// Настройки
// ============================================================

const char* WIFI_SSID = "Reolo";
const char* WIFI_PASS = "ZbeK673t";

const char* BT_SPEAKER_NAME = "JBL Flip 4";

const char* MDNS_SERVICE = "musicplayer";
const char* MDNS_PROTO   = "tcp";

const uint32_t POLL_INTERVAL_MS = 2000;


// ============================================================
// Сервер
// ============================================================

String serverHost;
uint16_t serverPort = 8000;

String currentTrack;

bool serverPower = false;
bool isPlaying = false;


// ============================================================
// PCM buffer
// ============================================================

class PCMBuffer : public Print {

public:

  static const size_t BUFFER_SIZE = 16 * 1024;

  PCMBuffer() {
    reset();
  }


  // ----------------------------------------------------------
  // Print::write(uint8_t)
  // ----------------------------------------------------------

  size_t write(uint8_t value) override {

    return write(
      &value,
      1
    );
  }


  // ----------------------------------------------------------
  // Print::write(buffer, size)
  // ----------------------------------------------------------

  size_t write(
    const uint8_t* data,
    size_t len
  ) override {

    if (data == nullptr || len == 0) {
      return 0;
    }

    size_t written = 0;

    portENTER_CRITICAL(&mux);

    while (
      written < len &&
      buffered < BUFFER_SIZE
    ) {

      size_t spaceToEnd =
        BUFFER_SIZE - writePos;

      size_t freeSpace =
        BUFFER_SIZE - buffered;

      size_t chunk =
        len - written;

      if (chunk > spaceToEnd) {
        chunk = spaceToEnd;
      }

      if (chunk > freeSpace) {
        chunk = freeSpace;
      }

      if (chunk == 0) {
        break;
      }

      memcpy(
        &buffer[writePos],
        data + written,
        chunk
      );

      writePos += chunk;

      if (writePos >= BUFFER_SIZE) {
        writePos = 0;
      }

      buffered += chunk;
      written += chunk;
    }

    portEXIT_CRITICAL(&mux);

    return written;
  }


  // ----------------------------------------------------------
  // Сколько PCM сейчас лежит в буфере.
  // ----------------------------------------------------------

  size_t availableBytes() {

    portENTER_CRITICAL(&mux);

    size_t result = buffered;

    portEXIT_CRITICAL(&mux);

    return result;
  }


  // ----------------------------------------------------------
  // Чтение PCM.
  // ----------------------------------------------------------

  size_t readBytes(
    uint8_t* data,
    size_t len
  ) {

    if (
      data == nullptr ||
      len == 0
    ) {
      return 0;
    }

    size_t result = 0;

    portENTER_CRITICAL(&mux);

    size_t chunk = len;

    if (chunk > buffered) {
      chunk = buffered;
    }

    if (chunk > 0) {

      size_t toEnd =
        BUFFER_SIZE - readPos;

      if (chunk <= toEnd) {

        memcpy(
          data,
          &buffer[readPos],
          chunk
        );

      } else {

        memcpy(
          data,
          &buffer[readPos],
          toEnd
        );

        memcpy(
          data + toEnd,
          &buffer[0],
          chunk - toEnd
        );
      }

      readPos += chunk;

      if (readPos >= BUFFER_SIZE) {
        readPos = 0;
      }

      buffered -= chunk;

      result = chunk;
    }

    portEXIT_CRITICAL(&mux);

    return result;
  }


  // ----------------------------------------------------------
  // Очистить буфер.
  // ----------------------------------------------------------

  void reset() {

    portENTER_CRITICAL(&mux);

    readPos = 0;
    writePos = 0;
    buffered = 0;

    portEXIT_CRITICAL(&mux);
  }


private:

  uint8_t buffer[BUFFER_SIZE];

  size_t readPos = 0;
  size_t writePos = 0;
  size_t buffered = 0;

  portMUX_TYPE mux =
    portMUX_INITIALIZER_UNLOCKED;
};


PCMBuffer pcmBuffer;



// ============================================================
// HTTP stream
// ============================================================

URLStream urlStream;



// ============================================================
// MP3 decoder
// ============================================================

MP3DecoderHelix mp3Decoder;


// EncodedAudioStream хочет Print*.
// неоднозначность между Print*, Stream*, AudioStream* и AudioOutput*.

EncodedAudioStream decoder(
  static_cast<Print*>(&pcmBuffer),
  &mp3Decoder
);


// Копирует:
// URLStream → decoder
//
// decoder при этом декодирует MP3 и пишет PCM в pcmBuffer.

StreamCopy copier(
  decoder,
  urlStream
);




// ============================================================
// Bluetooth A2DP
// ============================================================

BluetoothA2DPSource a2dp_source;


// ------------------------------------------------------------
// A2DP callback
//
// ESP32-A2DP получает сюда PCM.
// Формат:
//   16 bit
//   stereo
//   44100 Hz
// ------------------------------------------------------------

int32_t getAudioData(
  uint8_t* data,
  int32_t len
) {

  if (
    data == nullptr ||
    len <= 0
  ) {
    return 0;
  }


  size_t available =
    pcmBuffer.availableBytes();


  size_t toRead =
    len;


  if (toRead > available) {
    toRead = available;
  }


  if (toRead > 0) {

    size_t got =
      pcmBuffer.readBytes(
        data,
        toRead
      );


    if (got < (size_t)len) {

      memset(
        data + got,
        0,
        len - got
      );
    }

  } else {

    memset(
      data,
      0,
      len
    );
  }


  return len;
}


// ============================================================
// WiFi
// ============================================================

void connectWifi() {

  WiFi.mode(WIFI_STA);

  WiFi.begin(
    WIFI_SSID,
    WIFI_PASS
  );

  Serial.print(
    "Подключение к WiFi"
  );

  while (
    WiFi.status() != WL_CONNECTED
  ) {

    delay(300);

    Serial.print(".");
  }

  Serial.println();

  Serial.print(
    "IP: "
  );

  Serial.println(
    WiFi.localIP()
  );
}


// ============================================================
// mDNS discovery
// ============================================================

bool discoverServer() {

  if (
    !MDNS.begin(
      "esp32-music-client"
    )
  ) {

    Serial.println(
      "Ошибка запуска mDNS"
    );

    return false;
  }


  Serial.println(
    "Ищем сервер через mDNS..."
  );


  int n =
    MDNS.queryService(
      MDNS_SERVICE,
      MDNS_PROTO
    );


  if (n == 0) {

    Serial.println(
      "Сервер не найден"
    );

    return false;
  }


  serverHost =
    MDNS.address(0).toString();


  serverPort =
    MDNS.port(0);


  Serial.printf(
    "Сервер найден: %s:%d\n",
    serverHost.c_str(),
    serverPort
  );


  return true;
}


// ============================================================
// HTTP /state
// ============================================================

bool fetchState(
  String& trackOut,
  bool& powerOut
) {

  HTTPClient http;


  String url =
    "http://" +
    serverHost +
    ":" +
    String(serverPort) +
    "/state";


  http.begin(url);


  int code =
    http.GET();


  if (code != 200) {

    http.end();

    return false;
  }


  String payload =
    http.getString();


  http.end();


  // Формат:
  // {
  //   "power": true,
  //   "track": "name.mp3",
  //   "volume": 1.0
  // }


  powerOut =
    payload.indexOf(
      "\"power\": true"
    ) != -1 ||
    payload.indexOf(
      "\"power\":true"
    ) != -1;


  int ti =
    payload.indexOf(
      "\"track\": \""
    );


  if (ti == -1) {

    ti =
      payload.indexOf(
        "\"track\":\""
      );
  }


  if (ti != -1) {

    int start =
      payload.indexOf(
        '"',
        ti + 7
      );


    if (start != -1) {

      start++;


      int end =
        payload.indexOf(
          '"',
          start
        );


      if (end != -1) {

        trackOut =
          payload.substring(
            start,
            end
          );

      } else {

        trackOut = "";
      }

    } else {

      trackOut = "";
    }

  } else {

    trackOut = "";
  }


  return true;
}


// ============================================================
// Остановка
// ============================================================

void stopStreaming() {

  Serial.println(
    "Остановка стрима"
  );


  isPlaying = false;


  copier.end();

  decoder.end();

  urlStream.end();


  pcmBuffer.reset();
}


// ============================================================
// Запуск стрима
// ============================================================

void startStreamingTrack(
  const String& track
) {

  Serial.print(
    "Стримим: "
  );

  Serial.println(track);


  // Остановить предыдущий поток.

  copier.end();

  decoder.end();

  urlStream.end();

  pcmBuffer.reset();


  String url =
    "http://" +
    serverHost +
    ":" +
    String(serverPort) +
    "/music/" +
    track;


  Serial.print(
    "URL: "
  );

  Serial.println(url);


  // ----------------------------------------------------------
  // Открываем HTTP MP3 stream.
  // ----------------------------------------------------------

  if (
    !urlStream.begin(
      url.c_str(),
      "audio/mpeg"
    )
  ) {

    Serial.println(
      "Ошибка открытия URLStream"
    );

    isPlaying = false;

    return;
  }


  // ----------------------------------------------------------
  // Запускаем MP3 decoder.
  // ----------------------------------------------------------

  if (!decoder.begin()) {

    Serial.println(
      "Ошибка запуска MP3 decoder"
    );

    urlStream.end();

    isPlaying = false;

    return;
  }


  // ----------------------------------------------------------
  // URLStream → decoder
  // ----------------------------------------------------------

  copier.begin(
    decoder,
    urlStream
  );


  isPlaying = true;


  Serial.println(
    "Стрим запущен"
  );
}


// ============================================================
// setup
// ============================================================

void btConnectionStateChanged(
  esp_a2d_connection_state_t state,
  void* ptr
) {
  Serial.print("Bluetooth state: ");

  switch (state) {
    case ESP_A2D_CONNECTION_STATE_DISCONNECTED:
      Serial.println("DISCONNECTED");
      break;

    case ESP_A2D_CONNECTION_STATE_CONNECTING:
      Serial.println("CONNECTING");
      break;

    case ESP_A2D_CONNECTION_STATE_CONNECTED:
      Serial.println("CONNECTED");
      break;

    case ESP_A2D_CONNECTION_STATE_DISCONNECTING:
      Serial.println("DISCONNECTING");
      break;

    default:
      Serial.println("UNKNOWN");
      break;
  }
}

void setup() {

  Serial.begin(115200);

  delay(500);


  Serial.println();

  Serial.println(
    "=============================="
  );

  Serial.println(
    " ESP32 MUSIC CLIENT"
  );

  Serial.println(
    "=============================="
  );


  // ----------------------------------------------------------
  // WiFi
  // ----------------------------------------------------------

  connectWifi();


  // ----------------------------------------------------------
  // mDNS
  // ----------------------------------------------------------

  if (
    !discoverServer()
  ) {

    Serial.println(
      "Перезагрузка через 5с..."
    );

    delay(5000);

    ESP.restart();
  }


  // ----------------------------------------------------------
  // PCM
  // ----------------------------------------------------------

  pcmBuffer.reset();


  // ----------------------------------------------------------
  // Bluetooth
  // ----------------------------------------------------------

  Serial.println(
  "Подключаемся к Bluetooth-колонке..."
    );

    a2dp_source.set_data_callback(
      getAudioData
    );

    a2dp_source.set_on_connection_state_changed(
      btConnectionStateChanged
    );

    a2dp_source.start(
      BT_SPEAKER_NAME
    );

    Serial.println(
      "Bluetooth A2DP запущен"
);

}


// ============================================================
// loop
// ============================================================

unsigned long lastPoll = 0;


void loop() {

  unsigned long now =
    millis();


  // ----------------------------------------------------------
  // Качаем MP3 → декодер → PCM
  // ----------------------------------------------------------

  if (isPlaying) {

    copier.copy();
  }


  // ----------------------------------------------------------
  // Опрос /state
  // ----------------------------------------------------------

  if (
    now - lastPoll >=
    POLL_INTERVAL_MS
  ) {

    lastPoll = now;


    String track;
    bool power;


    if (
      fetchState(
        track,
        power
      )
    ) {

      serverPower =
        power;


      // ------------------------------------------------------
      // Сервер остановил музыку
      // ------------------------------------------------------

      if (
        !power &&
        isPlaying
      ) {

        stopStreaming();
      }


      // ------------------------------------------------------
      // Переключился трек
      // ------------------------------------------------------

      else if (
        power &&
        track != currentTrack
      ) {

        currentTrack =
          track;

        startStreamingTrack(
          track
        );
      }


      // ------------------------------------------------------
      // Сервер играет, ESP32 ещё ничего не играет
      // ------------------------------------------------------

      else if (
        power &&
        !isPlaying
      ) {

        currentTrack =
          track;

        startStreamingTrack(
          track
        );
      }
    }
  }


  delay(1);
}
