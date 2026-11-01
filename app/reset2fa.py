"""Крайний случай: администратор потерял и телефон, и резервные коды.
На сервере: python -m app.reset2fa ЛОГИН — при следующем входе человек подключит приложение-ключ заново."""
import sys

from . import db

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Укажите логин: python -m app.reset2fa admin")
    n = db.run("UPDATE users SET totp_on=0, totp_secret=NULL, totp_last=0, recovery=NULL WHERE login=?", (sys.argv[1].strip().lower(),))
    print("Ключ сброшен" if db.q1("SELECT id FROM users WHERE login=?", (sys.argv[1].strip().lower(),)) else "Такого логина нет")
