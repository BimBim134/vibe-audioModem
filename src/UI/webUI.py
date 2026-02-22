import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import zmq
import numpy as np
import threading
import logging

logging.basicConfig(level=logging.INFO)

app = dash.Dash(__name__)

# Global variable to store the latest FFT data
FFT_SIZE = 4096
latest_fft = np.zeros(FFT_SIZE)
fft_lock = threading.Lock()

def zmq_listener():
    global latest_fft
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    # The GNU Radio zeromq publisher binds to tcp://*:5556, so we connect to it
    socket.connect("tcp://localhost:5556")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    logging.info("ZMQ Listener started, connecting to port 5556")
    
    while True:
        try:
            msg = socket.recv()
            # GNU Radio sends gr.sizeof_float (32-bit float)
            data = np.frombuffer(msg, dtype=np.float32)
            if len(data) == FFT_SIZE:
                with fft_lock:
                    latest_fft = data
            else:
                # Store it anyway if the size doesn't match, maybe configuration changed
                with fft_lock:
                    latest_fft = data
        except Exception as e:
            logging.error(f"Error receiving ZMQ message: {e}")

# Start the ZMQ listener thread
listener_thread = threading.Thread(target=zmq_listener, daemon=True)
listener_thread.start()

app.layout = html.Div([
    html.H1("Spectroscope Temps Réel", style={'textAlign': 'center'}),
    dcc.Graph(id='live-spectroscope-graph'),
    dcc.Interval(
        id='interval-component',
        interval=200, # Update interval in milliseconds
        n_intervals=0
    )
])

@app.callback(Output('live-spectroscope-graph', 'figure'),
              [Input('interval-component', 'n_intervals')])
def update_graph_live(n):
    with fft_lock:
        data = latest_fft.copy()
    
    # We plot the raw bins for the prototype
    x = np.arange(len(data))
    
    fig = go.Figure(data=[go.Scatter(x=x, y=data, mode='lines', line=dict(color='#00ffcc'))])
    
    # Optional dynamic Y-axis, but fixing the bottom at 0 usually looks better for magnitude
    y_max = np.max(data)
    y_max = y_max * 1.1 if y_max > 0 else 1.0

    fig.update_layout(
        title='Magnitude Spectrum (Port 5556)',
        xaxis_title='Frequency Bin',
        yaxis_title='Magnitude',
        yaxis=dict(range=[0, y_max]),
        template='plotly_dark',
        margin=dict(l=40, r=40, t=40, b=40)
    )
    
    return fig

if __name__ == '__main__':
    logging.info("Starting Dash server...")
    app.run(debug=True, use_reloader=False, port=8050)
