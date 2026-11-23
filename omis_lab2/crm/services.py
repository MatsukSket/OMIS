from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
from typing import Protocol

from .model import Client, Task, STATUSES


class IClientRepository(Protocol):
    def list(self): ...
    def save(self, client: Client, key=None): ...


class ITaskRepository(Protocol):
    def list(self, client_id=None): ...
    def save(self, task: Task, key=None): ...
    def delete(self, client_id, key): ...


class ValidationService:
    def validateClient(self, client):
        if not all((client.company, client.contact, client.phone, client.email, client.manager)):
            raise ValueError('Заполните все поля и выберите менеджера.')
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', client.email):
            raise ValueError('Проверьте адрес электронной почты.')
        if not 7 <= len(re.sub(r'\D', '', client.phone)) <= 15:
            raise ValueError('Проверьте номер телефона.')


class ClientService:
    def __init__(self, repository: IClientRepository, db, validation):
        self.repository = repository
        self.db = db
        self.validation = validation

    def list(self):
        return self.repository.list()

    def save(self, client, key=None):
        self.validation.validateClient(client)
        with self.db.db:
            names = self.db.rows('select company from clients where id<>?', (key or -1,))
            if any(row[0].casefold() == client.company.casefold() for row in names):
                raise ValueError('Компания уже зарегистрирована.')
            self.repository.save(client, key)

    def create(self, client):
        self.save(client)

    def update(self, key, client):
        self.save(client, key)


class TaskService:
    def __init__(self, repository: ITaskRepository):
        self.repository = repository

    def list(self, client_id=None):
        return self.repository.list(client_id)

    def delete(self, client_id, key):
        self.repository.delete(client_id, key)

    def save(self, task, key=None):
        if not task.description or not task.assignee:
            raise ValueError('Введите описание и выберите исполнителя.')
        self.repository.save(task, key)

    def listToday(self):
        return [r for r in self.list() if r['due'] <= date.today().isoformat() and r['status'] != STATUSES[-1]]


class FileStorage:
    def __init__(self, db):
        self.db = db

    def store(self, clientId, file):
        path = Path(file)
        if path.stat().st_size > 20 * 1024**2:
            raise ValueError('Максимальный размер — 20 МБ.')
        with self.db.db:
            cursor = self.db.db.execute('insert into files(client,name,content) values(?,?,?)',
                                        (clientId, path.name, path.read_bytes()))
        return cursor.lastrowid

    def find(self, clientId):
        return self.db.rows('select id,name,length(content) size from files where client=?',(clientId,))


class ExcelReportExporter:
    def export(self, headers, data, path):
        from openpyxl import Workbook
        book = Workbook()
        sheet = book.active
        sheet.title = 'Продажи'
        sheet.append(headers)
        for row in data:
            sheet.append(tuple(row))
            sheet.cell(sheet.max_row,1).data_type = 's'
        for column, width in zip('ABCD', (32,14,20,30)):
            sheet.column_dimensions[column].width = width
        book.save(path)

