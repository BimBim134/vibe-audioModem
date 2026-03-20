function injectMessage(html) {
    const box = document.getElementById('chat-box');
    const div = document.createElement('div');
    div.innerHTML = html;
    // Get the first child which is our actual msg div
    const msgDiv = div.firstElementChild;
    box.appendChild(msgDiv);
    window.scrollTo(0, document.body.scrollHeight);
}

function injectTemplate(type, sender, meta, content) {
    const html = `
        <div class="msg ${type}">
            <div class="header">
                <span class="sender">${sender}</span>
                <span class="meta">${meta}</span>
            </div>
            <div class="content">${content}</div>
        </div>
    `;
    injectMessage(html);
}
