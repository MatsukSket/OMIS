"""Transactional SQLite event delivery for all writers of the CRM database."""

def install(connection):
    if connection.execute("select 1 from sqlite_master where name='crm_inbox'").fetchone():
        return
    with connection:
        connection.execute('begin immediate')
        if connection.execute("select 1 from sqlite_master where name='crm_inbox'").fetchone():
            return
        connection.execute('alter table clients add column finished integer not null default 0')
        connection.execute('''create table crm_inbox(
            id integer primary key, recipient integer not null, client_id integer,
            owner integer, assignee integer, admin_only integer default 0, company text, message text not null,
            created text default current_timestamp, seen integer not null default 0)''')
        connection.execute('create index inbox_recipient on crm_inbox(recipient,id)')
        connection.execute('''insert into crm_inbox(recipient,owner,message,seen,created)
            select recipient,recipient,message,seen,null from notices''')
        specs = [
            ('clients','company contact phone email manager finished', 'Новый клиент',
             """case when NEW.finished != OLD.finished then case when NEW.finished=1
             then 'Работа с клиентом завершена' else 'Работа с клиентом возобновлена' end
             when NEW.manager != OLD.manager then 'Изменён ответственный менеджер'
             else 'Обновлена карточка клиента' end""", 'Клиент удалён', None),
            ('tasks','client description assignee priority due status','Новая задача',
             """case when NEW.status='Выполнено' and OLD.status!=NEW.status then 'Задача выполнена'
             when NEW.assignee!=OLD.assignee then 'Задача переназначена' else 'Задача изменена' end""",
             'Задача удалена','description'),
            ('deals','client amount created closed',None,
             """case when OLD.closed is null and NEW.closed is not null then 'Сделка закрыта'
             when OLD.closed is not null and NEW.closed is null then 'Сделка открыта повторно'
             else 'Сделка изменена' end""",'Сделка удалена','amount'),
            ('calls','client day result','Звонок добавлен',"'Звонок изменён'",'Звонок удалён','result'),
            ('files','client name content','Файл прикреплён',"'Файл изменён'",'Файл удалён','name'),
            ('users','name role department active','Добавлен сотрудник',"'Изменён профиль сотрудника'",
             'Удалён сотрудник','name')]
        for table, fields, added, updated, removed, detail in specs:
            for op in ('insert','update','delete'):
                row = 'OLD' if op == 'delete' else 'NEW'
                message = {'insert':f"'{added}'", 'update':updated, 'delete':f"'{removed}'"}[op]
                if table == 'deals' and op == 'insert':
                    message = "case when NEW.closed is null then 'Сделка открыта' else 'Добавлена закрытая сделка' end"
                if detail:
                    message += f" || ' · ' || {row}.{detail}"
                if table == 'deals':
                    message += " || ' BYN'"
                condition = ''
                if op == 'update':
                    condition = 'when ' + ' or '.join(f'OLD.{f} is not NEW.{f}' for f in fields.split())
                if table == 'users':
                    select = f"""select u.id,null,null,null,1,null,{message} from users u
                                where u.active=1 and u.role='Администратор'"""
                else:
                    if table == 'clients':
                        source = f'(select {row}.id id,{row}.manager manager,{row}.company company)'
                    else:
                        source = f'(select id,manager,company from clients where id={row}.client)'
                    assigned = f" or u.id={row}.assignee" if table == 'tasks' else ''
                    assignee = f"{row}.assignee" if table == "tasks" else "null"
                    select = f"""select u.id,c.id,c.manager,{assignee},0,c.company,{message}
                        from {source} c join users m on m.id=c.manager cross join users u
                        where u.active=1 and (u.role='Администратор' or u.id=c.manager
                        or (u.role='Руководитель' and u.department=m.department){assigned})"""
                connection.execute(f'''create trigger crm_event_{table}_{op} after {op} on {table}
                    {condition} begin insert into crm_inbox(recipient,client_id,owner,assignee,admin_only,company,message)
                    {select}; end''')


class Inbox:
    def __init__(self, db, user_id):
        self.db = db
        self.user_id = user_id

    def rows(self):
        return self.db.rows('''select n.id,datetime(n.created,'localtime') day,n.company,n.message,n.seen
            from crm_inbox n join users u on u.id=n.recipient
            left join clients c on c.id=n.client_id
            left join users m on m.id=coalesce(c.manager,n.owner)
            where n.recipient=? and u.active=1 and (u.role='Администратор' or
            (n.admin_only=0 and (u.id=m.id or (u.role='Руководитель' and u.department=m.department)
            or u.id=n.assignee)))
            order by n.id desc''',(self.user_id,))

    def mark_read(self, rows):
        with self.db.db:
            self.db.db.executemany('update crm_inbox set seen=1 where recipient=? and id=?',
                                   [(self.user_id,r['id']) for r in rows if not r['seen']])
