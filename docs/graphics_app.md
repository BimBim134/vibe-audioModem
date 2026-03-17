# Graphics Application (`graphics_app.py`)

## Overview

The `graphics_app.py` module provides a PyQt6-based GUI application for vibe-audioModem. It visualizes real-time FFT spectrum data, spectrograms (waterfall displays), constellation diagrams, and provides a messaging interface for transmitting and receiving data via audio modem.

## Dependencies

- **PySide6**: Qt6 bindings for Python (QtWidgets, QtCore, QtUiTools)
- **PyQtGraph**: Fast plotting library for visualization
- **PySide6.QtWebEngineWidgets**: For embedded web content (chat view)
- **ZeroMQ (zmq)**: For inter-thread/process communication
- **NumPy**: Numerical computing
- **PMT**: GNU Radio Python Message Template (for message serialization)

## Classes

### ZMQWorker

A Qt worker object that receives FFT spectrum data via ZeroMQ.

**Signals:**
- `data_received(np.ndarray)`: Emitted when FFT data is received

**Constructor:**
- `__init__(ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG)`: Initialize with port configuration

**Methods:**
- `run()`: Main loop that connects to ZMQ port and listens for FFT data
- `stop()`: Stop the worker by setting `running` flag to False

**Notes:**
- Subscribes to `tcp://127.0.0.1:{fft_port}`
- Expects data as float32 numpy array
- 1 second timeout on receive, 100 message HWM

---

### MessageZMQWorker

A Qt worker that receives reassembled messages from the packet decoder.

**Signals:**
- `message_received(dict)`: Emitted when a decoded message is received

**Constructor:**
- `__init__(ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG)`: Initialize with port configuration

**Methods:**
- `run()`: Main loop that receives serialized PMT messages
- `stop()`: Stop the worker

**Notes:**
- Expects PMT-serialized dictionary payloads
- Handles deserialization using `pmt.to_python()`

---

### ConstellationZMQWorker

A Qt worker that receives constellation points (complex numbers) from the demodulator.

**Signals:**
- `data_received(np.ndarray)`: Emitted when constellation data is received

**Constructor:**
- `__init__(ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG)`: Initialize with port configuration

**Methods:**
- `run()`: Main loop that connects to multiple constellation ports
- `stop()`: Stop the worker

**Notes:**
- Can subscribe to multiple demodulator workers (`constellation_ports_count`)
- Data is expected as complex64 numpy array

---

### TransmitWorker

A Qt worker that handles data transmission in a separate thread.

**Signals:**
- `finished()`: Emitted when transmission is complete

**Constructor:**
- `__init__(message: Any, signal_conf: SignalConfig, pkt_conf: PacketConfig, sender_name: str = "default")`

**Methods:**
- `run()`: Executes transmission via `send_data()`

---

### MainWindow

The main application window, subclass of `QtWidgets.QMainWindow`.

**Constructor:**
```python
def __init__(
    self,
    signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG,
    pkt_conf: PacketConfig = DEFAULT_PACKET_CONFIG,
)
```

**UI Components:**
- **Spectroscope**: Real-time FFT spectrum display (PlotWidget)
- **Spectrogram**: Waterfall/rolling buffer display (ImageItem)
- **Constellation Diagram**: I/Q scatter plot for demodulated symbols
- **Message Editor**: QTextEdit for composing messages
- **Send Button**: QPushButton to trigger transmission
- **Carrier Frequency**: QDoubleSpinBox for setting carrier frequency
- **Modulation Chooser**: QComboBox for selecting modulation presets
- **Messages Board**: QWebEngineView for chat interface

**Methods:**

- `init_chat_window()`: Initialize the embedded HTML/CSS/JS chat view
- `inject_template_message(type, sender, meta, content)`: Inject a formatted message into the webview
- `inject_html_message(html_content)`: Inject raw HTML into the webview
- `update_constellation(data)`: Update constellation scatter plot with new I/Q points
- `update_carrier_freq(value)`: Update signal configuration carrier frequency
- `update_modulation_preset(index)`: Apply selected modulation preset
- `display_received_message(payload)`: Format and display received message
- `update_plots(data)`: Update spectroscope and spectrogram displays
- `start_transmission()`: Initiate message transmission
- `closeEvent(event)`: Cleanup ZMQ threads and sockets on close

**Threading:**
- Maintains three separate QThreads for ZMQ workers
- Uses Qt signal/slot mechanism for thread-safe UI updates

---

## Configuration

### PyQtGraph Dark Theme
Configured at module level:
```python
pg.setConfigOption('background', '#12141a')
pg.setConfigOption('foreground', '#a6adc8')
```

### ZMQ Configuration
- Config publisher bound to `tcp://127.0.0.1:{config_port}`
- Used to broadcast preset changes to GNU Radio flowgraph

---

## Usage

### Running the Application

```python
from src.UI.pyqt.graphics_app import run_graphics_app
from src.config import DEFAULT_SIGNAL_CONFIG, DEFAULT_PORTS_CONFIG, DEFAULT_PACKET_CONFIG

run_graphics_app(
    signal_conf=DEFAULT_SIGNAL_CONFIG,
    ports_conf=DEFAULT_PORTS_CONFIG,
    pkt_conf=DEFAULT_PACKET_CONFIG,
)
```

### Command Line

```bash
python -m src.UI.pyqt.graphics_app
```

---

## Signal Flow

```
┌─────────────────┐     ZMQ SUB      ┌──────────────────┐
│ GNU Radio       │ ──────────────► │ ZMQWorker        │
│ FFT Sink        │   (fft_port)    │ → update_plots() │
└─────────────────┘                  └──────────────────┘

┌─────────────────┐     ZMQ SUB      ┌──────────────────────┐
│ Packet Decoder  │ ──────────────►  │ MessageZMQWorker     │
│                 │ (messages_port)  │ → display_received_ │
└─────────────────┘                  │    message()        │
                                     └──────────────────────┘

┌─────────────────┐     ZMQ SUB      ┌────────────────────────┐
│ Demodulator     │ ──────────────►  │ ConstellationZMQWorker│
│ (complex)       │(constellation   │ → update_constellation │
│                 │   _port)         │                        │
└─────────────────┘                  └────────────────────────┘

┌─────────────────┐     ZMQ PUB      ┌─────────────────┐
│ MainWindow      │ ──────────────►  │ GNU Radio       │
│ Config Publisher│ (config_port)    │ Flowgraph       │
└─────────────────┘                  └─────────────────┘
```

---

## Modulation Presets

The application supports three modulation presets defined in `src.config`:

| Preset | Description |
|--------|-------------|
| SLOW   | Low baudrate, robust transmission |
| MEDIUM | Balanced speed/reliability |
| FAST   | High baudrate, less robust |

The selected preset is broadcast to the GNU Radio flowgraph via ZMQ.
