// Clientside callback namespace for the spectrogram dashboard
window.dash_clientside = window.dash_clientside || {};

var DOWNSAMPLE_FACTOR = 4;  // Must match SPECTROGRAM_DOWNSAMPLE in Python
var MAX_ROWS = 200;

window.dash_clientside.spectrogram = {
    /**
     * Process a batch of FFT rows: update spectroscope with latest,
     * add all rows to the spectrogram (downsampled).
     * @param {Array[]|Array} fftBatch - Batch of FFT rows from the server
     * @param {Array[]} spectrogramData - 2D array of accumulated spectrogram rows
     * @returns {Array[]} Updated spectrogram data for the Store
     */
    update: function (fftBatch, spectrogramData) {
        if (!fftBatch || fftBatch.length === 0) {
            return window.dash_clientside.no_update;
        }

        // Process each FFT row in the batch
        for (var b = 0; b < fftBatch.length; b++) {
            var row = fftBatch[b];

            // Downsample for the spectrogram
            var downsampled = [];
            for (var i = 0; i < row.length; i += DOWNSAMPLE_FACTOR) {
                downsampled.push(row[i]);
            }

            spectrogramData.push(downsampled);
            if (spectrogramData.length > MAX_ROWS) {
                spectrogramData.shift();
            }
        }

        // Use the last row in the batch for the spectroscope (full resolution)
        var latestRow = fftBatch[fftBatch.length - 1];

        // Find the Plotly graph element inside the Dash wrapper
        var wrapper = document.getElementById('live-graph');
        if (wrapper) {
            var plots = wrapper.getElementsByClassName('js-plotly-plot');
            var graphEl = (plots.length > 0) ? plots[0] : wrapper;
            if (graphEl && graphEl.data) {
                Plotly.restyle(graphEl, { 'y': [latestRow] }, [1]);
                Plotly.restyle(graphEl, { 'z': [spectrogramData] }, [2]);
            }
        }

        return spectrogramData;
    }
};
