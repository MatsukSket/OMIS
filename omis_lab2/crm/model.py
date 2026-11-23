from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import sqlite3
from .notifications import install

ROOT = Path(__file__).resolve().parent.parent
ROLES = ('Менеджер', 'Руководитель', 'Администратор')
STATUSES = ('Новая', 'В работе', 'Выполнено')
PRIORITIES = ('Низкий', 'Средний', 'Высокий')


@dataclass
class User:
    id: int
    name: str
    role: str
    department: str


@dataclass
class Client:
    company: str
    contact: str
    phone: str
    email: str
    manager: int
    finished: int = 0


@dataclass
class Task:
    client: int
    description: str
    assignee: int
    priority: str
    due: str
    status: str


@dataclass
class Deal:
    amount: int
    created: str
    closed: str | None


@dataclass
class Call:
    day: str
    result: str


class Database:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('pragma foreign_keys=on')

        if self.rows("select 1 from sqlite_master where name='clients'"):
            install(self.db)

    def rows(self, sql, args=()):
        return self.db.execute(sql, args).fetchall()

    def initialize(self):
        self.db.executescript("""
        create table users(id integer primary key,name text,role text,department text,active integer default 1);
        create table clients(id integer primary key,company text collate nocase unique,contact text,phone text,email text,manager references users);
        create table tasks(id integer primary key,client references clients,description text,assignee references users,priority text,due text,status text);
        create table deals(id integer primary key,client references clients,amount integer,created text,closed text);
        create table calls(id integer primary key,client references clients,day text,result text);
        create table files(id integer primary key,client references clients,name text,content blob);
        create table notices(id integer primary key,recipient references users,message text,seen integer default 0);
        """)
        self.db.executemany('insert into users(name,role,department) values(?,?,?)', [
            ('Иван Петров', ROLES[0], 'Продажи'), ('Мария Сидорова', ROLES[1], 'Продажи'),
            ('Анна Соколова', ROLES[2], 'Управление'), ('Елена Белова', ROLES[0], 'Продажи'),
            ('Олег Кузнецов', ROLES[0], 'Опт')])
        day = lambda offset: (date.today() + timedelta(days=offset)).isoformat()
        for i, (company, manager) in enumerate([('ООО «Ромашка»',1),('ИП Ковалёв',1),('ЗАО «Вектор»',4),('ООО «Гамма»',5)], 1):
            self.db.execute('insert into clients values(?,?,?,?,?,?)',(i, company, ['Алексей Смирнов','Дмитрий Ковалёв','Ольга Иванова','Алина Орлова'][i-1], f'+37529123456{i}', f'contact{i}@example.org', manager))
            self.db.execute('insert into tasks values(null,?,?,?,?,?,?)',(i,['Подготовить предложение','Позвонить клиенту','Согласовать договор','Отправить счёт'][i-1],manager,PRIORITIES[i%3],day(i-3),STATUSES[i%3]))
            self.db.execute('insert into calls values(null,?,?,?)',(i,day(-2),'Обсудили условия поставки'))
            if i != 2:
                self.db.execute('insert into deals values(null,?,?,?,?)',(i, i*1250,day(-7),day(-1)))
            self.db.execute('insert into notices(recipient,message) values(?,?)',(manager,'Назначена задача по клиенту '+company))
        self.db.commit()
        install(self.db)


class AccessControlService:
    def __init__(self, db, user):
        self.db, self.user = db, user

    def users(self):
        condition, args = '1', ()
        if self.user.role == ROLES[0]:
            condition, args = 'id=?', (self.user.id,)
        elif self.user.role == ROLES[1]:
            condition, args = 'department=?', (self.user.department,)
        return self.db.rows('select * from users where '+condition+' order by name',args)

    def managers(self):
        return [u for u in self.users() if u['role']==ROLES[0] and u['active']]

    def scope(self):
        ids = [u['id'] for u in self.users()]
        return 'select id from clients where manager in ('+','.join('?' for _ in ids)+')', ids


class ClientRepository:
    def __init__(self, access):
        self.access = access
        self.db = access.db

    def list(self):
        scope, args = self.access.scope()
        return self.db.rows('select c.*,u.name owner,u.department from clients c join users u on u.id=c.manager where c.id in ('+scope+') order by company',args)

    def save(self, client, key=None):
        args = tuple(vars(client).values())
        if key is None:
            self.db.db.execute('insert into clients(company,contact,phone,email,manager,finished) values(?,?,?,?,?,?)',args)
        else:
            self.db.db.execute('update clients set company=?,contact=?,phone=?,email=?,manager=?,finished=? where id=?',(*args,key))


