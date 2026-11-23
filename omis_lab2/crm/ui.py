from datetime import date
from pathlib import Path
import sqlite3

from PySide6.QtCore import QDate, Signal, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QDialog, QMainWindow, QLabel, QLineEdit, QPushButton, QComboBox,
    QVBoxLayout, QHBoxLayout, QFormLayout, QDialogButtonBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QFrame, QMessageBox,
    QFileDialog, QDateEdit, QTabWidget, QProgressBar, QCheckBox, QSpinBox
)
from .model import (User, Client, Task, Deal, Call, ROLES, PRIORITIES, STATUSES,
                    AccessControlService, ClientRepository, TaskRepository, DealRepository,
                    CallRepository, ReportService)

from .notifications import Inbox
from .services import ClientService, TaskService, ValidationService, ExcelReportExporter, FileStorage

STYLE = """
QWidget {font: 10pt 'Segoe UI';color:#172337;}
QMainWindow,QDialog {background:#f4f6fa;}
QFrame#sidebar {background:#162034;} QFrame#sidebar QLabel {color:white;}
QPushButton {background:white;border:1px solid #cdd6e1;border-radius:5px;padding:7px 12px;}
QPushButton:hover {background:#e9efff;} QPushButton#primary,QPushButton:checked {background:#385fe0;color:white;}
QFrame#sidebar QPushButton {text-align:left;color:white;background:#162034;border:0;}
QFrame#sidebar QPushButton:checked {background:#395fd9;}
QLabel#heading {font-size:19pt;font-weight:650;} QLabel#brand {font-size:20pt;font-weight:bold;}
QLineEdit,QComboBox,QDateEdit,QSpinBox {background:white;border:1px solid #cbd4df;border-radius:4px;padding:6px;}
QComboBox {combobox-popup:0;}
QComboBoxPrivateContainer {background:#ffffff;border:0;}
QComboBox QAbstractItemView {background:#ffffff;color:#172337;border:1px solid #cbd4df;selection-background-color:#385fe0;selection-color:#ffffff;}
QComboBox QAbstractItemView::item {background:#ffffff;color:#172337;padding:5px;}
QComboBox QAbstractItemView::item:selected,QComboBox QAbstractItemView::item:hover {background:#385fe0;color:#ffffff;}
QTableWidget {background:white;alternate-background-color:#f7f9fc;border:1px solid #dce2ec;selection-background-color:#cddaff;selection-color:#162034;}
QHeaderView::section {background:#ecf0f7;padding:7px;border:0;font-weight:bold;}
QLineEdit:focus,QComboBox:focus,QDateEdit:focus {border-color:#385fe0;}
QFrame#sidebar QPushButton:hover:!checked {background:#263953;}
QTabWidget::pane {background:white;border:1px solid #cbd4df;}
QTabBar::tab {background:#ecf0f7;padding:7px 14px;}
QTabBar::tab:selected {background:white;border-bottom:2px solid #385fe0;}
QCalendarWidget {background:white;}
QCalendarWidget QWidget#qt_calendar_navigationbar {background:#eaf0fa;}
QCalendarWidget QToolButton {color:#172337;background:transparent;border:0;padding:4px 8px;font-weight:bold;}
QCalendarWidget QToolButton:hover {background:#d5e1f6;}
QCalendarWidget QMenu,QCalendarWidget QSpinBox {background:white;color:#172337;}
QCalendarWidget QMenu::item:selected {background:#385fe0;color:white;}
QCalendarWidget QAbstractItemView {background:white;alternate-background-color:#edf2fa;color:#172337;selection-background-color:#385fe0;selection-color:white;}
QCalendarWidget QAbstractItemView:disabled {color:#65748a;}
QProgressBar {background:#ecf0f7;border:1px solid #cbd4df;text-align:center;}
QProgressBar::chunk {background:#adc3ff;}
"""


def button(label, action, primary=False):
    b = QPushButton(label)
    if primary:
        b.setObjectName('primary')
    b.clicked.connect(lambda checked=False: action())
    return b


def title(text):
    w = QLabel(text)
    w.setObjectName('heading')
    return w


def combo(options, current=None):
    w = QComboBox()
    for value, label in options:
        w.addItem(str(label), value)
    idx = w.findData(current)
    if idx >= 0:
        w.setCurrentIndex(idx)
    return w


