import sys
from PySide6.QtCore import QEventLoop, QLocale, Qt
from PySide6.QtWidgets import QApplication, QDialog
from .model import Database, ROOT
from .ui import Login, MainWindow, STYLE


def main():
    app = QApplication(sys.argv)
    QLocale.setDefault(QLocale('ru_RU'))
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)
    path = ROOT / 'data' / 'crm.sqlite3'
    path.parent.mkdir(exist_ok=True)
    store = Database(path)
    try:
        if not store.rows("select name from sqlite_master where type='table' and name='users'"):
            store.initialize()
        while True:
            login = Login(store)
            if login.exec() != QDialog.DialogCode.Accepted:
                break
            window = MainWindow(store, login.user)
            loop = QEventLoop()
            window.closed.connect(loop.quit)
            window.show()
            loop.exec()
            window.closed.disconnect(loop.quit)
            if not window.logout_requested:
                break
    finally:
        store.db.close()


if __name__ == '__main__':
    main()