class TaskRepository:
    def __init__(self, access):
        self.access = access

    def list(self, client_id=None):
        scope, args = self.access.scope()
        sql = ('select t.*,c.company,u.name owner from tasks t join clients c on c.id=t.client '
               'join users u on u.id=t.assignee where t.client in (' + scope + ')')
        if client_id is not None:
            sql += ' and t.client=?'
            args = (*args, client_id)
        return self.access.db.rows(sql + ' order by t.due, t.id', args)

    def save(self, task, key=None):
        db = self.access.db.db
        scope, args = self.access.scope()
        values = tuple(vars(task).values())
        with db:
            if not self.access.db.rows('select id from clients where id=? and id in (' + scope + ')',
                                       (task.client, *args)):
                raise ValueError('Клиент больше недоступен.')
            if key is None:
                db.execute('insert into tasks(client,description,assignee,priority,due,status) values(?,?,?,?,?,?)', values)
            else:
                cursor = db.execute(
                    'update tasks set client=?,description=?,assignee=?,priority=?,due=?,status=? '
                    'where id=? and client in (' + scope + ')', (*values, key, *args))
                if cursor.rowcount != 1:
                    raise ValueError('Задача больше недоступна.')


    def delete(self, client_id, key):
        scope, args = self.access.scope()
        with self.access.db.db as db:
            cursor = db.execute('delete from tasks where id=? and client=? and client in (' + scope + ')',
                                (key, client_id, *args))
            if cursor.rowcount != 1:
                raise ValueError('Задача больше недоступна.')


class CallRepository:
    def __init__(self, access):
        self.access = access

    def list(self, client_id):
        scope, args = self.access.scope()
        return self.access.db.rows(
            'select id,day,result from calls where client=? and client in (' + scope + ') '
            'order by day desc, id desc', (client_id, *args))

    def save(self, client_id, call, key=None):
        if not call.result.strip():
            raise ValueError('Введите результат звонка.')
        scope, args = self.access.scope()
        with self.access.db.db as db:
            if key is None:
                cursor = db.execute(
                    'insert into calls(client,day,result) select id,?,? from clients '
                    'where id=? and id in (' + scope + ')', (call.day, call.result, client_id, *args))
            else:
                cursor = db.execute(
                    'update calls set day=?,result=? where id=? and client=? and client in ('
                    + scope + ')', (call.day, call.result, key, client_id, *args))
            if cursor.rowcount != 1:
                raise ValueError('Клиент или звонок больше недоступны.')

    def delete(self, client_id, key):
        scope, args = self.access.scope()
        with self.access.db.db as db:
            cursor = db.execute('delete from calls where id=? and client=? and client in (' + scope + ')',
                                (key, client_id, *args))
            if cursor.rowcount != 1:
                raise ValueError('Звонок больше недоступен.')


class DealRepository:
    def __init__(self, access):
        self.access = access

    def list(self, client_id):
        scope, args = self.access.scope()
        return self.access.db.rows(
            'select id, amount, created, closed from deals where client=? and client in ('
            + scope + ') order by created desc, id desc', (client_id, *args))

    def save(self, client_id, deal, deal_id=None):
        if not 0 < deal.amount <= 999_999_999:
            raise ValueError('Введите сумму от 1 до 999 999 999 BYN.')
        if deal.closed and deal.closed < deal.created:
            raise ValueError('Дата закрытия не может быть раньше даты открытия.')
        scope, args = self.access.scope()
        values = (deal.amount, deal.created, deal.closed)
        with self.access.db.db as connection:
            if deal_id is None:
                cursor = connection.execute(
                    'insert into deals(client,amount,created,closed) select id,?,?,? from clients '
                    'where id=? and id in (' + scope + ')', (*values, client_id, *args))
            else:
                cursor = connection.execute(
                    'update deals set amount=?, created=?, closed=? where id=? and client=? '
                    'and client in (' + scope + ')', (*values, deal_id, client_id, *args))
            if cursor.rowcount != 1:
                raise ValueError('Клиент или сделка больше недоступны.')

    def delete(self, client_id, deal_id):
        scope, args = self.access.scope()
        with self.access.db.db as connection:
            cursor = connection.execute(
                'delete from deals where id=? and client=? and client in (' + scope + ')',
                (deal_id, client_id, *args))
            if cursor.rowcount != 1:
                raise ValueError('Сделка больше недоступна.')


class ReportService:
    def __init__(self, access):
        self.access = access

    def build(self, days):
        scope, args = self.access.scope()
        start = (date.today()-timedelta(days=days-1)).isoformat()
        return self.access.db.rows('''select c.company, count(d.id) total, coalesce(sum(d.amount),0) revenue,
            round(avg(julianday(d.closed)-julianday(d.created)),1) duration from clients c
            left join deals d on d.client=c.id and d.closed between ? and ?
            where c.id in ('''+scope+') group by c.id order by revenue desc',[start,date.today().isoformat(),*args])