def grid(headers, rows):
    w = QTableWidget(0, len(headers))
    w.setHorizontalHeaderLabels(headers)
    w.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    w.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    w.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    w.verticalHeader().hide()
    w.setAlternatingRowColors(True)
    w.setShowGrid(False)
    w.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    fill_grid(w, rows)
    return w


def fill_grid(table, rows):
    table.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            table.setItem(i,j,QTableWidgetItem(str(value if value is not None else '—')))
    table.setCurrentCell(-1, -1)


def date_field(value=None):
    field = QDateEdit(QDate.fromString(value, 'yyyy-MM-dd') if value else QDate.currentDate())
    field.setCalendarPopup(True)
    calendar = field.calendarWidget()
    calendar.setVerticalHeaderFormat(calendar.VerticalHeaderFormat.NoVerticalHeader)
    calendar.setMinimumWidth(300)
    field.setDisplayFormat('dd.MM.yyyy')
    return field


def form(parent, caption, fields, save):
    dialog = QDialog(parent)
    dialog.setWindowTitle(caption)
    dialog.setMinimumWidth(430)
    layout = QVBoxLayout(dialog)
    layout.addWidget(title(caption))
    entries = QFormLayout()
    for name, widget in fields:
        entries.addRow(name,widget)
    layout.addLayout(entries)
    actions = QDialogButtonBox()
    actions.addButton('Отмена',QDialogButtonBox.ButtonRole.RejectRole)
    actions.addButton('Сохранить',QDialogButtonBox.ButtonRole.AcceptRole)
    def submit():
        try:
            save()
        except (ValueError, sqlite3.Error, OSError) as err:
            QMessageBox.warning(dialog,'Проверьте данные',str(err))
            return
        dialog.accept()
    actions.accepted.connect(submit)
    actions.rejected.connect(dialog.reject)
    layout.addWidget(actions)
    return dialog.exec()


class Login(QDialog):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.user = None
        self.setWindowTitle('CRM · Вход')
        self.setMinimumWidth(410)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32,28,32,28)
        layout.addWidget(title('Вход в CRM'))
        layout.addWidget(QLabel('Учебный вход. Введите любые логин и пароль.'))
        self.login = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        for label, field in [('Логин',self.login),('Пароль',self.password)]:
            layout.addWidget(QLabel(label))
            layout.addWidget(field)
        for role, label in zip(ROLES,['менеджер','руководитель','администратор']):
            layout.addWidget(button('Войти как '+label,lambda r=role:self.enter(r),True))
        self.error = QLabel()
        layout.addWidget(self.error)

    def enter(self,role):
        if not self.login.text().strip() or not self.password.text():
            self.error.setText('Заполните логин и пароль.')
            return
        rows = self.db.rows('select id,name,role,department from users where active=1 and role=? order by id limit 1',(role,))
        if rows:
            self.user = User(**dict(rows[0]))
            self.accept()
        else:
            self.error.setText('Нет активного пользователя этой роли.')


class ClientListView:
    def openClients(self):
        layout = self.page('Клиенты', self.scoped_title('клиенты'))
        rows = self.clients.list()
        search = QLineEdit()
        search.setPlaceholderText('Поиск по компании, телефону или email')
        tools = QHBoxLayout()
        layout.addLayout(tools)
        tools.addWidget(search)
        tools.addWidget(button('+ Добавить клиента', self.client_form,True))
        table = grid(['Компания','Контакт','Телефон','Email','Менеджер','Отдел'],
                     [[r[k] for k in ('company','contact','phone','email','owner','department')] for r in rows])
        layout.addWidget(table)
        def filter_rows(query):
            for i,r in enumerate(rows):
                table.setRowHidden(i,query.casefold() not in ' '.join(str(x) for x in r).casefold())
            table.clearSelection()
            table.setCurrentCell(-1,-1)
        search.textChanged.connect(filter_rows)
        show = lambda:self.selected(table,rows,self.card)
        table.doubleClicked.connect(lambda _:show())
        actions = QHBoxLayout()
        actions.addWidget(button('Открыть карточку', show))
        actions.addWidget(button('Открыть сделки', lambda: self.selected(
            table, rows, lambda client: self.card(client, show_deals=True))))
        actions.addStretch()
        layout.addLayout(actions)

    def client_form(self,r=None):
        fields = [QLineEdit(r[k] if r else '') for k in ('company','contact','phone','email')]
        managers = combo([(u['id'],u['name']) for u in self.access.managers()],r['manager'] if r else None)
        finished = QCheckBox('Работа с клиентом завершена')
        finished.setChecked(bool(r and r['finished']))
        def save():
            vals = [f.text().strip() for f in fields]
            client = Client(*vals, managers.currentData(), int(finished.isChecked()))
            if r:
                self.clients.update(r['id'], client)
            else:
                self.clients.create(client)
        if form(self,'Редактирование клиента' if r else 'Новый клиент',list(zip(['Компания','Контактное лицо','Телефон','Email'],fields))+[('Менеджер',managers), ('',finished)],save):
            self.openClients()



