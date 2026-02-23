import dash
from dash import dcc, html, Patch
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import zmq
import numpy as np
import threading
import logging

from src.config import PortsConfig, SignalConfig

logging.basicConfig(format="%(levelname)s: %(processName)s: %(module)s: %(funcName)s: %(message)s", level=logging.DEBUG)

def start_dashboard(ports: PortsConfig, sig: SignalConfig, stop_event=None):
    """
    Start the Dash dashboard as a standalone process.
    """
    # Silence Werkzeug (Flask) access logs
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    app = dash.Dash(__name__, update_title=None, title="Vibe - AudioModem")

    freqs = np.linspace(0, sig.nyquist_freq, ports.half_fft_size)

    latest_fft = np.zeros(ports.half_fft_size)
    fft_lock = threading.Lock()

    def zmq_listener():
        nonlocal latest_fft
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect(f"tcp://localhost:{ports.fft_port}")
        socket.setsockopt_string(zmq.SUBSCRIBE, "")
        
        logging.info(f"Dashboard: ZMQ Listener started, connecting to port {ports.fft_port}")
        
        # Use stop_event if provided, otherwise check if the thread is still valid
        while stop_event is None or not stop_event.is_set():
            try:
                # Use a timeout to avoid blocking indefinitely, allowing periodic stop_event checks
                if socket.poll(1000, zmq.POLLIN):
                    msg = socket.recv()
                    data = np.frombuffer(msg, dtype=np.float32)
                    with fft_lock:
                        if len(data) == ports.fft_size:
                            latest_fft = data[ports.half_fft_size:]
                        else:
                            # Fallback for dynamic resizing
                            mid = len(data) // 2
                            latest_fft = data[mid:]
                        latest_fft = 10*np.log(latest_fft)
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
        data=[
            # Trace 0: Invisible baseline at -100
            go.Scatter(x=freqs, y=np.full(len(freqs), -100), mode='lines', line=dict(width=0), hoverinfo='skip', showlegend=False),
            # Trace 1: Spectrogram trace filling down to the baseline
            go.Scatter(x=freqs, y=np.zeros(len(freqs)), mode='lines', line=dict(color='#00ffcc'), fill='tonexty')
        ]
    )
    initial_fig.update_layout(
        title=f'Magnitude Spectrum (Port {ports.fft_port})',
        xaxis_title='Fréquence (Hz)',
        yaxis_title='Magnitude',
        template='plotly_dark',
        margin=dict(l=40, r=40, t=60, b=40),
        yaxis=dict(range=[-100, 100])
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
        patched_fig["data"][1]["y"] = data

        return patched_fig

    logging.info("Starting Dash server...")
    app.run(debug=False, use_reloader=False, port=8050, dev_tools_hot_reload=False)

if __name__ == '__main__':
    from src.config import DEFAULT_PORTS_CONFIG, DEFAULT_SIGNAL_CONFIG
    start_dashboard(DEFAULT_PORTS_CONFIG, DEFAULT_SIGNAL_CONFIG)

