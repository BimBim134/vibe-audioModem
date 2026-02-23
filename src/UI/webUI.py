import dash
from dash import dcc, html, Patch
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import zmq
import numpy as np
import threading
import logging

from src.config import PortsConfig, SignalConfig

logging.basicConfig(level=logging.INFO)

def start_dashboard(ports_conf: PortsConfig, signal_conf: SignalConfig, stop_event=None):
    """
    Start the Dash dashboard as a standalone process.
    """
    # Silence Werkzeug (Flask) access logs
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    app = dash.Dash(__name__, update_title=None, title="Vibe - AudioModem")

    # Load configuration from arguments
    FFT_SIZE = ports_conf.fft_size
    FFT_PORT = ports_conf.fft_port
    NYQUIST = signal_conf.nyquist_freq

    # The spectrum is symmetric for real signals, so we only need the first half (positive frequencies)
    HALF_FFT_SIZE = FFT_SIZE // 2
    # Start at 1 to avoid log(0) issues on x-axis
    freqs = np.linspace(0, NYQUIST, HALF_FFT_SIZE)

    latest_fft = np.zeros(HALF_FFT_SIZE)
    fft_lock = threading.Lock()

    def zmq_listener():
        nonlocal latest_fft
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect(f"tcp://localhost:{FFT_PORT}")
        socket.setsockopt_string(zmq.SUBSCRIBE, "")
        
        logging.info(f"Dashboard: ZMQ Listener started, connecting to port {FFT_PORT}")
        
        # Use stop_event if provided, otherwise check if the thread is still valid
        while stop_event is None or not stop_event.is_set():
            try:
                # Use a timeout to avoid blocking indefinitely, allowing periodic stop_event checks
                if socket.poll(1000, zmq.POLLIN):
                    msg = socket.recv()
                    data = np.frombuffer(msg, dtype=np.float32)
                    if len(data) == FFT_SIZE:
                        with fft_lock:
                            # GNU Radio fft_vfc with shift=True puts 0Hz at the center. 
                            # The first half (0:2048) is -Nyquist to 0Hz.
                            # The second half (2048:4096) is 0Hz to +Nyquist.
                            latest_fft = data[HALF_FFT_SIZE:]
                    else:
                        with fft_lock:
                            # Fallback for dynamic resizing
                            mid = len(data) // 2
                            latest_fft = 10*np.log(data[mid:])
                elif stop_event and stop_event.is_set():
                    break
            except Exception as e:
                logging.error(f"Dashboard: Error receiving ZMQ message: {e}")
                if stop_event and stop_event.is_set():
                    break
        
        socket.close()
        context.term()
        logging.info("Dashboard: ZMQ Listener stopped.")

    listener_thread = threading.Thread(target=zmq_listener, name="DashboardZMQListener", daemon=True)
    listener_thread.start()

    # Initialize the figure ONCE
    initial_fig = go.Figure(
        data=[go.Scatter(x=freqs, y=np.zeros(HALF_FFT_SIZE), mode='lines', line=dict(color='#00ffcc'))]
    )
    initial_fig.update_layout(
        title=f'Magnitude Spectrum (Port {FFT_PORT})',
        xaxis_title='Fréquence (Hz)',
        yaxis_title='Magnitude',
        template='plotly_dark',
        margin=dict(l=40, r=40, t=60, b=40),
        yaxis=dict(range=[0, 20])
    )

    app.layout = html.Div([
        dcc.Graph(id='live-spectroscope-graph', figure=initial_fig, config={'displayModeBar': False}),
        dcc.Interval(
            id='interval-component',
            interval=100, # Update interval in milliseconds
            n_intervals=0
        )
    ], style={'backgroundColor': '#111111', 'minHeight': '100vh', 'padding': '20px', 'boxSizing': 'border-box'})

    @app.callback(Output('live-spectroscope-graph', 'figure'),
                  [Input('interval-component', 'n_intervals')])
    def update_graph_live(n):
        with fft_lock:
            data = latest_fft.copy()
        
        patched_fig = Patch()
        patched_fig["data"][0]["y"] = data

        return patched_fig

    logging.info("Starting Dash server...")
    # Disable dev_tools_hot_reload to stop the "F5" refresh feel
    app.run(debug=False, use_reloader=False, port=8050, dev_tools_hot_reload=False)

if __name__ == '__main__':
    from src.config import DEFAULT_SIGNAL_CONFIG, DEFAULT_PORTS_CONFIG
    start_dashboard(DEFAULT_PORTS_CONFIG, DEFAULT_SIGNAL_CONFIG)

