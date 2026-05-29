import logging
import multiprocessing
import numpy as np
import zmq
import pmt

from src.misc.config import SignalConfig, PortsConfig, PacketConfig
from src.misc.config import (
    DEFAULT_SIGNAL_CONFIG,
    DEFAULT_PORTS_CONFIG,
    DEFAULT_PACKET_CONFIG,
)
from src.rx.worker_manager import WorkerManager
from src.rx.signal_processor import SignalProcessor

logger = logging.getLogger(__name__)

def search_for_incomming_transmission(
    ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG,
    signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    pkt_conf: PacketConfig = DEFAULT_PACKET_CONFIG,
    stop_event=multiprocessing.Event(),
    nb_workers: int = 2,
    persistence: int = 50,
    fft_buffer_size: int = 10,
    min_prominence: float = 2.0,
    enable_smoothing: bool = True,
    enable_noise_floor: bool = True,
    persistence_hits: int = 3,
):
    """
    Main orchestrator for signal detection and worker management.
    Listens for FFT data and config updates via ZMQ.
    """
    logger.info("search_for_incomming_transmission started")

    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://127.0.0.1:{ports_conf.fft_port}")
    socket.setsockopt(zmq.SUBSCRIBE, b"")

    config_socket = context.socket(zmq.SUB)
    config_socket.connect(f"tcp://127.0.0.1:{ports_conf.config_port}")
    config_socket.setsockopt(zmq.SUBSCRIBE, b"")

    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)
    poller.register(config_socket, zmq.POLLIN)

    # Socket for sending system messages to web UI
    system_pub_socket = context.socket(zmq.PUB)
    system_pub_socket.bind(f"tcp://*:{ports_conf.peak_detector_system_port}")

    half_size = ports_conf.fft_size // 2
    freq_resolution = signal_conf.samp_rate / ports_conf.fft_size

    # Initialize modular components
    worker_manager = WorkerManager(nb_workers, signal_conf, ports_conf, pkt_conf, system_pub_socket)
    signal_processor = SignalProcessor(
        fft_size=ports_conf.fft_size,
        freq_resolution=freq_resolution,
        baudrate=signal_conf.baudrate,
        buffer_size=fft_buffer_size,
        min_prominence=min_prominence,
        enable_smoothing=enable_smoothing,
        enable_noise_floor=enable_noise_floor,
        persistence_hits=persistence_hits
    )

    no_data_count = 0
    max_no_data = 50

    try:
        while not stop_event.is_set():
            socks = dict(poller.poll(100))

            # 1. Handle config updates
            if config_socket in socks and socks[config_socket] == zmq.POLLIN:
                try:
                    raw_config = config_socket.recv(flags=zmq.NOBLOCK)
                    config_payload = pmt.to_python(pmt.deserialize_str(raw_config))
                    if isinstance(config_payload, dict) and config_payload.get("type") in ["preset_update", "config_update"]:
                        new_baudrate = config_payload.get("baudrate")
                        if new_baudrate:
                            signal_conf.baudrate = new_baudrate
                            signal_processor.baudrate = new_baudrate
                        
                        if config_payload.get("carrier_freq"):
                            signal_conf.carrier_freq = config_payload.get("carrier_freq")
                        if config_payload.get("beeper_duration"):
                            signal_conf.beeper_duration = config_payload.get("beeper_duration")

                        # Update robustness options if present in config
                        processor_opts = {}
                        for opt in ['enable_smoothing', 'enable_noise_floor', 'persistence_hits', 'min_prominence', 'recalibrate_noise_floor']:
                            if opt in config_payload:
                                processor_opts[opt] = config_payload[opt]
                        if processor_opts:
                            signal_processor.set_options(**processor_opts)

                        worker_manager.update_all_presets(signal_conf)
                except Exception as e:
                    logger.error(f"Error processing config message: {e}")

            # 2. Handle FFT data
            if socket not in socks or socks[socket] != zmq.POLLIN:
                no_data_count += 1
                if no_data_count > max_no_data:
                    logger.info("No FFT data for 5 seconds, audio source gone. Exiting.")
                    break
                continue

            no_data_count = 0
            try:
                msg = socket.recv(flags=zmq.NOBLOCK)
            except zmq.Again:
                continue

            data = np.frombuffer(msg, dtype=np.float32)
            if data.size != ports_conf.fft_size:
                continue

            # Process spectrum
            real_spectrum = data[half_size:]
            peak_freqs = signal_processor.process_frame(real_spectrum)

            # Update workers
            worker_manager.update_worker_states(peak_freqs, signal_conf.baudrate, persistence)
            worker_manager.dispatch_peaks(peak_freqs, signal_conf.baudrate)

    except KeyboardInterrupt:
        logger.info("Peak detector: KeyboardInterrupt received")
    finally:
        logger.info("Peak detector: cleaning up...")
        worker_manager.terminate_all()
        socket.close()
        config_socket.close()
        system_pub_socket.close()
        context.term()


if __name__ == "__main__":
    pass
