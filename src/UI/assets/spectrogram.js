// Clientside callback namespace for the spectrogram dashboard
window.dash_clientside = window.dash_clientside || {};

var DOWNSAMPLE_FACTOR = 4;  // Must match SPECTROGRAM_DOWNSAMPLE in Python

window.dash_clientside.spectrogram = {
    /**
     * Accumulate FFT rows into the spectrogram and update the graph in-place.
     * @param {Array} fftRow - Latest FFT magnitude row from the server (full resolution)
     * @param {Array[]} spectrogramData - 2D array of accumulated spectrogram rows (downsampled)
     * @returns {Array[]} Updated spectrogram data for the Store
     */
    update: function (fftRow, spectrogramData) {
        if (!fftRow) {
            return window.dash_clientside.no_update;
        }

        // Downsample FFT row for the spectrogram (keep 1 bin out of N)
        var downsampled = [];
        for (var i = 0; i < fftRow.length; i += DOWNSAMPLE_FACTOR) {
            downsampled.push(fftRow[i]);
        }

        // Roll spectrogram: remove oldest row, append new downsampled row
        spectrogramData.push(downsampled);
        if (spectrogramData.length > 200) {
            spectrogramData.shift();
        }

        // Find the Plotly graph element inside the Dash wrapper
        var wrapper = document.getElementById('live-graph');
        if (wrapper) {
            var plots = wrapper.getElementsByClassName('js-plotly-plot');
            var graphEl = (plots.length > 0) ? plots[0] : wrapper;
            if (graphEl && graphEl.data) {
                // Update spectroscope (trace 1) and spectrogram (trace 2)
                Plotly.restyle(graphEl, { 'y': [fftRow] }, [1]);
                Plotly.restyle(graphEl, { 'z': [spectrogramData] }, [2]);
            }
        }

        return spectrogramData;
    }
};
