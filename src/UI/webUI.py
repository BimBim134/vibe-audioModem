import dash
from dash import dcc, html, no_update
from dash.dependencies import Input, Output, State
import plotly.graph_objs as go
from plotly.subplots import make_subplots
import zmq
import numpy as np
import threading
import logging

from src.config import PortsConfig, SignalConfig

logging.basicConfig(
    format="%(levelname)s: %(processName)s: %(module)s: %(funcName)s: %(message)s",
    level=logging.DEBUG,
)

SPECTROGRAM_DOWNSAMPLE = 4  # Keep 1 bin out of N for the heatmap
MAX_BATCH_SIZE = 20  # Max FFT rows per batch to prevent huge payloads


def start_dashboard(ports: PortsConfig, sig: SignalConfig, stop_event=None):
    """
    Start the Dash dashboard as a standalone process.
    """
    # Silence Werkzeug (Flask) access logs
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    app = dash.Dash(__name__, update_title=None, title="Vibe - AudioModem")

    # Cache-busting: prevent browser from caching JS assets
    @app.server.after_request
    def add_no_cache_header(response):
        if response.content_type and "javascript" in response.content_type:
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
        return response

    freqs = np.linspace(0, sig.nyquist_freq, ports.half_fft_size)

    latest_fft = np.zeros(ports.half_fft_size)
    fft_batch = []  # accumulate FFT rows between intervals
    fft_lock = threading.Lock()

    def zmq_listener():
        nonlocal latest_fft
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect(f"tcp://localhost:{ports.fft_port}")
        socket.setsockopt_string(zmq.SUBSCRIBE, "")

        logging.info(
            f"ZMQ Listener started, connecting to port {ports.fft_port}"
        )

        # Use stop_event if provided, otherwise check if the thread is still valid
        while stop_event is None or not stop_event.is_set():
            try:
                # Use a timeout to avoid blocking indefinitely, allowing periodic stop_event checks
                if socket.poll(1000, zmq.POLLIN):
                    msg = socket.recv()
                    data = np.frombuffer(msg, dtype=np.float32)
                    with fft_lock:
                        if len(data) == ports.fft_size:
                            latest_fft = data[ports.half_fft_size :]
                        else:
                            # Fallback for dynamic resizing
                            mid = len(data) // 2
                            latest_fft = data[mid:]
                        latest_fft = 10 * np.log(latest_fft)
                        fft_batch.append(latest_fft.tolist())
                elif stop_event and stop_event.is_set():
                    break
            except Exception as e:
                logging.error(f"Error receiving ZMQ message: {e}")
                if stop_event and stop_event.is_set():
                    break

        socket.close()
        context.term()
        logging.info("ZMQ Listener stopped.")

    listener_thread = threading.Thread(
        target=zmq_listener, name="DashboardZMQListener", daemon=True
    )
    listener_thread.start()

    # Init spectrogram as nested list for JS compatibility
    spectro_bins = ports.half_fft_size // SPECTROGRAM_DOWNSAMPLE
    init_spectrogram = [[-100.0] * spectro_bins for _ in range(200)]

    # Combined figure with subplots
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0, row_heights=[0.3, 0.7]
    )

    freqs_list = freqs.tolist()
    freqs_downsampled = freqs[::SPECTROGRAM_DOWNSAMPLE].tolist()

    # Row 1: Spectroscope
    # Trace 0: Invisible baseline
    fig.add_trace(
        go.Scatter(
            x=freqs_list,
            y=[-100.0] * len(freqs_list),
            mode="lines",
            line=dict(width=0),
            hoverinfo="skip",
            showlegend=False,
        ),
        row=1,
        col=1,
    )
    # Trace 1: Spectroscope data
    fig.add_trace(
        go.Scatter(
            x=freqs_list,
            y=[0.0] * len(freqs_list),
            mode="lines",
            line=dict(color="#00ffcc"),
            fill="tonexty",
            name="Magnitude",
        ),
        row=1,
        col=1,
    )

    # Row 2: Spectrogram
    # Trace 2: Heatmap
    fig.add_trace(
        go.Heatmap(
            z=init_spectrogram,
            x=freqs_downsampled,
            colorscale="Viridis",
            zmin=-100,
            zmax=100,
            showscale=False,
            name="Spectrogram",
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=0, r=0, t=0, b=0),
        height=800,
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_yaxes(range=[-100, 40], visible=False, row=1, col=1)
    fig.update_yaxes(visible=False, row=2, col=1)
    fig.update_xaxes(visible=False)

    app.layout = html.Div(
        [
            dcc.Graph(id="live-graph", figure=fig, config={"displayModeBar": False}),
            dcc.Store(id="fft-store"),
            dcc.Store(id="spectrogram-store", data=init_spectrogram),
            dcc.Interval(id="graph-interval", interval=100, n_intervals=0),
        ],
        style={
            "backgroundColor": "#111111",
            "minHeight": "100vh",
            "margin": "0",
            "padding": "0",
            "overflow": "hidden",
        },
    )

    # Server-side: push all FFT rows accumulated since last interval
    @app.callback(Output("fft-store", "data"), [Input("graph-interval", "n_intervals")])
    def push_fft_batch(n):
        with fft_lock:
            if not fft_batch:
                return no_update
            # Limit batch size to prevent huge payloads
            batch = list(fft_batch[-MAX_BATCH_SIZE:])
            fft_batch.clear()
        return batch

    # Clientside: accumulate spectrogram + update graph directly in browser
    # JS code is in assets/spectrogram.js
    app.clientside_callback(
        dash.ClientsideFunction("spectrogram", "update"),
        Output("spectrogram-store", "data"),
        [Input("fft-store", "data")],
        [State("spectrogram-store", "data")],
    )

    logging.info("Starting Dash server...")
    app.run(debug=False, use_reloader=False, port=8050, dev_tools_hot_reload=False)


if __name__ == "__main__":
    from src.config import DEFAULT_PORTS_CONFIG, DEFAULT_SIGNAL_CONFIG

    start_dashboard(DEFAULT_PORTS_CONFIG, DEFAULT_SIGNAL_CONFIG)