class ClientCardView:
    def records_tab(self, parent, client_id, repository, columns, labels, edit):
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        table = grid([label for label, _ in columns], [])
        layout.addWidget(table)
        actions = QHBoxLayout()
        layout.addLayout(actions)
        rows = []

        def refresh():
            rows[:] = repository.list(client_id)
            fill_grid(table, [[row[key] for _, key in columns] for row in rows])

        def edit_record(record=None):
            if edit(record):
                refresh()

        def edit_selected():
            self.selected(table, rows, edit_record)

        def delete(record):
            answer = QMessageBox.question(
                parent, labels[2], f'{labels[2]}?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                try:
                    repository.delete(client_id, record['id'])
                except (ValueError, sqlite3.Error) as error:
                    QMessageBox.warning(parent, labels[2], str(error))
                refresh()

        actions.addWidget(button(labels[0], edit_record, True))
        actions.addWidget(button(labels[1], edit_selected))
        actions.addWidget(button(labels[2], lambda: self.selected(table, rows, delete)))
        table.doubleClicked.connect(lambda _: edit_selected())
        refresh()
        return panel

    def call_form(self, parent, client_id, record):
        day = date_field(record['day'] if record else None)
        result = QLineEdit(record['result'] if record else '')

        def save():
            call = Call(day.date().toString('yyyy-MM-dd'), result.text().strip())
            self.calls.save(client_id, call, record['id'] if record else None)

        return form(parent, 'Изменение звонка' if record else 'Новый звонок',
                    [('Дата звонка', day), ('Результат', result)], save)

    def deals_tab(self, parent, client_id):
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        table = grid(['Сумма, BYN', 'Открыта', 'Закрыта'], [])
        layout.addWidget(table)
        actions = QHBoxLayout()
        layout.addLayout(actions)
        rows = []

        def refresh():
            rows[:] = self.deals.list(client_id)
            fill_grid(table, [
                (r['amount'], QDate.fromString(r['created'], 'yyyy-MM-dd').toString('dd.MM.yyyy'),
                 QDate.fromString(r['closed'], 'yyyy-MM-dd').toString('dd.MM.yyyy')
                 if r['closed'] else 'Открыта')
                for r in rows
            ])

        def edit(record=None):
            amount = QSpinBox()
            amount.setRange(1, 999_999_999)
            if record:
                amount.setValue(record['amount'])
            created = date_field(record['created'] if record else None)
            closed = date_field(record['closed'] if record else None)
            complete = QCheckBox('Сделка закрыта')
            complete.setChecked(bool(record and record['closed']))
            closed.setEnabled(complete.isChecked())
            complete.toggled.connect(closed.setEnabled)

            def save():
                deal = Deal(amount.value(), created.date().toString('yyyy-MM-dd'),
                            closed.date().toString('yyyy-MM-dd') if complete.isChecked() else None)
                self.deals.save(client_id, deal, record['id'] if record else None)

            if form(parent, 'Изменение сделки' if record else 'Новая сделка',
                    [('Сумма, BYN', amount), ('Дата открытия', created),
                     ('', complete), ('Дата закрытия', closed)], save):
                refresh()

        def delete(record):
            answer = QMessageBox.question(
                parent, 'Удаление сделки', f'Удалить сделку на {record["amount"]} BYN?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                try:
                    self.deals.delete(client_id, record['id'])
                except (ValueError, sqlite3.Error) as error:
                    QMessageBox.warning(parent, 'Удаление сделки', str(error))
                refresh()

        def edit_selected():
            self.selected(table, rows, edit)

        actions.addWidget(button('+ Новая сделка', edit, True))
        actions.addWidget(button('Изменить сделку', edit_selected))
        actions.addWidget(button('Удалить сделку', lambda: self.selected(table, rows, delete)))
        table.doubleClicked.connect(lambda _: edit_selected())
        refresh()
        return panel

    def card(self,r, *, show_deals=False):
        dialog = QDialog(self)
        dialog.setWindowTitle('Карточка клиента')
        dialog.resize(720,440)
        layout = QVBoxLayout(dialog)
        layout.addWidget(title(r['company']))
        layout.addWidget(QLabel(' · '.join(r[k] for k in ('contact','phone','email'))))
        tabs = QTabWidget()
        layout.addWidget(tabs)
        files = self.storage.find(r['id'])
        client_id = r['id']
        tasks = self.records_tab(
            dialog, client_id, self.tasks,
            [('Описание', 'description'), ('Исполнитель', 'owner'), ('Срок', 'due'), ('Статус', 'status')],
            ('+ Новая задача', 'Изменить задачу', 'Удалить задачу'),
            lambda record: self.task_form(record, parent=dialog, client_id=client_id))
        tabs.addTab(tasks, 'Задачи')
        deals = self.deals_tab(dialog, r['id'])
        tabs.addTab(deals, 'Сделки')
        calls = self.records_tab(
            dialog, client_id, self.calls, [('Дата', 'day'), ('Результат', 'result')],
            ('+ Новый звонок', 'Изменить звонок', 'Удалить звонок'),
            lambda record: self.call_form(dialog, client_id, record))
        tabs.addTab(calls, 'Звонки')
        ft = grid(['Файл','Размер, байт'],[(f['name'],f['size']) for f in files])
        tabs.addTab(ft,'Файлы')
        if show_deals:
            tabs.setCurrentWidget(deals)
        def attach():
            fn,_ = QFileDialog.getOpenFileName(dialog,'Прикрепить файл','','Документы (*.pdf *.docx *.xlsx *.jpg *.png)')
            if fn:
                try:
                    file_id = self.storage.store(r['id'], fn)
                    record = next(file for file in self.storage.find(r['id']) if file['id']==file_id)
                    files.append(record)
                    i=ft.rowCount()
                    ft.insertRow(i)
                    for j,k in enumerate(('name','size')):
                        ft.setItem(i,j,QTableWidgetItem(str(record[k])))
                    tabs.setCurrentWidget(ft)
                except (ValueError,OSError,sqlite3.Error) as err:
                    QMessageBox.warning(dialog,'Файл',str(err))
        def download(f):
            target,_ = QFileDialog.getSaveFileName(dialog,'Сохранить файл',f['name'])
            if target:
                try:
                    Path(target).write_bytes(self.db.rows('select content from files where id=?',(f['id'],))[0][0])
                except OSError as err:
                    QMessageBox.warning(dialog,'Файл',str(err))
        actions = QHBoxLayout()
        layout.addLayout(actions)
        actions.addWidget(button('Прикрепить файл',attach))
        actions.addWidget(button('Скачать файл',lambda:self.selected(ft,files,download)))
        actions.addWidget(button('Редактировать',dialog.accept))
        actions.addWidget(button('Закрыть',dialog.reject))
        if dialog.exec():
            self.client_form(r)



class TaskDashboardView:
    def openDashboard(self):
        layout = self.page('Задачи',self.scoped_title('задачи'))
        layout.addWidget(QLabel('Задача — поручение сотруднику по клиенту, например отправить предложение к пятнице.'))
        rows = self.tasks.list()
        table = grid(['Задача','Клиент','Исполнитель','Приоритет','Срок','Статус'],[[r[k] for k in ('description','company','owner','priority','due','status')] for r in rows])
        for i,r in enumerate(rows):
            if r['due'] < date.today().isoformat() and r['status'] != STATUSES[-1]:
                table.item(i,4).setForeground(QColor('#bd2738'))
        layout.addWidget(table)
        layout.addWidget(button('+ Новая задача',self.task_form,True))
        edit = lambda:self.selected(table,rows,self.task_form)
        layout.addWidget(button('Изменить задачу',edit))
        table.doubleClicked.connect(lambda _:edit())

    def task_form(self,r=None, *, parent=None, client_id=None):
        clients = self.clients.list()
        if client_id is not None:
            clients = [client for client in clients if client['id'] == client_id]
        if not clients:
            QMessageBox.information(parent or self,'Задача','Нет доступного клиента.')
            return False
        def choices(items,current):
            return combo([(i,i) for i in items],current)
        client = combo([(c['id'],c['company']) for c in clients],r['client'] if r else None)
        client.setEnabled(client_id is None)
        name = QLineEdit(r['description'] if r else '')
        managers = [(u['id'], u['name']) for u in self.access.managers()]
        if r and r['assignee'] not in {key for key, _ in managers}:
            managers.append((r['assignee'], r['owner']))
        staff = combo(managers,r['assignee'] if r else None)
        priority = choices(PRIORITIES,r['priority'] if r else 'Средний')
        status = choices(STATUSES,r['status'] if r else None)
        due = date_field(r['due'] if r else None)
        def save():
            if not name.text().strip() or not staff.currentData():
                raise ValueError('Введите описание и выберите исполнителя.')
            self.tasks.save(Task(client.currentData(),name.text().strip(),staff.currentData(),priority.currentData(),due.date().toString('yyyy-MM-dd'),status.currentData()),r['id'] if r else None)
        saved = form(parent or self,'Изменение задачи' if r else 'Новая задача',[('Описание',name),('Клиент',client),('Исполнитель',staff),('Срок',due),('Приоритет',priority),('Статус',status)],save)
        if saved and client_id is None:
            self.openDashboard()
        return saved



class NotificationView:
    def notifications(self):
        layout = self.page('Уведомления', 'Уведомления')
        self.notice_table = grid(['Дата и время','Клиент','Событие','Статус'], [])
        layout.addWidget(self.notice_table)
        def read():
            self.inbox.mark_read(self.notice_rows)
            self.sync_notifications()
        layout.addWidget(button('Отметить все как прочитанные', read))
        self.sync_notifications(force=True)

    def sync_notifications(self, force=False):
        version = (self.db.db.total_changes, self.db.rows('pragma data_version')[0][0])
        if not force and version == self.notice_version:
            return
        first_load = self.notice_version is None
        self.notice_version = version
        rows = self.inbox.rows()
        previous_id = self.notice_rows[0]['id'] if self.notice_rows else 0
        if rows and not first_load and rows[0]['id'] > previous_id:
            latest = rows[0]
            self.statusBar().showMessage(' · '.join(filter(None, (latest['company'], latest['message']))), 7000)
        unread = sum(not r['seen'] for r in rows)
        self.links['Уведомления'].setText(f'Уведомления ({unread})' if unread else 'Уведомления')
        if self.links['Уведомления'].isChecked():
            fill_grid(self.notice_table, [(r['day'],r['company'],r['message'],
                      'Прочитано' if r['seen'] else 'Новое') for r in rows])
        self.notice_rows = rows


class AnalyticsView:
    def openAnalytics(self):
        layout = self.page('Аналитика','Аналитика продаж')
        period = combo([(1,'День'),(7,'Неделя'),(30,'Месяц')],7)
        layout.addWidget(period)
        layout.addWidget(button('Сформировать отчёт',lambda:self.report(period.currentData()),True))
        layout.addStretch()

    def report(self,days):
        data = self.reports.build(days)
        dialog = QDialog(self)
        dialog.setWindowTitle('Отчёт по продажам')
        dialog.resize(680,520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(title(f'Продажи за {days} дн.'))
        total = sum(r['revenue'] for r in data)
        layout.addWidget(QLabel(f'Выручка: {total:,} BYN   ·   Закрыто сделок: {sum(r["total"] for r in data)}'))
        headers = ['Клиент','Сделки','Выручка, BYN','Средняя длительность, дн.']
        layout.addWidget(grid(headers,data))
        for r in data[:5]:
            bar = QProgressBar()
            bar.setRange(0,max(1,total))
            bar.setValue(r['revenue'])
            bar.setFormat(f'{r["company"]}   {r["revenue"]} BYN')
            layout.addWidget(bar)
        def export():
            path,_ = QFileDialog.getSaveFileName(dialog,'Экспорт отчёта','Продажи.xlsx','Excel (*.xlsx)')
            if path:
                try:
                    ExcelReportExporter().export(headers,data,path)
                except OSError as err:
                    QMessageBox.warning(dialog,'Экспорт',str(err))
        layout.addWidget(button('Скачать Excel',export))
        layout.addWidget(button('Закрыть',dialog.accept))
        dialog.exec()



class MainWindow(ClientListView, ClientCardView, TaskDashboardView, NotificationView, AnalyticsView, QMainWindow):
    closed = Signal()

    def closeEvent(self, event):
        super().closeEvent(event)
        if event.isAccepted():
            self.notice_timer.stop()
            self.closed.emit()

    def __init__(self, db, user):
        super().__init__()
        self.db, self.user = db,user
        self.access = AccessControlService(db,user)
        self.deals = DealRepository(self.access)
        self.calls = CallRepository(self.access)
        self.clients = ClientService(ClientRepository(self.access), db, ValidationService())
        self.storage = FileStorage(db)
        self.tasks = TaskService(TaskRepository(self.access))
        self.reports = ReportService(self.access)
        self.logout_requested = False
        self.resize(1160,720)
        self.setWindowTitle('CRM · '+user.name)
        self.shell = QWidget()
        self.setCentralWidget(self.shell)
        self.row = QHBoxLayout(self.shell)
        self.row.setContentsMargins(0,0,0,0)
        side = QFrame()
        side.setObjectName('sidebar')
        side.setFixedWidth(205)
        nav = QVBoxLayout(side)
        brand = QLabel('CRM')
        brand.setObjectName('brand')
        nav.addWidget(brand)
        self.row.addWidget(side)
        self.content = None
        self.links = {}
        pages = [('Клиенты',self.openClients),('Задачи',self.openDashboard)]
        if user.role != ROLES[0]:
            pages.append(('Аналитика',self.openAnalytics))
        pages.append(('Уведомления',self.notifications))
        if user.role == ROLES[2]:
            pages.append(('Настройки',self.settings))
        for name, action in pages:
            b = button(name,action)
            b.setCheckable(True)
            self.links[name] = b
            nav.addWidget(b)
        nav.addStretch()
        nav.addWidget(QLabel(user.name+'\n'+user.role+' · '+user.department))
        nav.addWidget(button('Выйти',self.logout))
        self.inbox = Inbox(db, user.id)
        self.notice_version = None
        self.notice_rows = []
        self.notice_timer = QTimer(self)
        self.notice_timer.timeout.connect(self.sync_notifications)
        self.notice_timer.start(1000)
        self.sync_notifications()
        self.openClients()

    def logout(self):
        if QMessageBox.question(self,'Выход','Вернуться к экрану входа?') == QMessageBox.StandardButton.Yes:
            self.logout_requested = True
            self.close()

    def page(self,key,caption):
        if self.content:
            self.row.removeWidget(self.content)
            self.content.deleteLater()
        self.content = QWidget()
        self.row.addWidget(self.content,1)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(20,20,20,20)
        layout.addWidget(title(caption))
        for name, b in self.links.items():
            b.setChecked(name==key)
        return layout

    def scoped_title(self, noun):
        return [f'Мои {noun}',f'{noun.capitalize()} отдела',f'Все {noun}'][ROLES.index(self.user.role)]

    def selected(self, table, rows, action):
        idx = table.currentRow()
        if idx < 0:
            QMessageBox.information(self,'Выбор записи','Выберите строку в таблице.')
        else:
            action(rows[idx])

    def settings(self):
        layout = self.page('Настройки','Пользователи и роли')
        rows = self.access.users()
        table = grid(['Имя','Роль','Отдел','Статус'],[(u['name'],u['role'],u['department'],'Активен' if u['active'] else 'Заблокирован') for u in rows])
        layout.addWidget(table)
        def edit(u=None):
            name = QLineEdit(u['name'] if u else '')
            dept = QLineEdit(u['department'] if u else '')
            role = combo([(r,r) for r in ROLES],u['role'] if u else None)
            active = combo([(1,'Активен'),(0,'Заблокирован')],u['active'] if u else None)
            def save():
                args = (name.text().strip(),role.currentData(),dept.text().strip(),active.currentData())
                if not args[0] or not args[2]:
                    raise ValueError('Введите имя и отдел.')
                if u and u['id']==self.user.id and (not args[3] or args[1]!=ROLES[2]):
                    raise ValueError('Текущий администратор должен оставаться активным.')
                with self.db.db:
                    if u:
                        self.db.db.execute('update users set name=?,role=?,department=?,active=? where id=?',(*args,u['id']))
                    else:
                        self.db.db.execute('insert into users(name,role,department,active) values(?,?,?,?)',args)
            if form(self,'Пользователь',[('Имя',name),('Роль',role),('Отдел',dept),('Статус',active)],save):
                self.settings()
        layout.addWidget(button('+ Новый пользователь',edit,True))
        layout.addWidget(button('Редактировать пользователя',lambda:self.selected(table,rows,edit)))

