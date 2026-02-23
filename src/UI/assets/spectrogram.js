// Clientside callback namespace for the spectrogram dashboard
window.dash_clientside = window.dash_clientside || {};

window.dash_clientside.spectrogram = {
    /**
     * Accumulate FFT rows into the spectrogram and update the graph in-place.
     * @param {Array} fftRow - Latest FFT magnitude row from the server
     * @param {Array[]} spectrogramData - 2D array of accumulated spectrogram rows
     * @returns {Array[]} Updated spectrogram data for the Store
     */
    update: function (fftRow, spectrogramData) {
        if (!fftRow) {
            return window.dash_clientside.no_update;
        }

        // Roll spectrogram: remove oldest row, append new row
        spectrogramData.push(fftRow);
        if (spectrogramData.length > 200) {
            spectrogramData.shift();
        }

        // Find the Plotly graph element inside the Dash wrapper
        var wrapper = document.getElementById('live-graph');
        if (wrapper) {
            var plots = wrapper.getElementsByClassName('js-plotly-plot');
            var graphEl = (plots.length > 0) ? plots[0] : wrapper;
            if (graphEl && graphEl.data) {
                Plotly.restyle(graphEl, { 'y': [fftRow] }, [1]);
                Plotly.restyle(graphEl, { 'z': [spectrogramData] }, [2]);
            }
        }

        return spectrogramData;
    }
};
