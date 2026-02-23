import dash
from dash import dcc, html, Patch, no_update
from dash.dependencies import Input, Output
import plotly.graph_objs as go
from plotly.subplots import make_subplots
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

    spectrogram_data = np.full((200, ports.half_fft_size), - 100)

    latest_fft = np.zeros(ports.half_fft_size)
    new_data_flag = [False]  # mutable container avoids nonlocal in callback
    fft_lock = threading.Lock()

    def zmq_listener():
        nonlocal latest_fft
        nonlocal spectrogram_data
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
                        spectrogram_data = np.roll(spectrogram_data, -1, axis=0)
                        spectrogram_data[-1, :] = latest_fft
                        new_data_flag[0] = True
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

    # Combined figure with subplots
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.3, 0.7],
        subplot_titles=("Spectroscope", "Spectrogram")
    )

    # Row 1: Spectroscope
    # Trace 0: Invisible baseline
    fig.add_trace(
        go.Scatter(x=freqs, y=np.full(len(freqs), -100), mode='lines', line=dict(width=0), hoverinfo='skip', showlegend=False),
        row=1, col=1
    )
    # Trace 1: Spectroscope data
    fig.add_trace(
        go.Scatter(x=freqs, y=np.zeros(len(freqs)), mode='lines', line=dict(color='#00ffcc'), fill='tonexty', name="Magnitude"),
        row=1, col=1
    )

    # Row 2: Spectrogram
    # Trace 2: Heatmap
    fig.add_trace(
        go.Heatmap(
            z=spectrogram_data,
            x=freqs,
            colorscale='Viridis',
            zmin=-100,
            zmax=100,
            showscale=False,
            name="Spectrogram"
        ),
        row=2, col=1
    )

    fig.update_layout(
        template='plotly_dark',
        margin=dict(l=40, r=40, t=60, b=40),
        height=800,
        showlegend=False
    )
    fig.update_yaxes(title_text="Magn. (dB)", range=[-100, 40], row=1, col=1)
    fig.update_yaxes(title_text="Temps", row=2, col=1)
    fig.update_xaxes(title_text="Fréquence (Hz)", row=2, col=1)

    app.layout = html.Div([
        dcc.Graph(id='live-graph', figure=fig, config={'displayModeBar': False}),
        dcc.Interval(
            id='graph-interval',
            interval=200, # Update interval in milliseconds
            n_intervals=0
        ),
    ], style={'backgroundColor': '#111111', 'minHeight': '100vh', 'padding': '20px', 'boxSizing': 'border-box'})

    @app.callback(Output('live-graph', 'figure'),
                  [Input('graph-interval', 'n_intervals')])
    def update_combined_graph(n):
        with fft_lock:
            if not new_data_flag[0]:
                return no_update
            new_data_flag[0] = False
            latest_data = latest_fft.tolist()
            spectro_data = spectrogram_data.tolist()
        
        patched_fig = Patch()
        patched_fig["data"][1]["y"] = latest_data
        patched_fig["data"][2]["z"] = spectro_data

        return patched_fig

    logging.info("Starting Dash server...")
    app.run(debug=False, use_reloader=False, port=8050, dev_tools_hot_reload=False)

if __name__ == '__main__':
    from src.config import DEFAULT_PORTS_CONFIG, DEFAULT_SIGNAL_CONFIG
    start_dashboard(DEFAULT_PORTS_CONFIG, DEFAULT_SIGNAL_CONFIG)

