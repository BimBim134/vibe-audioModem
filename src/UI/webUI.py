import dash
from dash import dcc, html, Patch
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import zmq
import numpy as np
import threading
import logging

from src.config import DEFAULT_PORTS_CONFIG, DEFAULT_SIGNAL_CONFIG

logging.basicConfig(level=logging.INFO)

app = dash.Dash(__name__, update_title=None, title="Spectroscope Temps Réel")

# Load configuration from config.py
FFT_SIZE = DEFAULT_PORTS_CONFIG.fft_size
FFT_PORT = DEFAULT_PORTS_CONFIG.fft_port
SAMP_RATE = DEFAULT_SIGNAL_CONFIG.samp_rate
NYQUIST = DEFAULT_SIGNAL_CONFIG.nyquist_freq

# The spectrum is symmetric for real signals, so we only need the first half (positive frequencies)
HALF_FFT_SIZE = FFT_SIZE // 2
freqs = np.linspace(0, NYQUIST, HALF_FFT_SIZE)

latest_fft = np.zeros(HALF_FFT_SIZE)
fft_lock = threading.Lock()

def zmq_listener():
    global latest_fft
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://localhost:{FFT_PORT}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    logging.info(f"ZMQ Listener started, connecting to port {FFT_PORT}")
    
    while True:
        try:
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
                    latest_fft = data[mid:]
        except Exception as e:
            logging.error(f"Error receiving ZMQ message: {e}")

listener_thread = threading.Thread(target=zmq_listener, daemon=True)
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
    yaxis=dict(range=[0, 1]) 
)

app.layout = html.Div([
    html.H1("Spectroscope Temps Réel", style={'textAlign': 'center', 'fontFamily': 'sans-serif', 'color': '#ffffff'}),
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
    
    # Update max y-axis dynamically
    y_max = np.max(data)
    if y_max > 0.01: # Avoid jitters or division by zero
        patched_fig["layout"]["yaxis"]["range"] = [0, y_max * 1.2]

    return patched_fig

if __name__ == '__main__':
    logging.info("Starting Dash server...")
    # Disable dev_tools_hot_reload to stop the "F5" refresh feel
    app.run(debug=True, use_reloader=False, port=8050, dev_tools_hot_reload=False)
