import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLineEdit
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import Qt, QTimer

class MaMessagerie(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Chat PySide6 + WebEngine")
        self.resize(500, 700)

        # --- Interface ---
        layout = QVBoxLayout()
        self.view = QWebEngineView()
        layout.addWidget(self.view)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Tapez votre message...")
        self.input_field.returnPressed.connect(self.envoyer_message)
        layout.addWidget(self.input_field)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # --- HTML Initial ---
        self.init_chat_window()

    def init_chat_window(self):
        # Le HTML reste identique, c'est du standard web
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: 'Segoe UI', sans-serif; background: #f4f7f6; padding: 10px; display: flex; flex-direction: column; }
                .msg { 
                    max-width: 80%; margin-bottom: 12px; padding: 10px 15px; 
                    border-radius: 15px; font-size: 14px; position: relative;
                }
                .sent { align-self: flex-end; background: #007bff; color: white; border-bottom-right-radius: 2px; }
                .received { align-self: flex-start; background: #e9e9eb; color: #333; border-bottom-left-radius: 2px; }
            </style>
        </head>
        <body>
            <div id="chat-box" style="display: flex; flex-direction: column;"></div>
            <script>
                function injectMessage(text, side) {
                    const box = document.getElementById('chat-box');
                    const div = document.createElement('div');
                    div.className = 'msg ' + side;
                    div.innerText = text;
                    box.appendChild(div);
                    window.scrollTo(0, document.body.scrollHeight);
                }
            </script>
        </body>
        </html>
        """
        self.view.setHtml(html_template)

    def ajouter_bulle(self, texte, side="sent"):
        # En PySide6, on accède aussi à la page via .page()
        # L'exécution est asynchrone par nature
        texte_esc = texte.replace("'", "\\'")
        self.view.page().runJavaScript(f"injectMessage('{texte_esc}', '{side}')")

    def envoyer_message(self):
        texte = self.input_field.text().strip()
        if texte:
            self.ajouter_bulle(texte, "sent")
            self.input_field.clear()
            
            # Simulation réponse
            QTimer.singleShot(800, lambda: self.ajouter_bulle("Réponse automatique PySide6", "received"))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    fenetre = MaMessagerie()
    fenetre.show()
    sys.exit(app.exec())